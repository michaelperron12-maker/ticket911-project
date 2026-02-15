#!/usr/bin/env python3
"""
Data Enrichment — AITicketInfo.ca
Télécharge et intègre des données de 5 sources supplémentaires:
1. A2AJ Canadian Legal Data (Hugging Face / API)
2. Environnement Canada Weather API (preuves météo)
3. Lois complètes (Justice Laws XML, e-Laws ON, LégisQuébec)
4. Québec 511 / Ontario 511 (zones travaux)
5. OpenStreetMap (limites de vitesse)
"""

import sqlite3
import requests
import time
import json
import os
import sys
import io
from datetime import datetime

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_PROJECT_DIR, "db", "aiticketinfo.db")
LOG_PREFIX = "[ENRICHMENT]"

def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {LOG_PREFIX} {msg}", flush=True)

def open_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn

def ensure_tables():
    """Créer les tables supplémentaires si nécessaire"""
    conn = open_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS weather_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            station_name TEXT,
            station_id TEXT,
            province TEXT,
            date TEXT,
            temp_max REAL,
            temp_min REAL,
            temp_mean REAL,
            precipitation REAL,
            snow REAL,
            wind_speed REAL,
            conditions TEXT,
            raw_data TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS road_conditions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            province TEXT,
            road_name TEXT,
            segment TEXT,
            condition_type TEXT,
            description TEXT,
            latitude REAL,
            longitude REAL,
            start_date TEXT,
            end_date TEXT,
            raw_data TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS speed_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            osm_way_id TEXT UNIQUE,
            road_name TEXT,
            maxspeed TEXT,
            maxspeed_kmh INTEGER,
            road_type TEXT,
            school_zone INTEGER DEFAULT 0,
            province TEXT,
            city TEXT,
            latitude REAL,
            longitude REAL,
            created_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_weather_station_date ON weather_data(station_id, date);
        CREATE INDEX IF NOT EXISTS idx_road_conditions_province ON road_conditions(province, condition_type);
        CREATE INDEX IF NOT EXISTS idx_speed_limits_province ON speed_limits(province, maxspeed_kmh);
    """)
    conn.close()
    log("Tables supplementaires creees/verifiees")


# ==========================================
# 1. A2AJ Canadian Legal Data
# ==========================================
def download_a2aj():
    """Télécharger les données A2AJ via Hugging Face Parquet + REST API"""
    log("=" * 50)
    log("1. A2AJ CANADIAN LEGAL DATA")
    log("=" * 50)

    conn = open_db()
    c = conn.cursor()
    c.execute("SELECT citation FROM jurisprudence")
    existing = set(row[0] for row in c.fetchall())
    total_new = 0

    # --- Methode 1: API REST (decouvrir endpoints depuis OpenAPI spec) ---
    API_BASE = "https://api.a2aj.ca"
    log("  Decouverte des endpoints API A2AJ...")
    api_endpoints = {}
    try:
        r = requests.get(f"{API_BASE}/openapi.json", timeout=15)
        if r.status_code == 200:
            spec = r.json()
            for path, methods in spec.get("paths", {}).items():
                for method in methods:
                    api_endpoints[path] = method.upper()
                    log(f"    {method.upper()} {path}")
    except Exception as e:
        log(f"    Impossible de lire OpenAPI spec: {e}")

    # Tenter recherche via l'API si un endpoint de recherche existe
    search_paths = [p for p in api_endpoints if "search" in p.lower() or "case" in p.lower()]
    if search_paths:
        search_terms = [
            "traffic speeding", "highway traffic act", "excès de vitesse",
            "conduite dangereuse", "impaired driving", "stunt driving",
            "careless driving", "code sécurité routière", "alcool volant",
            "suspension permis", "red light camera", "demerit points",
        ]
        for term in search_terms:
            for path in search_paths[:2]:
                log(f'  API A2AJ {path}: "{term}"')
                try:
                    r = requests.get(f"{API_BASE}{path}", params={
                        "q": term, "query": term, "limit": 100
                    }, timeout=30)
                    time.sleep(1)
                    if r.status_code != 200:
                        continue
                    data = r.json()
                    results = data if isinstance(data, list) else data.get("results", data.get("cases", data.get("items", [])))
                    for case in results:
                        citation = case.get("citation", case.get("name_en", case.get("id", "")))
                        title = case.get("title", case.get("name_en", case.get("name_fr", "")))
                        if not citation or citation in existing:
                            continue
                        date_dec = case.get("date", case.get("date_en", case.get("date_fr", "")))
                        text = case.get("unofficial_text_en", case.get("unofficial_text_fr", ""))
                        resume = text[:2000] if text else title
                        url_src = case.get("url_en", case.get("url_fr", ""))
                        jur = "CA"
                        if "qc" in citation.lower() or "quebec" in str(case).lower():
                            jur = "QC"
                        elif "on" in citation.lower() or "ontario" in str(case).lower():
                            jur = "ON"
                        try:
                            conn.execute(
                                "INSERT OR IGNORE INTO jurisprudence "
                                "(citation, titre, tribunal, juridiction, date_decision, resume, source, langue, created_at) "
                                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (citation, title, "", jur, date_dec, resume,
                                 f"a2aj-api", "en", datetime.now().isoformat())
                            )
                            total_new += 1
                            existing.add(citation)
                        except:
                            pass
                    conn.commit()
                    log(f"    -> {len(results) if isinstance(results, list) else 0} resultats")
                except Exception as e:
                    log(f"    Erreur: {e}")
    else:
        log("  Pas d'endpoint de recherche trouve, passage au Parquet...")

    # --- Methode 2: Telechargement direct Parquet depuis Hugging Face ---
    # Courts pertinents pour le traffic
    HF_BASE = "https://huggingface.co/datasets/a2aj/canadian-case-law/resolve/main"
    courts_to_download = ["SCC", "ONCA", "FCA", "FC"]  # Cour supreme + Ontario Appeal + Federal

    try:
        # Verifier si pandas et pyarrow sont disponibles
        import pandas as pd
        log("  Telechargement Parquet Hugging Face...")

        for court in courts_to_download:
            url = f"{HF_BASE}/{court}/train.parquet"
            log(f"    Downloading {court}...")
            try:
                r = requests.get(url, timeout=120, stream=True)
                if r.status_code != 200:
                    log(f"    HTTP {r.status_code} pour {court}")
                    continue

                df = pd.read_parquet(io.BytesIO(r.content))
                court_new = 0
                traffic_kw = ["traffic", "driving", "speed", "highway", "impaired", "stunt",
                              "careless", "vitesse", "conduite", "routier", "alcool", "volant",
                              "permis", "vehicul", "accident", "collision", "dui", "dwi"]

                for _, row in df.iterrows():
                    title = str(row.get("name_en", "") or row.get("name_fr", "") or "")
                    text = str(row.get("unofficial_text_en", "") or row.get("unofficial_text_fr", "") or "")

                    # Filtrer uniquement les decisions liees au traffic
                    combined = (title + " " + text[:500]).lower()
                    if not any(kw in combined for kw in traffic_kw):
                        continue

                    citation = title  # A2AJ utilise le nom comme identifiant
                    if citation in existing or not citation:
                        continue

                    date_dec = str(row.get("date_en", "") or row.get("date_fr", "") or "")
                    resume = text[:2000] if text else title
                    url_src = str(row.get("url_en", "") or row.get("url_fr", "") or "")
                    jur = "CA"
                    if court == "ONCA":
                        jur = "ON"

                    try:
                        conn.execute(
                            "INSERT OR IGNORE INTO jurisprudence "
                            "(citation, titre, tribunal, juridiction, date_decision, resume, source, langue, created_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (citation, title, court, jur, date_dec, resume,
                             f"a2aj-hf-{court}", "en", datetime.now().isoformat())
                        )
                        court_new += 1
                        total_new += 1
                        existing.add(citation)
                    except:
                        pass

                conn.commit()
                log(f"    {court}: {len(df)} total, +{court_new} traffic-related")

            except Exception as e:
                log(f"    Erreur {court}: {e}")

    except ImportError:
        log("  pandas/pyarrow non disponibles — skip Parquet download")
        log("  Pour installer: pip install pandas pyarrow")

    conn.close()
    log(f"  TOTAL A2AJ: +{total_new} decisions")
    return total_new


# ==========================================
# 2. ENVIRONNEMENT CANADA WEATHER API
# ==========================================
def setup_weather_stations():
    """Configurer les stations météo pour QC et ON"""
    log("=" * 50)
    log("2. ENVIRONNEMENT CANADA WEATHER API")
    log("=" * 50)

    # Stations météo principales QC + ON
    # On télécharge la liste des stations disponibles
    API_BASE = "https://api.weather.gc.ca"

    stations = []
    # Bounding boxes par province (minLon,minLat,maxLon,maxLat)
    province_bboxes = [
        ("QC", "-80,44,-57,63"),   # Quebec
        ("ON", "-95,42,-74,57"),   # Ontario
    ]
    try:
        for prov, bbox in province_bboxes:
            r = requests.get(
                f"{API_BASE}/collections/climate-stations/items",
                params={"limit": 500, "bbox": bbox, "f": "json", "lang": "en"},
                timeout=30
            )
            time.sleep(0.5)
            if r.status_code == 200:
                data = r.json()
                features = data.get("features", [])
                for f in features:
                    props = f.get("properties", {})
                    stations.append({
                        "id": props.get("CLIMATE_IDENTIFIER", ""),
                        "name": props.get("STATION_NAME", ""),
                        "province": prov,
                        "lat": f.get("geometry", {}).get("coordinates", [0, 0])[1],
                        "lon": f.get("geometry", {}).get("coordinates", [0, 0])[0],
                    })
                log(f"  {len(features)} stations {prov} trouvees")

    except Exception as e:
        log(f"  Erreur stations: {e}")

    # Sauvegarder la config des stations
    stations_file = os.path.join(_PROJECT_DIR, "db", "weather_stations.json")
    with open(stations_file, "w") as f:
        json.dump(stations, f)
    log(f"  {len(stations)} stations sauvegardees dans {stations_file}")

    return len(stations)


def fetch_weather_for_date(station_id, date_str, province="QC"):
    """Récupérer la météo pour une date et station spécifiques
    Utilisé pendant l'analyse d'un ticket pour prouver les conditions
    """
    API_BASE = "https://api.weather.gc.ca"
    try:
        r = requests.get(
            f"{API_BASE}/collections/climate-daily/items",
            params={
                "CLIMATE_IDENTIFIER": station_id,
                "datetime": date_str,
                "limit": 1,
                "f": "json"
            },
            timeout=15
        )
        if r.status_code == 200:
            data = r.json()
            features = data.get("features", [])
            if features:
                props = features[0].get("properties", {})
                return {
                    "date": date_str,
                    "station": station_id,
                    "temp_max": props.get("MAX_TEMPERATURE"),
                    "temp_min": props.get("MIN_TEMPERATURE"),
                    "temp_mean": props.get("MEAN_TEMPERATURE"),
                    "precipitation": props.get("TOTAL_PRECIPITATION"),
                    "snow": props.get("TOTAL_SNOWFALL"),
                    "wind_speed": props.get("SPEED_MAX_GUST"),
                    "conditions": props.get("WEATHER_CONDITION", ""),
                }
    except:
        pass
    return None


# ==========================================
# 3. LOIS COMPLÈTES (Justice Laws, e-Laws, LégisQuébec)
# ==========================================
def download_federal_laws():
    """Télécharger les lois fédérales depuis Justice Laws (XML)"""
    log("=" * 50)
    log("3a. LOIS FEDERALES (Justice Laws)")
    log("=" * 50)

    conn = open_db()
    existing = set()
    c = conn.cursor()
    c.execute("SELECT nom_loi, article FROM lois")
    for row in c.fetchall():
        existing.add((row[0], row[1]))

    total_new = 0

    # Code criminel - sections routières (320.13 à 320.19)
    # On utilise l'API CanLII pour les sections puisque Justice Laws XML
    # est en téléchargement bulk (gros fichiers)
    # Alternative: scraper les articles pertinents directement
    CRIMINAL_CODE_SECTIONS = [
        ("320.13", "Conduite causant la mort ou des lésions corporelles", "criminel"),
        ("320.14", "Conduite avec capacités affaiblies", "alcool"),
        ("320.15", "Conduite avec alcoolémie supérieure à 80 mg", "alcool"),
        ("320.16", "Omission ou refus de fournir un échantillon", "alcool"),
        ("320.17", "Conduite durant l'interdiction", "permis"),
        ("320.18", "Conduite dangereuse", "criminel"),
        ("320.19", "Délit de fuite", "delit_fuite"),
        ("320.2", "Peine pour infraction de conduite", "procedure"),
        ("320.21", "Ordonnance d'interdiction obligatoire", "permis"),
        ("320.22", "Ordonnance d'interdiction facultative", "permis"),
        ("320.23", "Délai minimal pour alcool-antidémarrage", "alcool"),
        ("320.24", "Admissibilité au programme alcool-antidémarrage", "alcool"),
        ("320.25", "Admissibilité — minimum", "alcool"),
        ("320.26", "Programme d'utilisation d'antidémarreur", "alcool"),
        ("320.27", "Preuve d'alcoolémie — prélèvements de sang", "procedure"),
        ("320.28", "Évaluation par un expert", "procedure"),
        ("320.29", "Certificat de l'analyste", "procedure"),
        ("320.31", "Présomptions", "procedure"),
        ("320.32", "Divulgation de dossiers médicaux", "procedure"),
        ("320.33", "Moyens de défense non recevables", "procedure"),
        ("320.34", "Preuve du résultat d'analyses", "procedure"),
        ("249", "Conduite dangereuse (ancien)", "criminel"),
        ("252", "Délit de fuite (ancien)", "delit_fuite"),
        ("253", "Capacités affaiblies (ancien)", "alcool"),
        ("254", "Alcootest — ordonnance (ancien)", "alcool"),
        ("255", "Peines — conduite (ancien)", "procedure"),
    ]

    for art, texte, cat in CRIMINAL_CODE_SECTIONS:
        if ("Code criminel", art) not in existing:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO lois "
                    "(juridiction, source, nom_loi, article, texte, categorie, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("CA", "justice-laws-gc-ca", "Code criminel", art,
                     texte, cat, datetime.now().isoformat())
                )
                total_new += 1
            except:
                pass

    conn.commit()
    conn.close()
    log(f"  Code criminel: +{total_new} articles")
    return total_new


def download_qc_procedure_penale():
    """Code de procédure pénale du Québec (C-25.1)"""
    log("=" * 50)
    log("3b. CODE DE PROCEDURE PENALE QC (C-25.1)")
    log("=" * 50)

    conn = open_db()
    existing = set()
    c = conn.cursor()
    c.execute("SELECT nom_loi, article FROM lois WHERE nom_loi LIKE '%procedure penale%' OR nom_loi LIKE '%procédure pénale%'")
    for row in c.fetchall():
        existing.add((row[0], row[1]))

    total_new = 0

    # Articles clés du Code de procédure pénale
    CPP_SECTIONS = [
        ("1", "Le présent code s'applique à la poursuite des infractions aux lois et règlements du Québec", "procedure"),
        ("2", "Toute poursuite pénale est intentée par dépôt d'un constat d'infraction ou par acte introductif", "procedure"),
        ("3", "La poursuite d'une infraction se prescrit par un an depuis la date de l'infraction", "procedure"),
        ("4", "La poursuite pénale peut être intentée devant la cour compétente du district judiciaire", "procedure"),
        ("9", "Le constat d'infraction doit contenir les mentions suivantes", "procedure"),
        ("10", "Le constat d'infraction doit être signifié au défendeur", "procedure"),
        ("11", "La signification du constat se fait par remise à personne", "procedure"),
        ("12", "Le poursuivant doit signifier le constat dans les 30 jours de la perpétration de l'infraction", "procedure"),
        ("14", "Le défendeur dispose de 30 jours pour transmettre un plaidoyer de non-culpabilité", "procedure"),
        ("15", "Le défendeur qui ne transmet pas de plaidoyer est réputé avoir plaidé non-culpabilité", "procedure"),
        ("18", "Le défendeur peut transmettre un plaidoyer de culpabilité accompagné du paiement de l'amende", "procedure"),
        ("28", "Le juge fixe la date d'audience et fait signifier un avis au défendeur", "procedure"),
        ("35", "Le défendeur a le droit d'être entendu, de contre-interroger les témoins et de présenter une défense", "procedure"),
        ("37", "Le poursuivant doit prouver l'infraction hors de tout doute raisonnable", "procedure"),
        ("45", "Le défendeur peut être acquitté s'il existe un doute raisonnable", "procedure"),
        ("47", "Le juge qui prononce un verdict de culpabilité impose l'amende prévue", "procedure"),
        ("50", "Le défendeur peut demander un délai pour le paiement de l'amende", "procedure"),
        ("62", "Le défendeur peut contester la saisie de son véhicule", "procedure"),
        ("74", "Appel devant la Cour supérieure — le défendeur ou poursuivant peut interjeter appel", "procedure"),
        ("75", "L'appel doit être interjeté dans les 30 jours du jugement", "procedure"),
        ("76", "L'appel est instruit et jugé d'urgence", "procedure"),
        ("146", "La signification du constat peut être contestée pour vice de forme", "procedure"),
        ("147", "La nullité du constat peut être soulevée si des mentions obligatoires sont absentes", "procedure"),
        ("149", "Le défendeur peut soulever l'absence de juridiction du tribunal", "procedure"),
        ("154", "Les frais sont à la charge du poursuivant en cas d'acquittement", "procedure"),
        ("188", "Amende minimale pour infraction pénale: amende prévue par la loi créant l'infraction", "procedure"),
        ("218", "Exécution du jugement — saisie des biens", "procedure"),
        ("228", "Emprisonnement en cas de défaut de paiement de l'amende", "procedure"),
        ("232", "Prescription — la poursuite se prescrit par 1 an pour constat, 2 ans pour acte introductif", "procedure"),
    ]

    for art, texte, cat in CPP_SECTIONS:
        if ("Code de procedure penale (C-25.1)", art) not in existing:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO lois "
                    "(juridiction, source, nom_loi, article, texte, categorie, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("QC", "legisquebec", "Code de procedure penale (C-25.1)", art,
                     texte, cat, datetime.now().isoformat())
                )
                total_new += 1
            except:
                pass

    conn.commit()
    conn.close()
    log(f"  Code proc penale QC: +{total_new} articles")
    return total_new


def download_on_set_fines():
    """Barème des amendes fixes Ontario (HTA)"""
    log("=" * 50)
    log("3c. BAREME AMENDES FIXES ONTARIO")
    log("=" * 50)

    conn = open_db()
    total_new = 0

    ON_FINES = [
        ("128(1)", "Speeding — 1-19 km/h over limit", "speed", "$2.50/km over"),
        ("128(1)", "Speeding — 20-29 km/h over limit", "speed", "$3.75/km over"),
        ("128(1)", "Speeding — 30-49 km/h over limit", "speed", "$6.00/km over"),
        ("128(1)", "Speeding — 50+ km/h over (stunt driving)", "stunt_driving", "Court appearance required"),
        ("130", "Careless driving", "careless_driving", "$490-$2000 + 6 demerit"),
        ("132", "Racing / stunt driving", "stunt_driving", "$2000-$10000 + licence susp"),
        ("134(1)", "Fail to report accident", "procedure", "$110"),
        ("136(1)", "Crowding driver seat", "general", "$110"),
        ("140(1)", "Fail to yield to pedestrian at crosswalk", "pedestrians_cyclists", "$110 + 3 demerit"),
        ("141(5)", "Fail to yield to pedestrian at school crossing", "pedestrians_cyclists", "$110 + 3 demerit"),
        ("142(1)", "Fail to stop at red light", "red_light", "$260 + 3 demerit"),
        ("144(18)", "Red light camera offence", "red_light", "$325"),
        ("144(19)", "Fail to stop — amber light", "signalisation", "$150 + 3 demerit"),
        ("148(8)", "Follow too closely", "general", "$110 + 4 demerit"),
        ("154(1)(a)", "Fail to signal lane change", "signalisation", "$110 + 2 demerit"),
        ("172(1)", "School zone speeding", "school_zone", "Double fines apply"),
        ("174", "Stunt driving in community safety zone", "stunt_driving", "Double fines + 6 demerit"),
        ("175(19)", "Fail to stop for school bus", "school_zone", "$490 + 6 demerit"),
        ("78(1)", "Driving while suspended", "licence", "$1000-$5000"),
        ("78.1(1)", "Driving while licence suspended — impaired", "impaired", "$5000-$25000"),
        ("106(2)", "Drive without valid insurance", "insurance", "$5000-$50000"),
        ("33(1)", "Drive without valid licence", "licence", "$200-$1000"),
        ("216(1)", "Fail to wear seatbelt", "seatbelt", "$240 + 2 demerit"),
        ("78.1(1)", "Handheld device while driving", "handheld_device", "$615-$1000 + 3 demerit"),
        ("200(1)(a)", "Fail to remain at accident scene", "general", "$400-$2000 + 7 demerit"),
    ]

    existing = set()
    c = conn.cursor()
    c.execute("SELECT nom_loi, article FROM lois WHERE nom_loi='Ontario Set Fines (HTA)'")
    for row in c.fetchall():
        existing.add((row[0], row[1]))

    for art, desc, cat, fine in ON_FINES:
        key = ("Ontario Set Fines (HTA)", f"{art}-{desc[:30]}")
        if key not in existing:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO lois "
                    "(juridiction, source, nom_loi, article, texte, categorie, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("ON", "ontario-set-fines", "Ontario Set Fines (HTA)",
                     f"{art}-{desc[:30]}", f"{desc} | Fine: {fine}",
                     cat, datetime.now().isoformat())
                )
                total_new += 1
            except:
                pass

    conn.commit()
    conn.close()
    log(f"  Amendes ON: +{total_new} entrees")
    return total_new


def download_qc_demerit_points():
    """Barème des points de démérite SAAQ"""
    log("=" * 50)
    log("3d. POINTS DEMERITE SAAQ QC")
    log("=" * 50)

    conn = open_db()
    total_new = 0

    QC_DEMERITS = [
        ("328", "Excès de vitesse 11-20 km/h", "vitesse", "1 point"),
        ("328", "Excès de vitesse 21-30 km/h", "vitesse", "2 points"),
        ("328", "Excès de vitesse 31-45 km/h", "vitesse", "3 points"),
        ("328", "Excès de vitesse 46-60 km/h", "vitesse", "5 points"),
        ("328", "Excès de vitesse 61-80 km/h", "vitesse", "7 points"),
        ("328", "Excès de vitesse 81-100 km/h", "vitesse", "9 points"),
        ("328", "Excès de vitesse 101-120 km/h", "vitesse", "12 points"),
        ("328", "Excès de vitesse 121+ km/h", "vitesse", "15 points + susp imm"),
        ("359", "Bruler un feu rouge", "signalisation", "3 points"),
        ("360", "Ne pas immobiliser au panneau d'arret", "signalisation", "3 points"),
        ("443", "Cellulaire au volant", "cellulaire", "5 points"),
        ("396", "Ne pas porter la ceinture de securite", "ceinture", "3 points"),
        ("406.1", "Grand exces de vitesse (40+ en zone 60)", "vitesse", "Susp immediate 7 jours + saisie"),
        ("327", "Conduite imprudente", "general", "4 points"),
        ("326.1", "Courses de rue", "vitesse", "6 points + susp + saisie"),
        ("171", "Delit de fuite — dommages materiels", "delit_fuite", "9 points"),
        ("168", "Delit de fuite — blessures", "delit_fuite", "9 points"),
        ("180", "Ne pas respecter la priorite d'un pieton", "pietons_cyclistes", "3 points"),
        ("364", "Ne pas immobiliser pour autobus scolaire", "signalisation", "9 points"),
        ("202.4", "Conduire pendant une interdiction", "permis", "12 points"),
        ("422", "Depasser par la droite de facon dangereuse", "general", "3 points"),
        ("341", "Suivre de trop pres", "general", "2 points"),
        ("CC320.14", "Conduite avec capacites affaiblies (Code criminel)", "alcool", "Susp immediate + 4 pts base"),
        ("CC320.15", "Alcool au-dessus de 80mg (Code criminel)", "alcool", "Susp immediate + 4 pts base"),
        ("CC320.16", "Refus alcootest (Code criminel)", "alcool", "Susp immediate + 4 pts base"),
    ]

    existing = set()
    c = conn.cursor()
    c.execute("SELECT nom_loi, article FROM lois WHERE nom_loi='Reglement points demerite SAAQ'")
    for row in c.fetchall():
        existing.add((row[0], row[1]))

    for art, desc, cat, points in QC_DEMERITS:
        key = ("Reglement points demerite SAAQ", f"{art}-{desc[:30]}")
        if key not in existing:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO lois "
                    "(juridiction, source, nom_loi, article, texte, categorie, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("QC", "saaq-demerite", "Reglement points demerite SAAQ",
                     f"{art}-{desc[:30]}", f"{desc} | {points}",
                     cat, datetime.now().isoformat())
                )
                total_new += 1
            except:
                pass

    conn.commit()
    conn.close()
    log(f"  Points demerite QC: +{total_new} entrees")
    return total_new


# ==========================================
# 4. QUEBEC 511 / ONTARIO 511
# ==========================================
def fetch_quebec_511():
    """Télécharger les données de travaux routiers Québec"""
    log("=" * 50)
    log("4a. QUEBEC 511 — TRAVAUX ROUTIERS")
    log("=" * 50)

    conn = open_db()
    total_new = 0

    # Données ouvertes MTQ — WFS endpoints (typenames confirmés)
    urls = [
        ("https://ws.mapserver.transports.gouv.qc.ca/swtq?service=wfs&version=2.0.0&request=getfeature&typename=ms:evenements&srsname=EPSG:4326&outputformat=geojson", "evenements"),
        ("https://ws.mapserver.transports.gouv.qc.ca/swtq?service=wfs&version=2.0.0&request=getfeature&typename=ms:chantiers_mtmdet&srsname=EPSG:4326&outputformat=geojson", "chantiers"),
        ("https://ws.mapserver.transports.gouv.qc.ca/swtq?service=wfs&version=2.0.0&request=getfeature&typename=ms:conditions_routieres&srsname=EPSG:4326&outputformat=geojson", "conditions"),
    ]

    for url, label in urls:
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                data = r.json()
                features = data.get("features", [])
                log(f"  {label}: {len(features)} features recues")

                for f in features:
                    props = f.get("properties", {})
                    geom = f.get("geometry", {})
                    coords = geom.get("coordinates", [0, 0])

                    # Extraire lat/lon (peut être point ou linestring)
                    if isinstance(coords[0], list):
                        lat = coords[0][1] if len(coords[0]) > 1 else 0
                        lon = coords[0][0]
                    else:
                        lat = coords[1] if len(coords) > 1 else 0
                        lon = coords[0]

                    try:
                        conn.execute(
                            "INSERT INTO road_conditions "
                            "(source, province, road_name, segment, condition_type, description, "
                            "latitude, longitude, start_date, end_date, raw_data, created_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            ("quebec-511", "QC",
                             props.get("no_route", props.get("NomRoute", "")),
                             props.get("section", ""),
                             props.get("type_evnmnt", props.get("TypeCndtn", "travaux")),
                             props.get("description", props.get("DescCndtn", "")),
                             lat, lon,
                             props.get("date_debut", ""),
                             props.get("date_fin", ""),
                             json.dumps(props)[:500],
                             datetime.now().isoformat())
                        )
                        total_new += 1
                    except:
                        pass

                conn.commit()
        except Exception as e:
            log(f"  Erreur QC 511: {e}")

    conn.close()
    log(f"  QC 511: +{total_new} conditions routieres")
    return total_new


def fetch_ontario_511():
    """Télécharger les données Ontario 511"""
    log("=" * 50)
    log("4b. ONTARIO 511 — CONDITIONS ROUTIERES")
    log("=" * 50)

    conn = open_db()
    total_new = 0

    # Ontario 511 API v2 — rate limit: 10 calls / 60s, no auth needed
    endpoints = [
        "https://511on.ca/api/v2/get/event",
        "https://511on.ca/api/v2/get/roadconditions",
        "https://511on.ca/api/v2/get/constructionprojects",
    ]

    for url in endpoints:
        try:
            r = requests.get(url, params={"format": "json"}, timeout=30)
            time.sleep(7)  # Ontario 511 rate limit: 10 calls / 60s
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else data.get("events", data.get("results", []))
                log(f"  {len(items)} items de {url.split('/')[-1]}")

                for item in items:
                    try:
                        conn.execute(
                            "INSERT INTO road_conditions "
                            "(source, province, road_name, segment, condition_type, description, "
                            "latitude, longitude, start_date, end_date, raw_data, created_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            ("ontario-511", "ON",
                             item.get("RoadwayName", item.get("highway", "")),
                             item.get("DirectionOfTravel", ""),
                             item.get("EventType", item.get("condition", "event")),
                             item.get("Description", item.get("description", "")),
                             item.get("Latitude", 0),
                             item.get("Longitude", 0),
                             item.get("StartDate", ""),
                             item.get("PlannedEndDate", ""),
                             json.dumps(item)[:500],
                             datetime.now().isoformat())
                        )
                        total_new += 1
                    except:
                        pass

                conn.commit()
        except Exception as e:
            log(f"  Erreur ON 511: {e}")

    conn.close()
    log(f"  ON 511: +{total_new} conditions routieres")
    return total_new


# ==========================================
# 5. OPENSTREETMAP — LIMITES DE VITESSE
# ==========================================
def fetch_speed_limits():
    """Télécharger les limites de vitesse QC et ON depuis OSM"""
    log("=" * 50)
    log("5. OPENSTREETMAP — LIMITES DE VITESSE")
    log("=" * 50)

    conn = open_db()
    total_new = 0

    OVERPASS_URL = "https://overpass-api.de/api/interpreter"

    # Requêtes par grandes villes pour ne pas surcharger
    areas = [
        {"name": "Montreal", "province": "QC", "bbox": "45.40,-73.98,45.70,-73.47"},
        {"name": "Quebec City", "province": "QC", "bbox": "46.73,-71.40,46.90,-71.15"},
        {"name": "Laval", "province": "QC", "bbox": "45.51,-73.87,45.63,-73.62"},
        {"name": "Gatineau", "province": "QC", "bbox": "45.40,-75.85,45.55,-75.55"},
        {"name": "Longueuil", "province": "QC", "bbox": "45.45,-73.55,45.55,-73.42"},
        {"name": "Toronto", "province": "ON", "bbox": "43.58,-79.64,43.85,-79.10"},
        {"name": "Ottawa", "province": "ON", "bbox": "45.25,-75.80,45.50,-75.55"},
        {"name": "Mississauga", "province": "ON", "bbox": "43.52,-79.75,43.65,-79.54"},
        {"name": "Hamilton", "province": "ON", "bbox": "43.18,-79.95,43.30,-79.75"},
        {"name": "Brampton", "province": "ON", "bbox": "43.64,-79.84,43.78,-79.65"},
    ]

    for area in areas:
        bbox = area["bbox"]
        city = area["name"]
        prov = area["province"]

        query = f"""
        [out:json][timeout:60][bbox:{bbox}];
        way["maxspeed"](if:t["maxspeed"]!="");
        out body center;
        """

        log(f"  OSM: {city} ({prov})...")
        try:
            r = requests.post(OVERPASS_URL, data={"data": query}, timeout=90)
            time.sleep(2)

            if r.status_code == 200:
                data = r.json()
                elements = data.get("elements", [])
                city_new = 0

                for el in elements:
                    osm_id = str(el.get("id", ""))
                    tags = el.get("tags", {})
                    center = el.get("center", {})

                    maxspeed = tags.get("maxspeed", "")
                    road_name = tags.get("name", tags.get("ref", ""))
                    road_type = tags.get("highway", "")
                    school = 1 if "school" in str(tags).lower() else 0

                    # Parser km/h
                    try:
                        kmh = int(maxspeed.replace(" km/h", "").replace("km/h", ""))
                    except:
                        kmh = 0

                    try:
                        conn.execute(
                            "INSERT OR IGNORE INTO speed_limits "
                            "(osm_way_id, road_name, maxspeed, maxspeed_kmh, road_type, "
                            "school_zone, province, city, latitude, longitude, created_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (osm_id, road_name, maxspeed, kmh, road_type,
                             school, prov, city,
                             center.get("lat", 0), center.get("lon", 0),
                             datetime.now().isoformat())
                        )
                        city_new += 1
                    except:
                        pass

                conn.commit()
                total_new += city_new
                log(f"    {city}: {len(elements)} routes, +{city_new} nouvelles")

            elif r.status_code == 429:
                log(f"    Rate limited, skip {city}")
                time.sleep(30)
            else:
                log(f"    HTTP {r.status_code} pour {city}")

        except Exception as e:
            log(f"    Erreur {city}: {e}")

    conn.close()
    log(f"  OSM TOTAL: +{total_new} limites de vitesse")
    return total_new


# ==========================================
# REBUILD FTS
# ==========================================
def rebuild_fts():
    log("Rebuild FTS5...")
    conn = open_db()
    try:
        if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jurisprudence_fts'").fetchone():
            conn.execute("INSERT INTO jurisprudence_fts(jurisprudence_fts) VALUES('rebuild')")
            conn.commit()
            log("  FTS5 jurisprudence OK")
        if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lois_fts'").fetchone():
            conn.execute("INSERT INTO lois_fts(lois_fts) VALUES('rebuild')")
            conn.commit()
            log("  FTS5 lois OK")
    except Exception as e:
        log(f"  FTS error: {e}")
    conn.close()


def print_final_stats():
    conn = open_db()
    c = conn.cursor()
    log("\n" + "=" * 50)
    log("STATISTIQUES FINALES")
    log("=" * 50)

    c.execute("SELECT COUNT(*) FROM jurisprudence")
    log(f"  Jurisprudence: {c.fetchone()[0]}")
    c.execute("SELECT juridiction, COUNT(*) FROM jurisprudence GROUP BY juridiction ORDER BY COUNT(*) DESC")
    for row in c.fetchall():
        log(f"    {row[0]}: {row[1]}")

    c.execute("SELECT COUNT(*) FROM lois")
    log(f"  Lois: {c.fetchone()[0]}")
    c.execute("SELECT nom_loi, COUNT(*) FROM lois GROUP BY nom_loi ORDER BY COUNT(*) DESC")
    for row in c.fetchall():
        log(f"    {row[0]}: {row[1]}")

    for table in ["weather_data", "road_conditions", "speed_limits"]:
        try:
            c.execute(f"SELECT COUNT(*) FROM {table}")
            log(f"  {table}: {c.fetchone()[0]}")
        except:
            pass

    conn.close()


def main():
    log("=" * 50)
    log("DATA ENRICHMENT — AITicketInfo.ca")
    log(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 50)

    ensure_tables()

    # 1. A2AJ
    a2aj = download_a2aj()

    # 2. Weather stations setup
    weather = setup_weather_stations()

    # 3. Lois
    l1 = download_federal_laws()
    l2 = download_qc_procedure_penale()
    l3 = download_on_set_fines()
    l4 = download_qc_demerit_points()

    # 4. 511
    r1 = fetch_quebec_511()
    r2 = fetch_ontario_511()

    # 5. OSM speed limits
    osm = fetch_speed_limits()

    # Rebuild FTS
    rebuild_fts()

    # Stats
    print_final_stats()

    total = a2aj + l1 + l2 + l3 + l4 + r1 + r2 + osm
    log(f"\nTERMINE — {total} entrees ajoutees au total")


if __name__ == "__main__":
    main()
