"""
Module d'import des cas de jurisprudence curates (seed v1 + v2).
Importe les 135+ cas detailles dans PostgreSQL.
Source: /var/www/aiticketinfo/seed_jurisprudence_v2.py
"""
import logging
import sys
import os
from utils.db import get_connection, log_import

logger = logging.getLogger(__name__)

# Chemin vers le projet aiticketinfo (local ou serveur)
SEED_V2_PATHS = [
    '/var/www/aiticketinfo/seed_jurisprudence_v2.py',
    os.path.expanduser('~/Desktop/projet web/aiticketinfo/seed_jurisprudence_v2.py'),
]


def _load_seed_data():
    """Charge les listes CASES_QC_V2 et CASES_ON_V2 depuis le script seed."""
    for path in SEED_V2_PATHS:
        if os.path.exists(path):
            logger.info(f"  Loading seed data from {path}")
            # Charger le module dynamiquement
            import importlib.util
            spec = importlib.util.spec_from_file_location("seed_v2", path)
            mod = importlib.util.module_from_spec(spec)
            # Prevenir l'execution du main
            sys.modules['seed_v2'] = mod
            try:
                spec.loader.exec_module(mod)
            except Exception as e:
                # Le module peut echouer sur certains imports, on ignore
                logger.debug(f"  Module load partial: {e}")

            qc = getattr(mod, 'CASES_QC_V2', [])
            on = getattr(mod, 'CASES_ON_V2', [])
            logger.info(f"  Found {len(qc)} QC cases + {len(on)} ON cases")
            return qc, on

    logger.warning("  seed_jurisprudence_v2.py not found in expected locations")
    return [], []


def import_seed_cases(cases, province):
    """Insere les cas curates dans la table jurisprudence PostgreSQL."""
    conn = get_connection()
    inserted = 0

    with conn:
        with conn.cursor() as cur:
            for case in cases:
                citation = case.get('citation', '')
                if not citation:
                    continue

                # Determiner database_id a partir du tribunal
                tribunal = (case.get('tribunal', '') or '').upper()
                database_id = None
                for code in ['QCCM', 'QCCA', 'QCCQ', 'QCCS', 'QCTAQ', 'ONCJ', 'ONCA', 'ONSCDC']:
                    if code in tribunal:
                        database_id = code.lower()
                        break

                # Mots-cles en array
                mots_cles_str = case.get('mots_cles', '')
                mots_cles = [m.strip() for m in mots_cles_str.split(',') if m.strip()]

                # Utiliser la citation comme canlii_id
                canlii_id = citation.strip()

                try:
                    cur.execute("""
                        INSERT INTO jurisprudence
                        (canlii_id, database_id, province, titre, citation,
                         date_decision, tribunal, langue, mots_cles,
                         resume, resultat, est_ticket_related, source)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (canlii_id) DO UPDATE SET
                            resume = CASE
                                WHEN LENGTH(COALESCE(EXCLUDED.resume,'')) > LENGTH(COALESCE(jurisprudence.resume,''))
                                THEN EXCLUDED.resume
                                ELSE jurisprudence.resume
                            END,
                            mots_cles = CASE
                                WHEN array_length(EXCLUDED.mots_cles, 1) > COALESCE(array_length(jurisprudence.mots_cles, 1), 0)
                                THEN EXCLUDED.mots_cles
                                ELSE jurisprudence.mots_cles
                            END,
                            resultat = COALESCE(EXCLUDED.resultat, jurisprudence.resultat)
                    """, (
                        canlii_id,
                        database_id,
                        province,
                        case.get('titre'),
                        citation,
                        case.get('date_decision'),
                        case.get('tribunal'),
                        case.get('langue', 'fr' if province == 'QC' else 'en'),
                        mots_cles,
                        case.get('resume'),
                        case.get('resultat'),
                        True,  # tous les cas seed sont ticket-related
                        'seed_curated_v2',
                    ))
                    inserted += 1
                except Exception as e:
                    logger.warning(f"    Seed insert error for {citation}: {e}")
                    conn.rollback()

    conn.close()
    return inserted


def run():
    """Point d'entree du module seed import."""
    logger.info("=" * 50)
    logger.info("MODULE IMPORT SEED CASES (curates 135+)")
    logger.info("=" * 50)

    qc_cases, on_cases = _load_seed_data()

    results = {}
    if qc_cases:
        count = import_seed_cases(qc_cases, 'QC')
        results['seed_qc'] = count
        logger.info(f"  Inserted {count}/{len(qc_cases)} QC seed cases.")
        log_import('seed_jurisprudence_qc', 'seed_jurisprudence_v2.py', 'seed_import',
                   len(qc_cases), count)

    if on_cases:
        count = import_seed_cases(on_cases, 'ON')
        results['seed_on'] = count
        logger.info(f"  Inserted {count}/{len(on_cases)} ON seed cases.")
        log_import('seed_jurisprudence_on', 'seed_jurisprudence_v2.py', 'seed_import',
                   len(on_cases), count)

    total = sum(results.values())
    logger.info(f"  Seed total: {total} cases importes")
    return results
