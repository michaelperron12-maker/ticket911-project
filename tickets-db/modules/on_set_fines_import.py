"""
Module Ontario Set Fines - Scrape depuis Ontario Court of Justice.
Source: https://www.ontariocourts.ca/ocj/provincial-offences/set-fines/
Schedule 43 = Highway Traffic Act (le plus pertinent pour les tickets routiers).
"""
import logging
import json
import re
import requests
from bs4 import BeautifulSoup
from utils.db import bulk_insert, log_import

logger = logging.getLogger(__name__)

# Schedule 43 = Highway Traffic Act
SET_FINES_URLS = {
    'schedule_43_hta': 'https://www.ontariocourts.ca/ocj/provincial-offences/set-fines/set-fines-i/schedule-43/',
    'schedule_61_caia': 'https://www.ontariocourts.ca/ocj/provincial-offences/set-fines/set-fines-i/schedule-61/',
}

# Surcharge et frais de cour Ontario
COURT_COSTS = 5.00
SURCHARGE_RATE = 0.25  # 25% du set fine


def _parse_fine(val):
    """Parse un montant comme '$125.00' en float."""
    if not val:
        return None
    cleaned = re.sub(r'[^\d.]', '', str(val))
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _scrape_schedule(url, loi_name):
    """Scrape une page de set fines et retourne les rows."""
    logger.info(f"  Scraping {loi_name} from {url}...")
    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"  Error fetching {url}: {e}")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    tables = soup.find_all('table')

    rows = []
    for table in tables:
        trs = table.find_all('tr')
        for tr in trs:
            tds = tr.find_all('td')
            if len(tds) < 3:
                continue

            # Format typique: Item | Offence | Section | Set Fine
            # ou: Offence | Section | Set Fine
            texts = [td.get_text(strip=True) for td in tds]

            if len(tds) >= 4:
                description = texts[1]
                article = texts[2]
                fine_str = texts[3]
            elif len(tds) == 3:
                description = texts[0]
                article = texts[1]
                fine_str = texts[2]
            else:
                continue

            amende = _parse_fine(fine_str)
            if amende is None or amende == 0:
                continue

            suramende = round(amende * SURCHARGE_RATE, 2)
            total = round(amende + suramende + COURT_COSTS, 2)

            rows.append((
                loi_name,
                article,
                description,
                amende,
                suramende,
                COURT_COSTS,
                total,
                None,  # points_inaptitude (pas dans ce dataset)
                None,  # date_mise_a_jour
                json.dumps({
                    'loi': loi_name,
                    'article': article,
                    'description': description,
                    'set_fine': amende,
                    'source_url': url,
                }),
            ))

    logger.info(f"    Parsed {len(rows)} fines from {loi_name}")
    return rows


def fetch_set_fines():
    """Fetch toutes les set fines depuis Ontario Courts."""
    logger.info("Fetching Ontario Set Fines...")
    total_inserted = 0

    for schedule_key, url in SET_FINES_URLS.items():
        loi_name = 'Highway Traffic Act' if 'hta' in schedule_key else 'Compulsory Automobile Insurance Act'
        rows = _scrape_schedule(url, loi_name)

        if rows:
            columns = [
                'loi', 'article', 'description_infraction',
                'amende_fixe', 'suramende', 'frais_cour', 'total_payable',
                'points_inaptitude', 'date_mise_a_jour', 'raw_data'
            ]
            count = bulk_insert('on_set_fines', columns, rows)
            total_inserted += count
            log_import(f'on_set_fines_{schedule_key}', url, 'on_set_fines_import',
                       len(rows), count)
        else:
            log_import(f'on_set_fines_{schedule_key}', url, 'on_set_fines_import',
                       0, 0, 'warning', 'No rows parsed')

    return total_inserted


def run():
    """Point d'entree du module Ontario Set Fines."""
    logger.info("=" * 50)
    logger.info("MODULE ONTARIO SET FINES (Court schedules)")
    logger.info("=" * 50)
    results = {}
    results['set_fines'] = fetch_set_fines()
    logger.info(f"Ontario Set Fines total: {sum(results.values())} records")
    return results
