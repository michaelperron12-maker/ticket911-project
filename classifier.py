#!/usr/bin/env python3
"""
aiticketinfo-classifier — Agent 24/7 classification et embeddings
Tourne en continu, prend son temps, corrige les donnees en boucle.
- Remplit embeddings manquants (via Fireworks qwen3-embedding-8b)
- Reclassifie database_id, resultat, est_ticket_related (mots-cles)
- Classification IA profonde: type_infraction, moyens_defense, article_csr (Phase 4)
- Sleep entre chaque operation pour pas surcharger
- Recommence une fois fini pour les nouveaux imports
Mis a jour 17 fev 2026 — ajout Phase 4 IA + modeles stables
"""

import os
import sys
import re
import time
import json
import signal
import psycopg2
import psycopg2.extras
import httpx
from datetime import datetime

# ══════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════
sys.path.insert(0, "/var/www/aiticketinfo")

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

PG_CONFIG = {
    'host': os.environ.get('TICKETS_DB_HOST', '172.18.0.3'),
    'port': int(os.environ.get('TICKETS_DB_PORT', 5432)),
    'dbname': os.environ.get('TICKETS_DB_NAME', 'tickets_qc_on'),
    'user': os.environ.get('TICKETS_DB_USER', 'ticketdb_user'),
    'password': os.environ.get('TICKETS_DB_PASS', 'Tk911PgSecure2026'),
}

LOG_FILE = "/var/www/aiticketinfo/logs/classifier.log"
STATE_FILE = "/var/www/aiticketinfo/db/classifier_phase4_state.json"
SLEEP_BETWEEN = 0.5      # secondes entre chaque dossier (etait 1)
SLEEP_BATCH = 3          # secondes entre chaque batch (etait 5)
SLEEP_CYCLE = 20         # secondes entre chaque cycle complet (etait 60)
BATCH_SIZE = 50          # dossiers par batch embedding
PHASE4_BATCH = 30        # dossiers par cycle Phase 4 IA (etait 10)
EMBEDDING_ENABLED = True
PHASE4_ENABLED = True    # Classification IA profonde

# Fireworks API — modeles stables testes 17 fev 2026
FW_KEY = os.environ.get("FIREWORKS_API_KEY", "fw_CbsGnsaL5NSi4wgasWhjtQ")
FW_URL = "https://api.fireworks.ai/inference/v1/chat/completions"
FW_MODELS = [
    "accounts/fireworks/models/deepseek-v3p2",     # #1 rapide+intelligent
    "accounts/fireworks/models/kimi-k2p5",          # #2 fallback
    "accounts/fireworks/models/minimax-m2p1",       # #3 fallback
]
FW_TIMEOUT = 20.0

# Groq API — fallback gratuit si Fireworks fail (ne pas surutiliser)
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

# Phase 4 prompt
PHASE4_PROMPT = '''Analyse cette decision judiciaire quebecoise/canadienne.
Reponds UNIQUEMENT en JSON valide (pas de texte avant/apres):
{{"article_csr":"str ou null","type_infraction":"exces_vitesse|feu_rouge|panneau_arret|cellulaire|ceinture|conduite_dangereuse|alcool_volant|depassement_interdit|virage_interdit|delit_fuite|distraction|stationnement|autre_csr|non_routier","resultat":"acquitte|coupable|reduit|rejete","moyens_defense":["str"],"motifs_juge":"1 phrase","resume":"2 phrases max"}}

DECISION:
{texte}

JSON:'''

# Mapping citation → database_id
CITATION_TO_DB = {
    "QCCM": "qccm", "QCCQ": "qccq", "QCCS": "qccs", "QCCA": "qcca",
    "QCCTQ": "qcctq", "QCTAQ": "qctaq",
    "ONCJ": "oncj", "ONSCDC": "onscdc", "ONCA": "onca",
    "ONSC": "onsc", "ONSCTD": "onsctd",
    "FC": "fc", "FCA": "fca", "SCC": "scc",
    "BCCA": "bcca", "BCSC": "bcsc", "BCPC": "bcpc",
    "ABCA": "abca", "ABQB": "abqb", "ABPC": "abpc",
    "SKCA": "skca", "SKQB": "skqb", "SKPC": "skpc",
    "MBCA": "mbca", "MBQB": "mbqb", "MBPC": "mbpc",
    "NBCA": "nbca", "NBQB": "nbqb",
    "NSCA": "nsca", "NSSC": "nssc",
}

RESULTAT_KW = {
    "acquitte": [
        "acquitté", "acquitte", "acquitted", "not guilty", "non coupable",
        "accueilli", "accueillie", "allowed", "appeal allowed",
        "conviction overturned", "conviction set aside", "verdict overturned",
        "new trial ordered", "charges withdrawn", "charges stayed",
        "stay of proceedings", "absous", "libéré", "libere",
        "accusation retirée", "accusation retiree", "withdrawn",
    ],
    "coupable": [
        "coupable", "guilty", "condamné", "condamne", "convicted",
        "appeal dismissed", "conviction upheld", "conviction confirmed",
        "sentence upheld", "found guilty", "plea guilty", "plaide coupable",
        "plaidoyer de culpabilité", "sentence imposed", "sentenced to",
        "fine imposed", "amende imposée", "imprisonment", "incarceration",
        "detention", "probation", "sursis",
    ],
    "rejete": [
        "rejeté", "rejete", "rejected", "dismissed", "irrecevable", "struck",
        "application dismissed", "motion dismissed", "leave denied",
        "permission denied", "demande rejetée", "requete rejetee",
        "sans suite", "declined", "refused",
    ],
    "reduit": [
        "réduit", "reduit", "reduced", "lesser", "amende réduite",
        "sentence reduced", "fine reduced", "lesser offence",
        "lesser included", "peine reduite", "diminué", "diminue",
        "conditional discharge", "absolution conditionnelle",
        "absolute discharge", "absolution inconditionnelle",
    ],
}

TRAFFIC_KW = [
    "vitesse", "excès", "exces", "radar", "cinémomètre", "cinematometre",
    "cellulaire", "téléphone", "telephone", "portable",
    "alcool", "alcootest", "ivresse", "facultés", "facultes",
    "feu rouge", "stop", "arrêt", "arret", "ceinture",
    "conduite dangereuse", "imprudent", "délit de fuite",
    "suspension", "permis", "constat", "infraction",
    "sécurité routière", "securite routiere", "CSR", "code de la route",
    "signalisation", "calibration", "contestation", "contravention",
    "speed", "speeding", "lidar", "cell phone", "handheld", "distracted",
    "alcohol", "impaired", "dui", "dwi", "breathalyzer",
    "red light", "stop sign", "seatbelt", "careless driving",
    "dangerous driving", "stunt driving", "highway traffic", "HTA", "traffic", "POA",
]

running = True


def signal_handler(sig, frame):
    global running
    log("Signal recu, arret en cours...")
    running = False


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def get_conn():
    return psycopg2.connect(**PG_CONFIG)


def extract_db_id(citation):
    if not citation:
        return None
    m = re.search(r'\d{4}\s+([A-Z]+)\s+\d+', citation)
    if m:
        code = m.group(1)
        return CITATION_TO_DB.get(code, code.lower())
    return None


def detect_resultat(titre, resume=""):
    t = f"{titre or ''} {resume or ''}".lower()
    for res, kws in RESULTAT_KW.items():
        for kw in kws:
            if kw.lower() in t:
                return res
    return None


def is_traffic(titre, resume=""):
    t = f"{titre or ''} {resume or ''}".lower()
    return any(kw.lower() in t for kw in TRAFFIC_KW)


# ══════════════════════════════════════════════════════════
# CLASSIFY SIMPLE: database_id, resultat, est_ticket_related
# ══════════════════════════════════════════════════════════

def classify_pass(conn):
    cur = conn.cursor()
    fixed = {"database_id": 0, "resultat": 0, "ticket_related": 0}

    cur.execute("SELECT id, citation FROM jurisprudence WHERE database_id IS NULL OR database_id = ''")
    for row_id, citation in cur.fetchall():
        if not running: break
        db_id = extract_db_id(citation)
        if db_id:
            cur.execute("UPDATE jurisprudence SET database_id = %s WHERE id = %s", (db_id, row_id))
            fixed["database_id"] += 1
    conn.commit()

    cur.execute("""SELECT id, titre, resume FROM jurisprudence
                   WHERE resultat IS NULL OR resultat = '' OR resultat = 'inconnu'""")
    for row_id, titre, resume in cur.fetchall():
        if not running: break
        r = detect_resultat(titre, resume)
        if r:
            cur.execute("UPDATE jurisprudence SET resultat = %s WHERE id = %s", (r, row_id))
            fixed["resultat"] += 1
    conn.commit()

    cur.execute("""SELECT id, titre, resume FROM jurisprudence
                   WHERE est_ticket_related = false OR est_ticket_related IS NULL""")
    for row_id, titre, resume in cur.fetchall():
        if not running: break
        if is_traffic(titre, resume):
            cur.execute("UPDATE jurisprudence SET est_ticket_related = true WHERE id = %s", (row_id,))
            fixed["ticket_related"] += 1
    conn.commit()
    cur.close()
    return fixed


# ══════════════════════════════════════════════════════════
# PHASE 4: Classification IA profonde (type_infraction etc.)
# ══════════════════════════════════════════════════════════

def truncate_text(t):
    if not t: return t
    for m in ["[1]", "MOTIFS", "JUGEMENT", "REASONS", "DISPOSITIF"]:
        i = t.find(m)
        if 0 < i < 2000:
            t = t[i:]
            break
    return t[:3500]


def get_case_text(case):
    tc = case.get("texte_complet") or ""
    if tc and len(tc) >= 100:
        return truncate_text(tc), "texte"
    parts = []
    for f in ["titre", "citation"]:
        v = case.get(f)
        if v: parts.append(v)
    ria = case.get("resume_ia") or ""
    res = case.get("resume") or ""
    if ria and len(ria) > len(res):
        parts.append(ria)
    elif res:
        parts.append(res)
    mc = case.get("mots_cles")
    if mc and isinstance(mc, list):
        parts.append("Mots-cles: " + ", ".join(mc[:10]))
    c = "\n".join(parts)
    return (c, "resume") if len(c) > 40 else (None, None)


def call_fireworks(texte):
    for model in FW_MODELS:
        try:
            resp = httpx.post(FW_URL,
                headers={"Authorization": f"Bearer {FW_KEY}", "Content-Type": "application/json"},
                json={"model": model,
                      "messages": [{"role": "user", "content": PHASE4_PROMPT.format(texte=texte)}],
                      "temperature": 0.0, "max_tokens": 600},
                timeout=httpx.Timeout(FW_TIMEOUT, connect=8.0))
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                result = extract_json(content)
                if result:
                    return result
        except httpx.TimeoutException:
            pass
        except Exception:
            pass
        time.sleep(0.5)
    # Fallback Groq (gratuit) si tous les modeles Fireworks ont fail
    if GROQ_KEY:
        try:
            resp = httpx.post(GROQ_URL,
                headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                json={"model": GROQ_MODEL,
                      "messages": [{"role": "user", "content": PHASE4_PROMPT.format(texte=texte)}],
                      "temperature": 0.0, "max_tokens": 600},
                timeout=httpx.Timeout(15.0, connect=8.0))
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                result = extract_json(content)
                if result:
                    return result
        except Exception:
            pass
    return None


def extract_json(content):
    if not content: return None
    start = content.find("{")
    if start < 0: return None
    end = content.rfind("}")
    if end <= start:
        s = content[start:]
        if s.count('"') % 2 == 1: s += '"'
        s += "]" * max(0, s.count("[") - s.count("]"))
        s += "}" * max(0, s.count("{") - s.count("}"))
        try: return json.loads(s)
        except Exception: return None
    try: return json.loads(content[start:end+1])
    except json.JSONDecodeError:
        s = content[start:end+1]
        last = s.rfind(",")
        if last > 0:
            s2 = s[:last]
            s2 += "]" * max(0, s2.count("[") - s2.count("]"))
            s2 += "}" * max(0, s2.count("{") - s2.count("}"))
            try: return json.loads(s2)
            except Exception: pass
    return None


def norm_resultat(r):
    if not r: return None
    r = str(r).lower().strip()
    if any(w in r for w in ["acquit", "non coupable", "not guilty"]): return "acquitte"
    if any(w in r for w in ["coupable", "guilty", "condamn", "convicted"]): return "coupable"
    if any(w in r for w in ["redui", "rédui", "reduced", "diminu"]): return "reduit"
    if any(w in r for w in ["rejet", "dismiss", "denied", "refus"]): return "rejete"
    if any(w in r for w in ["retir", "withdraw", "abandon"]): return "retire"
    if r in ("acquitte", "coupable", "reduit", "rejete", "retire"): return r
    return r[:30]


def phase4_pass(conn):
    if not PHASE4_ENABLED:
        return 0, 0

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, texte_complet, resume, resume_ia, titre, citation, mots_cles
        FROM jurisprudence
        WHERE classifie = false
          AND (texte_complet IS NOT NULL AND LENGTH(texte_complet) >= 100
               OR resume IS NOT NULL AND LENGTH(resume) > 50
               OR resume_ia IS NOT NULL AND LENGTH(resume_ia) > 50)
        ORDER BY
            CASE WHEN LOWER(COALESCE(tribunal,'')) = 'qccm' THEN 1
                 WHEN LOWER(COALESCE(tribunal,'')) = 'qccq' THEN 2 ELSE 4 END,
            id
        LIMIT %s
    """, (PHASE4_BATCH,))
    cases = cur.fetchall()

    if not cases:
        cur.close()
        return 0, 0

    ok = 0
    fail = 0
    for case in cases:
        if not running: break
        try:
            texte, src = get_case_text(case)
            if not texte:
                # Pas assez de texte — marquer comme classifie pour pas retenter
                cur.execute("UPDATE jurisprudence SET classifie=true, type_infraction='non_routier', confiance_classif=0.1 WHERE id=%s", (case["id"],))
                conn.commit()
                fail += 1
                continue

            result = call_fireworks(texte)
            time.sleep(0.3)

            if not result:
                fail += 1
                continue

            # Normaliser les champs
            for sf in ["article_csr", "type_infraction", "sous_type", "zone_type", "resultat", "motifs_juge", "resume"]:
                v = result.get(sf)
                if isinstance(v, list): result[sf] = v[0] if v else None
                elif isinstance(v, (int, float)): result[sf] = str(v)

            result["resultat"] = norm_resultat(result.get("resultat"))

            ti = result.get("type_infraction", "")
            if isinstance(ti, list): ti = ti[0] if ti else ""
            if ti and isinstance(ti, str):
                ti = ti.lower().strip()
                # Rejeter si c'est la liste complète (bug connu)
                if "|" in ti:
                    ti = "autre_csr"
                result["type_infraction"] = ti

            for f in ["moyens_defense", "arguments_gagnants", "arguments_rejetes"]:
                v = result.get(f)
                if not isinstance(v, list): result[f] = [v] if v else []

            conf = 0.5
            if result.get("article_csr") and result.get("type_infraction"): conf = 0.8
            if src == "texte": conf = min(1.0, conf + 0.15)

            cur.execute("""
                UPDATE jurisprudence SET
                    article_csr = COALESCE(%s, article_csr),
                    type_infraction = %s,
                    sous_type = COALESCE(%s, sous_type),
                    zone_type = COALESCE(%s, zone_type),
                    moyens_defense = %s,
                    arguments_gagnants = COALESCE(%s, arguments_gagnants),
                    arguments_rejetes = COALESCE(%s, arguments_rejetes),
                    motifs_juge = COALESCE(%s, motifs_juge),
                    resultat = COALESCE(%s, resultat),
                    resume_ia = COALESCE(resume_ia, %s),
                    classifie = true,
                    confiance_classif = %s
                WHERE id = %s
            """, (
                result.get("article_csr"), result.get("type_infraction"),
                result.get("sous_type"), result.get("zone_type"),
                result.get("moyens_defense") or [],
                result.get("arguments_gagnants") or [],
                result.get("arguments_rejetes") or [],
                result.get("motifs_juge"),
                result.get("resultat"),
                result.get("resume"),
                conf, case["id"],
            ))
            conn.commit()
            ok += 1

        except Exception as e:
            log(f"    [!] Phase4 id={case['id']}: {str(e)[:60]}")
            try:
                conn.rollback()
            except: pass
            fail += 1

    cur.close()
    return ok, fail


def save_phase4_state(ok_total, fail_total, remaining):
    try:
        state = {}
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                state = json.load(f)
        state["last_run"] = datetime.now().isoformat()
        state["ok_total"] = state.get("ok_total", 0) + ok_total
        state["fail_total"] = state.get("fail_total", 0) + fail_total
        state["remaining"] = remaining
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════
# EMBEDDINGS: remplir les manquants
# ══════════════════════════════════════════════════════════

def get_embedding_service():
    try:
        from embedding_service import embedding_service
        return embedding_service
    except Exception as e:
        log(f"  Embedding service indisponible: {e}")
        return None


def build_embed_text(row):
    parts = []
    if row.get("titre"): parts.append(row["titre"])
    if row.get("citation"): parts.append(row["citation"])
    if row.get("database_id"): parts.append(f"Tribunal: {row['database_id'].upper()}")
    if row.get("resume"): parts.append(row["resume"])
    if row.get("mots_cles"): parts.append(" ".join(row["mots_cles"][:20]))
    if row.get("resultat"): parts.append(f"Resultat: {row['resultat']}")
    if row.get("province"): parts.append(f"Province: {row['province']}")
    return " ".join(parts)[:8000]


def embedding_pass(conn):
    if not EMBEDDING_ENABLED:
        return 0

    svc = get_embedding_service()
    if not svc:
        return 0

    cur = conn.cursor()
    cur.execute("""SELECT id, titre, citation, database_id, resume,
                          mots_cles, resultat, province
                   FROM jurisprudence WHERE embedding IS NULL LIMIT %s""", (BATCH_SIZE,))
    columns = [d[0] for d in cur.description]
    rows = [dict(zip(columns, r)) for r in cur.fetchall()]

    if not rows:
        cur.close()
        return 0

    fixed = 0
    for row in rows:
        if not running: break
        try:
            text = build_embed_text(row)
            if not text.strip(): continue
            emb = svc.embed_single(text)
            if emb and len(emb) > 0:
                cur.execute("UPDATE jurisprudence SET embedding = %s::vector WHERE id = %s", (str(emb), row["id"]))
                conn.commit()
                fixed += 1
                time.sleep(SLEEP_BETWEEN)
        except Exception as e:
            conn.rollback()
            log(f"  Embedding erreur id={row['id']}: {e}")
            time.sleep(5)
    cur.close()
    return fixed


# ══════════════════════════════════════════════════════════
# STATS
# ══════════════════════════════════════════════════════════

def get_stats(conn):
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM jurisprudence")
    total = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM jurisprudence WHERE embedding IS NULL")
    no_embed = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM jurisprudence WHERE database_id IS NULL OR database_id = ''")
    no_db = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM jurisprudence WHERE resultat IS NULL OR resultat = '' OR resultat = 'inconnu'")
    no_res = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM jurisprudence WHERE classifie = false")
    no_class = cur.fetchone()[0]
    cur.close()
    return {"total": total, "no_embed": no_embed, "no_db_id": no_db, "no_resultat": no_res, "no_classif": no_class}


# ══════════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════════

def main():
    log("=" * 60)
    log("AITICKETINFO CLASSIFIER v2 — Demarrage")
    log("  Mode: 24/7 continu")
    log(f"  Embeddings: {'ON' if EMBEDDING_ENABLED else 'OFF'}")
    log(f"  Phase 4 IA: {'ON' if PHASE4_ENABLED else 'OFF'} ({PHASE4_BATCH}/cycle)")
    log(f"  Modeles: {', '.join(m.split('/')[-1] for m in FW_MODELS)}")
    log(f"  Cycle: {SLEEP_CYCLE}s")
    log("=" * 60)

    cycle = 0
    p4_ok_total = 0
    p4_fail_total = 0

    while running:
        cycle += 1
        try:
            conn = get_conn()
            stats = get_stats(conn)
            log(f"\n--- Cycle {cycle} ---")
            log(f"  DB: {stats['total']} total | {stats['no_embed']} sans embed | "
                f"{stats['no_db_id']} sans tribunal | {stats['no_resultat']} sans resultat | "
                f"{stats['no_classif']} non classifies")

            # 1. Classification simple (mots-cles)
            if stats["no_db_id"] > 0 or stats["no_resultat"] > 0:
                log("  Classification mots-cles...")
                fixed = classify_pass(conn)
                if any(v > 0 for v in fixed.values()):
                    log(f"  Corriges: db_id={fixed['database_id']}, "
                        f"resultat={fixed['resultat']}, traffic={fixed['ticket_related']}")

            # 2. Embeddings
            if stats["no_embed"] > 0 and EMBEDDING_ENABLED:
                log(f"  Embeddings ({stats['no_embed']} manquants)...")
                embedded = embedding_pass(conn)
                if embedded > 0:
                    log(f"  {embedded} embeddings crees")

            # 3. Phase 4 — Classification IA profonde
            if stats["no_classif"] > 0 and PHASE4_ENABLED:
                log(f"  Phase 4 IA ({stats['no_classif']} restants)...")
                p4_ok, p4_fail = phase4_pass(conn)
                p4_ok_total += p4_ok
                p4_fail_total += p4_fail
                if p4_ok > 0 or p4_fail > 0:
                    log(f"  Phase4: +{p4_ok} OK, {p4_fail} fail (total: {p4_ok_total} OK)")
                save_phase4_state(p4_ok, p4_fail, stats["no_classif"] - p4_ok)

            conn.close()

        except Exception as e:
            log(f"  ERREUR cycle {cycle}: {e}")
            time.sleep(30)

        if running:
            for _ in range(SLEEP_CYCLE):
                if not running: break
                time.sleep(1)

    log(f"\nAITICKETINFO CLASSIFIER v2 — Arret propre (Phase4: {p4_ok_total} OK)")


if __name__ == "__main__":
    main()
