"""
Helpers PostgreSQL : connexion, bulk insert, logging des imports.
"""
import psycopg2
import psycopg2.extras
import json
import logging
from config import DB_CONFIG

logger = logging.getLogger(__name__)


def get_connection():
    """Retourne une connexion PostgreSQL."""
    return psycopg2.connect(**DB_CONFIG)


def execute_schema(schema_file='schema.sql'):
    """Execute le fichier schema SQL pour creer/mettre a jour les tables."""
    conn = get_connection()
    with open(schema_file, 'r') as f:
        sql = f.read()
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    conn.close()
    logger.info("Schema cree/mis a jour avec succes.")


def bulk_insert(table, columns, rows, conflict_column=None):
    """
    Insert en masse.
    Si conflict_column est defini, fait ON CONFLICT DO NOTHING sur cette colonne.
    """
    if not rows:
        return 0

    conn = get_connection()
    cols = ', '.join(columns)
    placeholders = ', '.join(['%s'] * len(columns))

    if conflict_column:
        sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) ON CONFLICT ({conflict_column}) DO NOTHING"
    else:
        sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

    inserted = 0
    with conn:
        with conn.cursor() as cur:
            for batch_start in range(0, len(rows), 1000):
                batch = rows[batch_start:batch_start + 1000]
                for row in batch:
                    try:
                        cur.execute(sql, row)
                        inserted += cur.rowcount
                    except psycopg2.IntegrityError:
                        conn.rollback()
                        continue
                    except psycopg2.Error as e:
                        logger.warning(f"Insert error in {table}: {e}")
                        conn.rollback()
                        continue

    conn.close()
    logger.info(f"  {table}: {inserted}/{len(rows)} rows inserted.")
    return inserted


def bulk_insert_fast(table, columns, rows):
    """Insert rapide avec execute_batch (pas de gestion conflit individuel)."""
    if not rows:
        return 0

    conn = get_connection()
    cols = ', '.join(columns)
    placeholders = ', '.join(['%s'] * len(columns))
    sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"

    with conn:
        with conn.cursor() as cur:
            try:
                psycopg2.extras.execute_batch(cur, sql, rows, page_size=1000)
            except psycopg2.Error as e:
                logger.error(f"Bulk insert error in {table}: {e}")
                conn.rollback()
                return 0

    count = len(rows)
    conn.close()
    logger.info(f"  {table}: {count} rows inserted (fast mode).")
    return count


def execute_query(sql, params=None):
    """Execute une requete et retourne les resultats."""
    conn = get_connection()
    with conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            if cur.description:
                results = cur.fetchall()
            else:
                results = []
    conn.close()
    return results


def get_table_counts():
    """Retourne le nombre de lignes dans chaque table."""
    tables = [
        'qc_constats_infraction', 'qc_radar_photo_stats', 'qc_radar_photo_lieux',
        'jurisprudence', 'jurisprudence_citations', 'lois_articles',
        'on_traffic_offences', 'on_set_fines', 'ref_jurisprudence_cle',
        'speed_limits', 'road_conditions',
        'analyses_completes', 'agent_runs'
    ]
    counts = {}
    conn = get_connection()
    with conn:
        with conn.cursor() as cur:
            for t in tables:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {t}")
                    counts[t] = cur.fetchone()[0]
                except psycopg2.Error:
                    counts[t] = -1
                    conn.rollback()
    conn.close()
    return counts


def log_import(source_name, source_url, module_name, records_fetched, records_inserted,
               status='success', error_message=None, metadata=None):
    """Log un import dans data_source_log."""
    conn = get_connection()
    with conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO data_source_log
                (source_name, source_url, module_name, records_fetched, records_inserted,
                 status, error_message, completed_at, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), %s)
            """, (source_name, source_url, module_name, records_fetched, records_inserted,
                  status, error_message, json.dumps(metadata) if metadata else None))
    conn.close()
