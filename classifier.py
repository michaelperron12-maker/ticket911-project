#!/usr/bin/env python3
"""
aiticketinfo-classifier — Agent 24/7 classification et embeddings
Tourne en continu, prend son temps, corrige les donnees en boucle.
- Remplit embeddings manquants (via Fireworks API)
- Reclassifie database_id, resultat, est_ticket_related
- Sleep entre chaque operation pour pas surcharger
- Recommence une fois fini pour les nouveaux imports
"""

import os
import sys
import re
import time
import json
import signal
import psycopg2
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
SLEEP_BETWEEN = 1        # secondes entre chaque dossier
SLEEP_BATCH = 5          # secondes entre chaque batch
SLEEP_CYCLE = 60         # 5 min entre chaque cycle complet
BATCH_SIZE = 50           # dossiers par batch embedding
EMBEDDING_ENABLED = True  # activer/desactiver embeddings

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
# CLASSIFY: database_id, resultat, est_ticket_related
# ══════════════════════════════════════════════════════════

def classify_pass(conn):
    """Un pass de classification sur tous les dossiers incomplets"""
    cur = conn.cursor()
    fixed = {"database_id": 0, "resultat": 0, "ticket_related": 0}

    # 1. database_id manquants
    cur.execute("SELECT id, citation FROM jurisprudence WHERE database_id IS NULL OR database_id = ''")
    rows = cur.fetchall()
    for row_id, citation in rows:
        if not running:
            break
        db_id = extract_db_id(citation)
        if db_id:
            cur.execute("UPDATE jurisprudence SET database_id = %s WHERE id = %s", (db_id, row_id))
            fixed["database_id"] += 1
    conn.commit()

    # 2. resultat inconnus
    cur.execute("""SELECT id, titre, resume FROM jurisprudence
                   WHERE resultat IS NULL OR resultat = '' OR resultat = 'inconnu'""")
    rows = cur.fetchall()
    for row_id, titre, resume in rows:
        if not running:
            break
        r = detect_resultat(titre, resume)
        if r:
            cur.execute("UPDATE jurisprudence SET resultat = %s WHERE id = %s", (r, row_id))
            fixed["resultat"] += 1
    conn.commit()

    # 3. est_ticket_related
    cur.execute("""SELECT id, titre, resume FROM jurisprudence
                   WHERE est_ticket_related = false OR est_ticket_related IS NULL""")
    rows = cur.fetchall()
    for row_id, titre, resume in rows:
        if not running:
            break
        if is_traffic(titre, resume):
            cur.execute("UPDATE jurisprudence SET est_ticket_related = true WHERE id = %s", (row_id,))
            fixed["ticket_related"] += 1
    conn.commit()

    cur.close()
    return fixed


# ══════════════════════════════════════════════════════════
# EMBEDDINGS: remplir les manquants
# ══════════════════════════════════════════════════════════

def get_embedding_service():
    """Charger le service d'embedding"""
    try:
        from embedding_service import embedding_service
        return embedding_service
    except Exception as e:
        log(f"  Embedding service indisponible: {e}")
        return None


def build_embed_text(row):
    """Construire le texte pour embedding"""
    parts = []
    if row.get("titre"):
        parts.append(row["titre"])
    if row.get("citation"):
        parts.append(row["citation"])
    if row.get("database_id"):
        parts.append(f"Tribunal: {row['database_id'].upper()}")
    if row.get("resume"):
        parts.append(row["resume"])
    if row.get("mots_cles"):
        parts.append(" ".join(row["mots_cles"][:20]))
    if row.get("resultat"):
        parts.append(f"Resultat: {row['resultat']}")
    if row.get("province"):
        parts.append(f"Province: {row['province']}")
    text = " ".join(parts)
    return text[:8000]


def embedding_pass(conn):
    """Un pass pour remplir les embeddings manquants"""
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
        if not running:
            break
        try:
            text = build_embed_text(row)
            if not text.strip():
                continue

            # Appel API embedding
            emb = svc.embed_single(text)
            if emb and len(emb) > 0:
                cur.execute(
                    "UPDATE jurisprudence SET embedding = %s::vector WHERE id = %s",
                    (str(emb), row["id"])
                )
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
    """Stats rapides"""
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM jurisprudence")
    total = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM jurisprudence WHERE embedding IS NULL")
    no_embed = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM jurisprudence WHERE database_id IS NULL OR database_id = ''")
    no_db = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM jurisprudence WHERE resultat IS NULL OR resultat = '' OR resultat = 'inconnu'")
    no_res = cur.fetchone()[0]
    cur.close()
    return {"total": total, "no_embed": no_embed, "no_db_id": no_db, "no_resultat": no_res}


# ══════════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════════

def main():
    log("=" * 60)
    log("AITICKETINFO CLASSIFIER — Demarrage")
    log("  Mode: 24/7 continu")
    log(f"  Sleep entre dossiers: {SLEEP_BETWEEN}s")
    log(f"  Sleep entre cycles: {SLEEP_CYCLE}s")
    log(f"  Embeddings: {'ON' if EMBEDDING_ENABLED else 'OFF'}")
    log("=" * 60)

    cycle = 0
    while running:
        cycle += 1
        try:
            conn = get_conn()
            stats_before = get_stats(conn)
            log(f"\n--- Cycle {cycle} ---")
            log(f"  DB: {stats_before['total']} total | "
                f"{stats_before['no_embed']} sans embed | "
                f"{stats_before['no_db_id']} sans tribunal | "
                f"{stats_before['no_resultat']} sans resultat")

            # Classification
            if stats_before["no_db_id"] > 0 or stats_before["no_resultat"] > 0:
                log("  Classification...")
                fixed = classify_pass(conn)
                if any(v > 0 for v in fixed.values()):
                    log(f"  Corriges: db_id={fixed['database_id']}, "
                        f"resultat={fixed['resultat']}, "
                        f"traffic={fixed['ticket_related']}")
                else:
                    log("  Rien a corriger")

            # Embeddings
            if stats_before["no_embed"] > 0 and EMBEDDING_ENABLED:
                log(f"  Embeddings ({stats_before['no_embed']} manquants)...")
                embedded = embedding_pass(conn)
                if embedded > 0:
                    log(f"  {embedded} embeddings crees")
                else:
                    log("  Aucun embedding cree (service indisponible ou erreur)")
                time.sleep(SLEEP_BATCH)

            # Stats apres
            stats_after = get_stats(conn)
            if stats_after != stats_before:
                log(f"  Apres: {stats_after['no_embed']} sans embed | "
                    f"{stats_after['no_db_id']} sans tribunal | "
                    f"{stats_after['no_resultat']} sans resultat")

            conn.close()

        except Exception as e:
            log(f"  ERREUR cycle {cycle}: {e}")
            time.sleep(30)

        # Attendre avant le prochain cycle
        if running:
            log(f"  Prochain cycle dans {SLEEP_CYCLE}s...")
            for _ in range(SLEEP_CYCLE):
                if not running:
                    break
                time.sleep(1)

    log("\nAITICKETINFO CLASSIFIER — Arret propre")


if __name__ == "__main__":
    main()
