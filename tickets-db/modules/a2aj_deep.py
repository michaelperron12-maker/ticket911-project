"""
Module A2AJ - Recherche approfondie.
Plus de queries, recherche par nom de loi, recherche par section specifique.
Complement au module a2aj.py de base.
"""
import logging
import json
import time
from utils.fetcher import fetch_json
from utils.db import get_connection, log_import

logger = logging.getLogger(__name__)

A2AJ_BASE = 'https://api.a2aj.ca'
MIN_DELAY = 1.0


def _a2aj_fetch(endpoint, params):
    time.sleep(MIN_DELAY)
    url = f"{A2AJ_BASE}/{endpoint}"
    return fetch_json(url, params, delay=0, timeout=30)


def search_cases(query, datasets=None, lang='en', size=50):
    params = {
        'query': query,
        'search_type': 'full_text',
        'doc_type': 'cases',
        'size': min(size, 50),
        'search_language': lang,
        'sort_results': 'newest_first',
    }
    if datasets:
        params['dataset'] = datasets
    try:
        data = _a2aj_fetch('search', params)
        if isinstance(data, list):
            return data
        return data.get('results', [])
    except Exception as e:
        logger.warning(f"  A2AJ search error: {e}")
        return []


# Recherches approfondies - requetes specifiques par section de loi
DEEP_QUERIES = [
    # Ontario - HTA sections specifiques
    {'datasets': 'ONCA,ONSCDC,ONCJ', 'province': 'ON', 'lang': 'en', 'queries': [
        'section 128 Highway Traffic Act',          # Speeding
        'section 130 Highway Traffic Act',          # Careless driving
        'section 172 Highway Traffic Act',          # Stunt driving/racing
        'section 144 Highway Traffic Act',          # Red light
        'section 78.1 Highway Traffic Act',         # Distracted driving
        'section 106 Highway Traffic Act',          # Seatbelt
        'section 134 Highway Traffic Act',          # Following too closely
        'section 148 Highway Traffic Act',          # Improper passing
        'section 136 Highway Traffic Act',          # Right of way
        'section 199 Highway Traffic Act',          # Fail to remain at scene
        'section 32 Highway Traffic Act licence',   # Licence suspension
        'section 41 Highway Traffic Act demerit',   # Demerit points
        'speeding ticket dismissed',
        'traffic offence appeal allowed',
        'Charter rights traffic stop',
        'radar evidence reliability',
        'speed measuring device calibration',
        'due diligence traffic offence',
        'absolute liability speeding',
        'stunt driving 50 over',
    ]},
    # Ontario - Criminal driving
    {'datasets': 'ONCA,ONSCDC,ONCJ', 'province': 'ON', 'lang': 'en', 'queries': [
        'dangerous driving Criminal Code 320.13',
        'impaired driving Criminal Code 320.14',
        'over 80 blood alcohol',
        'refuse breathalyzer',
        'driving while disqualified',
    ]},
    # Federal - Supreme Court driving cases
    {'datasets': 'SCC', 'province': 'CA', 'lang': 'en', 'queries': [
        'dangerous driving',
        'impaired driving',
        'Highway Traffic Act constitutional',
        'traffic enforcement Charter',
        'absolute liability provincial offence',
    ]},
    # Broader Ontario search
    {'datasets': 'ONCA,ONSCDC,ONCJ', 'province': 'ON', 'lang': 'en', 'queries': [
        'licence suspension points',
        'G1 G2 novice driver',
        'insurance act motor vehicle',
        'accident fail to report',
        'street racing exhibition',
        'excessive speed highway',
    ]},
]


def insert_a2aj_cases(cases, province):
    """Insere les cas A2AJ dans jurisprudence."""
    conn = get_connection()
    inserted = 0
    with conn:
        with conn.cursor() as cur:
            for c in cases:
                lang_suffix = '_fr' if province == 'QC' else '_en'
                citation = (c.get(f'citation{lang_suffix}') or c.get('citation_en')
                            or c.get('citation_fr') or '')
                if not citation:
                    continue

                canlii_id = f"a2aj_{citation.replace(' ', '_').replace(',', '').replace('.', '')[:95]}"
                title = (c.get(f'name{lang_suffix}') or c.get('name_en')
                         or c.get('name_fr') or citation)
                date_raw = (c.get(f'document_date{lang_suffix}') or c.get('document_date_en') or '')
                date_str = date_raw[:10] if date_raw else ''
                dataset = c.get('dataset', '')
                snippet = c.get('snippet', '')
                url = (c.get(f'url{lang_suffix}') or c.get('url_en') or '')

                try:
                    cur.execute("""
                        INSERT INTO jurisprudence
                        (canlii_id, database_id, province, titre, citation,
                         date_decision, url_canlii, tribunal, langue,
                         resume, est_ticket_related, source, raw_metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (canlii_id) DO UPDATE SET
                            resume = CASE
                                WHEN COALESCE(LENGTH(EXCLUDED.resume), 0) > COALESCE(LENGTH(jurisprudence.resume), 0)
                                THEN EXCLUDED.resume
                                ELSE jurisprudence.resume
                            END,
                            raw_metadata = EXCLUDED.raw_metadata
                    """, (
                        canlii_id,
                        dataset.lower(),
                        province,
                        title,
                        citation,
                        date_str if date_str else None,
                        url,
                        dataset.lower(),
                        'fr' if province == 'QC' else 'en',
                        snippet,
                        True,
                        'a2aj',
                        json.dumps(c),
                    ))
                    inserted += 1
                except Exception as e:
                    logger.warning(f"    Insert error {citation}: {e}")
                    conn.rollback()
    conn.close()
    return inserted


def run():
    """Point d'entree recherche A2AJ approfondie."""
    logger.info("=" * 50)
    logger.info("MODULE A2AJ - RECHERCHE APPROFONDIE")
    logger.info("=" * 50)

    total_found = 0
    total_inserted = 0

    for config in DEEP_QUERIES:
        datasets = config['datasets']
        province = config['province']
        lang = config['lang']

        logger.info(f"  A2AJ deep search {province} ({datasets})...")

        for query in config['queries']:
            results = search_cases(query, datasets=datasets, lang=lang)
            if results:
                total_found += len(results)
                count = insert_a2aj_cases(results, province)
                total_inserted += count
                if count > 0:
                    logger.info(f"    '{query}': {len(results)} found, {count} new")
            # else silently skip empty results

    log_import('a2aj_deep', 'https://api.a2aj.ca', 'a2aj_deep', total_found, total_inserted)
    logger.info(f"A2AJ deep total: {total_found} found, {total_inserted} inserted")
    return {'found': total_found, 'inserted': total_inserted}
