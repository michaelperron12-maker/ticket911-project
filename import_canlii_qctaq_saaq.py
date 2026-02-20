#!/usr/bin/env python3
"""
Import massif CanLII — QCTAQ (Tribunal administratif du Quebec)
Importe TOUS les dossiers SAAQ sans filtre keyword restrictif.

Le TAQ contient ~130K+ dossiers dont ~49% sont SAAQ:
- Contestations de points d'inaptitude
- Revocations de permis
- Sanctions administratives
- Alcool au volant (interlock, suspension)
- Grands exces de vitesse

Rate-limited: 1.7s entre requetes, max 4700/jour
Usage:
  python3 import_canlii_qctaq_saaq.py                    # Import prod
  python3 import_canlii_qctaq_saaq.py --dry-run           # Simulation
  python3 import_canlii_qctaq_saaq.py --max-requests 500  # Limite custom
  python3 import_canlii_qctaq_saaq.py --resume             # Reprend ou on a arrete

Cron (dans canlii-updater.service ou separe):
  Rouler chaque jour avec --resume pour continuer l'import progressivement
"""

import os
import sys
import json
import time
import argparse
import psycopg2
import psycopg2.extras
import requests
from datetime import datetime, date

# ═══════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

API_KEY = os.environ.get("CANLII_API_KEY", "")
BASE_URL = "https://api.canlii.org/v1"
DB_ID = "qctaq"
LANG = "fr"
PROVINCE = "QC"

PG_CONFIG = {
    'host': os.environ.get('TICKETS_DB_HOST', '172.18.0.3'),
    'port': int(os.environ.get('TICKETS_DB_PORT', 5432)),
    'dbname': os.environ.get('TICKETS_DB_NAME', 'tickets_qc_on'),
    'user': os.environ.get('TICKETS_DB_USER', 'ticketdb_user'),
    'password': os.environ.get('TICKETS_DB_PASS', 'Tk911PgSecure2026'),
}

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db", "qctaq_import_state.json")
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

# Mots-cles pour TICKETS DE TRAFFIC/CIRCULATION seulement
# PAS les accidents, immigration, sante, etc.
SAAQ_KEYWORDS = [
    # SAAQ + permis (coeur du TAQ traffic)
    "saaq", "société de l'assurance automobile", "societe de l'assurance automobile",
    "permis de conduire", "droit de conduire",
    "révocation", "revocation",
    "points d'inaptitude", "points de démérite", "points de demerite",
    "inaptitude",
    # Alcool au volant (sanctions SAAQ)
    "alcool", "alcootest", "alcoolémie", "alcoolemie",
    "facultés affaiblies", "facultes affaiblies",
    "capacité affaiblie", "capacite affaiblie",
    "interlock", "antidémarreur", "antidemarreur", "éthylomètre",
    # Vitesse
    "vitesse", "excès de vitesse", "grand excès",
    "cinémomètre", "cinemometre", "radar", "photo radar",
    # Code de la securite routiere
    "code de la sécurité routière", "code de la securite routiere",
    "sécurité routière", "securite routiere",
    "csr", "c.s.r.",
    # Infractions traffic specifiques
    "constat d'infraction",
    "feu rouge", "cellulaire", "ceinture",
    "conduite dangereuse", "conduite imprudente",
    "délit de fuite", "delit de fuite",
    "circulation", "routier", "routière",
    # Immatriculation/plaque (lie au permis)
    "immatriculation", "plaque",
]

# Mots-cles a EXCLURE (pas des tickets traffic)
EXCLUDE_KEYWORDS = [
    "immigration", "réfugié", "refugie", "asile",
    "accident de travail", "accident du travail", "csst", "cnesst",
    "aide sociale", "solidarité sociale", "solidarite sociale",
    "impôt", "impot", "fiscal", "revenu",
    "environnement", "zonage", "urbanisme",
    "santé", "sante", "médical", "medical", "hôpital", "hopital",
    "indemnisation", "ivac",
    "logement", "locataire", "propriétaire",
    "assurance-emploi", "emploi",
    "éducation", "education", "école", "ecole",
]


# ═══════════════════════════════════════════════════════════
# RATE LIMITER
# ═══════════════════════════════════════════════════════════
class RateLimiter:
    def __init__(self, max_per_day=4700, delay=1.7):
        self.max_per_day = max_per_day
        self.delay = delay
        self.count = 0
        self.last_time = 0
        self.consecutive_429 = 0

    def wait(self):
        if self.count >= self.max_per_day:
            return False
        elapsed = time.time() - self.last_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_time = time.time()
        self.count += 1
        return True

    def remaining(self):
        return max(0, self.max_per_day - self.count)


# ═══════════════════════════════════════════════════════════
# STATE MANAGEMENT (pour --resume)
# ═══════════════════════════════════════════════════════════
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"last_offset": 0, "total_imported": 0, "total_filtered": 0, "total_scanned": 0}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    state["last_update"] = datetime.now().isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ═══════════════════════════════════════════════════════════
# FONCTIONS
# ═══════════════════════════════════════════════════════════
def is_saaq_related(title):
    """Check si un titre de decision TAQ est lie aux tickets traffic/circulation"""
    if not title:
        return False
    t = title.lower()

    # D'abord exclure les dossiers hors-sujet
    for ex in EXCLUDE_KEYWORDS:
        if ex in t:
            return False

    # Ensuite verifier si c'est lie au traffic
    for kw in SAAQ_KEYWORDS:
        if kw in t:
            return True
    return False


def browse_cases(offset, count, limiter):
    """Browse les decisions du qctaq avec pagination"""
    if not limiter.wait():
        return None

    try:
        resp = requests.get(
            f"{BASE_URL}/caseBrowse/{LANG}/{DB_ID}/",
            params={"api_key": API_KEY, "offset": offset, "resultCount": min(count, 100)},
            timeout=15
        )
        if resp.status_code == 200:
            limiter.consecutive_429 = 0
            return resp.json().get("cases", [])
        elif resp.status_code == 429:
            limiter.consecutive_429 += 1
            backoff = min(120, 1.7 * (2 ** limiter.consecutive_429))
            print(f"  [THROTTLE] HTTP 429 — backoff {backoff:.0f}s (x{limiter.consecutive_429})")
            time.sleep(backoff)
            return None
        else:
            print(f"  [WARN] HTTP {resp.status_code}")
            return []
    except Exception as e:
        print(f"  [ERR] Browse: {e}")
        return []


def get_case_metadata(case_id, limiter):
    """Recupere les metadonnees completes d'une decision"""
    if not limiter.wait():
        return None

    try:
        resp = requests.get(
            f"{BASE_URL}/caseBrowse/{LANG}/{DB_ID}/{case_id}/",
            params={"api_key": API_KEY}, timeout=15
        )
        if resp.status_code == 200:
            limiter.consecutive_429 = 0
            return resp.json()
        elif resp.status_code == 429:
            limiter.consecutive_429 += 1
            backoff = min(120, 1.7 * (2 ** limiter.consecutive_429))
            print(f"  [THROTTLE] metadata 429 — backoff {backoff:.0f}s")
            time.sleep(backoff)
            return None
    except Exception:
        pass
    return {}


def insert_case(conn, case_data, existing_ids):
    """Insere un dossier SAAQ dans PostgreSQL"""
    try:
        cur = conn.cursor()

        case_id_raw = case_data.get("caseId", {})
        if isinstance(case_id_raw, dict):
            canlii_id = case_id_raw.get("fr", case_id_raw.get("en", ""))
        else:
            canlii_id = str(case_id_raw)

        if canlii_id in existing_ids:
            return False

        title = case_data.get("title", "")
        citation = case_data.get("citation", "")
        decision_date = case_data.get("decisionDate", None)
        url = case_data.get("url", "")
        docket = case_data.get("docketNumber", "")
        keywords_raw = case_data.get("keywords", "")

        if isinstance(keywords_raw, str):
            mots_cles = [k.strip() for k in keywords_raw.split(",") if k.strip()]
        elif isinstance(keywords_raw, list):
            mots_cles = keywords_raw
        else:
            mots_cles = []

        cur.execute("""
            INSERT INTO jurisprudence
                (canlii_id, database_id, province, titre, citation,
                 numero_dossier, date_decision, url_canlii, tribunal,
                 langue, mots_cles, est_ticket_related,
                 source, raw_metadata, imported_at)
            VALUES (%s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, NOW())
            ON CONFLICT (canlii_id) DO NOTHING
        """, (
            canlii_id, DB_ID, PROVINCE, title, citation,
            docket, decision_date, url, DB_ID,
            LANG, mots_cles, True,
            "canlii-qctaq-saaq", json.dumps(case_data, ensure_ascii=False, default=str)
        ))
        conn.commit()
        existing_ids.add(canlii_id)
        return True
    except Exception as e:
        conn.rollback()
        print(f"  [ERR] Insert: {e}")
        return False


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Import massif QCTAQ SAAQ from CanLII")
    parser.add_argument("--dry-run", action="store_true", help="Simulation sans insert")
    parser.add_argument("--max-requests", type=int, default=4700,
                        help="Max requetes API par run (default: 4700)")
    parser.add_argument("--resume", action="store_true",
                        help="Reprendre ou on a arrete (utilise state file)")
    parser.add_argument("--reset", action="store_true",
                        help="Reset le state et recommencer a offset 0")
    args = parser.parse_args()

    if not API_KEY:
        print("[FATAL] CANLII_API_KEY non configuree")
        sys.exit(1)

    # State management
    state = load_state()
    if args.reset:
        state = {"last_offset": 0, "total_imported": 0, "total_filtered": 0, "total_scanned": 0}
        save_state(state)
        print("[RESET] State remis a zero")

    start_offset = state["last_offset"] if args.resume else 0
    limiter = RateLimiter(max_per_day=args.max_requests)

    print("=" * 60)
    print("  CANLII IMPORT MASSIF — QCTAQ (SAAQ)")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Max requetes: {args.max_requests}")
    print(f"  Offset depart: {start_offset}")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'PRODUCTION'}")
    if args.resume:
        print(f"  Resume: Deja importe {state['total_imported']} | Filtre {state['total_filtered']}")
    print("=" * 60)

    conn = psycopg2.connect(**PG_CONFIG)
    existing_ids = set()
    cur = conn.cursor()
    cur.execute("SELECT canlii_id FROM jurisprudence WHERE canlii_id IS NOT NULL")
    existing_ids = {row[0] for row in cur.fetchall()}
    cur.close()
    print(f"\n  Dossiers deja en DB: {len(existing_ids)}")

    offset = start_offset
    session_imported = 0
    session_filtered = 0
    session_skipped = 0
    session_scanned = 0
    empty_pages = 0
    stats = {}

    while True:
        if limiter.remaining() < 10:
            print(f"\n  [STOP] Quota quasi-epuise ({limiter.remaining()} restant)")
            break

        cases = browse_cases(offset, 100, limiter)

        if cases is None:
            # 429 or quota - retry once
            time.sleep(5)
            cases = browse_cases(offset, 100, limiter)
            if cases is None:
                print(f"  [STOP] Quota atteint apres retry")
                break

        if not cases:
            empty_pages += 1
            if empty_pages >= 3:
                print(f"  [DONE] 3 pages vides consecutives a offset {offset} — fin du tribunal")
                break
            offset += 100
            continue

        empty_pages = 0

        for case in cases:
            session_scanned += 1

            case_id_raw = case.get("caseId", {})
            if isinstance(case_id_raw, dict):
                canlii_id = case_id_raw.get("fr", case_id_raw.get("en", ""))
            else:
                canlii_id = str(case_id_raw)

            # Skip si deja importe
            if canlii_id in existing_ids:
                session_skipped += 1
                continue

            title = case.get("title", "")

            # Filtre SAAQ: on accepte tout ce qui est lie SAAQ/conduite/vehicule
            if not is_saaq_related(title):
                session_filtered += 1
                continue

            # Recuperer metadata si quota ok
            if limiter.remaining() < 5:
                break

            metadata = get_case_metadata(canlii_id, limiter)
            if metadata is None:
                break

            full_case = {**case, **metadata} if metadata else case

            if not args.dry_run:
                if insert_case(conn, full_case, existing_ids):
                    session_imported += 1

                    # Track type d'infraction basique
                    t = title.lower()
                    if "alcool" in t or "faculté" in t or "interlock" in t:
                        inftype = "alcool"
                    elif "vitesse" in t or "excès" in t or "radar" in t:
                        inftype = "vitesse"
                    elif "permis" in t or "suspension" in t or "révocation" in t:
                        inftype = "permis"
                    elif "point" in t or "inaptitude" in t:
                        inftype = "points"
                    else:
                        inftype = "autre_saaq"
                    stats[inftype] = stats.get(inftype, 0) + 1
            else:
                session_imported += 1

            if session_imported % 25 == 0 and session_imported > 0:
                print(f"  +{session_imported} importes | {session_filtered} filtres | "
                      f"{session_skipped} existants | offset={offset} | quota={limiter.remaining()}")

        offset += 100

        # Sauvegarder state regulierement
        if session_scanned % 500 == 0:
            state["last_offset"] = offset
            state["total_imported"] = state.get("total_imported", 0) + session_imported
            state["total_filtered"] = state.get("total_filtered", 0) + session_filtered
            state["total_scanned"] = state.get("total_scanned", 0) + session_scanned
            save_state(state)

    conn.close()

    # Sauvegarder state final
    state["last_offset"] = offset
    if args.resume:
        state["total_imported"] = state.get("total_imported", 0) + session_imported
        state["total_filtered"] = state.get("total_filtered", 0) + session_filtered
        state["total_scanned"] = state.get("total_scanned", 0) + session_scanned
    else:
        state["total_imported"] = session_imported
        state["total_filtered"] = session_filtered
        state["total_scanned"] = session_scanned
    save_state(state)

    # Log usage
    os.makedirs(LOG_DIR, exist_ok=True)
    usage_file = os.path.join(LOG_DIR, "canlii_qctaq_usage.json")
    with open(usage_file, "w") as f:
        json.dump({
            "day": date.today().timetuple().tm_yday,
            "count": limiter.count,
            "last_update": datetime.now().isoformat(),
            "session_imported": session_imported,
            "session_filtered": session_filtered,
            "session_skipped": session_skipped,
            "offset_reached": offset,
            "stats": stats,
        }, f, indent=2)

    # Resume
    print(f"\n{'='*60}")
    print(f"  RESUME — IMPORT QCTAQ SAAQ")
    print(f"{'='*60}")
    print(f"  Cette session:")
    print(f"    Nouveaux importes:   {session_imported}")
    print(f"    Filtres (hors SAAQ): {session_filtered}")
    print(f"    Deja existants:      {session_skipped}")
    print(f"    Pages scannees:      {session_scanned}")
    print(f"    Offset atteint:      {offset}")
    print(f"    Requetes utilisees:  {limiter.count}/{args.max_requests}")
    print(f"\n  Cumul total:")
    print(f"    Total importes:      {state['total_imported']}")
    print(f"    Total filtres:       {state['total_filtered']}")
    print(f"    Total scannes:       {state['total_scanned']}")
    print(f"\n  Par type:")
    for inftype, count in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"    {inftype:25s} {count:>6}")
    print(f"\n  Prochain run: python3 import_canlii_qctaq_saaq.py --resume")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
