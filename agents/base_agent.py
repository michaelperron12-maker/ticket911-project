"""
Base Agent — Classe parente pour tous les agents AITicketInfo
Stack multi-moteurs Fireworks AI — 12 modeles optimises par role
PostgreSQL backend (tickets_qc_on)
"""

import os
import json
import time
import re
import base64
import threading
from datetime import datetime
from openai import OpenAI
import psycopg2
import psycopg2.extras

# Load .env si disponible
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

# ═══════════════════════════════════════════════════════════
# POSTGRESQL — Base de donnees principale
# ═══════════════════════════════════════════════════════════
PG_CONFIG = {
    'host': os.environ.get('TICKETS_DB_HOST', '172.18.0.3'),
    'port': int(os.environ.get('TICKETS_DB_PORT', 5432)),
    'dbname': os.environ.get('TICKETS_DB_NAME', 'tickets_qc_on'),
    'user': os.environ.get('TICKETS_DB_USER', 'ticketdb_user'),
    'password': os.environ.get('TICKETS_DB_PASS', 'Tk911PgSecure2026'),
}

# ═══════════════════════════════════════════════════════════
# FIREWORKS AI — STACK MODELES (mis a jour 14 fev 2026)
# ═══════════════════════════════════════════════════════════
FIREWORKS_API_KEY = os.environ.get("FIREWORKS_API_KEY", "")

# --- TIER 1: Flagships (raisonnement juridique profond) ---
GLM5 = "accounts/fireworks/models/glm-5"                       # #1 — 744B MoE, 202K ctx, low hallucination, $1.00/$3.20
KIMI_K25 = "accounts/fireworks/models/kimi-k2p5"               # #2 — #1 intelligence Fireworks, 262K ctx, $0.60/$3.00
DEEPSEEK_V3 = "accounts/fireworks/models/deepseek-v3p2"        # #3 — 685B, 128K ctx, excellent rapport qualite/prix, $0.56/$1.68

# --- TIER 2: Raisonnement + Thinking ---
KIMI_THINK = "accounts/fireworks/models/kimi-k2-thinking"       # Thinking mode, 262K ctx, verification independante
DEEPSEEK_R1 = "accounts/fireworks/models/deepseek-r1-0528"     # Chain-of-thought, verification croisee
GLM4 = "accounts/fireworks/models/glm-4p7"                     # 430 t/s le plus rapide, multilingue, $0.60/$2.20

# --- TIER 3: Specialises ---
QWEN3 = "accounts/fireworks/models/qwen3-235b-a22b"            # Classification, knowledge, multilingue
MIXTRAL_FR = "accounts/fireworks/models/mixtral-8x22b-instruct" # Fort en francais (Mistral/France)
MINIMAX = "accounts/fireworks/models/minimax-m2p1"              # Rapide, $0.30/$1.20

# --- TIER 4: Rapides / Legers (intake, routing, validation) ---
GPT_OSS_LARGE = "accounts/fireworks/models/gpt-oss-120b"       # 120B, general purpose, $0.15/$0.60
GPT_OSS_SMALL = "accounts/fireworks/models/gpt-oss-20b"        # 20B, ultra-rapide, $0.07/$0.30
QWEN3_SMALL = "accounts/fireworks/models/qwen3-30b-a3b"        # 30B, latence 0.29s, $0.15/$0.60

# --- Vision (multimodal) ---
QWEN_VL = "accounts/fireworks/models/qwen3-vl-235b-a22b-instruct"  # Vision + texte

# --- Legacy / Aliases ---
KIMI_K2 = KIMI_K25                                              # Compatibilite ancien code
DEEPSEEK_MODEL = DEEPSEEK_V3                                    # Compatibilite ancien code
COGITO = KIMI_THINK                                              # Alias retire

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(_PROJECT_DIR, "data")
LOG_DIR = os.path.join(_PROJECT_DIR, "logs")

# ═══════════════════════════════════════════════════════════
# CANLII API — Rate Limiter (2 req/sec, 5000/jour max)
# ═══════════════════════════════════════════════════════════
CANLII_API_KEY = os.environ.get("CANLII_API_KEY", "")
CANLII_BASE_URL = "https://api.canlii.org/v1"


class CanLIIRateLimiter:
    """Thread-safe rate limiter pour CanLII API — PROTECTION MAXIMALE
    CanLII = seule source jurisprudence gratuite. Se faire couper = mort du projet.
    Limites officielles: 2 req/sec, 1 simultane, 5000/jour
    Nos limites: 1 req/3sec, 1 simultane, 4800/jour, backoff sur 429"""
    _lock = threading.Lock()
    _last_request_time = 0
    _daily_count = 0
    _daily_reset_day = 0
    _consecutive_429 = 0
    _usage_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "canlii_usage.json")
    DELAY = 1.7       # 1.7 sec entre requetes (3.4x plus lent que la limite de 2/sec)
    DAILY_MAX = 4800   # 200 de marge sous 5000

    @classmethod
    def _load_daily_count(cls):
        """Charge le compteur persistant (survit aux restarts)"""
        try:
            with open(cls._usage_file) as f:
                data = json.load(f)
                saved_day = data.get("day", 0)
                today = datetime.now().timetuple().tm_yday
                if saved_day == today:
                    cls._daily_count = data.get("count", 0)
                    cls._daily_reset_day = today
                else:
                    cls._daily_count = 0
                    cls._daily_reset_day = today
        except Exception:
            pass

    @classmethod
    def _save_daily_count(cls):
        """Persiste le compteur sur disque"""
        try:
            os.makedirs(os.path.dirname(cls._usage_file), exist_ok=True)
            with open(cls._usage_file, "w") as f:
                json.dump({
                    "day": datetime.now().timetuple().tm_yday,
                    "count": cls._daily_count,
                    "last_update": datetime.now().isoformat()
                }, f)
        except Exception:
            pass

    @classmethod
    def wait(cls):
        """Attend si necessaire pour respecter le rate limit. Retourne False si quota epuise."""
        with cls._lock:
            today = datetime.now().timetuple().tm_yday
            if today != cls._daily_reset_day:
                cls._daily_count = 0
                cls._daily_reset_day = today
                cls._consecutive_429 = 0
            else:
                cls._load_daily_count()

            if cls._daily_count >= cls.DAILY_MAX:
                return False

            # Backoff exponentiel si on recoit des 429
            if cls._consecutive_429 > 0:
                backoff = min(60, cls.DELAY * (2 ** cls._consecutive_429))
                time.sleep(backoff)
            else:
                elapsed = time.time() - cls._last_request_time
                if elapsed < cls.DELAY:
                    time.sleep(cls.DELAY - elapsed)

            cls._last_request_time = time.time()
            cls._daily_count += 1
            cls._save_daily_count()
            return True

    @classmethod
    def report_429(cls):
        """Signale un HTTP 429 — active le backoff exponentiel"""
        with cls._lock:
            cls._consecutive_429 += 1

    @classmethod
    def report_success(cls):
        """Signale un succes — reset le backoff"""
        with cls._lock:
            cls._consecutive_429 = 0

    @classmethod
    def remaining(cls):
        cls._load_daily_count()
        return max(0, cls.DAILY_MAX - cls._daily_count)


class BaseAgent:
    """Classe de base pour tous les agents AITicketInfo — PostgreSQL backend"""

    def __init__(self, name):
        self.name = name
        self.client = OpenAI(
            api_key=FIREWORKS_API_KEY,
            base_url="https://api.fireworks.ai/inference/v1",
            timeout=30.0  # 30s max par requete — evite blocage si modele down
        )

    def get_db(self):
        """Retourne une connexion PostgreSQL."""
        return psycopg2.connect(**PG_CONFIG)

    def log_run(self, action, input_summary, output_summary, tokens=0, duration=0, success=True, error=None):
        try:
            conn = self.get_db()
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""INSERT INTO agent_runs
                        (agent_name, action, input_summary, output_summary,
                         tokens_used, duration_seconds, success, error)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                        (self.name, action, str(input_summary)[:500], str(output_summary)[:500],
                         tokens, round(duration, 2), success, error))
            conn.close()
        except Exception as e:
            print(f"  [!] log_run error: {e}")

    # Cascade de fallback: si un modele est down, essayer le suivant
    # GLM5 → DeepSeek V3 → Kimi K2.5 → GLM4 → DeepSeek R1 → Mixtral FR → MiniMax → GPT-OSS 120B
    FALLBACK_CHAIN = [GLM5, DEEPSEEK_V3, KIMI_K25, GLM4, DEEPSEEK_R1, MIXTRAL_FR, MINIMAX, GPT_OSS_LARGE]

    def call_ai(self, prompt, system_prompt="", model=None, temperature=0.1, max_tokens=2000):
        """Appel AI via Fireworks — multi-moteurs avec fallback en cascade"""
        model = model or DEEPSEEK_V3
        start = time.time()
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            text = response.choices[0].message.content
            if not text or not text.strip():
                raise ValueError("Model returned empty response")
            tokens = response.usage.total_tokens if response.usage else 0
            duration = time.time() - start

            return {"text": text, "tokens": tokens, "duration": duration, "success": True, "model": model}
        except Exception as e:
            duration = time.time() - start
            # Fallback en cascade: essayer le prochain modele disponible
            try:
                idx = self.FALLBACK_CHAIN.index(model)
                if idx + 1 < len(self.FALLBACK_CHAIN):
                    next_model = self.FALLBACK_CHAIN[idx + 1]
                    self.log(f"Fallback {model.split('/')[-1]} → {next_model.split('/')[-1]}", "WARN")
                    return self.call_ai(prompt, system_prompt, model=next_model, temperature=temperature, max_tokens=max_tokens)
            except ValueError:
                # model pas dans la chain — essayer DeepSeek V3 comme fallback general
                if model != DEEPSEEK_V3:
                    self.log(f"Fallback {model.split('/')[-1]} → deepseek-v3", "WARN")
                    return self.call_ai(prompt, system_prompt, model=DEEPSEEK_V3, temperature=temperature, max_tokens=max_tokens)
            return {"text": "", "tokens": 0, "duration": duration, "success": False, "error": str(e)}

    def call_ai_vision(self, prompt, image_path=None, image_base64=None, system_prompt="", model=None, temperature=0.1, max_tokens=2000):
        """Appel AI Vision via Qwen3-VL — analyse d'images"""
        model = model or QWEN_VL
        start = time.time()
        try:
            # Encoder l'image si chemin fourni
            if image_path and not image_base64:
                with open(image_path, "rb") as f:
                    image_base64 = base64.b64encode(f.read()).decode("utf-8")

            if not image_base64:
                return self.call_ai(prompt, system_prompt, temperature=temperature, max_tokens=max_tokens)

            # Detecter le type MIME
            ext = (image_path or "image.jpg").rsplit(".", 1)[-1].lower()
            mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "gif": "gif"}.get(ext, "jpeg")

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{image_base64}"}}
                ]
            })

            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            text = response.choices[0].message.content
            tokens = response.usage.total_tokens if response.usage else 0
            duration = time.time() - start

            return {"text": text, "tokens": tokens, "duration": duration, "success": True, "model": model}
        except Exception as e:
            duration = time.time() - start
            self.log(f"Vision fail, fallback texte: {e}", "WARN")
            return self.call_ai(prompt, system_prompt, temperature=temperature, max_tokens=max_tokens)

    def parse_json_response(self, text):
        """Parse JSON depuis une reponse AI (gere blocs markdown, thinking text, etc.)"""
        if not text or not text.strip():
            raise ValueError("Empty response text")
        cleaned = text.strip()
        # Retirer blocs <think>...</think> (modeles thinking)
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned).strip()
        # Retirer blocs markdown
        md_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", cleaned)
        if md_match:
            cleaned = md_match.group(1).strip()
        # Extraire le JSON (premier objet { ... })
        json_match = re.search(r"\{[\s\S]*\}", cleaned)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(cleaned)

    # ═══════════════════════════════════════════════════════════
    # HELPERS DONNEES ENRICHIES (weather, road_conditions, speed_limits)
    # ═══════════════════════════════════════════════════════════

    def fetch_context_enrichi(self, ticket):
        """Lookup complet: meteo + conditions routieres + limites vitesse + stats constats + radar + principes cles + citations + legislation + radar lieux + collisions"""
        lieu = ticket.get("lieu", "")
        date = ticket.get("date", "")
        province = ticket.get("juridiction", "QC")
        city = self._extract_city(lieu)
        article = ticket.get("loi", "")
        infraction = ticket.get("infraction", "")

        result = {
            "weather": self._fetch_weather_live(city, date, province),
            "road_conditions": self._fetch_road_conditions(lieu, province),
            "speed_limits": self._fetch_speed_limits(lieu, province, city),
        }

        # Enrichissement QC: constats similaires + stats radar + lieux radar
        if province in ("QC", "Quebec"):
            result["constats_similaires"] = self._fetch_constats_similaires(article, lieu)
            result["radar_stats"] = self._fetch_radar_stats(lieu)
            result["radar_lieux"] = self._fetch_radar_lieux(lieu)

        # Montreal: collisions context
        if city and city.lower() in ("montreal", "montréal", "mtl"):
            result["mtl_collisions"] = self._fetch_mtl_collisions(lieu)

        # Principes juridiques cles (ref_jurisprudence_cle — 14 principes universels)
        result["principes_cles"] = self._fetch_principes_cles(infraction, province)

        # Jurisprudence legislation (165 liens loi<->jurisprudence)
        result["jurisprudence_legislation"] = self._fetch_jurisprudence_legislation(article, province)

        return result

    def _extract_city(self, lieu):
        """Extraire le nom de ville depuis le champ lieu du ticket"""
        if not lieu:
            return ""
        # Nettoyage basique: "Autoroute 40, Montreal" → "Montreal"
        # Aussi: "A-40 Est, km 123, Laval" → "Laval"
        parts = [p.strip() for p in lieu.replace("|", ",").split(",")]
        # Les villes connues dans notre DB
        known_cities = ["Montreal", "Toronto", "Quebec", "Laval", "Gatineau",
                        "Longueuil", "Ottawa", "Mississauga", "Hamilton", "Brampton",
                        "Sherbrooke", "Trois-Rivieres", "Levis", "Terrebonne",
                        "London", "Kitchener", "Windsor", "Markham", "Vaughan"]
        lieu_lower = lieu.lower()
        for c in known_cities:
            if c.lower() in lieu_lower:
                return c
        # Fallback: dernier element (souvent la ville)
        return parts[-1] if parts else ""

    def _fetch_weather_live(self, city, date_str, province="QC"):
        """Appel live api.weather.gc.ca pour meteo historique a la date du ticket"""
        if not date_str or not city:
            return None
        try:
            import requests as _req
            # Trouver la station la plus proche via le fichier de stations
            station_id = self._find_station(city, province)
            if not station_id:
                return None

            r = _req.get(
                "https://api.weather.gc.ca/collections/climate-daily/items",
                params={
                    "CLIMATE_IDENTIFIER": station_id,
                    "datetime": date_str,
                    "limit": 1,
                    "f": "json",
                    "lang": "en"
                },
                timeout=8
            )
            if r.status_code == 200:
                data = r.json()
                features = data.get("features", [])
                if features:
                    p = features[0].get("properties", {})
                    return {
                        "station": p.get("STATION_NAME", ""),
                        "date": date_str,
                        "temp_max": p.get("MAX_TEMPERATURE"),
                        "temp_min": p.get("MIN_TEMPERATURE"),
                        "temp_mean": p.get("MEAN_TEMPERATURE"),
                        "precipitation_mm": p.get("TOTAL_PRECIPITATION"),
                        "snow_cm": p.get("TOTAL_SNOWFALL"),
                        "snow_ground_cm": p.get("SNOW_ON_GROUND"),
                        "wind_gust_kmh": p.get("SPEED_MAX_GUST"),
                        "source": "Environnement Canada"
                    }
        except Exception:
            pass
        return None

    def _find_station(self, city, province):
        """Trouver l'ID de station meteo la plus proche via le fichier JSON"""
        stations_file = os.path.join(DATA_DIR, "..", "db", "weather_stations.json")
        if not os.path.exists(stations_file):
            return None
        try:
            with open(stations_file) as f:
                stations = json.load(f)
            city_lower = city.lower()
            # Chercher par nom de ville dans le nom de station
            for s in stations:
                if s.get("province") == province and city_lower in s.get("name", "").lower():
                    return s["id"]
            # Fallback: premiere station de la province
            for s in stations:
                if s.get("province") == province and s.get("id"):
                    return s["id"]
        except Exception:
            pass
        return None

    def _fetch_road_conditions(self, lieu, province):
        """Query road_conditions table pour le lieu du ticket (PostgreSQL)"""
        if not lieu:
            return []
        try:
            conn = self.get_db()
            cur = conn.cursor()
            lieu_parts = [p.strip() for p in lieu.replace(",", " ").split() if len(p.strip()) > 2]
            results = []
            for part in lieu_parts[:3]:
                cur.execute(
                    "SELECT road_name, condition_type, description, start_date, end_date "
                    "FROM road_conditions WHERE province=%s AND "
                    "(road_name ILIKE %s OR description ILIKE %s) LIMIT 5",
                    (province, f"%{part}%", f"%{part}%")
                )
                for row in cur.fetchall():
                    results.append({
                        "road": row[0], "type": row[1], "description": row[2],
                        "start": str(row[3]) if row[3] else "", "end": str(row[4]) if row[4] else ""
                    })
            conn.close()
            seen = set()
            unique = []
            for r in results:
                key = f"{r['road']}_{r['type']}"
                if key not in seen:
                    seen.add(key)
                    unique.append(r)
            return unique[:5]
        except Exception:
            return []

    def _fetch_speed_limits(self, lieu, province, city):
        """Query speed_limits table pour les limites de vitesse (PostgreSQL)"""
        if not lieu and not city:
            return []
        try:
            conn = self.get_db()
            cur = conn.cursor()
            results = []

            lieu_parts = [p.strip() for p in lieu.replace(",", " ").split() if len(p.strip()) > 2]
            for part in lieu_parts[:3]:
                cur.execute(
                    "SELECT road_name, maxspeed_kmh, road_type, school_zone, city "
                    "FROM speed_limits WHERE province=%s AND road_name ILIKE %s LIMIT 5",
                    (province, f"%{part}%")
                )
                for row in cur.fetchall():
                    results.append({
                        "road": row[0], "limit_kmh": row[1], "type": row[2],
                        "school_zone": bool(row[3]), "city": row[4]
                    })

            if not results and city:
                cur.execute(
                    "SELECT road_name, maxspeed_kmh, road_type, school_zone, city, "
                    "COUNT(*) as cnt FROM speed_limits "
                    "WHERE province=%s AND city=%s "
                    "GROUP BY road_name, maxspeed_kmh, road_type, school_zone, city "
                    "ORDER BY cnt DESC LIMIT 5",
                    (province, city)
                )
                for row in cur.fetchall():
                    results.append({
                        "road": f"Moyenne {row[4]}", "limit_kmh": row[1],
                        "type": row[2], "school_zone": bool(row[3]), "city": row[4]
                    })

            conn.close()
            return results[:5]
        except Exception:
            return []

    def _fetch_constats_similaires(self, article_loi, lieu):
        """Cherche des constats similaires dans qc_constats_infraction (356K+ records)"""
        results = []
        try:
            conn = self.get_db()
            cur = conn.cursor()

            # Extraire l'article du champ loi (ex: "Code de la securite routiere, art. 299" → "299")
            import re as _re
            art_match = _re.search(r"(?:art\.?\s*)?(\d+(?:\.\d+)?)", article_loi or "")
            article = art_match.group(1) if art_match else ""

            if article:
                # Stats pour le même article CSR
                cur.execute("""
                    SELECT
                        raw_data->>'NO_ARTCL_L_R' AS article,
                        raw_data->>'DESCN_CAT_INFRA' AS categorie,
                        COUNT(*) AS nb_constats,
                        COUNT(DISTINCT raw_data->>'COD_MUNI_LIEU') AS nb_municipalites,
                        MIN(raw_data->>'DAT_INFRA_COMMI') AS premiere_date,
                        MAX(raw_data->>'DAT_INFRA_COMMI') AS derniere_date
                    FROM qc_constats_infraction
                    WHERE raw_data->>'NO_ARTCL_L_R' = %s
                    GROUP BY raw_data->>'NO_ARTCL_L_R', raw_data->>'DESCN_CAT_INFRA'
                    LIMIT 5
                """, (article,))

                for row in cur.fetchall():
                    results.append({
                        "article": row[0], "categorie": row[1],
                        "nb_constats": row[2], "nb_municipalites": row[3],
                        "premiere_date": str(row[4]) if row[4] else "",
                        "derniere_date": str(row[5]) if row[5] else ""
                    })

            # Stats generales vitesse si applicable
            if not results:
                cur.execute("""
                    SELECT
                        raw_data->>'DESCN_CAT_INFRA' AS categorie,
                        COUNT(*) AS nb_constats
                    FROM qc_constats_infraction
                    WHERE raw_data->>'DESCN_CAT_INFRA' ILIKE %s
                    GROUP BY raw_data->>'DESCN_CAT_INFRA'
                    ORDER BY nb_constats DESC LIMIT 5
                """, ("%vitesse%",))
                for row in cur.fetchall():
                    results.append({"categorie": row[0], "nb_constats": row[1]})

            conn.close()
        except Exception:
            pass
        return results

    def _fetch_radar_stats(self, lieu):
        """Cherche les stats radar photo pour le lieu du ticket (27K+ records)"""
        results = []
        if not lieu:
            return results
        try:
            conn = self.get_db()
            cur = conn.cursor()

            # Chercher par mots-clés du lieu dans le champ Site
            lieu_parts = [p.strip() for p in lieu.replace(",", " ").split() if len(p.strip()) > 3]
            for part in lieu_parts[:3]:
                cur.execute("""
                    SELECT
                        raw_data->>'Site' AS site,
                        raw_data->>'Moyen' AS moyen,
                        (raw_data->>'Nombre')::bigint AS nb_constats,
                        (raw_data->>'Montant')::numeric AS montant_total,
                        raw_data->>'Date' AS date_rapport
                    FROM qc_radar_photo_stats
                    WHERE raw_data->>'Site' ILIKE %s
                    ORDER BY (raw_data->>'Nombre')::bigint DESC
                    LIMIT 5
                """, (f"%{part}%",))
                for row in cur.fetchall():
                    results.append({
                        "site": (row[0] or "")[:150], "moyen": row[1],
                        "nb_constats": row[2], "montant_total": float(row[3]) if row[3] else 0,
                        "date_rapport": row[4]
                    })

            conn.close()
            # Dedup par site
            seen = set()
            unique = []
            for r in results:
                key = r["site"][:50]
                if key not in seen:
                    seen.add(key)
                    unique.append(r)
            return unique[:10]
        except Exception:
            return []

    def _fetch_radar_lieux(self, lieu):
        """Cherche les emplacements exacts de radar photo (qc_radar_photo_lieux — 160 sites)"""
        results = []
        if not lieu:
            return results
        try:
            conn = self.get_db()
            cur = conn.cursor()
            lieu_parts = [p.strip() for p in lieu.replace(",", " ").split() if len(p.strip()) > 3]
            for part in lieu_parts[:3]:
                cur.execute("""
                    SELECT emplacement, direction, vitesse_limite,
                           type_appareil, municipalite, route,
                           latitude, longitude
                    FROM qc_radar_photo_lieux
                    WHERE emplacement ILIKE %s
                       OR municipalite ILIKE %s
                       OR route ILIKE %s
                    LIMIT 5
                """, (f"%{part}%", f"%{part}%", f"%{part}%"))
                for row in cur.fetchall():
                    results.append({
                        "site": (row[0] or "")[:200], "direction": row[1] or "",
                        "limite_vitesse": row[2], "type_appareil": row[3] or "",
                        "municipalite": row[4] or "", "route": row[5] or "",
                        "lat": row[6], "lon": row[7]
                    })
            conn.close()
            # Dedup
            seen = set()
            unique = []
            for r in results:
                key = f"{r['site'][:50]}_{r.get('direction','')}"
                if key not in seen:
                    seen.add(key)
                    unique.append(r)
            return unique[:10]
        except Exception:
            return []

    def _fetch_mtl_collisions(self, lieu):
        """Statistiques collisions Montreal autour du lieu du ticket (mtl_collisions — 218K+ rows)"""
        results = []
        if not lieu:
            return results
        try:
            conn = self.get_db()
            cur = conn.cursor()
            lieu_parts = [p.strip() for p in lieu.replace(",", " ").split() if len(p.strip()) > 3]
            for part in lieu_parts[:3]:
                cur.execute("""
                    SELECT
                        rue1,
                        gravite,
                        COUNT(*) AS nb_collisions,
                        SUM(COALESCE(nombre_blesses_graves, 0) + COALESCE(nombre_blesses_legers, 0)) AS nb_blesses,
                        SUM(COALESCE(nombre_deces, 0)) AS nb_mortels,
                        MIN(date_collision) AS premiere_date,
                        MAX(date_collision) AS derniere_date
                    FROM mtl_collisions
                    WHERE rue1 ILIKE %s OR rue2 ILIKE %s
                    GROUP BY rue1, gravite
                    ORDER BY nb_collisions DESC
                    LIMIT 5
                """, (f"%{part}%", f"%{part}%"))
                for row in cur.fetchall():
                    results.append({
                        "rue": (row[0] or "")[:100], "gravite": row[1] or "",
                        "nb_collisions": row[2], "nb_blesses": row[3] or 0,
                        "nb_mortels": row[4] or 0,
                        "premiere_date": str(row[5]) if row[5] else "",
                        "derniere_date": str(row[6]) if row[6] else ""
                    })
            conn.close()
            # Dedup
            seen = set()
            unique = []
            for r in results:
                key = f"{r['rue'][:50]}_{r.get('gravite','')}"
                if key not in seen:
                    seen.add(key)
                    unique.append(r)
            return unique[:10]
        except Exception:
            return []

    def _fetch_principes_cles(self, infraction, province):
        """Charge les principes juridiques cles pertinents (ref_jurisprudence_cle — 14 principes)"""
        results = []
        try:
            conn = self.get_db()
            cur = conn.cursor()
            # Charger tous les principes (seulement 14 lignes) — filtrer par province
            cur.execute("""
                SELECT nom_cas, citation, tribunal, loi_applicable, article_applicable,
                       principe_juridique, type_infraction, resultat, notes, province
                FROM ref_jurisprudence_cle
                WHERE province IN (%s, 'CA')
                   OR province IS NULL
                ORDER BY annee DESC NULLS LAST
            """, (province,))
            for row in cur.fetchall():
                results.append({
                    "cle": row[0] or "", "principe": (row[5] or "")[:300],
                    "source": row[1] or "", "province": row[9] or "CA",
                    "categorie": row[6] or "",
                    "application": f"Art. {row[4] or '?'} {row[3] or ''} — {row[7] or ''}: {(row[8] or '')[:150]}"
                })
            conn.close()
        except Exception:
            pass
        return results

    def _fetch_jurisprudence_legislation(self, article_loi, province):
        """Trouve les cas de jurisprudence qui citent cette loi (jurisprudence_legislation — 165 rows)"""
        results = []
        if not article_loi:
            return results
        try:
            conn = self.get_db()
            cur = conn.cursor()
            # Extraire le numero d'article
            import re as _re
            art_match = _re.search(r"(?:art\.?\s*|s\.?\s*|section\s*)?(\d+(?:\.\d+)?)", article_loi)
            article = art_match.group(1) if art_match else ""
            if not article:
                conn.close()
                return results

            # jurisprudence_legislation n'a pas de FK directe vers jurisprudence
            # On join via case_canlii_id (qui correspond a canlii_id dans jurisprudence)
            cur.execute("""
                SELECT jl.titre_legislation, jl.database_id,
                       j.citation, j.database_id AS tribunal, j.date_decision,
                       j.resultat, j.resume
                FROM jurisprudence_legislation jl
                LEFT JOIN jurisprudence j ON j.canlii_id = jl.case_canlii_id
                WHERE jl.titre_legislation ILIKE %s
                ORDER BY j.date_decision DESC NULLS LAST
                LIMIT 10
            """, (f"%{article}%",))
            for row in cur.fetchall():
                results.append({
                    "legislation": (row[0] or "")[:150],
                    "legislation_db": row[1] or "",
                    "citation": row[2] or "",
                    "tribunal": (row[3] or "").upper(),
                    "date": str(row[4]) if row[4] else "",
                    "resultat": row[5] or "inconnu",
                    "resume": (row[6] or "")[:200]
                })
            conn.close()
        except Exception:
            pass
        return results

    def _fetch_jurisprudence_citations(self, jurisprudence_ids):
        """Enrichit les precedents avec les cas lies (jurisprudence_citations — 716 rows)"""
        results = []
        if not jurisprudence_ids:
            return results
        try:
            conn = self.get_db()
            cur = conn.cursor()
            # Pour chaque precedent, trouver les cas cites et citants via canlii_id
            for jid in jurisprudence_ids[:10]:
                # D'abord, trouver le canlii_id de ce precedent
                cur.execute("SELECT canlii_id FROM jurisprudence WHERE id = %s", (jid,))
                row = cur.fetchone()
                if not row or not row[0]:
                    continue
                canlii_id = row[0]

                cur.execute("""
                    SELECT jc.target_citation, jc.target_database_id,
                           jc.type_citation, jc.target_titre,
                           j.resume, j.resultat
                    FROM jurisprudence_citations jc
                    LEFT JOIN jurisprudence j ON j.canlii_id = jc.target_canlii_id
                    WHERE jc.source_canlii_id = %s
                    LIMIT 5
                """, (canlii_id,))
                for row in cur.fetchall():
                    results.append({
                        "parent_id": jid,
                        "cited_citation": row[0] or row[3] or "",
                        "cited_db": row[1] or "",
                        "relationship": row[2] or "cites",
                        "resume": (row[4] or "")[:200],
                        "resultat": row[5] or "inconnu"
                    })
            conn.close()
        except Exception:
            pass
        return results

    # ═══════════════════════════════════════════════════════════
    # CANLII API — Recherche jurisprudence live (rate-limited)
    # ═══════════════════════════════════════════════════════════

    def canlii_search_cases(self, database_id, query="", result_count=10, lang="fr"):
        """Recherche CanLII API — decisions d'un tribunal avec rate limiting"""
        if not CANLII_API_KEY:
            return []
        if not CanLIIRateLimiter.wait():
            self.log("CanLII: quota journalier atteint", "WARN")
            return []
        try:
            import requests
            params = {
                "api_key": CANLII_API_KEY,
                "offset": 0,
                "resultCount": min(result_count, 100)
            }
            resp = requests.get(f"{CANLII_BASE_URL}/caseBrowse/{lang}/{database_id}/",
                                params=params, timeout=15)
            if resp.status_code == 200:
                CanLIIRateLimiter.report_success()
                return resp.json().get("cases", [])[:result_count]
            elif resp.status_code == 429:
                CanLIIRateLimiter.report_429()
                self.log(f"CanLII {database_id}: HTTP 429 — backoff actif", "WARN")
            else:
                self.log(f"CanLII {database_id}: HTTP {resp.status_code}", "WARN")
        except Exception as e:
            self.log(f"CanLII erreur: {e}", "WARN")
        return []

    def canlii_case_metadata(self, database_id, case_id, lang="fr"):
        """Metadata CanLII d'une decision specifique (rate-limited)"""
        if not CANLII_API_KEY:
            return {}
        if not CanLIIRateLimiter.wait():
            return {}
        try:
            import requests
            resp = requests.get(
                f"{CANLII_BASE_URL}/caseBrowse/{lang}/{database_id}/{case_id}/",
                params={"api_key": CANLII_API_KEY}, timeout=15)
            if resp.status_code == 200:
                CanLIIRateLimiter.report_success()
                return resp.json()
            elif resp.status_code == 429:
                CanLIIRateLimiter.report_429()
        except Exception:
            pass
        return {}

    def canlii_citator(self, database_id, case_id, citator_type="citingCases"):
        """Citateur CanLII — decisions citees/citantes (rate-limited)
        citator_type: citedCases | citingCases | citedLegislations"""
        if not CANLII_API_KEY:
            return []
        if not CanLIIRateLimiter.wait():
            return []
        try:
            import requests
            # Le citateur fonctionne UNIQUEMENT en anglais
            resp = requests.get(
                f"{CANLII_BASE_URL}/caseCitator/en/{database_id}/{case_id}/{citator_type}",
                params={"api_key": CANLII_API_KEY}, timeout=15)
            if resp.status_code == 200:
                CanLIIRateLimiter.report_success()
                return resp.json().get(citator_type, [])
            elif resp.status_code == 429:
                CanLIIRateLimiter.report_429()
        except Exception:
            pass
        return []

    def canlii_remaining_quota(self):
        """Retourne le nombre de requetes CanLII restantes aujourd'hui"""
        return CanLIIRateLimiter.remaining()

    def format_contexte_pour_prompt(self, contexte):
        """Formatter le contexte enrichi en texte pour injection dans un prompt AI"""
        if not contexte:
            return ""
        sections = []

        w = contexte.get("weather")
        if w:
            sections.append(
                f"METEO ({w.get('source', 'Env Canada')}) — {w.get('date', '')}:\n"
                f"  Temperature: {w.get('temp_min', '?')}°C à {w.get('temp_max', '?')}°C (moy: {w.get('temp_mean', '?')}°C)\n"
                f"  Precipitations: {w.get('precipitation_mm', 0)} mm | Neige: {w.get('snow_cm', 0)} cm | Neige au sol: {w.get('snow_ground_cm', 0)} cm\n"
                f"  Vent max: {w.get('wind_gust_kmh', '?')} km/h | Station: {w.get('station', '?')}"
            )

        roads = contexte.get("road_conditions", [])
        if roads:
            lines = ["CONDITIONS ROUTIERES (511):"]
            for r in roads:
                lines.append(f"  - {r.get('road', '?')}: {r.get('type', '?')} — {r.get('description', '')[:100]}")
            sections.append("\n".join(lines))

        speeds = contexte.get("speed_limits", [])
        if speeds:
            lines = ["LIMITES DE VITESSE (OpenStreetMap):"]
            for s in speeds:
                zone = " [ZONE SCOLAIRE]" if s.get("school_zone") else ""
                lines.append(f"  - {s.get('road', '?')}: {s.get('limit_kmh', '?')} km/h ({s.get('type', '')}){zone}")
            sections.append("\n".join(lines))

        constats = contexte.get("constats_similaires", [])
        if constats:
            lines = ["STATISTIQUES CONSTATS SIMILAIRES (Données Québec — 356K+ constats):"]
            for c in constats:
                if c.get("nb_constats"):
                    lines.append(
                        f"  - Art. {c.get('article', '?')} ({c.get('categorie', '?')}): "
                        f"{c['nb_constats']:,} constats dans {c.get('nb_municipalites', '?')} municipalités "
                        f"({c.get('premiere_date', '?')} à {c.get('derniere_date', '?')})"
                    )
                elif c.get("categorie"):
                    lines.append(f"  - {c['categorie']}: {c.get('nb_constats', 0):,} constats")
            sections.append("\n".join(lines))

        radar = contexte.get("radar_stats", [])
        if radar:
            lines = ["STATISTIQUES RADAR PHOTO (site specifique):"]
            for r in radar:
                montant_str = f"${r['montant_total']:,.0f}" if r.get("montant_total") else "?"
                lines.append(
                    f"  - {r.get('site', '?')}\n"
                    f"    Appareil: {r.get('moyen', '?')} | Constats: {r.get('nb_constats', 0):,} | "
                    f"Montant total: {montant_str} | Date: {r.get('date_rapport', '?')}"
                )
            sections.append("\n".join(lines))

        # Radar lieux exacts (160 emplacements precis)
        radar_lieux = contexte.get("radar_lieux", [])
        if radar_lieux:
            lines = ["EMPLACEMENTS RADAR PHOTO EXACTS (SAAQ — 160 sites):"]
            for rl in radar_lieux:
                lines.append(
                    f"  - {rl.get('site', '?')} ({rl.get('direction', '?')})\n"
                    f"    Limite: {rl.get('limite_vitesse', '?')} km/h | Type: {rl.get('type_appareil', '?')} | "
                    f"Municipalite: {rl.get('municipalite', '?')}"
                )
            sections.append("\n".join(lines))

        # Montreal collisions (contexte dangerosité du lieu)
        mtl_coll = contexte.get("mtl_collisions", [])
        if mtl_coll:
            lines = ["COLLISIONS MONTREAL (historique — 218K+ incidents):"]
            for mc in mtl_coll:
                lines.append(
                    f"  - {mc.get('rue', '?')}: {mc.get('nb_collisions', 0)} collisions "
                    f"({mc.get('nb_blesses', 0)} blessés, {mc.get('nb_mortels', 0)} décès) "
                    f"| Gravité: {mc.get('gravite', '?')}"
                )
            sections.append("\n".join(lines))

        # Principes juridiques cles (ref_jurisprudence_cle)
        principes = contexte.get("principes_cles", [])
        if principes:
            lines = ["PRINCIPES JURIDIQUES CLES (jurisprudence établie):"]
            for p in principes:
                lines.append(
                    f"  - [{p.get('cle', '?')}] {p.get('principe', '')}\n"
                    f"    Source: {p.get('source', '?')} | Application: {p.get('application', '')}"
                )
            sections.append("\n".join(lines))

        # Jurisprudence legislation (liens cas <-> lois)
        juris_leg = contexte.get("jurisprudence_legislation", [])
        if juris_leg:
            lines = ["JURISPRUDENCE CITANT CETTE LOI (liens cas-legislation):"]
            for jl in juris_leg:
                lines.append(
                    f"  - Cas: {jl.get('citation', '?')} → Loi: {jl.get('legislation', '?')}\n"
                    f"    Tribunal: {jl.get('tribunal', '?')} | Resultat: {jl.get('resultat', '?')}"
                )
            sections.append("\n".join(lines))

        return "\n\n".join(sections) if sections else ""

    def log(self, msg, level="INFO"):
        symbols = {"INFO": "[i]", "OK": "[+]", "FAIL": "[X]", "WARN": "[!]", "STEP": ">>>"}
        print(f"  {symbols.get(level, '')} [{self.name}] {msg}")
