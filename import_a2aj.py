#!/usr/bin/env python3
"""
import_a2aj.py — Importateur A2AJ (Access to Algorithmic Justice)
Source complementaire a CanLII pour jurisprudence traffic.
v2: format correct (citation_en, name_en, etc.)
"""

import os
import sys
import re
import json
import time
import requests
import psycopg2
from datetime import datetime

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

A2AJ_BASE = "https://api.a2aj.ca"
LOG_FILE = "/var/www/aiticketinfo/logs/import_a2aj.log"
STATE_FILE = "/var/www/aiticketinfo/db/a2aj_import_state.json"

SLEEP_BETWEEN = 1
SLEEP_FETCH = 1
MAX_PER_QUERY = 50
DATASETS = "ONCA,SCC,FCA,FC,BCCA,BCSC"

SEARCH_QUERIES = [
    "speeding OR speed limit OR radar",
    "traffic ticket OR traffic offence OR traffic violation",
    "highway traffic act OR HTA",
    "impaired driving OR drunk driving OR DUI OR DWI",
    "dangerous driving OR careless driving OR stunt driving",
    "red light OR stop sign OR traffic signal",
    "cell phone driving OR distracted driving",
    "seatbelt OR seat belt violation",
    "licence suspension OR driving suspension",
    "breathalyzer OR breath sample OR blood alcohol",
    "motor vehicle accident OR collision",
    "parking violation OR parking ticket",
    "racing OR street racing",
    "fail to stop OR hit and run OR leaving scene",
    "demerit points OR driving record",
]

CITATION_TO_DB = {
    "QCCM": "qccm", "QCCQ": "qccq", "QCCS": "qccs", "QCCA": "qcca",
    "QCCTQ": "qcctq", "QCTAQ": "qctaq",
    "ONCJ": "oncj", "ONSCDC": "onscdc", "ONCA": "onca", "ONSC": "onsc",
    "FC": "fc", "FCA": "fca", "SCC": "scc", "CSC": "csc",
    "BCCA": "bcca", "BCSC": "bcsc",
    "CHRT": "chrt", "CMAC": "cmac", "TCC": "tcc",
}

RESULTAT_KW = {
    "acquitte": ["acquitted", "not guilty", "acquitté", "appeal allowed", "conviction overturned", "accueilli"],
    "coupable": ["guilty", "convicted", "conviction upheld", "appeal dismissed", "coupable"],
    "rejete": ["dismissed", "rejected", "struck", "rejeté", "irrecevable"],
    "reduit": ["reduced", "lesser", "sentence reduced", "réduit"],
}


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
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


def detect_province(db_id):
    if not db_id:
        return "CA"
    prov = {
        "qccm": "QC", "qccq": "QC", "qccs": "QC", "qcca": "QC",
        "oncj": "ON", "onscdc": "ON", "onca": "ON", "onsc": "ON",
        "bcca": "BC", "bcsc": "BC",
        "fc": "CA", "fca": "CA", "scc": "CA", "csc": "CA",
        "chrt": "CA", "cmac": "CA", "tcc": "CA",
    }
    return prov.get(db_id, "CA")


def detect_resultat(text):
    t = (text or "").lower()
    for res, kws in RESULTAT_KW.items():
        for kw in kws:
            if kw.lower() in t:
                return res
    return "inconnu"


def search_a2aj(query):
    params = {
        "query": query, "doc_type": "cases", "size": MAX_PER_QUERY,
        "search_language": "en", "sort_results": "newest_first",
        "dataset": DATASETS,
    }
    try:
        r = requests.get(f"{A2AJ_BASE}/search", params=params, timeout=30)
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception as e:
        log(f"  Erreur recherche: {e}")
        return []


def fetch_case_text(citation):
    try:
        r = requests.get(f"{A2AJ_BASE}/fetch", params={
            "citation": citation, "doc_type": "cases",
            "output_language": "both", "end_char": 6000,
        }, timeout=30)
        r.raise_for_status()
        return r.json().get("text", "")
    except Exception as e:
        log(f"    Fetch erreur {citation}: {e}")
        return ""


def main():
    log("=" * 60)
    log("IMPORT A2AJ v2 — Demarrage")
    log(f"  {len(SEARCH_QUERIES)} queries, datasets: {DATASETS}")
    log("=" * 60)

    conn = get_conn()
    cur = conn.cursor()

    total_imported = 0
    total_skipped = 0
    total_errors = 0
    seen = set()

    for qi, query in enumerate(SEARCH_QUERIES):
        log(f"\n--- Query {qi+1}/{len(SEARCH_QUERIES)}: {query[:50]} ---")
        results = search_a2aj(query)
        log(f"  {len(results)} resultats A2AJ")

        imported_q = 0
        skipped_q = 0

        for case in results:
            # A2AJ format: citation_en, name_en, document_date_en, snippet
            citation = case.get("citation_en", "")
            if not citation or citation in seen:
                continue
            seen.add(citation)

            # Check duplicates
            cur.execute("SELECT 1 FROM jurisprudence WHERE citation = %s LIMIT 1", (citation,))
            if cur.fetchone():
                skipped_q += 1
                continue

            # Extract data
            title_en = case.get("name_en", "")
            title_fr = case.get("name_fr", "")
            titre = title_fr if title_fr else title_en
            date_str = case.get("document_date_en", "")
            snippet = case.get("snippet", "")
            dataset = case.get("dataset", "")
            url = case.get("url_en", "")

            # Fetch full text for resume
            full_text = fetch_case_text(citation)
            time.sleep(SLEEP_FETCH)

            resume = full_text[:2000] if full_text else snippet
            db_id = extract_db_id(citation) or dataset.lower()
            province = detect_province(db_id)
            resultat = detect_resultat(f"{titre} {resume}")

            # Year
            year = None
            m = re.search(r'(\d{4})\s+[A-Z]+\s+\d+', citation)
            if m:
                year = int(m.group(1))

            # Date
            date_decision = None
            if date_str:
                try:
                    date_decision = datetime.fromisoformat(date_str.replace("+00:00", "")).date()
                except Exception:
                    pass

            # Mots-cles
            mots_cles = list(set(
                w for w in re.findall(r'\b\w+\b', titre.lower())
                if len(w) > 3 and w not in ("the", "and", "for", "that", "this", "with", "from", "dans", "pour", "avec")
            ))[:20]

            try:
                cur.execute("""
                    INSERT INTO jurisprudence
                        (citation, titre, resume, database_id, province, resultat,
                         date_decision, mots_cles, est_ticket_related, source, url_canlii)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, true, 'a2aj', %s)
                    RETURNING id
                """, (citation, titre, resume, db_id, province, resultat,
                      date_decision, mots_cles, url))
                result = cur.fetchone()
                if result:
                    imported_q += 1
                    total_imported += 1
                conn.commit()
            except Exception as e:
                conn.rollback()
                log(f"    Erreur insert {citation}: {e}")
                total_errors += 1

        total_skipped += skipped_q
        log(f"  Importes: {imported_q} | Deja existants: {skipped_q}")
        time.sleep(SLEEP_BETWEEN)

    cur.close()
    conn.close()

    # State
    state = {
        "last_run": datetime.now().isoformat(),
        "imported": total_imported,
        "skipped": total_skipped,
        "errors": total_errors,
        "citations_seen": len(seen),
    }
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass

    log(f"\n{'=' * 60}")
    log(f"IMPORT A2AJ — Termine")
    log(f"  Importes: {total_imported}")
    log(f"  Deja existants: {total_skipped}")
    log(f"  Erreurs: {total_errors}")
    log(f"  Citations uniques: {len(seen)}")
    log(f"{'=' * 60}")


if __name__ == "__main__":
    main()
