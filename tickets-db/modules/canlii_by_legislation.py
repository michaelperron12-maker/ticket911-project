"""
Module CanLII - Recherche jurisprudence par legislation citee.
Au lieu de scanner TOUTES les decisions et filtrer par titre (inefficace),
on utilise le citateur pour trouver les cas qui CITENT les lois routieres.

Strategie:
1. Pour chaque loi cible (CSR C-24.2, HTA H.8, Code criminel conduite),
   chercher les cas qui citent cette loi via legislationBrowse metadata
2. Beaucoup plus efficace: 1 req pour la loi → liste des cas citants

Partage le rate limiter avec canlii.py via fichier compteur.
"""
import logging
import json
import time
import os
import requests
from config import CANLII_BASE, CANLII_API_KEY
from utils.db import get_connection, log_import

logger = logging.getLogger(__name__)

MIN_DELAY = 0.65
_last_request_time = 0.0
_counter_file = os.path.join(os.path.dirname(__file__), '..', 'logs', 'canlii_counter.json')
DAILY_LIMIT = 4800


def _load_counter():
    try:
        if os.path.exists(_counter_file):
            with open(_counter_file) as f:
                data = json.load(f)
            if data.get('date') == time.strftime('%Y-%m-%d'):
                return data.get('count', 0)
    except Exception:
        pass
    return 0


def _save_counter(count):
    try:
        os.makedirs(os.path.dirname(_counter_file), exist_ok=True)
        with open(_counter_file, 'w') as f:
            json.dump({'date': time.strftime('%Y-%m-%d'), 'count': count}, f)
    except Exception:
        pass


def _rate_limited_fetch(url, params):
    global _last_request_time
    count = _load_counter()
    if count >= DAILY_LIMIT:
        raise RuntimeError(f"CanLII daily limit reached: {count}")

    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < MIN_DELAY:
        time.sleep(MIN_DELAY - elapsed)

    _last_request_time = time.time()
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()

    count += 1
    if count % 50 == 0:
        logger.info(f"  [CanLII-leg] {count}/{DAILY_LIMIT} requetes utilisees")
    _save_counter(count)
    return resp.json()


# Legislations cibles pour tickets routiers
# Format: (databaseId, legislationId, province, description)
TARGET_LAWS = [
    # Quebec - Code de la securite routiere
    ('qcs', 'rlrq-c-c-24.2', 'QC', 'Code de la securite routiere'),
    # Quebec - Code de procedure penale
    ('qcs', 'rlrq-c-c-25.1', 'QC', 'Code de procedure penale'),
    # Quebec - Assurance automobile
    ('qcs', 'rlrq-c-a-25', 'QC', 'Loi assurance automobile'),
    # Ontario - Highway Traffic Act
    ('ons', 'rso-1990-c-h8', 'ON', 'Highway Traffic Act'),
    # Ontario - Provincial Offences Act
    ('ons', 'rso-1990-c-p33', 'ON', 'Provincial Offences Act'),
    # Federal - Code criminel (conduite dangereuse, alcool)
    ('cas', 'rsc-1985-c-c-46', 'CA', 'Code criminel'),
]


def fetch_citing_cases(db_id, legislation_id):
    """Utilise le citateur pour trouver les cas qui citent une legislation."""
    # L'API CanLII n'a pas d'endpoint direct "cases citing this legislation"
    # Mais on peut chercher les cas dans les tribunaux specifiques
    # qui ont cette legislation dans leurs citations
    # Pour ca on utilise caseBrowse avec le metadata de chaque cas
    # ALTERNATIVE: on cherche via le titre/keywords
    pass


def search_by_legislation_keyword(province):
    """Cherche des cas par mots-cles de legislation dans tous les tribunaux."""
    count = _load_counter()
    if count >= DAILY_LIMIT:
        return []

    # Utiliser caseBrowse avec filtrage plus intelligent
    # On cherche les cas recents (plus pertinents) dans les tribunaux cibles
    tribunals = {
        'QC': ['qccq', 'qccm', 'qccs'],  # Tribunaux ou on trouve des tickets
        'ON': ['oncj', 'onscdc'],
    }

    all_cases = []
    dbs = tribunals.get(province, [])

    for db_id in dbs:
        count = _load_counter()
        if count >= DAILY_LIMIT:
            break

        lang = 'fr' if province == 'QC' else 'en'

        # Fetch les cas les plus recents (plus de chances d'etre ticket-related)
        # On utilise decisionDateAfter pour cibler les dernieres annees
        for year_start in ['2020-01-01', '2015-01-01', '2010-01-01']:
            count = _load_counter()
            if count >= DAILY_LIMIT:
                break

            offset = 0
            max_per_period = 5000  # Max 5000 par periode pour economiser
            period_cases = []

            while offset < max_per_period:
                count = _load_counter()
                if count >= DAILY_LIMIT:
                    break

                url = f"{CANLII_BASE}/caseBrowse/{lang}/{db_id}/"
                params = {
                    'api_key': CANLII_API_KEY,
                    'offset': offset,
                    'resultCount': 100,
                    'decisionDateAfter': year_start,
                }

                try:
                    data = _rate_limited_fetch(url, params)
                    cases = data.get('cases', [])
                    if not cases:
                        break
                    period_cases.extend(cases)
                    offset += 100
                except RuntimeError:
                    break
                except Exception as e:
                    logger.error(f"  Error {db_id} offset {offset}: {e}")
                    break

            # Pour chaque cas, fetch metadata individuel pour voir les keywords/legislation
            # C'est cher (1 req/cas) mais cible
            ticket_count = 0
            for case in period_cases:
                count = _load_counter()
                if count >= DAILY_LIMIT:
                    break

                case_id_obj = case.get('caseId', {})
                if isinstance(case_id_obj, dict):
                    canlii_id = case_id_obj.get('en', '') or case_id_obj.get('fr', '')
                else:
                    canlii_id = str(case_id_obj)
                if not canlii_id:
                    continue

                # Fetch metadata pour voir keywords
                try:
                    meta_url = f"{CANLII_BASE}/caseBrowse/{lang}/{db_id}/{canlii_id}/"
                    meta = _rate_limited_fetch(meta_url, {'api_key': CANLII_API_KEY})
                    keywords = (meta.get('keywords', '') or '').lower()

                    # Verifier si c'est lie aux tickets
                    kw_check = ['securite routiere', 'highway traffic', 'speed',
                                'vitesse', 'infraction', 'constat', 'radar',
                                'alcool', 'impaired', 'driving', 'conduite',
                                'C-24.2', 'c-24.2', 'stunt', 'careless',
                                'ticket', 'amende', 'fine', 'permis', 'licence']

                    if any(kw in keywords for kw in kw_check):
                        case['_keywords'] = meta.get('keywords', '')
                        case['_province'] = province
                        case['_database_id'] = db_id
                        case['_is_ticket'] = True
                        case['_meta'] = meta
                        all_cases.append(case)
                        ticket_count += 1

                except RuntimeError:
                    break
                except Exception:
                    pass

            logger.info(f"    {db_id} since {year_start}: {ticket_count} ticket-related in {len(period_cases)} cases")

            # Si on a trouve des cas, pas besoin d'aller plus loin dans le temps
            if ticket_count > 20:
                break

    return all_cases


def insert_cases(cases):
    """Insere les cas trouves dans jurisprudence."""
    conn = get_connection()
    inserted = 0
    with conn:
        with conn.cursor() as cur:
            for d in cases:
                case_id_obj = d.get('caseId', {})
                if isinstance(case_id_obj, dict):
                    canlii_id = case_id_obj.get('en', '') or case_id_obj.get('fr', '')
                else:
                    canlii_id = str(case_id_obj)
                if not canlii_id:
                    continue

                meta = d.get('_meta', {})
                keywords_str = d.get('_keywords', '')
                kw_list = [k.strip() for k in keywords_str.replace(';', ',').split(',') if k.strip()] if keywords_str else []

                try:
                    cur.execute("""
                        INSERT INTO jurisprudence
                        (canlii_id, database_id, province, titre, citation,
                         numero_dossier, date_decision, url_canlii, tribunal,
                         langue, mots_cles, est_ticket_related, source, raw_metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (canlii_id) DO UPDATE SET
                            mots_cles = CASE
                                WHEN COALESCE(array_length(EXCLUDED.mots_cles, 1), 0) > COALESCE(array_length(jurisprudence.mots_cles, 1), 0)
                                THEN EXCLUDED.mots_cles
                                ELSE jurisprudence.mots_cles
                            END,
                            est_ticket_related = TRUE,
                            raw_metadata = EXCLUDED.raw_metadata
                    """, (
                        canlii_id,
                        d.get('_database_id'),
                        d.get('_province'),
                        d.get('title', meta.get('title', '')),
                        d.get('citation', meta.get('citation', '')),
                        meta.get('docketNumber'),
                        d.get('decisionDate', meta.get('decisionDate')),
                        meta.get('url', d.get('url')),
                        d.get('_database_id'),
                        'fr' if d.get('_province') == 'QC' else 'en',
                        kw_list if kw_list else None,
                        True,
                        'canlii_by_law',
                        json.dumps({**d, '_meta': meta}),
                    ))
                    inserted += 1
                except Exception as e:
                    logger.warning(f"    Insert error {canlii_id}: {e}")
                    conn.rollback()
    conn.close()
    return inserted


def run():
    """Point d'entree - recherche par legislation citee."""
    logger.info("=" * 50)
    logger.info("MODULE CANLII - RECHERCHE PAR LEGISLATION CITEE")
    logger.info("=" * 50)

    if not CANLII_API_KEY:
        logger.warning("  CLE API CANLII MANQUANTE")
        return {}

    count = _load_counter()
    logger.info(f"  Requetes restantes: {DAILY_LIMIT - count}")
    if count >= DAILY_LIMIT:
        logger.warning("  Limite quotidienne atteinte, skip")
        return {}

    results = {}
    total = 0

    for province in ['QC', 'ON']:
        logger.info(f"  Recherche {province} par keywords metadata...")
        cases = search_by_legislation_keyword(province)
        if cases:
            inserted = insert_cases(cases)
            total += inserted
            results[province] = inserted
            logger.info(f"  {province}: {len(cases)} trouves, {inserted} inseres")

    log_import('canlii_by_legislation', 'api.canlii.org', 'canlii_by_legislation', total, total)
    logger.info(f"Total par legislation: {total} cas inseres")

    count = _load_counter()
    logger.info(f"  Requetes restantes: {DAILY_LIMIT - count}")
    return results
