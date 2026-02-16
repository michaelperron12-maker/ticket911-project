#!/usr/bin/env python3
"""
Import — Google Scholar Case Law
Scrape decisions traffic QC + ON depuis Google Scholar
Usage: python3 import_scholar_cases.py [--dry-run] [--max-pages 5] [--province QC|ON|all]
"""

import os
import sys
import json
import time
import re
import random
import argparse
import requests
import psycopg2
from datetime import datetime
from html import unescape

# ═══════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════
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

LOGDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOGDIR, exist_ok=True)

# Requetes de recherche Google Scholar Case Law
SEARCH_QUERIES = {
    'QC': [
        # Francais — infractions routieres QC
        '"excès de vitesse" constat infraction',
        '"code de la sécurité routière" acquitté',
        '"cellulaire au volant" cour municipale',
        '"alcool au volant" facultés affaiblies québec',
        '"radar photographique" contestation',
        '"feu rouge" infraction circulation',
        '"ceinture de sécurité" constat',
        '"conduite dangereuse" québec coupable',
        'SAAQ "points d\'inaptitude" tribunal',
        '"permis de conduire" révocation SAAQ',
        '"constat d\'infraction" vice forme',
        '"cour municipale" vitesse acquitté',
        '"grand excès de vitesse" québec',
        '"délit de fuite" code routière',
    ],
    'ON': [
        # Anglais — traffic offences ON
        '"Highway Traffic Act" speeding dismissed',
        '"stunt driving" Ontario "not guilty"',
        '"impaired driving" Ontario acquitted',
        '"red light camera" Ontario appeal',
        '"careless driving" Ontario court',
        '"distracted driving" cellphone Ontario',
        '"Provincial Offences Act" traffic',
        '"radar" speeding Ontario dismissed',
        '"suspended licence" driving Ontario',
        '"dangerous driving" Ontario guilty',
    ],
}

# Headers pour eviter blocage
HEADERS_LIST = [
    {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'fr-CA,fr;q=0.9,en;q=0.5',
    },
    {
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-CA,en;q=0.9,fr;q=0.5',
    },
]

SCHOLAR_URL = "https://scholar.google.com/scholar"


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def strip_html(text):
    """Retirer les tags HTML"""
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', ' ', unescape(text))
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


def extract_cases_from_html(html_content):
    """Extraire les cas depuis le HTML de Google Scholar"""
    cases = []

    # Pattern pour les resultats Scholar
    # Chaque resultat est dans un div avec class="gs_r gs_or gs_scl"
    results = re.findall(
        r'<div[^>]*class="gs_r gs_or gs_scl"[^>]*>(.*?)</div>\s*</div>\s*</div>',
        html_content, re.DOTALL
    )

    if not results:
        # Fallback: chercher les titres de resultats
        results = re.findall(
            r'<h3[^>]*class="gs_rt"[^>]*>(.*?)</h3>.*?<div[^>]*class="gs_rs"[^>]*>(.*?)</div>',
            html_content, re.DOTALL
        )
        for title_html, snippet_html in results:
            # Extraire URL
            url_match = re.search(r'href="([^"]+)"', title_html)
            url = url_match.group(1) if url_match else ''

            title = strip_html(title_html)
            snippet = strip_html(snippet_html)

            if title:
                cases.append({
                    'title': title,
                    'url': url,
                    'snippet': snippet,
                })
    else:
        for block in results:
            # Titre
            title_match = re.search(r'<h3[^>]*class="gs_rt"[^>]*>(.*?)</h3>', block, re.DOTALL)
            title = strip_html(title_match.group(1)) if title_match else ''

            # URL
            url_match = re.search(r'<h3[^>]*class="gs_rt"[^>]*>.*?href="([^"]+)"', block, re.DOTALL)
            url = url_match.group(1) if url_match else ''

            # Snippet
            snippet_match = re.search(r'<div[^>]*class="gs_rs"[^>]*>(.*?)</div>', block, re.DOTALL)
            snippet = strip_html(snippet_match.group(1)) if snippet_match else ''

            # Citation info
            cite_match = re.search(r'<div[^>]*class="gs_a"[^>]*>(.*?)</div>', block, re.DOTALL)
            cite_info = strip_html(cite_match.group(1)) if cite_match else ''

            if title:
                cases.append({
                    'title': title,
                    'url': url,
                    'snippet': snippet,
                    'cite_info': cite_info,
                })

    return cases


def extract_citation(title, cite_info=''):
    """Extraire la citation juridique du titre ou info"""
    text = title + ' ' + cite_info
    # Patterns citations canadiennes
    patterns = [
        r'(\d{4}\s+[A-Z]{2,6}\s+\d+)',       # 2024 QCCA 123
        r'(\d{4}\s+CanLII\s+\d+)',              # 2024 CanLII 12345
        r'(\[\d{4}\]\s+\d+\s+[A-Z.]+\s+\d+)',  # [2024] 1 S.C.R. 123
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return ''


def extract_date_from_cite(cite_info):
    """Extraire la date depuis les infos de citation"""
    if not cite_info:
        return None
    # Chercher annee
    m = re.search(r'(\d{4})', cite_info)
    if m:
        year = int(m.group(1))
        if 1990 <= year <= 2030:
            return f"{year}-01-01"
    return None


def detect_tribunal_scholar(title, cite_info=''):
    """Detecter le tribunal depuis Scholar"""
    text = (title + ' ' + cite_info).lower()
    if 'qcca' in text or "cour d'appel" in text:
        return "qcca"
    if 'qccs' in text or "cour supérieure" in text or "superior court" in text:
        return "qccs"
    if 'qccq' in text or "cour du québec" in text:
        return "qccq"
    if 'qccm' in text or "cour municipale" in text or "municipal court" in text:
        return "qccm"
    if 'qctaq' in text or "tribunal administratif" in text:
        return "qctaq"
    if 'oncj' in text or "ontario court of justice" in text:
        return "oncj"
    if 'onca' in text or "court of appeal for ontario" in text:
        return "onca"
    if 'onscdc' in text or "divisional court" in text:
        return "onscdc"
    return "inconnu"


def detect_resultat(text):
    t = text.lower()
    if any(w in t for w in ["acquitté", "acquitted", "not guilty", "non coupable", "dismissed"]):
        return "acquitte"
    if any(w in t for w in ["rejeté", "rejected"]):
        return "rejete"
    if any(w in t for w in ["coupable", "guilty", "convicted", "condamné"]):
        return "coupable"
    if any(w in t for w in ["réduit", "reduced"]):
        return "reduit"
    return "inconnu"


def search_scholar(query, start=0):
    """Rechercher sur Google Scholar Case Law"""
    params = {
        'q': query,
        'hl': 'fr',
        'as_sdt': '2006',  # Case law only
        'start': start,
    }

    headers = random.choice(HEADERS_LIST)

    try:
        r = requests.get(SCHOLAR_URL, params=params, headers=headers, timeout=30)
        if r.status_code == 429:
            print("    [THROTTLE] Google Scholar rate limit — pause 60s")
            time.sleep(60)
            return None
        if r.status_code != 200:
            print(f"    [WARN] HTTP {r.status_code}")
            return []
        return extract_cases_from_html(r.text)
    except Exception as e:
        print(f"    [ERR] {e}")
        return []


# ═══════════════════════════════════════════════════════════
# IMPORT
# ═══════════════════════════════════════════════════════════

def import_scholar(conn, dry_run=False, max_pages=3, provinces=None):
    """Import cas depuis Google Scholar"""
    print("\n" + "=" * 60)
    print("  GOOGLE SCHOLAR — Case Law Traffic")
    print("=" * 60)

    if provinces is None:
        provinces = ['QC', 'ON']

    cur = conn.cursor()

    # IDs existants
    cur.execute("SELECT url_canlii FROM jurisprudence WHERE source = 'google-scholar'")
    existing_urls = {row[0] for row in cur.fetchall()}
    print(f"  Deja en DB (google-scholar): {len(existing_urls)}")

    total_inserted = 0
    total_fetched = 0
    total_skipped = 0

    for province in provinces:
        queries = SEARCH_QUERIES.get(province, [])
        lang = 'fr' if province == 'QC' else 'en'

        print(f"\n  Province: {province} — {len(queries)} requetes")

        for qi, query in enumerate(queries):
            print(f"\n  [{qi+1}/{len(queries)}] {query[:60]}...")

            for page in range(max_pages):
                start = page * 10
                cases = search_scholar(query, start)

                if cases is None:  # Rate limited
                    print("  [STOP] Rate limit — arret pour cette session")
                    break

                if not cases:
                    break

                total_fetched += len(cases)

                for case in cases:
                    url = case.get('url', '')
                    title = case.get('title', '')
                    cite_info = case.get('cite_info', '')

                    if not url or url in existing_urls:
                        total_skipped += 1
                        continue

                    citation = extract_citation(title, cite_info)
                    tribunal = detect_tribunal_scholar(title, cite_info)
                    resultat = detect_resultat(title + ' ' + case.get('snippet', ''))
                    decision_date = extract_date_from_cite(cite_info)

                    scholar_id = f"scholar-{hash(url) & 0xFFFFFFFF:08x}"

                    if dry_run:
                        print(f"    [DRY] {title[:70]}")
                        total_inserted += 1
                        continue

                    try:
                        cur.execute("""
                            INSERT INTO jurisprudence
                                (canlii_id, database_id, province, titre, citation,
                                 date_decision, url_canlii, tribunal, langue,
                                 mots_cles, resume, resultat, est_ticket_related,
                                 source, raw_metadata, imported_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                            ON CONFLICT (canlii_id) DO NOTHING
                        """, (
                            scholar_id, tribunal, province, title, citation,
                            decision_date, url, tribunal, lang,
                            [], case.get('snippet', '')[:5000],
                            resultat, True,
                            'google-scholar',
                            json.dumps(case, ensure_ascii=False, default=str),
                        ))
                        conn.commit()
                        existing_urls.add(url)
                        total_inserted += 1
                        print(f"    + {title[:65]}")
                    except Exception as e:
                        conn.rollback()
                        print(f"    [ERR] {e}")

                # Delai entre pages — respecter Google
                delay = random.uniform(8, 15)
                print(f"    Page {page+1}: {len(cases)} resultats — pause {delay:.0f}s")
                time.sleep(delay)

            # Delai entre requetes
            time.sleep(random.uniform(5, 10))

    print(f"\n  TOTAL: {total_fetched} fetch, {total_inserted} inseres, {total_skipped} deja existants")

    # Log
    try:
        cur.execute("""
            INSERT INTO data_source_log
                (source_name, source_url, module_name, records_fetched, records_inserted,
                 completed_at, status)
            VALUES (%s, %s, %s, %s, %s, NOW(), %s)
        """, ("google-scholar", "scholar.google.com", "import_scholar_cases",
              total_fetched, total_inserted, "done"))
        conn.commit()
    except Exception:
        conn.rollback()

    return total_inserted


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Import Google Scholar case law")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-pages", type=int, default=3,
                        help="Max pages par requete (default: 3, = 30 resultats)")
    parser.add_argument("--province", type=str, default="all",
                        help="Province: QC|ON|all")
    args = parser.parse_args()

    provinces = ['QC', 'ON'] if args.province == 'all' else [args.province.upper()]

    print("=" * 60)
    print("  IMPORT GOOGLE SCHOLAR CASE LAW")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'PRODUCTION'}")
    print(f"  Max pages: {args.max_pages}")
    print(f"  Provinces: {provinces}")
    print("=" * 60)

    conn = psycopg2.connect(**PG_CONFIG)
    try:
        count = import_scholar(conn, args.dry_run, args.max_pages, provinces)
    finally:
        conn.close()

    with open(os.path.join(LOGDIR, "scholar_usage.json"), "w") as f:
        json.dump({
            "last_update": datetime.now().isoformat(),
            "inserted": count,
            "provinces": provinces,
        }, f)

    print(f"\nTermine — {count} cas importes")


if __name__ == "__main__":
    main()
