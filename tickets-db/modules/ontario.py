"""
Module Ontario Open Data.
Aucune cle API requise.
Principalement des CSV a telecharger directement.
"""
import logging
import csv
import io
import json
from utils.fetcher import fetch_csv_url, fetch_json
from utils.db import bulk_insert, log_import

logger = logging.getLogger(__name__)

# URLs
OPP_TRAFFIC_CSV = 'https://files.ontario.ca/opendata/1314-012_traffic_violation_numbers_csv_2008-12.csv'
TORONTO_PARKING_CKAN = 'https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/package_show?id=parking-tickets'


def _safe_int(val):
    if val is None or val == '':
        return None
    try:
        return int(float(str(val).replace(',', '')))
    except (ValueError, TypeError):
        return None


def fetch_opp_traffic():
    """Fetch OPP traffic offences.

    Le CSV est au format pivote:
      Row 1: header (vide)
      Row 2: Geography, Violations, 2008, 2009, 2010, 2011, 2012
      Row 3+: data rows

    On filtre seulement les lignes qui commencent par 'Ontario'.
    """
    logger.info("Fetching Ontario OPP traffic offences...")
    try:
        content = fetch_csv_url(OPP_TRAFFIC_CSV)
        lines = content.splitlines()
        # Skip row 1 (title), use row 2 as header
        if len(lines) < 3:
            logger.error("  CSV too short")
            return 0

        reader = csv.reader(io.StringIO('\n'.join(lines[1:])))
        header = next(reader)
        # header: ['Geography...', 'Violations...', '2008', '2009', '2010', '2011', '2012']
        year_cols = [h.strip() for h in header[2:]]

        rows = []
        for line in reader:
            if len(line) < 3:
                continue
            geography = line[0].strip()
            if not geography.startswith('Ontario'):
                continue
            violation_type = line[1].strip()
            if not violation_type:
                continue

            for i, year_str in enumerate(year_cols):
                year = _safe_int(year_str)
                if year is None:
                    continue
                val = line[2 + i].strip() if (2 + i) < len(line) else ''
                count_val = _safe_int(val)
                if count_val is None or count_val == 0:
                    continue
                rows.append((
                    year,
                    violation_type,
                    count_val,
                    None,
                    'opp_traffic_offences',
                    json.dumps({
                        'geography': geography,
                        'violation': violation_type,
                        'year': year,
                        'count': count_val,
                    }),
                ))

        columns = [
            'annee', 'type_infraction', 'nombre_infractions',
            'variation_annuelle', 'source_dataset', 'raw_data'
        ]
        count = bulk_insert('on_traffic_offences', columns, rows)
        logger.info(f"  Inserted {count} OPP traffic offences.")
        log_import('on_traffic_offences_opp', OPP_TRAFFIC_CSV, 'ontario', len(rows), count)
        return count
    except Exception as e:
        logger.error(f"  Error fetching OPP data: {e}")
        log_import('on_traffic_offences_opp', OPP_TRAFFIC_CSV, 'ontario', 0, 0, 'error', str(e))
        return 0


def fetch_toronto_parking():
    """Tente de fetch Toronto parking tickets (dataset possiblement retire)."""
    logger.info("Fetching Toronto parking tickets...")
    try:
        data = fetch_json(TORONTO_PARKING_CKAN)
        resources = data.get('result', {}).get('resources', [])
        csv_found = False
        for res in resources:
            if res.get('format', '').upper() == 'CSV':
                csv_url = res.get('url')
                logger.info(f"  Found CSV: {csv_url}")
                csv_found = True
                # Les fichiers sont tres gros (37M records)
                # On log la decouverte, traitement manuel recommande
                log_import('to_parking_tickets', csv_url, 'ontario', 0, 0, 'info',
                           'Dataset volumineux (37M records) - import partiel recommande')
                break
        if not csv_found:
            logger.info("  No CSV resources found for Toronto parking.")
            log_import('to_parking_tickets', '', 'ontario', 0, 0, 'skipped', 'No CSV available')
    except Exception as e:
        logger.warning(f"  Toronto parking dataset non disponible: {e}")
        log_import('to_parking_tickets', '', 'ontario', 0, 0, 'skipped', str(e))


def run():
    """Point d'entree du module Ontario."""
    logger.info("=" * 50)
    logger.info("MODULE ONTARIO OPEN DATA")
    logger.info("=" * 50)
    results = {}
    results['opp_traffic'] = fetch_opp_traffic()
    fetch_toronto_parking()
    logger.info(f"Ontario total: {sum(results.values())} records")
    return results
