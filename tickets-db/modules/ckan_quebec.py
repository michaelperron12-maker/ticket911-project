"""
Module Donnees Quebec - CKAN API.
Aucune cle API requise.

Datasets :
- Constats d'infraction (Controle routier QC) - CSV par annee
- Statistiques radar-photo (constats signifies)
- Localisation radars photo (GPS)
- Vehicules en circulation
- Collisions SAAQ
"""
import logging
import json
from config import DONNEES_QC_BASE
from utils.fetcher import ckan_datastore_fetch_all, ckan_get_resources
from utils.db import bulk_insert, log_import

logger = logging.getLogger(__name__)

CONSTATS_SLUG = 'constats-infraction-controle-routier'
RADAR_STATS_SLUG = 'statistiques-constats-signifies-radar-photographique'
RADAR_LIEUX_SLUG = 'radar-photo'
VEHICULES_SLUG = 'vehicules-en-circulation'


def _safe_int(val):
    """Convertit en int ou None."""
    if val is None or val == '':
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _safe_float(val):
    """Convertit en float ou None."""
    if val is None or val == '':
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _get(r, *keys):
    """Recupere la premiere valeur non-None parmi les cles."""
    for k in keys:
        v = r.get(k)
        if v is not None and v != '':
            return v
    return None


def fetch_constats():
    """Fetch les constats d'infraction de Controle routier QC (toutes annees)."""
    logger.info("Fetching constats d'infraction Controle routier QC...")
    resources = ckan_get_resources(DONNEES_QC_BASE, CONSTATS_SLUG)

    total_inserted = 0
    for res in resources:
        if res.get('format', '').upper() != 'CSV':
            continue
        resource_id = res['id']
        name = res.get('name', resource_id)
        logger.info(f"  Processing resource: {name} ({resource_id})")

        try:
            records = ckan_datastore_fetch_all(DONNEES_QC_BASE, resource_id)
            if not records:
                logger.info(f"    No records in DataStore, skipping.")
                continue

            rows = []
            for r in records:
                rows.append((
                    _safe_int(_get(r, 'ANNEE', 'annee')),
                    _get(r, 'DATE_INFRACTION', 'date_infraction'),
                    _get(r, 'HEURE_INFRACTION', 'heure_infraction'),
                    _get(r, 'REGION', 'region'),
                    _get(r, 'LIEU_INFRACTION', 'lieu_infraction'),
                    _get(r, 'TYPE_INTERVENTION', 'type_intervention'),
                    _get(r, 'LOI', 'loi'),
                    _get(r, 'REGLEMENT', 'reglement'),
                    _get(r, 'ARTICLE', 'article'),
                    _get(r, 'DESCRIPTION_INFRACTION', 'description_infraction'),
                    _safe_int(_get(r, 'VITESSE_PERMISE', 'vitesse_permise')),
                    _safe_int(_get(r, 'VITESSE_CONSTATEE', 'vitesse_constatee')),
                    _safe_float(_get(r, 'MONTANT_AMENDE', 'montant_amende')),
                    _safe_int(_get(r, 'POINTS_INAPTITUDE', 'points_inaptitude')),
                    _get(r, 'CATEGORIE_VEHICULE', 'categorie_vehicule'),
                    json.dumps(r),
                    resource_id,
                ))

            columns = [
                'annee_donnees', 'date_infraction', 'heure_infraction',
                'region', 'lieu_infraction', 'type_intervention',
                'loi', 'reglement', 'article', 'description_infraction',
                'vitesse_permise', 'vitesse_constatee', 'montant_amende',
                'points_inaptitude', 'categorie_vehicule',
                'raw_data', 'source_resource_id'
            ]
            count = bulk_insert('qc_constats_infraction', columns, rows)
            total_inserted += count

        except Exception as e:
            logger.error(f"    Error processing {name}: {e}")
            log_import(f'qc_constats_{name}', res.get('url'), 'ckan_quebec', 0, 0, 'error', str(e))

    log_import('qc_constats_infraction',
               f'https://www.donneesquebec.ca/recherche/dataset/{CONSTATS_SLUG}',
               'ckan_quebec', total_inserted, total_inserted)
    return total_inserted


def fetch_radar_stats():
    """Fetch les statistiques des constats signifies par radar photo."""
    logger.info("Fetching statistiques radar-photo...")
    resources = ckan_get_resources(DONNEES_QC_BASE, RADAR_STATS_SLUG)
    total = 0
    for res in resources:
        if res.get('format', '').upper() != 'CSV':
            continue
        resource_id = res['id']
        try:
            records = ckan_datastore_fetch_all(DONNEES_QC_BASE, resource_id)
            rows = []
            for r in records:
                rows.append((
                    _get(r, 'DATE_RAPPORT', 'date_rapport'),
                    _get(r, 'TYPE_APPAREIL', 'type_appareil'),
                    _get(r, 'LOCALISATION', 'localisation'),
                    _get(r, 'MUNICIPALITE', 'municipalite'),
                    _get(r, 'ROUTE', 'route'),
                    _get(r, 'DIRECTION', 'direction'),
                    _safe_int(_get(r, 'VITESSE_LIMITE', 'vitesse_limite')),
                    _safe_int(_get(r, 'NOMBRE_CONSTATS', 'nombre_constats')),
                    _get(r, 'PERIODE', 'periode'),
                    json.dumps(r),
                    resource_id,
                ))
            columns = [
                'date_rapport', 'type_appareil', 'localisation',
                'municipalite', 'route', 'direction', 'vitesse_limite',
                'nombre_constats', 'periode', 'raw_data', 'source_resource_id'
            ]
            count = bulk_insert('qc_radar_photo_stats', columns, rows)
            total += count
        except Exception as e:
            logger.error(f"  Error radar stats: {e}")
    log_import('qc_radar_photo_stats', '', 'ckan_quebec', total, total)
    return total


def fetch_radar_lieux():
    """Fetch localisation des radars photo (GPS)."""
    logger.info("Fetching localisation radars photo...")
    resources = ckan_get_resources(DONNEES_QC_BASE, RADAR_LIEUX_SLUG)
    total = 0
    for res in resources:
        fmt = res.get('format', '').upper()
        if fmt not in ('CSV', 'GEOJSON', 'JSON'):
            continue
        resource_id = res['id']
        try:
            records = ckan_datastore_fetch_all(DONNEES_QC_BASE, resource_id)
            rows = []
            for r in records:
                rows.append((
                    _get(r, 'TYPE_APPAREIL', 'type_appareil'),
                    _get(r, 'MUNICIPALITE', 'municipalite'),
                    _get(r, 'ROUTE', 'route'),
                    _get(r, 'EMPLACEMENT', 'emplacement'),
                    _get(r, 'DIRECTION', 'direction'),
                    _safe_int(_get(r, 'VITESSE_LIMITE', 'vitesse_limite')),
                    _safe_float(_get(r, 'LATITUDE', 'latitude')),
                    _safe_float(_get(r, 'LONGITUDE', 'longitude')),
                    _get(r, 'DATE_MISE_SERVICE', 'date_mise_service'),
                    True,
                    json.dumps(r),
                ))
            columns = [
                'type_appareil', 'municipalite', 'route', 'emplacement',
                'direction', 'vitesse_limite', 'latitude', 'longitude',
                'date_mise_service', 'actif', 'raw_data'
            ]
            count = bulk_insert('qc_radar_photo_lieux', columns, rows)
            total += count
        except Exception as e:
            logger.error(f"  Error radar lieux: {e}")
    log_import('qc_radar_photo_lieux', '', 'ckan_quebec', total, total)
    return total


def fetch_vehicules():
    """Fetch vehicules en circulation SAAQ."""
    logger.info("Fetching vehicules en circulation...")
    resources = ckan_get_resources(DONNEES_QC_BASE, VEHICULES_SLUG)
    total = 0
    for res in resources:
        if res.get('format', '').upper() != 'CSV':
            continue
        resource_id = res['id']
        try:
            records = ckan_datastore_fetch_all(DONNEES_QC_BASE, resource_id)
            rows = []
            for r in records:
                rows.append((
                    _safe_int(_get(r, 'ANNEE', 'annee')),
                    _get(r, 'REGION', 'region'),
                    _get(r, 'TYPE_VEHICULE', 'type_vehicule'),
                    _safe_int(_get(r, 'NOMBRE_VEHICULES', 'nombre_vehicules')),
                    json.dumps(r),
                ))
            columns = ['annee', 'region', 'type_vehicule', 'nombre_vehicules', 'raw_data']
            count = bulk_insert('qc_vehicules_circulation', columns, rows)
            total += count
        except Exception as e:
            logger.error(f"  Error vehicules: {e}")
    log_import('qc_vehicules_circulation', '', 'ckan_quebec', total, total)
    return total


def run():
    """Point d'entree du module Quebec."""
    logger.info("=" * 50)
    logger.info("MODULE DONNEES QUEBEC (CKAN API)")
    logger.info("=" * 50)
    results = {}
    results['constats'] = fetch_constats()
    results['radar_stats'] = fetch_radar_stats()
    results['radar_lieux'] = fetch_radar_lieux()
    results['vehicules'] = fetch_vehicules()
    logger.info(f"Quebec total: {sum(results.values())} records")
    return results
