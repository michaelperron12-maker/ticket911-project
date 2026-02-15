"""
Module CanLII Legislation Browse.
Recupere les lois et reglements pertinents via l'API CanLII.

Endpoints:
- /v1/legislationBrowse/{lang}/ → liste des bases legislatives
- /v1/legislationBrowse/{lang}/{databaseId}/ → liste des lois/reglements
- /v1/legislationBrowse/{lang}/{databaseId}/{legislationId}/ → metadata d'une loi

Partage le rate limiter avec le module canlii.py principal.
"""
import logging
import json
import time
import os
from config import CANLII_BASE, CANLII_API_KEY
from utils.db import get_connection, log_import

logger = logging.getLogger(__name__)

# Rate limiting - partage avec canlii.py via fichier compteur
MIN_DELAY = 0.55
_last_request_time = 0.0
_counter_file = os.path.join(os.path.dirname(__file__), '..', 'logs', 'canlii_counter.json')
DAILY_LIMIT = 4800


def _load_counter():
    """Charge le compteur quotidien."""
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
    """Sauvegarde le compteur quotidien."""
    try:
        os.makedirs(os.path.dirname(_counter_file), exist_ok=True)
        with open(_counter_file, 'w') as f:
            json.dump({'date': time.strftime('%Y-%m-%d'), 'count': count}, f)
    except Exception:
        pass


def _rate_limited_fetch(url, params, request_count):
    """Fetch avec rate limiting strict."""
    import requests

    global _last_request_time

    if request_count >= DAILY_LIMIT:
        raise RuntimeError(f"CanLII daily limit reached: {request_count}")

    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < MIN_DELAY:
        time.sleep(MIN_DELAY - elapsed)

    _last_request_time = time.time()

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


# Bases legislatives pertinentes pour tickets routiers
LEGISLATION_DBS = {
    'QC': [
        ('qcs', 'fr'),   # Lois refondues du Quebec
        ('qcr', 'fr'),   # Reglements du Quebec
    ],
    'ON': [
        ('ons', 'en'),   # Statutes of Ontario
        ('onr', 'en'),   # Regulations of Ontario
    ],
    'CA': [
        ('cas', 'en'),   # Federal Statutes
    ],
}

# Lois specifiques a chercher dans les metadata
TARGET_LEGISLATION = [
    # Quebec
    'C-24.2',       # Code de la securite routiere
    'C-25.1',       # Code de procedure penale
    # Ontario
    'H.8',          # Highway Traffic Act
    'P.33',         # Provincial Offences Act
    # Federal
    'C-46',         # Code criminel
]


def fetch_legislation_list(database_id, lang='fr'):
    """Recupere la liste des lois/reglements d'une base legislative."""
    request_count = _load_counter()
    url = f"{CANLII_BASE}/legislationBrowse/{lang}/{database_id}/"
    params = {'api_key': CANLII_API_KEY}

    try:
        data = _rate_limited_fetch(url, params, request_count)
        request_count += 1
        _save_counter(request_count)
        return data.get('legislations', []), request_count
    except Exception as e:
        logger.error(f"  Error fetching legislation list for {database_id}: {e}")
        return [], request_count


def fetch_legislation_metadata(database_id, legislation_id, lang='fr'):
    """Recupere les metadata d'une loi specifique."""
    request_count = _load_counter()
    url = f"{CANLII_BASE}/legislationBrowse/{lang}/{database_id}/{legislation_id}/"
    params = {'api_key': CANLII_API_KEY}

    try:
        data = _rate_limited_fetch(url, params, request_count)
        request_count += 1
        _save_counter(request_count)
        return data, request_count
    except Exception as e:
        logger.warning(f"  Error fetching metadata for {legislation_id}: {e}")
        return {}, request_count


def insert_legislation(legislations, province):
    """Insere les lois dans la table lois_articles."""
    conn = get_connection()
    inserted = 0
    with conn:
        with conn.cursor() as cur:
            for leg in legislations:
                leg_id = leg.get('legislationId', '')
                if not leg_id:
                    continue

                title = leg.get('title', '')
                db_id = leg.get('databaseId', '')
                leg_type = leg.get('type', '')
                url = leg.get('url', '')
                citation = leg.get('citation', '')

                try:
                    cur.execute("""
                        INSERT INTO lois_articles
                        (province, loi, code_loi, article, titre_article,
                         url_source)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (province, code_loi, article) DO UPDATE SET
                            loi = EXCLUDED.loi,
                            titre_article = EXCLUDED.titre_article,
                            url_source = EXCLUDED.url_source
                    """, (
                        province,
                        title,
                        leg_id[:20] if leg_id else '',
                        leg_id[:50],  # article = legislation_id as identifier
                        f"{title} ({citation})" if citation else title,
                        url,
                    ))
                    inserted += 1
                except Exception as e:
                    logger.warning(f"    Insert error for {leg_id}: {e}")
                    conn.rollback()
    conn.close()
    return inserted


def run():
    """Point d'entree du module legislation CanLII."""
    logger.info("=" * 50)
    logger.info("MODULE CANLII LEGISLATION BROWSE")
    logger.info("=" * 50)

    if not CANLII_API_KEY:
        logger.warning("  CLE API CANLII NON CONFIGUREE - skip legislation")
        return {}

    request_count = _load_counter()
    logger.info(f"  Requetes restantes: {DAILY_LIMIT - request_count}")

    if request_count >= DAILY_LIMIT:
        logger.warning("  Limite quotidienne deja atteinte, skip legislation")
        return {}

    results = {}
    total_inserted = 0

    for province, dbs in LEGISLATION_DBS.items():
        for db_id, lang in dbs:
            request_count = _load_counter()
            if request_count >= DAILY_LIMIT:
                logger.warning(f"  Limite atteinte, arret a {db_id}")
                break

            logger.info(f"  Fetching legislation list: {db_id} ({province})...")
            legislations, request_count = fetch_legislation_list(db_id, lang)

            if legislations:
                # Filtrer pour les lois pertinentes aux tickets
                relevant = []
                for leg in legislations:
                    leg_id = leg.get('legislationId', '')
                    title = (leg.get('title', '') or '').lower()

                    # Chercher les lois cibles ou mots-cles pertinents
                    is_relevant = (
                        any(t.lower() in leg_id.lower() for t in TARGET_LEGISLATION) or
                        any(kw in title for kw in [
                            'sécurité routière', 'securite routiere', 'code de la route',
                            'highway traffic', 'provincial offences', 'criminal code',
                            'code criminel', 'procedure penale', 'procédure pénale',
                            'vehicule', 'véhicule', 'motor vehicle', 'driving',
                            'permis de conduire', "driver's licence", 'assurance automobile',
                            'transport routier', 'road',
                        ])
                    )
                    if is_relevant:
                        leg['_province'] = province
                        leg['_database_id'] = db_id
                        relevant.append(leg)

                logger.info(f"    {len(relevant)}/{len(legislations)} lois pertinentes aux tickets")

                if relevant:
                    count = insert_legislation(relevant, province)
                    total_inserted += count
                    results[db_id] = count

                    # Fetch metadata pour les lois cibles (max 10)
                    for leg in relevant[:10]:
                        request_count = _load_counter()
                        if request_count >= DAILY_LIMIT:
                            break
                        leg_id = leg.get('legislationId', '')
                        meta, request_count = fetch_legislation_metadata(db_id, leg_id, lang)
                        if meta:
                            logger.info(f"      {leg_id}: {meta.get('title', 'N/A')}")

    log_import('canlii_legislation', 'api.canlii.org/legislationBrowse',
               'canlii_legislation', total_inserted, total_inserted)
    logger.info(f"Legislation total: {total_inserted} lois pertinentes importees")
    return results
