#!/usr/bin/env python3
"""
Import massif — Donnees ouvertes Quebec
Sources: constats infraction CRQ, radar photo stats, radar lieux, collisions SAAQ
API: CKAN Datastore (donneesquebec.ca) + WFS MTQ + S3 SAAQ
Usage: python3 import_donnees_qc.py [--dry-run] [--source constats|radars|lieux|collisions|all]
"""

import os
import sys
import json
import time
import argparse
import requests
import psycopg2
import psycopg2.extras
from datetime import datetime, date
from io import StringIO
import csv

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

QC_API = "https://www.donneesquebec.ca/recherche/api/3/action"
MTQ_WFS = "https://ws.mapserver.transports.gouv.qc.ca/swtq"

LOGDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOGDIR, exist_ok=True)

# Resource IDs par annee — Constats infraction CRQ (2012-2022)
CONSTATS_RESOURCES = {
    2022: "f729aed7-cdfd-49be-a234-db1e22e29740",
    2021: "3f917506-e6bd-44e4-ba45-7b33a7991c7d",
    2020: "2007fea7-9fad-4823-851b-2e5124a3687f",
    2019: "73ba424e-9525-4172-8dd9-7f9a3ddc2a2a",
    2018: "1fb6afc2-9100-4205-a39f-982fdbfa46b8",
    2017: "a6ffcd66-d6cb-438a-9172-615863b9c3f4",
    2016: "2598f77a-6a47-4583-827d-64f5e36657c3",
    2015: "691dccba-1d43-434d-bdde-d8503daa383f",
    2014: "9b442ef2-35ad-47bd-bc2d-168d4babdf47",
    2013: "ef029a35-ba32-47c1-917f-f253ab22cbf6",
    2012: "5785cb7d-38f2-4adb-a703-b072c0614b5e",
}

# Resource ID le plus recent pour radar photo stats
RADAR_STATS_LATEST = "12404555-0996-4396-a21e-d2bba5635a72"

# S3 URLs — Rapports accident SAAQ (2011-2022)
SAAQ_ACCIDENT_YEARS = list(range(2011, 2023))
SAAQ_S3_BASE = "https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Rapport_Accident_{year}.csv"


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def fetch_datastore(resource_id, batch=32000):
    """Fetch tous les records d'un resource CKAN datastore"""
    all_records = []
    offset = 0
    while True:
        try:
            r = requests.get(f"{QC_API}/datastore_search", params={
                "resource_id": resource_id, "limit": batch, "offset": offset
            }, timeout=120)
            if r.status_code != 200:
                print(f"    [ERR] HTTP {r.status_code} pour {resource_id}")
                break
            result = r.json().get("result", {})
            records = result.get("records", [])
            total = result.get("total", 0)
            all_records.extend(records)
            print(f"    Fetch {len(all_records)}/{total}")
            if len(records) < batch:
                break
            offset += batch
            time.sleep(0.5)  # politesse
        except Exception as e:
            print(f"    [ERR] {e}")
            break
    return all_records


def safe_int(val, default=None):
    """Convertir en int safe"""
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
    for fmt in ('%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%d/%m/%Y', '%Y%m%d'):
        try:
            return datetime.strptime(str(val).strip()[:10], fmt).date()
        except ValueError:
            continue
    return None


def log_import(conn, source_name, source_url, module, fetched, inserted, updated, status, error=None):
    """Log dans data_source_log"""
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO data_source_log
                (source_name, source_url, module_name, records_fetched, records_inserted,
                 records_updated, completed_at, status, error_message)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s, %s)
        """, (source_name, source_url, module, fetched, inserted, updated, status, error))
        conn.commit()
    except Exception:
        conn.rollback()


# ═══════════════════════════════════════════════════════════
# 1. CONSTATS D'INFRACTION CRQ
# ═══════════════════════════════════════════════════════════

def import_constats(conn, dry_run=False, years=None):
    """Import constats infraction depuis Donnees ouvertes QC"""
    print("\n" + "=" * 60)
    print("  CONSTATS D'INFRACTION — Controle routier Quebec")
    print("=" * 60)

    if years is None:
        years = sorted(CONSTATS_RESOURCES.keys())

    cur = conn.cursor()

    # Verifier quelles annees sont deja importees
    cur.execute("SELECT DISTINCT annee_donnees FROM qc_constats_infraction")
    existing_years = {row[0] for row in cur.fetchall()}
    cur.execute("SELECT COUNT(*) FROM qc_constats_infraction")
    existing_total = cur.fetchone()[0]
    print(f"  Deja en DB: {existing_total} records ({sorted(existing_years)})")

    total_inserted = 0
    total_fetched = 0

    for year in years:
        if year in existing_years:
            print(f"\n  [{year}] Deja importe — skip")
            continue

        resource_id = CONSTATS_RESOURCES.get(year)
        if not resource_id:
            continue

        print(f"\n  [{year}] Telechargement...")
        records = fetch_datastore(resource_id)
        total_fetched += len(records)

        if not records:
            print(f"  [{year}] Aucun record")
            continue

        print(f"  [{year}] {len(records)} records — insertion...")

        if dry_run:
            total_inserted += len(records)
            continue

        inserted = 0
        for rec in records:
            try:
                cur.execute("""
                    INSERT INTO qc_constats_infraction
                        (annee_donnees, date_infraction, region, lieu_infraction,
                         type_intervention, loi, article, description_infraction,
                         vitesse_permise, vitesse_constatee, categorie_vehicule,
                         raw_data, source_resource_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    year,
                    safe_date(rec.get('DAT_INFRA_COMMI')),
                    rec.get('COD_MUNI_LIEU', ''),
                    rec.get('COD_MUNI_LIEU', ''),
                    rec.get('TYP_DOCUM_INTRT', ''),
                    rec.get('CODE_LOI_REGLEMENT', ''),
                    rec.get('NO_ARTCL_L_R', ''),
                    rec.get('DESCN_CAT_INFRA', ''),
                    safe_int(rec.get('VITSS_PERMS')),
                    safe_int(rec.get('VITSS_CNSTA')),
                    rec.get('DESC_TYP_VEH_INFRA', ''),
                    json.dumps(rec, ensure_ascii=False, default=str),
                    resource_id
                ))
                inserted += 1
            except Exception as e:
                conn.rollback()
                if inserted == 0:
                    print(f"    [ERR] {e}")
                continue

        conn.commit()
        total_inserted += inserted
        print(f"  [{year}] +{inserted} inseres")
        log_import(conn, f"constats-crq-{year}",
                   f"donneesquebec.ca/{resource_id}", "import_donnees_qc",
                   len(records), inserted, 0, "done")

    print(f"\n  TOTAL: {total_fetched} fetch, {total_inserted} inseres")
    return total_inserted


# ═══════════════════════════════════════════════════════════
# 2. RADAR PHOTO STATS
# ═══════════════════════════════════════════════════════════

def import_radar_stats(conn, dry_run=False):
    """Import stats radar photo depuis Donnees ouvertes QC"""
    print("\n" + "=" * 60)
    print("  STATISTIQUES RADAR PHOTO — Quebec")
    print("=" * 60)

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM qc_radar_photo_stats")
    existing = cur.fetchone()[0]
    print(f"  Deja en DB: {existing}")

    # Truncate et reimporter (donnees cumulatives)
    if not dry_run and existing > 0:
        cur.execute("TRUNCATE TABLE qc_radar_photo_stats")
        conn.commit()
        print("  Table truncated (donnees cumulatives)")

    records = fetch_datastore(RADAR_STATS_LATEST, batch=5000)
    print(f"  {len(records)} records telecharges")

    if dry_run or not records:
        return len(records)

    inserted = 0
    for rec in records:
        try:
            moyen = rec.get('Moyen', '')
            type_app = 'Fixe' if moyen == 'CINP' else 'Mobile' if moyen == 'MOBL' else 'Feu rouge' if moyen == 'FERG' else moyen

            cur.execute("""
                INSERT INTO qc_radar_photo_stats
                    (date_rapport, type_appareil, localisation,
                     nombre_constats, raw_data, source_resource_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                safe_date(rec.get('Date')),
                type_app,
                rec.get('Site', ''),
                safe_int(rec.get('Nombre')),
                json.dumps(rec, ensure_ascii=False, default=str),
                RADAR_STATS_LATEST
            ))
            inserted += 1
        except Exception as e:
            conn.rollback()
            if inserted == 0:
                print(f"    [ERR] {e}")
            continue

    conn.commit()
    print(f"  +{inserted} inseres")
    log_import(conn, "radar-photo-stats", f"donneesquebec.ca/{RADAR_STATS_LATEST}",
               "import_donnees_qc", len(records), inserted, 0, "done")
    return inserted


# ═══════════════════════════════════════════════════════════
# 3. RADAR PHOTO EMPLACEMENTS (WFS MTQ)
# ═══════════════════════════════════════════════════════════

def import_radar_lieux(conn, dry_run=False):
    """Import emplacements radar photo depuis WFS MTQ"""
    print("\n" + "=" * 60)
    print("  EMPLACEMENTS RADAR PHOTO — MTQ WFS")
    print("=" * 60)

    cur = conn.cursor()

    # Telecharger CSV via WFS
    url = (f"{MTQ_WFS}?service=wfs&version=2.0.0&request=getfeature"
           f"&typename=ms:radars_photos&outfile=RadarPhoto&outputformat=csv")
    print(f"  Telechargement WFS...")

    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
    except Exception as e:
        print(f"  [ERR] {e}")
        return 0

    reader = csv.DictReader(StringIO(r.text))
    rows = list(reader)
    print(f"  {len(rows)} emplacements")

    if dry_run:
        return len(rows)

    # Truncate et reimporter
    cur.execute("TRUNCATE TABLE qc_radar_photo_lieux")
    conn.commit()

    inserted = 0
    for row in rows:
        try:
            cur.execute("""
                INSERT INTO qc_radar_photo_lieux
                    (type_appareil, municipalite, emplacement,
                     date_mise_service, actif, raw_data)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                row.get('typeAppareil', ''),
                row.get('municipalite', ''),
                row.get('description', ''),
                safe_date(row.get('dateDebutService')),
                not bool(row.get('dateFinService', '').strip()),
                json.dumps(row, ensure_ascii=False, default=str),
            ))
            inserted += 1
        except Exception as e:
            conn.rollback()
            if inserted == 0:
                print(f"    [ERR] {e}")
            continue

    conn.commit()
    print(f"  +{inserted} inseres")
    log_import(conn, "radar-photo-lieux", url, "import_donnees_qc",
               len(rows), inserted, 0, "done")
    return inserted


# ═══════════════════════════════════════════════════════════
# 4. COLLISIONS SAAQ (S3 CSV)
# ═══════════════════════════════════════════════════════════

def import_collisions_saaq(conn, dry_run=False, years=None):
    """Import rapports accident SAAQ depuis S3"""
    print("\n" + "=" * 60)
    print("  COLLISIONS SAAQ — Rapports accident")
    print("=" * 60)

    if years is None:
        years = SAAQ_ACCIDENT_YEARS

    cur = conn.cursor()
    cur.execute("SELECT DISTINCT annee FROM qc_collisions_saaq")
    existing_years = {row[0] for row in cur.fetchall()}
    cur.execute("SELECT COUNT(*) FROM qc_collisions_saaq")
    existing_total = cur.fetchone()[0]
    print(f"  Deja en DB: {existing_total} records ({sorted(existing_years)})")

    total_inserted = 0

    for year in years:
        if year in existing_years:
            print(f"\n  [{year}] Deja importe — skip")
            continue

        url = SAAQ_S3_BASE.format(year=year)
        print(f"\n  [{year}] Telechargement S3...")

        try:
            r = requests.get(url, timeout=120)
            if r.status_code != 200:
                print(f"  [{year}] HTTP {r.status_code} — skip")
                continue
        except Exception as e:
            print(f"  [{year}] [ERR] {e}")
            continue

        # Detecter encoding
        content = r.content.decode('latin-1', errors='replace')
        reader = csv.DictReader(StringIO(content))
        rows = list(reader)
        print(f"  [{year}] {len(rows)} records")

        if dry_run:
            total_inserted += len(rows)
            continue

        inserted = 0
        for row in rows:
            try:
                cur.execute("""
                    INSERT INTO qc_collisions_saaq
                        (annee, date_collision, gravite, nombre_vehicules,
                         nombre_deces, nombre_blesses_graves, nombre_blesses_legers,
                         conditions_meteo, etat_surface, eclairage,
                         raw_data, source_resource_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    safe_int(row.get('AN', year)),
                    safe_date(row.get('DT_ACCDN')),
                    row.get('GRAVITE', ''),
                    safe_int(row.get('NB_VEH_IMPLIQUES_ACCDN')),
                    safe_int(row.get('NB_MORTS', 0), 0),
                    safe_int(row.get('NB_BLESSES_GRAVES', 0), 0),
                    safe_int(row.get('NB_BLESSES_LEGERS', 0), 0),
                    row.get('CD_COND_METEO', ''),
                    row.get('CD_ETAT_SURFC', ''),
                    row.get('CD_ECLRM', ''),
                    json.dumps(row, ensure_ascii=False, default=str),
                    f"saaq-s3-{year}"
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
        total_inserted += inserted
        print(f"  [{year}] +{inserted} inseres")
        log_import(conn, f"collisions-saaq-{year}", url, "import_donnees_qc",
                   len(rows), inserted, 0, "done")

    print(f"\n  TOTAL collisions: {total_inserted} inseres")
    return total_inserted


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Import Donnees ouvertes Quebec")
    parser.add_argument("--dry-run", action="store_true", help="Ne pas inserer en DB")
    parser.add_argument("--source", type=str, default="all",
                        help="Source: constats|radars|lieux|collisions|all")
    args = parser.parse_args()

    print("=" * 60)
    print("  IMPORT DONNEES OUVERTES QUEBEC")
    print(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'PRODUCTION'}")
    print(f"  Source: {args.source}")
    print("=" * 60)

    conn = psycopg2.connect(**PG_CONFIG)
    results = {}

    try:
        if args.source in ('all', 'constats'):
            results['constats'] = import_constats(conn, args.dry_run)

        if args.source in ('all', 'radars'):
            results['radars'] = import_radar_stats(conn, args.dry_run)

        if args.source in ('all', 'lieux'):
            results['lieux'] = import_radar_lieux(conn, args.dry_run)

        if args.source in ('all', 'collisions'):
            results['collisions'] = import_collisions_saaq(conn, args.dry_run)
    finally:
        conn.close()

    # Resume
    print(f"\n{'=' * 60}")
    print("  RESUME IMPORT DONNEES QC")
    print(f"{'=' * 60}")
    for src, count in results.items():
        print(f"  {src:20s} {count:>8} records")
    total = sum(results.values())
    print(f"  {'TOTAL':20s} {total:>8} records")
    print(f"{'=' * 60}")

    # Save log
    with open(os.path.join(LOGDIR, "donnees_qc_usage.json"), "w") as f:
        json.dump({
            "last_update": datetime.now().isoformat(),
            "results": results,
            "total": total,
        }, f)


if __name__ == "__main__":
    main()
