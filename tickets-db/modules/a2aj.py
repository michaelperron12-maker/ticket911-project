"""
Module A2AJ - Access to Algorithmic Justice.
Alternative GRATUITE a CanLII pour jurisprudence canadienne en texte integral.

API: https://api.a2aj.ca/docs
- /search : recherche plein texte (max 50 resultats par requete)
- /fetch  : texte integral par citation
- /coverage : info sur les datasets disponibles

Avantages vs CanLII:
- Texte integral des decisions (pas juste metadata)
- Pas de limite quotidienne stricte (mais on reste poli: 1 req/sec)
- 116,000+ decisions canadiennes
- Filtrage par dataset (tribunal), date, langue

Limites:
- Max 50 resultats par recherche
- Pas encore tous les tribunaux QC (surtout federal, ON, BC)
- Pas de citateur (citations entre cas)
"""
import logging
import json
import time
from utils.fetcher import fetch_json
from utils.db import get_connection, log_import

logger = logging.getLogger(__name__)

A2AJ_BASE = 'https://api.a2aj.ca'
MIN_DELAY = 1.0  # 1 req/sec pour etre poli

# Datasets A2AJ pertinents pour tickets routiers
# Format: (dataset_code, province, lang)
# Voir /coverage pour la liste complete
SEARCH_CONFIGS = [
    # Quebec
    {'datasets': 'QCCA,QCCS,QCCQ', 'province': 'QC', 'lang': 'fr',
     'queries': [
         'code sécurité routière excès vitesse',
         'constat infraction routière radar',
         'grand excès vitesse article 328',
         'alcool volant conduite dangereuse',
         'cellulaire distraction conduite',
         'points inaptitude permis',
         'feu rouge infraction',
     ]},
    # Ontario
    {'datasets': 'ONCA,ONSCDC,ONCJ', 'province': 'ON', 'lang': 'en',
     'queries': [
         'highway traffic act speeding',
         'stunt driving racing section 172',
         'radar lidar speed detection',
         'careless dangerous driving',
         'provincial offences traffic ticket',
         'distracted driving cell phone',
         'demerit points licence suspension',
     ]},
    # Federal (certains cas de conduite)
    {'datasets': 'SCC,FCA,FC', 'province': 'CA', 'lang': 'en',
     'queries': [
         'criminal code dangerous driving',
         'impaired driving over 80',
     ]},
]


def _a2aj_fetch(endpoint, params):
    """Fetch A2AJ API avec rate limiting poli."""
    time.sleep(MIN_DELAY)
    url = f"{A2AJ_BASE}/{endpoint}"
    return fetch_json(url, params, delay=0, timeout=30)


def search_cases(query, datasets=None, lang='en', start_date=None, end_date=None, size=50):
    """Recherche de cas dans A2AJ."""
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
    if start_date:
        params['start_date'] = start_date
    if end_date:
        params['end_date'] = end_date

    try:
        data = _a2aj_fetch('search', params)
        if isinstance(data, list):
            return data
        return data.get('results', [])
    except Exception as e:
        logger.warning(f"  A2AJ search error for '{query}': {e}")
        return []


def fetch_full_text(citation, lang='en'):
    """Recupere le texte integral d'un cas par citation."""
    params = {
        'citation': citation,
        'doc_type': 'cases',
        'output_language': lang,
    }
    try:
        data = _a2aj_fetch('fetch', params)
        return data
    except Exception as e:
        logger.warning(f"  A2AJ fetch error for '{citation}': {e}")
        return {}


def fetch_coverage():
    """Recupere les infos sur les datasets disponibles."""
    try:
        data = _a2aj_fetch('coverage', {'doc_type': 'cases'})
        return data
    except Exception as e:
        logger.warning(f"  A2AJ coverage error: {e}")
        return {}


def insert_a2aj_cases(cases, province, source_query):
    """Insere les cas A2AJ dans la table jurisprudence."""
    conn = get_connection()
    inserted = 0
    with conn:
        with conn.cursor() as cur:
            for c in cases:
                # Champs A2AJ: citation_en/fr, name_en/fr, document_date_en/fr, url_en/fr, snippet
                lang_suffix = '_fr' if province == 'QC' else '_en'
                citation = (c.get(f'citation{lang_suffix}') or c.get('citation_en')
                            or c.get('citation_fr') or '')
                if not citation:
                    continue

                # Utiliser la citation comme canlii_id (format compatible)
                canlii_id = f"a2aj_{citation.replace(' ', '_').replace(',', '').replace('.', '')[:95]}"
                title = (c.get(f'name{lang_suffix}') or c.get('name_en')
                         or c.get('name_fr') or citation)
                date_raw = (c.get(f'document_date{lang_suffix}') or c.get('document_date_en') or '')
                date_str = date_raw[:10] if date_raw else ''  # Extract YYYY-MM-DD
                dataset = c.get('dataset', '')
                snippet = c.get('snippet', '')
                url = (c.get(f'url{lang_suffix}') or c.get('url_en') or '')

                try:
                    cur.execute("""
                        INSERT INTO jurisprudence
                        (canlii_id, database_id, province, titre, citation,
                         date_decision, url_canlii, tribunal, langue,
                         resume,
                         est_ticket_related, source, raw_metadata)
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
                    logger.warning(f"    A2AJ insert error for {citation}: {e}")
                    conn.rollback()
    conn.close()
    return inserted


def run():
    """Point d'entree du module A2AJ."""
    logger.info("=" * 50)
    logger.info("MODULE A2AJ - JURISPRUDENCE TEXTE INTEGRAL")
    logger.info("=" * 50)

    # Verifier la couverture
    coverage = fetch_coverage()
    if coverage:
        logger.info(f"  A2AJ coverage: {json.dumps(coverage, indent=2)[:500]}")

    total_inserted = 0
    total_found = 0

    for config in SEARCH_CONFIGS:
        datasets = config['datasets']
        province = config['province']
        lang = config['lang']

        logger.info(f"  Searching A2AJ for {province} ({datasets})...")

        for query in config['queries']:
            results = search_cases(query, datasets=datasets, lang=lang)
            if results:
                total_found += len(results)
                count = insert_a2aj_cases(results, province, query)
                total_inserted += count
                logger.info(f"    '{query}': {len(results)} found, {count} inserted")
            else:
                logger.info(f"    '{query}': 0 results")

    log_import('a2aj', 'https://api.a2aj.ca', 'a2aj', total_found, total_inserted)
    logger.info(f"A2AJ total: {total_found} found, {total_inserted} inserted")
    return {'found': total_found, 'inserted': total_inserted}
