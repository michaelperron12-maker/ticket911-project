"""
Module Vehicules en circulation SAAQ - Donnees Quebec CSV direct download.
Aucune cle API requise.
Source: https://www.donneesquebec.ca/recherche/dataset/vehicules-en-circulation
Les fichiers CSV sont heberges sur S3 (pas dans le DataStore API).
"""
import logging
import json
import csv
import io
import requests
from collections import Counter
from utils.db import bulk_insert, log_import

logger = logging.getLogger(__name__)

# URLs directes des CSV sur S3 (par annee)
VEHICULES_CSV_URLS = {
    2022: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Vehicule_En_Circulation_2022.csv',
    2021: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Vehicule_En_Circulation_2021.csv',
    2020: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Vehicule_En_Circulation_2020.csv',
    2019: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Vehicule_En_Circulation_2019.csv',
    2018: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Vehicule_En_Circulation_2018.csv',
    2017: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Vehicule_En_Circulation_2017.csv',
    2016: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Vehicule_En_Circulation_2016.csv',
    2015: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Vehicule_En_Circulation_2015.csv',
    2014: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Vehicule_En_Circulation_2014.csv',
    2013: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Vehicule_En_Circulation_2013.csv',
    2012: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Vehicule_En_Circulation_2012.csv',
    2011: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Vehicule_En_Circulation_2011.csv',
}

# Mapping CLAS code -> type vehicule lisible
CLAS_MAP = {
    'PAU': 'Promenade/Automobile',
    'CAM': 'Camion',
    'HMN': 'Hors route/Motoneige',
    'MOT': 'Motocyclette',
    'CYC': 'Cyclomoteur',
    'TAX': 'Taxi',
    'AUT': 'Autobus',
    'REM': 'Remorque',
    'URG': 'Urgence',
    'AGR': 'Agricole',
    'OUT': 'Outillage',
}


def _safe_int(val):
    if val is None or val == '':
        return None
    try:
        return int(float(str(val).replace(',', '').strip()))
    except (ValueError, TypeError):
        return None


def fetch_vehicules():
    """Fetch vehicules en circulation SAAQ depuis les CSV S3.

    Les CSV ont des millions de lignes par annee (1 ligne par vehicule).
    On agrege par annee + region + type_vehicule pour reduire le volume.
    """
    logger.info("Fetching vehicules en circulation SAAQ (CSV direct download)...")
    total_inserted = 0

    for year, url in sorted(VEHICULES_CSV_URLS.items()):
        logger.info(f"  Downloading {year} from {url}...")
        try:
            resp = requests.get(url, timeout=300, stream=True)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"  Error downloading {year}: {e}")
            log_import(f'qc_vehicules_{year}', url, 'ckan_vehicules',
                       0, 0, 'error', str(e))
            continue

        # Decode CSV (BOM-aware), aggregate by region + type
        content = resp.content.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(content))

        # Aggregate: (region, type_vehicule) -> count
        agg = Counter()
        total_lines = 0
        for r in reader:
            total_lines += 1
            region = (r.get('REG_ADM') or '').strip() or 'Inconnue'
            clas = (r.get('CLAS') or '').strip()
            type_veh = CLAS_MAP.get(clas, clas or 'Autre')
            agg[(region, type_veh)] += 1

        logger.info(f"    {year}: {total_lines} vehicules, {len(agg)} groupes region/type")

        rows = []
        for (region, type_veh), count in agg.items():
            rows.append((
                year,
                region,
                type_veh,
                count,
                json.dumps({
                    'annee': year,
                    'region': region,
                    'type_vehicule': type_veh,
                    'nombre': count,
                    'source_url': url,
                }),
            ))

        if rows:
            columns = ['annee', 'region', 'type_vehicule', 'nombre_vehicules', 'raw_data']
            count = bulk_insert('qc_vehicules_circulation', columns, rows)
            total_inserted += count
            logger.info(f"    {year}: {count} aggregated records inserted.")
            log_import(f'qc_vehicules_{year}', url, 'ckan_vehicules',
                       total_lines, count)
        else:
            log_import(f'qc_vehicules_{year}', url, 'ckan_vehicules',
                       0, 0, 'warning', 'No rows parsed')

    return total_inserted


def run():
    """Point d'entree du module vehicules en circulation."""
    logger.info("=" * 50)
    logger.info("MODULE VEHICULES EN CIRCULATION SAAQ")
    logger.info("=" * 50)
    results = {}
    results['vehicules'] = fetch_vehicules()
    logger.info(f"Vehicules total: {sum(results.values())} aggregated records")
    return results
