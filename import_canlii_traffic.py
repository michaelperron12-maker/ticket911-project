#!/usr/bin/env python3
"""
Import massif CanLII — Focus tickets traffic (vitesse, cellulaire, alcool, contestés)
Rate-limited: 2 req/sec, 4500/jour max (marge sous 5000)
Usage: python3 import_canlii_traffic.py [--dry-run] [--max-requests 4000]
"""

import os
import sys
import json
import time
import re
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

PG_CONFIG = {
    'host': os.environ.get('TICKETS_DB_HOST', '172.18.0.3'),
    'port': int(os.environ.get('TICKETS_DB_PORT', 5432)),
    'dbname': os.environ.get('TICKETS_DB_NAME', 'tickets_qc_on'),
    'user': os.environ.get('TICKETS_DB_USER', 'ticketdb_user'),
    'password': os.environ.get('TICKETS_DB_PASS', 'Tk911PgSecure2026'),
}

# Tribunaux cibles (traffic-related) par ordre de priorité
TRIBUNAUX = [
    # QC — Cours municipales = presque 100% traffic
    {"db": "qccm", "province": "QC", "lang": "fr", "priority": 1,
     "name": "Cours municipales QC"},
    # QC — Cour du Québec (appels traffic + penal)
    {"db": "qccq", "province": "QC", "lang": "fr", "priority": 2,
     "name": "Cour du Québec"},
    # QC — Cour supérieure (appels)
    {"db": "qccs", "province": "QC", "lang": "fr", "priority": 3,
     "name": "Cour supérieure QC"},
    # QC — Cour d'appel
    {"db": "qcca", "province": "QC", "lang": "fr", "priority": 3,
     "name": "Cour d'appel QC"},
    # ON — Ontario Court of Justice (traffic tickets)
    {"db": "oncj", "province": "ON", "lang": "en", "priority": 1,
     "name": "Ontario Court of Justice"},
    # ON — Divisional Court (appels)
    {"db": "onscdc", "province": "ON", "lang": "en", "priority": 2,
     "name": "Divisional Court ON"},
    # ON — Cour d'appel
    {"db": "onca", "province": "ON", "lang": "en", "priority": 3,
     "name": "Court of Appeal ON"},
]

# Mots-clés pour filtrer les dossiers traffic pertinents
KEYWORDS_FR = [
    # Vitesse
    "vitesse", "excès de vitesse", "excès", "radar", "cinémomètre",
    "photo radar", "cinémometre", "photoradar",
    # Cellulaire
    "cellulaire", "téléphone", "telephone", "appareil",
    "main", "texto", "texte",
    # Alcool
    "alcool", "alcootest", "alcoolémie", "alcoolemie",
    "ivresse", "ébriété", "facultés affaiblies", "facultes affaiblies",
    "capacité affaiblie", "capacite affaiblie",
    "taux d'alcoolémie",
    # Contestation / procédure
    "contestation", "acquitté", "acquitte", "non coupable",
    "rejet", "annulation", "vice de forme",
    "signalisation", "calibration",
    # Infractions courantes
    "feu rouge", "stop", "arrêt", "arret",
    "ceinture", "conduite dangereuse",
    "délit de fuite", "delit de fuite",
    "suspension", "permis",
    "constat d'infraction", "constat",
    # Code de la sécurité routière
    "sécurité routière", "securite routiere", "C.S.R.", "CSR",
    "code de la route",
]

KEYWORDS_EN = [
    # Speed
    "speed", "speeding", "radar", "lidar",
    "photo radar", "speed camera",
    # Cell phone
    "cell phone", "cellphone", "handheld", "distracted",
    "texting", "mobile device",
    # Alcohol
    "alcohol", "impaired", "dui", "dwi", "breathalyzer",
    "blood alcohol", "BAC", "intoxicated",
    "over 80", "over .08",
    # Contestation
    "acquitted", "dismissed", "not guilty",
    "charter", "disclosure",
    "calibration", "signage",
    # Common offences
    "red light", "stop sign", "seatbelt",
    "careless driving", "dangerous driving",
    "stunt driving", "racing",
    "fail to stop", "hit and run",
    "suspended", "licence",
    # Highway Traffic Act
    "highway traffic", "HTA", "traffic",
    "provincial offences", "POA",
]

# ═══════════════════════════════════════════════════════════
# RATE LIMITER
# ═══════════════════════════════════════════════════════════
class RateLimiter:
    def __init__(self, max_per_day=4800, delay=1.7):
        self.max_per_day = max_per_day
        self.delay = delay  # 1.7 sec entre requetes, 1 a la fois
        self.count = 0
        self.last_time = 0

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
# FONCTIONS
# ═══════════════════════════════════════════════════════════

def is_traffic_related(title, lang="fr"):
    """Vérifie si un titre de décision est lié au traffic"""
    if not title:
        return False
    title_lower = title.lower()

    # qccm = presque toujours traffic, accepter tout
    keywords = KEYWORDS_FR if lang == "fr" else KEYWORDS_EN

    for kw in keywords:
        if kw.lower() in title_lower:
            return True
    return False


def detect_infraction_type(title):
    """Détecte le type d'infraction à partir du titre"""
    t = (title or "").lower()
    if any(w in t for w in ["vitesse", "speed", "radar", "cinémo", "cinemo", "photo radar", "lidar"]):
        return "vitesse"
    if any(w in t for w in ["cellulaire", "téléphone", "telephone", "cell phone", "handheld", "distract", "texting"]):
        return "cellulaire"
    if any(w in t for w in ["alcool", "alcootest", "impaired", "dui", "dwi", "ivresse", "ébriété", "blood alcohol", "over 80", "faculté"]):
        return "alcool"
    if any(w in t for w in ["feu rouge", "red light"]):
        return "feu_rouge"
    if any(w in t for w in ["ceinture", "seatbelt"]):
        return "ceinture"
    if any(w in t for w in ["stunt", "racing", "course", "grand excès"]):
        return "grand_exces"
    if any(w in t for w in ["stop", "arrêt", "arret"]):
        return "stop"
    if any(w in t for w in ["dangereuse", "dangerous", "careless"]):
        return "conduite_dangereuse"
    if any(w in t for w in ["permis", "suspen", "licence"]):
        return "permis"
    return "autre"


def detect_resultat(title):
    """Tente de détecter le résultat à partir du titre"""
    t = (title or "").lower()
    if any(w in t for w in ["acquitté", "acquitte", "acquitted", "not guilty", "non coupable"]):
        return "acquitte"
    if any(w in t for w in ["rejeté", "rejete", "rejected", "dismissed"]):
        return "rejete"
    if any(w in t for w in ["coupable", "guilty", "condamné", "condamne", "convicted"]):
        return "coupable"
    if any(w in t for w in ["réduit", "reduit", "reduced"]):
        return "reduit"
    return "inconnu"


def get_existing_canlii_ids(conn):
    """Récupère tous les canlii_id déjà importés"""
    cur = conn.cursor()
    cur.execute("SELECT canlii_id FROM jurisprudence WHERE canlii_id IS NOT NULL")
    return {row[0] for row in cur.fetchall()}


def browse_cases(db_id, lang, offset, count, limiter):
    """Browse les décisions d'un tribunal avec pagination"""
    if not limiter.wait():
        return None  # Quota épuisé

    params = {
        "api_key": API_KEY,
        "offset": offset,
        "resultCount": min(count, 100)
    }
    try:
        resp = requests.get(f"{BASE_URL}/caseBrowse/{lang}/{db_id}/",
                           params=params, timeout=15)
        if resp.status_code == 200:
            limiter.consecutive_429 = 0
            return resp.json().get("cases", [])
        elif resp.status_code == 429:
            limiter.consecutive_429 = getattr(limiter, 'consecutive_429', 0) + 1
            backoff = min(120, 1.7 * (2 ** limiter.consecutive_429))
            print(f"    [THROTTLE] HTTP 429 — backoff {backoff:.0f}s (x{limiter.consecutive_429})")
            time.sleep(backoff)
            return None
        else:
            print(f"    [WARN] HTTP {resp.status_code} pour {db_id}")
            return []
    except Exception as e:
        print(f"    [ERR] {e}")
        return []


def get_case_metadata(db_id, case_id, lang, limiter):
    """Récupère les métadonnées complètes d'une décision"""
    if not limiter.wait():
        return None

    try:
        resp = requests.get(
            f"{BASE_URL}/caseBrowse/{lang}/{db_id}/{case_id}/",
            params={"api_key": API_KEY}, timeout=15)
        if resp.status_code == 200:
            limiter.consecutive_429 = 0
            return resp.json()
        elif resp.status_code == 429:
            limiter.consecutive_429 = getattr(limiter, 'consecutive_429', 0) + 1
            backoff = min(120, 1.7 * (2 ** limiter.consecutive_429))
            print(f"    [THROTTLE] HTTP 429 metadata — backoff {backoff:.0f}s")
            time.sleep(backoff)
            return None
    except Exception:
        pass
    return {}


def insert_case(conn, case_data, tribunal_info):
    """Insère un dossier dans PostgreSQL"""
    try:
        cur = conn.cursor()

        # Préparer les données
        case_id_raw = case_data.get("caseId", {})
        if isinstance(case_id_raw, dict):
            canlii_id = case_id_raw.get("en", case_id_raw.get("fr", ""))
        else:
            canlii_id = str(case_id_raw)

        title = case_data.get("title", "")
        citation = case_data.get("citation", "")
        decision_date = case_data.get("decisionDate", None)
        url = case_data.get("url", "")
        docket = case_data.get("docketNumber", "")
        language = case_data.get("language", tribunal_info["lang"])
        keywords_raw = case_data.get("keywords", "")

        # Mots-clés: peut être string ou liste
        if isinstance(keywords_raw, str):
            mots_cles = [k.strip() for k in keywords_raw.split(",") if k.strip()]
        elif isinstance(keywords_raw, list):
            mots_cles = keywords_raw
        else:
            mots_cles = []

        infraction_type = detect_infraction_type(title)
        resultat = detect_resultat(title)

        cur.execute("""
            INSERT INTO jurisprudence
                (canlii_id, database_id, province, titre, citation,
                 numero_dossier, date_decision, url_canlii, tribunal,
                 langue, mots_cles, resultat, est_ticket_related,
                 source, raw_metadata, imported_at)
            VALUES (%s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, NOW())
            ON CONFLICT (canlii_id) DO UPDATE SET
                titre = EXCLUDED.titre,
                mots_cles = EXCLUDED.mots_cles,
                raw_metadata = EXCLUDED.raw_metadata,
                resultat = EXCLUDED.resultat
        """, (
            canlii_id, tribunal_info["db"], tribunal_info["province"],
            title, citation,
            docket, decision_date, url, tribunal_info["db"],
            language, mots_cles, resultat, True,
            "canlii-api", json.dumps(case_data, ensure_ascii=False, default=str)
        ))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"    [ERR] Insert: {e}")
        return False


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Import CanLII traffic cases")
    parser.add_argument("--dry-run", action="store_true", help="Ne pas insérer en DB")
    parser.add_argument("--max-requests", type=int, default=4800,
                        help="Max requêtes API (default: 4800, marge 200 sous 5000)")
    parser.add_argument("--page-size", type=int, default=100,
                        help="Résultats par page (default: 100, max: 100)")
    parser.add_argument("--tribunaux", type=str, default="",
                        help="Filtrer tribunaux (ex: qccm,qccq)")
    args = parser.parse_args()

    if not API_KEY:
        print("[FATAL] CANLII_API_KEY non configurée")
        sys.exit(1)

    limiter = RateLimiter(max_per_day=args.max_requests)

    print("=" * 60)
    print("  CANLII IMPORT — TRAFFIC TICKETS (vitesse/cell/alcool)")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Max requêtes: {args.max_requests}")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'PRODUCTION'}")
    print("=" * 60)

    conn = psycopg2.connect(**PG_CONFIG)
    existing_ids = get_existing_canlii_ids(conn)
    print(f"\n  Dossiers déjà importés: {len(existing_ids)}")

    # Filtrer tribunaux si demandé
    tribunaux = TRIBUNAUX
    if args.tribunaux:
        filter_dbs = [t.strip() for t in args.tribunaux.split(",")]
        tribunaux = [t for t in TRIBUNAUX if t["db"] in filter_dbs]

    total_imported = 0
    total_skipped = 0
    total_filtered = 0
    stats = {}

    for trib in tribunaux:
        db_id = trib["db"]
        lang = trib["lang"]
        name = trib["name"]
        is_municipal = db_id == "qccm"  # qccm = presque tout traffic

        print(f"\n{'─'*50}")
        print(f"  {name} ({db_id}) — Priority {trib['priority']}")
        print(f"{'─'*50}")

        offset = 0
        trib_imported = 0
        trib_skipped = 0
        trib_filtered = 0

        while True:
            if limiter.remaining() < 10:
                print(f"  [STOP] Quota quasi-épuisé ({limiter.remaining()} restant)")
                break

            cases = browse_cases(db_id, lang, offset, args.page_size, limiter)
            if cases is None:
                print(f"  [STOP] Quota atteint")
                break
            if not cases:
                print(f"  [DONE] Fin des résultats à offset {offset}")
                break

            for case in cases:
                case_id_raw = case.get("caseId", {})
                if isinstance(case_id_raw, dict):
                    canlii_id = case_id_raw.get("en", case_id_raw.get("fr", ""))
                else:
                    canlii_id = str(case_id_raw)

                # Skip si déjà importé
                if canlii_id in existing_ids:
                    trib_skipped += 1
                    continue

                title = case.get("title", "")

                # Filter: qccm = tout accepter (c'est du traffic)
                # Autres tribunaux: filtrer par mots-clés
                if not is_municipal and not is_traffic_related(title, lang):
                    trib_filtered += 1
                    continue

                # Récupérer metadata complète
                if limiter.remaining() < 5:
                    break

                metadata = get_case_metadata(db_id, canlii_id, lang, limiter)
                if metadata is None:
                    print(f"  [STOP] Quota atteint pendant metadata")
                    break

                # Merger les données
                full_case = {**case, **metadata} if metadata else case

                if not args.dry_run:
                    if insert_case(conn, full_case, trib):
                        existing_ids.add(canlii_id)
                        trib_imported += 1
                    else:
                        continue
                else:
                    trib_imported += 1

                inftype = detect_infraction_type(title)
                if inftype not in stats:
                    stats[inftype] = 0
                stats[inftype] += 1

                if trib_imported % 10 == 0 and trib_imported > 0:
                    print(f"    ... {trib_imported} importés | {trib_filtered} filtrés | "
                          f"{trib_skipped} existants | Quota: {limiter.remaining()}")

            offset += args.page_size

            if limiter.remaining() < 10:
                break

        total_imported += trib_imported
        total_skipped += trib_skipped
        total_filtered += trib_filtered
        print(f"  >>> {db_id}: +{trib_imported} importés | {trib_filtered} filtrés | "
              f"{trib_skipped} existants")

        if limiter.remaining() < 10:
            print(f"\n[STOP GLOBAL] Quota épuisé — {limiter.count} requêtes utilisées")
            break

    conn.close()

    # Résumé final
    print(f"\n{'='*60}")
    print(f"  RÉSUMÉ IMPORT CANLII")
    print(f"{'='*60}")
    print(f"  Nouveaux dossiers:  {total_imported}")
    print(f"  Filtrés (hors-sujet): {total_filtered}")
    print(f"  Déjà existants:    {total_skipped}")
    print(f"  Requêtes utilisées: {limiter.count}/{args.max_requests}")
    print(f"  Total en DB:       {len(existing_ids)}")
    print(f"\n  Par type d'infraction:")
    for inftype, count in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"    {inftype:25s} {count:>6}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
