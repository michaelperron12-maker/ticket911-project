"""
Module Collisions SAAQ - Donnees Quebec CSV direct download.
Aucune cle API requise.
Source: https://www.donneesquebec.ca/recherche/dataset/rapports-d-accident
Les fichiers CSV sont heberges sur S3 (pas dans le DataStore API).
"""
import logging
import json
import csv
import io
import requests
from utils.db import bulk_insert, log_import

logger = logging.getLogger(__name__)

# URLs directes des CSV sur S3 (par annee)
COLLISION_CSV_URLS = {
    2022: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Rapport_Accident_2022.csv',
    2021: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Rapport_Accident_2021.csv',
    2020: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Rapport_Accident_2020.csv',
    2019: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Rapport_Accident_2019.csv',
    2018: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Rapport_Accident_2018.csv',
    2017: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Rapport_Accident_2017.csv',
    2016: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Rapport_Accident_2016.csv',
    2015: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Rapport_Accident_2015.csv',
    2014: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Rapport_Accident_2014.csv',
    2013: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Rapport_Accident_2013.csv',
    2012: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Rapport_Accident_2012.csv',
    2011: 'https://dq-prd-bucket1.s3.ca-central-1.amazonaws.com/saaq/Rapport_Accident_2011.csv',
}


def _safe_int(val):
    if val is None or val == '':
        return None
    try:
        return int(float(str(val).replace(',', '').strip()))
    except (ValueError, TypeError):
        return None


def _clean(val):
    if val is None:
        return None
    val = str(val).strip()
    return val if val else None


def fetch_collisions_saaq():
    """Fetch les rapports d'accident SAAQ depuis les CSV S3."""
    logger.info("Fetching collisions SAAQ (CSV direct download)...")
    total_inserted = 0

    for year, url in sorted(COLLISION_CSV_URLS.items()):
        logger.info(f"  Downloading {year} from {url}...")
        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"  Error downloading {year}: {e}")
            log_import(f'qc_collisions_saaq_{year}', url, 'ckan_collisions_saaq',
                       0, 0, 'error', str(e))
            continue

        # Decode CSV (BOM-aware)
        content = resp.content.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(content))

        rows = []
        for r in reader:
            # Map CSV columns to DB columns
            # CSV: AN, NO_SEQ_COLL, MS_ACCDN, HR_ACCDN, JR_SEMN_ACCDN, GRAVITE,
            #      NB_VICTIMES_TOTAL, NB_VEH_IMPLIQUES_ACCDN, REG_ADM, VITESSE_AUTOR,
            #      CD_GENRE_ACCDN, CD_ETAT_SURFC, CD_ECLRM, CD_ENVRN_ACCDN,
            #      CD_CATEG_ROUTE, CD_ASPCT_ROUTE, CD_LOCLN_ACCDN, CD_CONFG_ROUTE,
            #      CD_ZON_TRAVX_ROUTR, CD_COND_METEO, IND_AUTO_CAMION_LEGER,
            #      IND_VEH_LOURD, IND_MOTO_CYCLO, IND_VELO, IND_PIETON
            rows.append((
                _safe_int(r.get('AN')),
                None,  # date_collision (not directly available, only month MS_ACCDN)
                _clean(r.get('HR_ACCDN')),
                _clean(r.get('REG_ADM')),
                None,  # municipalite (not in this dataset)
                None,  # route (not in this dataset)
                _clean(r.get('CD_CATEG_ROUTE')),
                _clean(r.get('GRAVITE')),
                _safe_int(r.get('NB_VEH_IMPLIQUES_ACCDN')),
                _safe_int(r.get('NB_VICTIMES_TOTAL')),
                None,  # nombre_deces (not separate column)
                None,  # nombre_blesses_graves
                None,  # nombre_blesses_legers
                _clean(r.get('CD_ECLRM')),
                _clean(r.get('CD_ETAT_SURFC')),
                _clean(r.get('CD_COND_METEO')),
                json.dumps({k: v for k, v in r.items() if v}),
                f'saaq_csv_{year}',
            ))

        if rows:
            columns = [
                'annee', 'date_collision', 'heure_collision',
                'region_admin', 'municipalite', 'route', 'type_route',
                'gravite', 'nombre_vehicules', 'nombre_victimes',
                'nombre_deces', 'nombre_blesses_graves', 'nombre_blesses_legers',
                'eclairage', 'etat_surface', 'conditions_meteo',
                'raw_data', 'source_resource_id'
            ]
            count = bulk_insert('qc_collisions_saaq', columns, rows)
            total_inserted += count
            logger.info(f"    {year}: {count} collision records inserted.")
            log_import(f'qc_collisions_saaq_{year}', url, 'ckan_collisions_saaq',
                       len(rows), count)
        else:
            logger.warning(f"    {year}: No rows parsed.")
            log_import(f'qc_collisions_saaq_{year}', url, 'ckan_collisions_saaq',
                       0, 0, 'warning', 'No rows parsed')

    return total_inserted


def run():
    """Point d'entree du module collisions SAAQ."""
    logger.info("=" * 50)
    logger.info("MODULE COLLISIONS SAAQ (CSV direct download)")
    logger.info("=" * 50)
    results = {}
    results['collisions_saaq'] = fetch_collisions_saaq()
    logger.info(f"Collisions SAAQ total: {sum(results.values())} records")
    return results
