#!/usr/bin/env python3
"""
Import conditions routières hivernales — MTQ (Données Québec)
Source: ws.mapserver.transports.gouv.qc.ca (WFS API, gratuit, pas de clé)
~448 segments routiers en temps réel (oct-avr)
+ archives quotidiennes année courante
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

# API MTQ — Conditions routières (WFS, gratuit, pas de clé)
WFS_URL = "https://ws.mapserver.transports.gouv.qc.ca/swtq"
WFS_PARAMS = {
    "service": "wfs",
    "version": "2.0.0",
    "request": "getfeature",
    "typename": "ms:conditions_routieres",
    "outfile": "CondRoutHiver_Continu",
    "srsname": "EPSG:4326",
    "outputformat": "csv",
}

# ═══════════════════════════════════════════════════════════
# TABLE PostgreSQL
# ═══════════════════════════════════════════════════════════

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS conditions_routieres_hiver (
    id SERIAL PRIMARY KEY,
    numero_segment TEXT NOT NULL,
    numero_route TEXT,
    nom_route TEXT,
    nom_region TEXT,
    localisation_debut TEXT,
    localisation_fin TEXT,
    code_etat_chaussee TEXT,
    etat_chaussee TEXT,
    code_couleur_chaussee TEXT,
    code_visibilite TEXT,
    visibilite TEXT,
    code_couleur_visibilite TEXT,
    presence_lames_neige BOOLEAN DEFAULT FALSE,
    en_vigueur_depuis TIMESTAMP,
    imported_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(numero_segment, en_vigueur_depuis)
);

CREATE INDEX IF NOT EXISTS idx_cond_route_region ON conditions_routieres_hiver(nom_region);
CREATE INDEX IF NOT EXISTS idx_cond_route_etat ON conditions_routieres_hiver(code_etat_chaussee);
CREATE INDEX IF NOT EXISTS idx_cond_route_date ON conditions_routieres_hiver(en_vigueur_depuis);
CREATE INDEX IF NOT EXISTS idx_cond_route_segment ON conditions_routieres_hiver(numero_segment);
"""


def fetch_conditions():
    """Récupère les conditions routières en temps réel via WFS"""
    print("  Appel API MTQ (WFS)...")
    resp = requests.get(WFS_URL, params=WFS_PARAMS, timeout=30)
    if resp.status_code != 200:
        print(f"  [ERR] HTTP {resp.status_code}")
        return []

    reader = csv.DictReader(io.StringIO(resp.text))
    rows = list(reader)
    print(f"  Segments reçus: {len(rows)}")
    return rows


def import_conditions(conn, rows):
    """Insère les conditions dans PostgreSQL"""
    cur = conn.cursor()
    inserted = 0
    updated = 0

    for row in rows:
        en_vigueur = row.get("EnVigueurDepuis", "")
        # Parse date format: 2026/02/14 14:27:13
        try:
            if en_vigueur:
                dt = datetime.strptime(en_vigueur, "%Y/%m/%d %H:%M:%S")
            else:
                dt = None
        except ValueError:
            dt = None

        lames = row.get("IndicateurPresenceLamesNeige", "N") == "O"

        try:
            cur.execute("""
                INSERT INTO conditions_routieres_hiver
                    (numero_segment, numero_route, nom_route, nom_region,
                     localisation_debut, localisation_fin,
                     code_etat_chaussee, etat_chaussee, code_couleur_chaussee,
                     code_visibilite, visibilite, code_couleur_visibilite,
                     presence_lames_neige, en_vigueur_depuis)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (numero_segment, en_vigueur_depuis) DO UPDATE SET
                    etat_chaussee = EXCLUDED.etat_chaussee,
                    code_etat_chaussee = EXCLUDED.code_etat_chaussee,
                    visibilite = EXCLUDED.visibilite,
                    presence_lames_neige = EXCLUDED.presence_lames_neige,
                    imported_at = NOW()
            """, (
                row.get("NumeroSegment", ""),
                row.get("NumeroRoute", ""),
                row.get("NomRoute", ""),
                row.get("NomRegion", ""),
                row.get("LocalisationDebutFR", ""),
                row.get("LocalisationFinFR", ""),
                row.get("CodeEtatChaussee", ""),
                row.get("DescriptionEtatChausseeFR", ""),
                row.get("CodeCouleurEtatChaussee", ""),
                row.get("CodeVisibilite", ""),
                row.get("DescriptionVisibiliteFR", ""),
                row.get("CodeCouleurVisibilite", ""),
                lames,
                dt,
            ))
            inserted += 1
        except Exception as e:
            conn.rollback()
            print(f"  [ERR] Segment {row.get('NumeroSegment','?')}: {e}")
            continue

    conn.commit()
    return inserted


def main():
    print("=" * 60)
    print("  IMPORT CONDITIONS ROUTIÈRES HIVERNALES QC")
    print(f"  Source: MTQ via WFS (Données Québec)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    conn = psycopg2.connect(**PG_CONFIG)
    cur = conn.cursor()

    # Créer la table
    cur.execute(CREATE_TABLE)
    conn.commit()
    print("\n  Table créée: conditions_routieres_hiver")

    # Fetch et import
    rows = fetch_conditions()
    if not rows:
        print("  [WARN] Aucune donnée reçue (hors saison oct-avr?)")
        conn.close()
        return

    inserted = import_conditions(conn, rows)

    # Stats
    cur.execute("SELECT count(*) FROM conditions_routieres_hiver")
    total = cur.fetchone()[0]

    cur.execute("""
        SELECT etat_chaussee, count(*)
        FROM conditions_routieres_hiver
        WHERE en_vigueur_depuis = (SELECT MAX(en_vigueur_depuis) FROM conditions_routieres_hiver LIMIT 1)
           OR en_vigueur_depuis >= NOW() - INTERVAL '1 day'
        GROUP BY etat_chaussee
        ORDER BY count(*) DESC
    """)
    print(f"\n  Segments importés: {inserted}")
    print(f"  Total en DB: {total}")
    print("\n  État actuel des routes:")
    for row in cur.fetchall():
        print(f"    {row[0]:30s} {row[1]:>5} segments")

    cur.execute("""
        SELECT nom_region, count(*)
        FROM conditions_routieres_hiver
        WHERE en_vigueur_depuis >= NOW() - INTERVAL '1 day'
        GROUP BY nom_region
        ORDER BY nom_region
    """)
    print("\n  Par région:")
    for row in cur.fetchall():
        print(f"    {row[0]:35s} {row[1]:>4} segments")

    conn.close()
    print(f"\n{'='*60}")
    print("  DONE")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
