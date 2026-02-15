#!/usr/bin/env python3
"""
data_repair.py — Auto-correcteur de donnees Ticket911
Corrige: database_id NULL, resultat inconnu, est_ticket_related, embeddings
Cron: 45 1 * * * (apres import 1h00 + embeddings 1h30)
"""

import os
import sys
import re
import time
import json
import psycopg2
from datetime import datetime

# ══════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════
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

LOG_FILE = "/var/www/aiticketinfo/logs/data_repair.log"
STATE_FILE = "/var/www/aiticketinfo/db/data_repair_state.json"

# Mapping citation code → database_id
CITATION_TO_DB = {
    # Quebec
    "QCCM": "qccm", "QCCQ": "qccq", "QCCS": "qccs", "QCCA": "qcca",
    "QCCTQ": "qcctq", "QCTAQ": "qctaq", "QCRPD": "qcrpd",
    # Ontario
    "ONCJ": "oncj", "ONSCDC": "onscdc", "ONCA": "onca",
    "ONSC": "onsc", "ONSCTD": "onsctd",
    # Federal
    "FC": "fc", "FCA": "fca", "SCC": "scc",
    # BC
    "BCCA": "bcca", "BCSC": "bcsc", "BCPC": "bcpc",
    # Alberta
    "ABCA": "abca", "ABQB": "abqb", "ABPC": "abpc",
    # Saskatchewan
    "SKCA": "skca", "SKQB": "skqb", "SKPC": "skpc",
    # Manitoba
    "MBCA": "mbca", "MBQB": "mbqb", "MBPC": "mbpc",
    # New Brunswick
    "NBCA": "nbca", "NBQB": "nbqb",
    # Nova Scotia
    "NSCA": "nsca", "NSSC": "nssc",
}

# Mots-cles pour detecter resultat
RESULTAT_KEYWORDS = {
    "acquitte": [
        "acquitté", "acquitte", "acquitted", "not guilty", "non coupable",
        "accueilli", "accueillie", "allowed", "appeal allowed",
    ],
    "coupable": [
        "coupable", "guilty", "condamné", "condamne", "convicted",
        "rejeté l'appel", "appeal dismissed", "condamnation confirmée",
    ],
    "rejete": [
        "rejeté", "rejete", "rejected", "dismissed", "irrecevable",
        "struck", "quashed",
    ],
    "reduit": [
        "réduit", "reduit", "reduced", "lesser", "moindre",
        "amende réduite", "fine reduced",
    ],
}

# Mots-cles traffic
TRAFFIC_KEYWORDS_FR = [
    "vitesse", "excès", "exces", "radar", "cinémomètre", "cinematometre",
    "cellulaire", "téléphone", "telephone", "portable",
    "alcool", "alcootest", "ivresse", "facultés", "facultes", "capacités",
    "feu rouge", "stop", "arrêt", "arret", "ceinture",
    "conduite dangereuse", "imprudent", "délit de fuite",
    "suspension", "permis", "constat", "infraction",
    "sécurité routière", "securite routiere", "C.S.R.", "CSR",
    "code de la route", "signalisation", "calibration",
    "contestation", "contravention",
]

TRAFFIC_KEYWORDS_EN = [
    "speed", "speeding", "radar", "lidar", "photo radar",
    "cell phone", "cellphone", "handheld", "distracted", "texting",
    "alcohol", "impaired", "dui", "dwi", "breathalyzer", "blood alcohol",
    "red light", "stop sign", "seatbelt", "careless driving",
    "dangerous driving", "stunt driving", "racing",
    "fail to stop", "hit and run", "suspended", "licence",
    "highway traffic", "HTA", "traffic", "provincial offences", "POA",
    "speedo", "calibration", "signage",
]


def log(msg):
    """Log avec timestamp"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def get_conn():
    return psycopg2.connect(**PG_CONFIG)


def extract_database_id(citation):
    """Extraire database_id depuis la citation (ex: '2024 QCCM 1234' → 'qccm')"""
    if not citation:
        return None
    match = re.search(r'\d{4}\s+([A-Z]+)\s+\d+', citation)
    if match:
        code = match.group(1)
        return CITATION_TO_DB.get(code, code.lower())
    return None


def detect_resultat(title, resume=""):
    """Detecter resultat depuis titre + resume"""
    texte = f"{title or ''} {resume or ''}".lower()
    for resultat, keywords in RESULTAT_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in texte:
                return resultat
    return None


def is_traffic_related(title, resume=""):
    """Verifier si un cas est lie au traffic"""
    texte = f"{title or ''} {resume or ''}".lower()
    all_keywords = TRAFFIC_KEYWORDS_FR + TRAFFIC_KEYWORDS_EN
    for kw in all_keywords:
        if kw.lower() in texte:
            return True
    return False


def repair_database_id(conn):
    """Remplir database_id manquants depuis les citations"""
    cur = conn.cursor()
    cur.execute("SELECT id, citation FROM jurisprudence WHERE database_id IS NULL OR database_id = ''")
    rows = cur.fetchall()
    fixed = 0
    for row_id, citation in rows:
        db_id = extract_database_id(citation)
        if db_id:
            cur.execute("UPDATE jurisprudence SET database_id = %s WHERE id = %s", (db_id, row_id))
            fixed += 1
    conn.commit()
    cur.close()
    return fixed, len(rows)


def repair_resultat(conn):
    """Reclassifier resultats inconnus"""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, titre, resume FROM jurisprudence
        WHERE resultat IS NULL OR resultat = '' OR resultat = 'inconnu'
    """)
    rows = cur.fetchall()
    fixed = 0
    for row_id, titre, resume in rows:
        new_resultat = detect_resultat(titre, resume)
        if new_resultat:
            cur.execute("UPDATE jurisprudence SET resultat = %s WHERE id = %s", (new_resultat, row_id))
            fixed += 1
    conn.commit()
    cur.close()
    return fixed, len(rows)


def repair_ticket_related(conn):
    """Reclassifier est_ticket_related"""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, titre, resume FROM jurisprudence
        WHERE est_ticket_related = false OR est_ticket_related IS NULL
    """)
    rows = cur.fetchall()
    fixed = 0
    for row_id, titre, resume in rows:
        if is_traffic_related(titre, resume):
            cur.execute("UPDATE jurisprudence SET est_ticket_related = true WHERE id = %s", (row_id,))
            fixed += 1
    conn.commit()
    cur.close()
    return fixed, len(rows)


def check_tsvector(conn):
    """Verifier l'etat des tsvector (colonnes generees, pas modifiables)"""
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM jurisprudence WHERE tsv_fr IS NULL")
    null_fr = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM jurisprudence WHERE tsv_en IS NULL")
    null_en = cur.fetchone()[0]
    cur.close()
    return null_fr, null_en


def check_data_quality(conn):
    """Rapport qualite donnees"""
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM jurisprudence")
    total = cur.fetchone()[0]

    quality = {"total": total, "fields": {}}
    for col in ['database_id', 'resume', 'titre', 'resultat', 'embedding', 'date_decision']:
        try:
            if col == 'embedding':
                cur.execute(f"SELECT count(*) FROM jurisprudence WHERE {col} IS NULL")
            else:
                cur.execute(f"SELECT count(*) FROM jurisprudence WHERE {col} IS NULL OR {col}::text = ''")
            null_count = cur.fetchone()[0]
            filled_pct = round((1 - null_count / total) * 100, 1) if total > 0 else 0
            quality["fields"][col] = {
                "null_count": null_count,
                "filled_pct": filled_pct,
            }
        except Exception as e:
            conn.rollback()
            quality["fields"][col] = {"error": str(e)}

    # Score global: moyenne ponderee
    weights = {"database_id": 3, "resume": 2, "titre": 2, "resultat": 3, "embedding": 2, "date_decision": 1}
    total_weight = sum(weights.values())
    score = 0
    for col, w in weights.items():
        f = quality["fields"].get(col, {})
        score += f.get("filled_pct", 0) * w
    quality["score"] = round(score / total_weight, 1) if total_weight > 0 else 0

    cur.close()
    return quality


def save_state(results):
    """Sauvegarder le resultat de la derniere reparation"""
    try:
        state = {
            "last_run": datetime.now().isoformat(),
            "results": results,
        }
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        log(f"Erreur sauvegarde state: {e}")


def main():
    log("=" * 60)
    log("DATA REPAIR — Debut")
    log("=" * 60)
    start = time.time()
    results = {}
    quality_before = {"score": "?"}
    quality_after = {"score": "?"}

    try:
        conn = get_conn()

        # 1. Qualite avant
        log("\n--- Audit qualite AVANT ---")
        quality_before = check_data_quality(conn)
        log(f"  Score global: {quality_before['score']}%")
        for col, info in quality_before["fields"].items():
            if "error" not in info:
                log(f"  {col}: {info['filled_pct']}% rempli ({info['null_count']} NULL)")
        results["quality_before"] = quality_before

        # 2. Reparer database_id
        log("\n--- Reparation database_id ---")
        fixed, total = repair_database_id(conn)
        log(f"  {fixed}/{total} corriges")
        results["database_id"] = {"fixed": fixed, "total": total}

        # 3. Reparer resultat
        log("\n--- Reparation resultat ---")
        fixed, total = repair_resultat(conn)
        log(f"  {fixed}/{total} corriges")
        results["resultat"] = {"fixed": fixed, "total": total}

        # 4. Reparer est_ticket_related
        log("\n--- Reparation est_ticket_related ---")
        fixed, total = repair_ticket_related(conn)
        log(f"  {fixed}/{total} reclassifies comme traffic")
        results["ticket_related"] = {"fixed": fixed, "total": total}

        # 5. Verifier tsvector (colonnes generees auto)
        log("\n--- Verification tsvector ---")
        null_fr, null_en = check_tsvector(conn)
        log(f"  tsvector FR NULL: {null_fr} | tsvector EN NULL: {null_en}")
        results["tsvector"] = {"null_fr": null_fr, "null_en": null_en}

        # 6. Qualite apres
        log("\n--- Audit qualite APRES ---")
        quality_after = check_data_quality(conn)
        log(f"  Score global: {quality_after['score']}%")
        for col, info in quality_after["fields"].items():
            if "error" not in info:
                before_pct = quality_before["fields"].get(col, {}).get("filled_pct", 0)
                delta = round(info["filled_pct"] - before_pct, 1)
                arrow = f" (+{delta}%)" if delta > 0 else ""
                log(f"  {col}: {info['filled_pct']}% rempli{arrow}")
        results["quality_after"] = quality_after

        conn.close()

    except Exception as e:
        log(f"ERREUR FATALE: {e}")
        results["error"] = str(e)

    duration = time.time() - start
    results["duration"] = round(duration, 1)

    log(f"\n{'=' * 60}")
    log(f"DATA REPAIR — Termine en {duration:.1f}s")
    log(f"  Score: {quality_before.get('score', '?')}% → {quality_after.get('score', '?')}%")
    log(f"{'=' * 60}\n")

    save_state(results)
    return results


if __name__ == "__main__":
    main()
