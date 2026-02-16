#!/usr/bin/env python3
"""
Import — Donnees ouvertes Montreal
Sources: collisions routieres SPVM, escouade mobilite
API: CKAN Datastore (donnees.montreal.ca)
Usage: python3 import_donnees_mtl.py [--dry-run] [--source collisions|escouade|all]
"""

import os
import sys
import json
import time
import argparse
import requests
import psycopg2
import psycopg2.extras
from datetime import datetime

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

MTL_API = "https://donnees.montreal.ca/api/3/action"

# Resource IDs
MTL_COLLISIONS_RID = "05deae93-d9fc-4acb-9779-e0942b5e962f"
MTL_ESCOUADE_RID = "ff81ecc4-d3b0-4661-806f-a27870e63a4e"

LOGDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOGDIR, exist_ok=True)


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def fetch_mtl_datastore(resource_id, batch=32000):
    """Fetch tous les records d'un resource CKAN Montreal"""
    all_records = []
    offset = 0
    while True:
        try:
            r = requests.get(f"{MTL_API}/datastore_search", params={
                "resource_id": resource_id, "limit": batch, "offset": offset
            }, timeout=120)
            if r.status_code != 200:
                print(f"    [ERR] HTTP {r.status_code}")
                break
            result = r.json().get("result", {})
            records = result.get("records", [])
            total = result.get("total", 0)
            all_records.extend(records)
            print(f"    Fetch {len(all_records)}/{total}")
            if len(records) < batch:
                break
            offset += batch
            time.sleep(0.5)
        except Exception as e:
            print(f"    [ERR] {e}")
            break
    return all_records


def safe_int(val, default=None):
    if val is None or val == '' or val == 'null':
        return default
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return default


def safe_float(val, default=None):
    if val is None or val == '' or val == 'null':
        return default
    try:
        return float(str(val).strip().replace(',', '.'))
    except (ValueError, TypeError):
        return default


def safe_date(val):
    if not val or val == 'null':
        return None
    for fmt in ('%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%d/%m/%Y'):
        try:
            return datetime.strptime(str(val).strip()[:10], fmt).date()
        except ValueError:
            continue
    return None


def safe_time(val):
    if not val or val == 'null':
        return None
    try:
        v = str(val).strip()
        if ':' in v:
            parts = v.split(':')
            return f"{int(parts[0]):02d}:{int(parts[1]):02d}:00"
        elif len(v) == 4 and v.isdigit():
            return f"{v[:2]}:{v[2:]}:00"
    except Exception:
        pass
    return None


def log_import(conn, source_name, module, fetched, inserted, status, error=None):
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO data_source_log
                (source_name, source_url, module_name, records_fetched, records_inserted,
                 completed_at, status, error_message)
            VALUES (%s, %s, %s, %s, %s, NOW(), %s, %s)
        """, (source_name, "donnees.montreal.ca", module, fetched, inserted, status, error))
        conn.commit()
    except Exception:
        conn.rollback()


# ═══════════════════════════════════════════════════════════
# 1. COLLISIONS ROUTIERES MONTREAL
# ═══════════════════════════════════════════════════════════

def import_collisions_mtl(conn, dry_run=False):
    """Import collisions routieres depuis donnees.montreal.ca"""
    print("\n" + "=" * 60)
    print("  COLLISIONS ROUTIERES — Montreal (SPVM/SAAQ)")
    print("=" * 60)

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM mtl_collisions")
    existing = cur.fetchone()[0]
    print(f"  Deja en DB: {existing}")

    records = fetch_mtl_datastore(MTL_COLLISIONS_RID)
    print(f"  {len(records)} records telecharges")

    if dry_run or not records:
        return len(records)

    # Truncate et reimporter (dataset complet qui se met a jour)
    if existing > 0:
        cur.execute("TRUNCATE TABLE mtl_collisions")
        conn.commit()
        print("  Table truncated (reimport complet)")

    inserted = 0
    for rec in records:
        try:
            no_coll = rec.get('NO_SEQ_COLL', '')
            cur.execute("""
                INSERT INTO mtl_collisions
                    (no_collision, date_collision, heure_collision,
                     rue1, rue2, latitude, longitude,
                     gravite, nombre_deces, nombre_blesses_graves,
                     nombre_blesses_legers, type_collision,
                     conditions_meteo, etat_surface, eclairage,
                     raw_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (no_collision) DO NOTHING
            """, (
                no_coll,
                safe_date(rec.get('DT_ACCDN')),
                safe_time(rec.get('HEURE_ACCDN')),
                rec.get('RUE_ACCDN', ''),
                rec.get('ACCDN_PRES_DE', ''),
                safe_float(rec.get('LOC_LAT')),
                safe_float(rec.get('LOC_LONG')),
                rec.get('GRAVITE', ''),
                safe_int(rec.get('NB_MORTS', 0), 0),
                safe_int(rec.get('NB_BLESSES_GRAVES', 0), 0),
                safe_int(rec.get('NB_BLESSES_LEGERS', 0), 0),
                rec.get('CD_GENRE_ACCDN', ''),
                rec.get('CD_COND_METEO', ''),
                rec.get('CD_ETAT_SURFC', ''),
                rec.get('CD_ECLRM', ''),
                json.dumps(rec, ensure_ascii=False, default=str),
            ))
            inserted += 1
            if inserted % 10000 == 0:
                conn.commit()
                print(f"    ... {inserted} inseres")
        except Exception as e:
            conn.rollback()
            if inserted == 0:
                print(f"    [ERR] {e}")
            continue

    conn.commit()
    print(f"  +{inserted} inseres")
    log_import(conn, "collisions-mtl", "import_donnees_mtl", len(records), inserted, "done")
    return inserted


# ═══════════════════════════════════════════════════════════
# 2. ESCOUADE MOBILITE MONTREAL
# ═══════════════════════════════════════════════════════════

def import_escouade(conn, dry_run=False):
    """Import interventions escouade mobilite Montreal"""
    print("\n" + "=" * 60)
    print("  ESCOUADE MOBILITE — Montreal")
    print("=" * 60)

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM mtl_escouade_mobilite")
    existing = cur.fetchone()[0]
    print(f"  Deja en DB: {existing}")

    records = fetch_mtl_datastore(MTL_ESCOUADE_RID)
    print(f"  {len(records)} records telecharges")

    if dry_run or not records:
        return len(records)

    # Truncate et reimporter
    if existing > 0:
        cur.execute("TRUNCATE TABLE mtl_escouade_mobilite")
        conn.commit()
        print("  Table truncated (reimport complet)")

    inserted = 0
    for rec in records:
        try:
            cur.execute("""
                INSERT INTO mtl_escouade_mobilite
                    (date_intervention, type_intervention, lieu, raw_data)
                VALUES (%s, %s, %s, %s)
            """, (
                safe_date(rec.get('DATE')),
                rec.get('NATURE INTERVENTION', rec.get('NATURE_INTERVENTION', '')),
                rec.get('ADRESSE', ''),
                json.dumps(rec, ensure_ascii=False, default=str),
            ))
            inserted += 1
            if inserted % 5000 == 0:
                conn.commit()
                print(f"    ... {inserted} inseres")
        except Exception as e:
            conn.rollback()
            if inserted == 0:
                print(f"    [ERR] {e}")
            continue

    conn.commit()
    print(f"  +{inserted} inseres")
    log_import(conn, "escouade-mobilite-mtl", "import_donnees_mtl", len(records), inserted, "done")
    return inserted


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Import Donnees ouvertes Montreal")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source", type=str, default="all",
                        help="Source: collisions|escouade|all")
    args = parser.parse_args()

    print("=" * 60)
    print("  IMPORT DONNEES OUVERTES MONTREAL")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'PRODUCTION'}")
    print("=" * 60)

    conn = psycopg2.connect(**PG_CONFIG)
    results = {}

    try:
        if args.source in ('all', 'collisions'):
            results['collisions_mtl'] = import_collisions_mtl(conn, args.dry_run)

        if args.source in ('all', 'escouade'):
            results['escouade_mobilite'] = import_escouade(conn, args.dry_run)
    finally:
        conn.close()

    print(f"\n{'=' * 60}")
    print("  RESUME IMPORT MONTREAL")
    print(f"{'=' * 60}")
    for src, count in results.items():
        print(f"  {src:25s} {count:>8} records")
    total = sum(results.values())
    print(f"  {'TOTAL':25s} {total:>8} records")
    print(f"{'=' * 60}")

    with open(os.path.join(LOGDIR, "donnees_mtl_usage.json"), "w") as f:
        json.dump({
            "last_update": datetime.now().isoformat(),
            "results": results,
            "total": total,
        }, f)


if __name__ == "__main__":
    main()
