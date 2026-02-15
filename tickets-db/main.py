#!/usr/bin/env python3
"""
Orchestrateur principal - Import base de donnees tickets QC/ON.
Utilise PostgreSQL sur le serveur OVH (Docker port 5432).

Usage:
    python3 main.py              # Import complet
    python3 main.py --schema     # Schema seulement
    python3 main.py --quebec     # Donnees Quebec seulement
    python3 main.py --montreal   # Donnees Montreal seulement
    python3 main.py --canlii     # CanLII seulement
    python3 main.py --a2aj       # A2AJ jurisprudence texte integral
    python3 main.py --legislation # CanLII legislation browse
    python3 main.py --ontario    # Ontario seulement
    python3 main.py --collisions  # Collisions SAAQ seulement
    python3 main.py --setfines    # Ontario Set Fines seulement
    python3 main.py --vehicules   # Vehicules en circulation SAAQ seulement
    python3 main.py --static     # Donnees statiques seulement
    python3 main.py --seed       # Seed cases curates (135+) seulement
    python3 main.py --status     # Afficher le status des tables
"""
import logging
import sys
import os
import argparse

# Ajouter le repertoire courant au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import LOG_DIR, LOG_FILE
from utils.db import execute_schema, get_table_counts

# Creer le repertoire de logs
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def print_status():
    """Affiche le nombre de lignes dans chaque table."""
    print("\n" + "=" * 60)
    print("STATUS DES TABLES")
    print("=" * 60)
    try:
        counts = get_table_counts()
        total = 0
        for table, count in sorted(counts.items()):
            status = f"  {count:>10,}" if count >= 0 else "  [table manquante]"
            print(f"  {table:<40} {status}")
            if count > 0:
                total += count
        print("-" * 60)
        print(f"  {'TOTAL':<40} {total:>10,}")
        print("=" * 60)
    except Exception as e:
        print(f"  Erreur de connexion: {e}")
        print("  Verifier que PostgreSQL est actif et la config est correcte.")


def main():
    parser = argparse.ArgumentParser(description='Import base de donnees tickets QC/ON')
    parser.add_argument('--schema', action='store_true', help='Creer le schema seulement')
    parser.add_argument('--quebec', action='store_true', help='Donnees Quebec seulement')
    parser.add_argument('--montreal', action='store_true', help='Donnees Montreal seulement')
    parser.add_argument('--canlii', action='store_true', help='CanLII seulement')
    parser.add_argument('--a2aj', action='store_true', help='A2AJ jurisprudence texte integral')
    parser.add_argument('--legislation', action='store_true', help='CanLII legislation browse')
    parser.add_argument('--ontario', action='store_true', help='Ontario seulement')
    parser.add_argument('--collisions', action='store_true', help='Collisions SAAQ seulement')
    parser.add_argument('--setfines', action='store_true', help='Ontario Set Fines seulement')
    parser.add_argument('--vehicules', action='store_true', help='Vehicules en circulation SAAQ seulement')
    parser.add_argument('--static', action='store_true', help='Donnees statiques seulement')
    parser.add_argument('--seed', action='store_true', help='Seed cases curates (135+) seulement')
    parser.add_argument('--status', action='store_true', help='Afficher status des tables')
    args = parser.parse_args()

    # Si --status, juste afficher et sortir
    if args.status:
        print_status()
        return

    # Determiner quoi executer
    run_all = not any([args.schema, args.quebec, args.montreal,
                       args.canlii, args.a2aj, args.legislation, args.ontario,
                       args.collisions, args.setfines, args.vehicules,
                       args.static, args.seed])

    logger.info("=" * 60)
    logger.info("DEBUT IMPORT - Base de donnees tickets QC/ON (PostgreSQL)")
    logger.info("=" * 60)

    # Etape 1 : Schema (toujours)
    logger.info("Etape 1: Creation/mise a jour du schema...")
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')
    execute_schema(schema_path)

    if args.schema:
        print_status()
        return

    # Etape 2 : Donnees statiques
    if run_all or args.static:
        logger.info("Etape 3: Import donnees statiques (jurisprudence cle, articles loi)...")
        from modules.static_data import run as run_static
        run_static()

    # Etape 3b : Seed cases curates (135+ cas detailles)
    if run_all or args.seed:
        logger.info("Etape 3b: Import seed cases curates (135+ QC/ON)...")
        from modules.seed_import import run as run_seed
        run_seed()

    # Etape 4 : Donnees Quebec
    if run_all or args.quebec:
        logger.info("Etape 4: Import Donnees Quebec (SAAQ, radars, constats)...")
        from modules.ckan_quebec import run as run_qc
        run_qc()

    # Etape 5 : Montreal Open Data
    if run_all or args.montreal:
        logger.info("Etape 5: Import Montreal Open Data (collisions, SPVM)...")
        from modules.ckan_montreal import run as run_mtl
        run_mtl()

    # Etape 6 : CanLII
    if run_all or args.canlii:
        logger.info("Etape 6: Import CanLII (jurisprudence QC + ON)...")
        from modules.canlii import run as run_canlii
        run_canlii()

    # Etape 7 : A2AJ (jurisprudence texte integral)
    if run_all or args.a2aj:
        logger.info("Etape 7: Import A2AJ (jurisprudence texte integral)...")
        from modules.a2aj import run as run_a2aj
        run_a2aj()

    # Etape 8 : CanLII Legislation Browse
    if run_all or args.legislation:
        logger.info("Etape 8: Import CanLII Legislation Browse...")
        from modules.canlii_legislation import run as run_legislation
        run_legislation()

    # Etape 9 : Ontario
    if run_all or args.ontario:
        logger.info("Etape 9: Import Ontario Open Data...")
        from modules.ontario import run as run_ontario
        run_ontario()

    # Etape 10 : Collisions SAAQ
    if run_all or args.collisions:
        logger.info("Etape 10: Import Collisions SAAQ (Donnees Quebec)...")
        from modules.ckan_collisions_saaq import run as run_collisions
        run_collisions()

    # Etape 11 : Ontario Set Fines
    if run_all or args.setfines:
        logger.info("Etape 11: Import Ontario Set Fines (Court schedules)...")
        from modules.on_set_fines_import import run as run_setfines
        run_setfines()

    # Etape 12 : Vehicules en circulation SAAQ
    if run_all or args.vehicules:
        logger.info("Etape 12: Import Vehicules en circulation SAAQ...")
        from modules.ckan_vehicules import run as run_vehicules
        run_vehicules()

    logger.info("=" * 60)
    logger.info("IMPORT TERMINE")
    logger.info("=" * 60)

    print_status()


if __name__ == '__main__':
    main()
