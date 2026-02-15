"""
Module Montreal Open Data - CKAN API.
Aucune cle API requise.

Datasets :
- Collisions routieres (depuis 2012)
- Actes criminels SPVM
- Signalisation stationnement sur rue
- Interventions escouade mobilite
"""
import logging
import json
from config import MONTREAL_BASE
from utils.fetcher import ckan_datastore_fetch_all, ckan_get_resources
from utils.db import bulk_insert, log_import

logger = logging.getLogger(__name__)

COLLISIONS_RESOURCE = '05deae93-d9fc-4acb-9779-e0942b5e962f'
SIGNALISATION_RESOURCE = '7f1d4ae9-1a12-46d7-953e-6b9c18c78680'


def _get(r, *keys):
    for k in keys:
        v = r.get(k)
        if v is not None and v != '':
            return v
    return None


def _safe_int(val, default=0):
    if val is None or val == '':
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _safe_float(val):
    if val is None or val == '':
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def fetch_collisions():
    """Fetch collisions routieres Montreal (depuis 2012)."""
    logger.info("Fetching collisions routieres Montreal...")
    records = ckan_datastore_fetch_all(MONTREAL_BASE, COLLISIONS_RESOURCE)
    rows = []
    for r in records:
        rows.append((
            _get(r, 'NO_COLLISION', 'no_collision'),
            _get(r, 'DT_ACCDN', 'date_collision'),
            _get(r, 'HR_ACCDN', 'heure_collision'),
            _get(r, 'ARRONDISSEMENT', 'arrondissement'),
            _get(r, 'RUE_ACCDN', 'rue1'),
            _get(r, 'ACCDN_PRES_DE', 'rue2'),
            _safe_float(_get(r, 'LATITUDE', 'latitude')),
            _safe_float(_get(r, 'LONGITUDE', 'longitude')),
            _get(r, 'GRAVITE', 'gravite'),
            _safe_int(_get(r, 'NB_MORTS', 'nombre_deces')),
            _safe_int(_get(r, 'NB_BLESSES_GRAVES', 'nombre_blesses_graves')),
            _safe_int(_get(r, 'NB_BLESSES_LEGERS', 'nombre_blesses_legers')),
            _get(r, 'TYPE_COLLISION', 'type_collision'),
            _get(r, 'CD_COND_METEO', 'conditions_meteo'),
            _get(r, 'CD_ETAT_SURFC', 'etat_surface'),
            _get(r, 'CD_ECLRM', 'eclairage'),
            json.dumps(r),
        ))
    columns = [
        'no_collision', 'date_collision', 'heure_collision', 'arrondissement',
        'rue1', 'rue2', 'latitude', 'longitude', 'gravite',
        'nombre_deces', 'nombre_blesses_graves', 'nombre_blesses_legers',
        'type_collision', 'conditions_meteo', 'etat_surface', 'eclairage',
        'raw_data'
    ]
    count = bulk_insert('mtl_collisions', columns, rows, conflict_column='no_collision')
    log_import('mtl_collisions', 'donnees.montreal.ca', 'ckan_montreal', len(records), count)
    return count


def fetch_actes_criminels():
    """Fetch actes criminels SPVM (filtrer categories liees circulation)."""
    logger.info("Fetching actes criminels SPVM...")
    resources = ckan_get_resources(MONTREAL_BASE, 'actes-criminels')
    total = 0
    for res in resources:
        if res.get('format', '').upper() != 'CSV':
            continue
        resource_id = res['id']
        try:
            records = ckan_datastore_fetch_all(MONTREAL_BASE, resource_id)
            rows = []
            for r in records:
                rows.append((
                    _get(r, 'CATEGORIE', 'categorie'),
                    _get(r, 'DATE', 'date'),
                    _get(r, 'QUART', 'quart'),
                    _safe_int(_get(r, 'PDQ', 'pdq'), default=None),
                    _get(r, 'ARRONDISSEMENT', 'arrondissement'),
                    _safe_float(_get(r, 'LATITUDE', 'latitude')),
                    _safe_float(_get(r, 'LONGITUDE', 'longitude')),
                    json.dumps(r),
                ))
            columns = [
                'categorie', 'date_evenement', 'quart', 'pdq',
                'arrondissement', 'latitude', 'longitude', 'raw_data'
            ]
            count = bulk_insert('mtl_actes_criminels', columns, rows)
            total += count
            break  # Prendre la resource la plus recente
        except Exception as e:
            logger.error(f"  Error actes criminels: {e}")
    log_import('mtl_actes_criminels', '', 'ckan_montreal', total, total)
    return total


def fetch_signalisation():
    """Fetch signalisation stationnement sur rue."""
    logger.info("Fetching signalisation stationnement Montreal...")
    records = ckan_datastore_fetch_all(MONTREAL_BASE, SIGNALISATION_RESOURCE)
    rows = []
    for r in records:
        rows.append((
            _get(r, 'PANNEAU_ID', 'panneau_id'),
            _get(r, 'CODE_RPA', 'code_rpa'),
            _get(r, 'DESCRIPTION_RPA', 'description_rpa'),
            _get(r, 'FLECHE', 'fleche'),
            _safe_float(_get(r, 'LATITUDE', 'latitude')),
            _safe_float(_get(r, 'LONGITUDE', 'longitude')),
            _get(r, 'RUE', 'rue'),
            _get(r, 'ARRONDISSEMENT', 'arrondissement'),
            json.dumps(r),
        ))
    columns = [
        'panneau_id', 'code_rpa', 'description_rpa', 'fleche',
        'latitude', 'longitude', 'rue', 'arrondissement', 'raw_data'
    ]
    count = bulk_insert('mtl_signalisation_stationnement', columns, rows)
    log_import('mtl_signalisation', '', 'ckan_montreal', len(records), count)
    return count


def fetch_escouade():
    """Fetch interventions escouade mobilite."""
    logger.info("Fetching interventions escouade mobilite...")
    resources = ckan_get_resources(MONTREAL_BASE, 'interventions-escouade-mobilite')
    total = 0
    for res in resources:
        if res.get('format', '').upper() != 'CSV':
            continue
        resource_id = res['id']
        try:
            records = ckan_datastore_fetch_all(MONTREAL_BASE, resource_id)
            rows = []
            for r in records:
                rows.append((
                    _get(r, 'DATE', 'date_intervention'),
                    _get(r, 'TYPE_INTERVENTION', 'type_intervention'),
                    _get(r, 'ARRONDISSEMENT', 'arrondissement'),
                    _get(r, 'LIEU', 'lieu'),
                    _safe_float(_get(r, 'LATITUDE', 'latitude')),
                    _safe_float(_get(r, 'LONGITUDE', 'longitude')),
                    json.dumps(r),
                ))
            columns = [
                'date_intervention', 'type_intervention', 'arrondissement',
                'lieu', 'latitude', 'longitude', 'raw_data'
            ]
            count = bulk_insert('mtl_escouade_mobilite', columns, rows)
            total += count
            break
        except Exception as e:
            logger.error(f"  Error escouade: {e}")
    log_import('mtl_escouade_mobilite', '', 'ckan_montreal', total, total)
    return total


def run():
    """Point d'entree du module Montreal."""
    logger.info("=" * 50)
    logger.info("MODULE MONTREAL OPEN DATA (CKAN API)")
    logger.info("=" * 50)
    results = {}
    results['collisions'] = fetch_collisions()
    results['actes_criminels'] = fetch_actes_criminels()
    results['signalisation'] = fetch_signalisation()
    results['escouade'] = fetch_escouade()
    logger.info(f"Montreal total: {sum(results.values())} records")
    return results
