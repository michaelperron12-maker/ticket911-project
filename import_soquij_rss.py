#!/usr/bin/env python3
"""
Import — SOQUIJ RSS Decisions vedettes
Source: blogue.soquij.qc.ca/decisions/feed/
Filtre: decisions liees au traffic routier
Usage: python3 import_soquij_rss.py [--dry-run]
"""

import os
import sys
import json
import re
import argparse
import requests
import psycopg2
import xml.etree.ElementTree as ET
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

# RSS Feeds SOQUIJ
RSS_FEEDS = [
    {
        "name": "Decisions vedettes",
        "url": "https://blogue.soquij.qc.ca/decisions/feed/",
        "filter_traffic": True,
    },
    {
        "name": "Blogue SOQUIJ",
        "url": "https://blogue.soquij.qc.ca/feed/",
        "filter_traffic": True,
    },
]

# Mots-cles traffic pour filtrage
TRAFFIC_KEYWORDS = [
    "vitesse", "excès de vitesse", "radar", "cinémomètre", "photo radar",
    "cellulaire", "téléphone", "distraction", "texting",
    "alcool", "alcootest", "ivresse", "ébriété", "facultés affaiblies",
    "capacité affaiblie", "alcoolémie",
    "feu rouge", "stop", "arrêt", "ceinture",
    "conduite dangereuse", "délit de fuite",
    "permis", "suspension", "révocation", "points d'inaptitude",
    "sécurité routière", "code de la route", "C.S.R.", "CSR",
    "SAAQ", "constat d'infraction", "constat",
    "infraction", "contravention", "amende",
    "conduite", "véhicule", "automobile", "circulation",
    "Highway Traffic", "HTA", "impaired", "DUI",
    "speeding", "traffic", "driving",
]

LOGDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOGDIR, exist_ok=True)


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


def is_traffic_related(title, description):
    """Verifier si le contenu est lie au traffic"""
    text = (title + " " + description).lower()
    return any(kw.lower() in text for kw in TRAFFIC_KEYWORDS)


def detect_tribunal(text):
    """Detecter le tribunal a partir du texte"""
    t = text.lower()
    if "cour d'appel" in t or "court of appeal" in t:
        return "qcca"
    if "cour supérieure" in t or "superior court" in t:
        return "qccs"
    if "cour du québec" in t or "court of quebec" in t:
        return "qccq"
    if "cour municipale" in t or "municipal court" in t:
        return "qccm"
    if "tribunal administratif" in t or "taq" in t:
        return "qctaq"
    if "tribunal des droits" in t:
        return "qctdp"
    return "qc-autre"


def detect_resultat(text):
    """Detecter le resultat"""
    t = text.lower()
    if any(w in t for w in ["acquitté", "acquitte", "acquitted", "not guilty", "non coupable"]):
        return "acquitte"
    if any(w in t for w in ["rejeté", "rejete", "rejected", "dismissed"]):
        return "rejete"
    if any(w in t for w in ["coupable", "guilty", "condamné", "convicted"]):
        return "coupable"
    if any(w in t for w in ["réduit", "reduit", "reduced"]):
        return "reduit"
    return "inconnu"


def parse_rss(url):
    """Parser un feed RSS et retourner les items"""
    try:
        r = requests.get(url, timeout=30, headers={
            'User-Agent': 'AITicketInfo/1.0 (jurisprudence research)'
        })
        r.raise_for_status()
    except Exception as e:
        print(f"  [ERR] Fetch RSS: {e}")
        return []

    items = []
    try:
        root = ET.fromstring(r.content)

        # Namespace RSS standard
        ns = {'content': 'http://purl.org/rss/1.0/modules/content/',
              'dc': 'http://purl.org/dc/elements/1.1/'}

        for item in root.findall('.//item'):
            title = item.findtext('title', '')
            link = item.findtext('link', '')
            pub_date = item.findtext('pubDate', '')
            description = strip_html(item.findtext('description', ''))

            # Contenu complet si disponible
            content_encoded = item.findtext('content:encoded', '', ns)
            full_content = strip_html(content_encoded) if content_encoded else description

            # Categories/tags
            categories = [cat.text for cat in item.findall('category') if cat.text]

            # Date
            decision_date = None
            if pub_date:
                for fmt in ('%a, %d %b %Y %H:%M:%S %z',
                            '%a, %d %b %Y %H:%M:%S %Z',
                            '%Y-%m-%dT%H:%M:%S'):
                    try:
                        decision_date = datetime.strptime(pub_date.strip(), fmt).date()
                        break
                    except ValueError:
                        continue

            items.append({
                'title': title,
                'link': link,
                'date': decision_date,
                'description': description,
                'full_content': full_content[:10000],  # cap
                'categories': categories,
            })
    except ET.ParseError as e:
        print(f"  [ERR] Parse XML: {e}")

    return items


# ═══════════════════════════════════════════════════════════
# IMPORT
# ═══════════════════════════════════════════════════════════

def import_soquij_rss(conn, dry_run=False):
    """Import decisions depuis RSS SOQUIJ"""
    print("\n" + "=" * 60)
    print("  SOQUIJ RSS — Decisions vedettes")
    print("=" * 60)

    cur = conn.cursor()

    # IDs existants (par URL pour dedoublonner)
    cur.execute("SELECT url_canlii FROM jurisprudence WHERE source = 'soquij-rss'")
    existing_urls = {row[0] for row in cur.fetchall()}
    print(f"  Deja en DB (soquij-rss): {len(existing_urls)}")

    total_fetched = 0
    total_inserted = 0
    total_filtered = 0

    for feed in RSS_FEEDS:
        print(f"\n  Feed: {feed['name']}")
        print(f"  URL: {feed['url']}")

        items = parse_rss(feed['url'])
        total_fetched += len(items)
        print(f"  {len(items)} items")

        for item in items:
            url = item['link']
            title = item['title']
            desc = item['description']

            # Skip si deja importe
            if url in existing_urls:
                continue

            # Filtrer traffic si demande
            if feed.get('filter_traffic') and not is_traffic_related(title, desc):
                total_filtered += 1
                continue

            # Generer un ID unique
            soquij_id = f"soquij-{hash(url) & 0xFFFFFFFF:08x}"

            tribunal = detect_tribunal(title + " " + desc)
            resultat = detect_resultat(title + " " + desc)
            mots_cles = item['categories'] if item['categories'] else []

            if dry_run:
                print(f"    [DRY] {title[:80]}")
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
                    soquij_id, tribunal, 'QC', title, '',
                    item['date'], url, tribunal, 'fr',
                    mots_cles, desc[:5000], resultat, True,
                    'soquij-rss',
                    json.dumps({
                        'title': title,
                        'url': url,
                        'date': str(item['date']),
                        'categories': mots_cles,
                        'content_preview': item['full_content'][:2000],
                    }, ensure_ascii=False, default=str),
                ))
                conn.commit()
                existing_urls.add(url)
                total_inserted += 1
                print(f"    + {title[:70]}")
            except Exception as e:
                conn.rollback()
                print(f"    [ERR] {e}")

    print(f"\n  TOTAL: {total_fetched} fetch, {total_inserted} inseres, {total_filtered} filtres")

    # Log
    try:
        cur.execute("""
            INSERT INTO data_source_log
                (source_name, source_url, module_name, records_fetched, records_inserted,
                 completed_at, status)
            VALUES (%s, %s, %s, %s, %s, NOW(), %s)
        """, ("soquij-rss", "blogue.soquij.qc.ca", "import_soquij_rss",
              total_fetched, total_inserted, "done"))
        conn.commit()
    except Exception:
        conn.rollback()

    return total_inserted


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Import SOQUIJ RSS decisions")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("  IMPORT SOQUIJ RSS")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'PRODUCTION'}")
    print("=" * 60)

    conn = psycopg2.connect(**PG_CONFIG)
    try:
        count = import_soquij_rss(conn, args.dry_run)
    finally:
        conn.close()

    with open(os.path.join(LOGDIR, "soquij_rss_usage.json"), "w") as f:
        json.dump({
            "last_update": datetime.now().isoformat(),
            "inserted": count,
        }, f)

    print(f"\nTermine — {count} decisions importees")


if __name__ == "__main__":
    main()
