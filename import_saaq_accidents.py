#!/usr/bin/env python3
"""
Import rapports d'accident SAAQ — Données Québec (2011-2022)
Source: donneesquebec.ca (CSV, gratuit, pas de clé)
~100K+ accidents/an × 12 ans = ~1.2M rapports
"""

import os
import sys
import csv
import io
import psycopg2
import psycopg2.extras
import requests
from datetime import datetime

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

BASE_URL = "https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq"
YEARS = list(range(2011, 2023))  # 2011-2022

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS saaq_rapports_accident (
    id SERIAL PRIMARY KEY,
    annee INTEGER NOT NULL,
    no_seq_collision TEXT NOT NULL,
    mois TEXT,
    heure TEXT,
    jour_semaine TEXT,
    gravite TEXT,
    nb_victimes INTEGER DEFAULT 0,
    nb_vehicules INTEGER DEFAULT 0,
    region_admin TEXT,
    vitesse_autorisee TEXT,
    genre_accident TEXT,
    etat_surface TEXT,
    eclairage TEXT,
    environnement TEXT,
    categorie_route TEXT,
    aspect_route TEXT,
    localisation TEXT,
    configuration_route TEXT,
    zone_travaux TEXT,
    condition_meteo TEXT,
    ind_auto BOOLEAN DEFAULT FALSE,
    ind_veh_lourd BOOLEAN DEFAULT FALSE,
    ind_moto BOOLEAN DEFAULT FALSE,
    ind_velo BOOLEAN DEFAULT FALSE,
    ind_pieton BOOLEAN DEFAULT FALSE,
    imported_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(annee, no_seq_collision)
);

CREATE INDEX IF NOT EXISTS idx_saaq_acc_annee ON saaq_rapports_accident(annee);
CREATE INDEX IF NOT EXISTS idx_saaq_acc_region ON saaq_rapports_accident(region_admin);
CREATE INDEX IF NOT EXISTS idx_saaq_acc_gravite ON saaq_rapports_accident(gravite);
CREATE INDEX IF NOT EXISTS idx_saaq_acc_vitesse ON saaq_rapports_accident(vitesse_autorisee);
CREATE INDEX IF NOT EXISTS idx_saaq_acc_genre ON saaq_rapports_accident(genre_accident);
CREATE INDEX IF NOT EXISTS idx_saaq_acc_meteo ON saaq_rapports_accident(condition_meteo);
"""


def import_year(conn, year):
    """Importe les rapports d'accident pour une année"""
    url = f"{BASE_URL}/Rapport_Accident_{year}.csv"
    print(f"  Téléchargement {year}...", end=" ", flush=True)

    try:
        resp = requests.get(url, timeout=60)
        if resp.status_code != 200:
            print(f"[ERR] HTTP {resp.status_code}")
            return 0
    except Exception as e:
        print(f"[ERR] {e}")
        return 0

    # Decode with BOM handling
    text = resp.content.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    print(f"{len(rows)} rapports", end=" ", flush=True)

    cur = conn.cursor()
    inserted = 0
    skipped = 0

    for row in rows:
        try:
            cur.execute("""
                INSERT INTO saaq_rapports_accident
                    (annee, no_seq_collision, mois, heure, jour_semaine,
                     gravite, nb_victimes, nb_vehicules, region_admin,
                     vitesse_autorisee, genre_accident, etat_surface,
                     eclairage, environnement, categorie_route, aspect_route,
                     localisation, configuration_route, zone_travaux,
                     condition_meteo, ind_auto, ind_veh_lourd, ind_moto,
                     ind_velo, ind_pieton)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (annee, no_seq_collision) DO NOTHING
            """, (
                int(row.get("AN", year)),
                row.get("NO_SEQ_COLL", "").strip(),
                row.get("MS_ACCDN", "").strip(),
                row.get("HR_ACCDN", "").strip(),
                row.get("JR_SEMN_ACCDN", "").strip(),
                row.get("GRAVITE", "").strip(),
                int(row.get("NB_VICTIMES_TOTAL", 0) or 0),
                int(row.get("NB_VEH_IMPLIQUES_ACCDN", 0) or 0),
                row.get("REG_ADM", "").strip(),
                row.get("VITESSE_AUTOR", "").strip(),
                row.get("CD_GENRE_ACCDN", "").strip(),
                row.get("CD_ETAT_SURFC", "").strip(),
                row.get("CD_ECLRM", "").strip(),
                row.get("CD_ENVRN_ACCDN", "").strip(),
                row.get("CD_CATEG_ROUTE", "").strip(),
                row.get("CD_ASPCT_ROUTE", "").strip(),
                row.get("CD_LOCLN_ACCDN", "").strip(),
                row.get("CD_CONFG_ROUTE", "").strip(),
                row.get("CD_ZON_TRAVX_ROUTR", "").strip() if row.get("CD_ZON_TRAVX_ROUTR") else None,
                row.get("CD_COND_METEO", "").strip(),
                row.get("IND_AUTO_CAMION_LEGER", "N").strip() == "O",
                row.get("IND_VEH_LOURD", "N").strip() == "O",
                row.get("IND_MOTO_CYCLO", "N").strip() == "O",
                row.get("IND_VELO", "N").strip() == "O",
                row.get("IND_PIETON", "N").strip() == "O",
            ))
            inserted += 1
        except Exception as e:
            conn.rollback()
            skipped += 1
            if skipped <= 3:
                print(f"\n    [ERR] {row.get('NO_SEQ_COLL','?')}: {e}")
            continue

    conn.commit()
    print(f"→ +{inserted} insérés, {skipped} ignorés")
    return inserted


def main():
    print("=" * 60)
    print("  IMPORT RAPPORTS D'ACCIDENT SAAQ (2011-2022)")
    print(f"  Source: Données Québec (CSV, gratuit)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    conn = psycopg2.connect(**PG_CONFIG)
    cur = conn.cursor()

    # Créer la table
    cur.execute(CREATE_TABLE)
    conn.commit()
    print("\n  Table créée: saaq_rapports_accident")

    # Import par année
    total = 0
    for year in YEARS:
        n = import_year(conn, year)
        total += n

    # Stats
    cur.execute("SELECT count(*) FROM saaq_rapports_accident")
    db_total = cur.fetchone()[0]

    cur.execute("""
        SELECT gravite, count(*)
        FROM saaq_rapports_accident
        GROUP BY gravite
        ORDER BY count(*) DESC
    """)
    print(f"\n  Total importé cette session: {total}")
    print(f"  Total en DB: {db_total}")
    print("\n  Par gravité:")
    for row in cur.fetchall():
        print(f"    {row[0]:45s} {row[1]:>8}")

    cur.execute("""
        SELECT annee, count(*)
        FROM saaq_rapports_accident
        GROUP BY annee
        ORDER BY annee
    """)
    print("\n  Par année:")
    for row in cur.fetchall():
        print(f"    {row[0]}  {row[1]:>8} rapports")

    cur.execute("""
        SELECT region_admin, count(*)
        FROM saaq_rapports_accident
        GROUP BY region_admin
        ORDER BY count(*) DESC
        LIMIT 10
    """)
    print("\n  Top 10 régions:")
    for row in cur.fetchall():
        print(f"    {row[0]:40s} {row[1]:>8}")

    conn.close()
    print(f"\n{'='*60}")
    print("  DONE")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
