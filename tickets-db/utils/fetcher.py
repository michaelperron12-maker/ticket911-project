"""
HTTP fetch avec retry, rate limiting et pagination CKAN.
"""
import requests
import time
import logging
from config import REQUEST_DELAY, MAX_RETRIES

logger = logging.getLogger(__name__)


def fetch_json(url, params=None, retries=None, delay=None, timeout=60):
    """Fetch JSON avec retry et rate limiting."""
    retries = retries or MAX_RETRIES
    delay = delay or REQUEST_DELAY

    for attempt in range(retries):
        try:
            time.sleep(delay)
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Attempt {attempt+1}/{retries} failed for {url}: {e}")
            if attempt == retries - 1:
                raise
            time.sleep(delay * (attempt + 1))


def fetch_csv_url(url, timeout=120):
    """Telecharge un CSV directement et retourne le contenu texte."""
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def ckan_datastore_fetch_all(base_url, resource_id, limit=32000):
    """Fetch toutes les lignes d'un DataStore CKAN avec pagination."""
    all_records = []
    offset = 0
    while True:
        url = f"{base_url}/datastore_search"
        params = {'resource_id': resource_id, 'limit': limit, 'offset': offset}
        data = fetch_json(url, params)
        records = data.get('result', {}).get('records', [])
        if not records:
            break
        all_records.extend(records)
        offset += limit
        logger.info(f"  Fetched {len(all_records)} records so far...")
        if len(records) < limit:
            break
    return all_records


def ckan_get_resources(base_url, dataset_slug):
    """Recupere la liste des resources (CSV) d'un dataset CKAN."""
    url = f"{base_url}/package_show"
    data = fetch_json(url, params={'id': dataset_slug})
    resources = data.get('result', {}).get('resources', [])
    return resources
