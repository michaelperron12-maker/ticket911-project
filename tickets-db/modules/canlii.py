"""
Module CanLII API - Jurisprudence QC + ON.
CLE API GRATUITE REQUISE - https://www.canlii.org/en/feedback/feedback.html

Limites API CanLII:
- 5 000 requetes par jour
- 2 requetes par seconde (0.5s minimum entre requetes)
- 1 requete a la fois (sequentiel)

Strategie :
1. Pour chaque tribunal pertinent, lister les decisions
2. Filtrer par mots-cles lies aux tickets/infractions routieres
3. Recuperer metadata + citations pour chaque decision pertinente
"""
import logging
import json
import time
import os
from config import CANLII_BASE, CANLII_API_KEY, CANLII_BATCH_SIZE, CANLII_MAX_PER_DB
from utils.fetcher import fetch_json
from utils.db import get_connection, log_import

logger = logging.getLogger(__name__)

# === RATE LIMITING STRICT ===
DAILY_LIMIT = 4800         # 5000 - marge de securite de 200
MIN_DELAY = 0.65           # 0.5s min + marge securite → eviter 429
_request_count = 0
_last_request_time = 0.0
_counter_file = os.path.join(os.path.dirname(__file__), '..', 'logs', 'canlii_counter.json')


def _load_counter():
    """Charge le compteur de requetes quotidien depuis le fichier."""
    global _request_count
    try:
        if os.path.exists(_counter_file):
            with open(_counter_file) as f:
                data = json.load(f)
            # Verifier si c'est le meme jour
            if data.get('date') == time.strftime('%Y-%m-%d'):
                _request_count = data.get('count', 0)
                logger.info(f"  CanLII compteur charge: {_request_count} requetes deja faites aujourd'hui")
            else:
                _request_count = 0
                logger.info("  CanLII compteur: nouveau jour, remise a zero")
    except Exception:
        _request_count = 0


def _save_counter():
    """Sauvegarde le compteur de requetes quotidien."""
    try:
        os.makedirs(os.path.dirname(_counter_file), exist_ok=True)
        with open(_counter_file, 'w') as f:
            json.dump({'date': time.strftime('%Y-%m-%d'), 'count': _request_count}, f)
    except Exception:
        pass


def _rate_limited_fetch(url, params):
    """Fetch avec rate limiting strict: 1 req a la fois, 0.5s min, 5000/jour."""
    global _request_count, _last_request_time

    # Verifier limite quotidienne
    if _request_count >= DAILY_LIMIT:
        logger.warning(f"  LIMITE QUOTIDIENNE ATTEINTE ({_request_count}/{DAILY_LIMIT}). Arret.")
        raise RuntimeError(f"CanLII daily limit reached: {_request_count}")

    # Respecter le delai minimum (0.5s entre requetes)
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < MIN_DELAY:
        time.sleep(MIN_DELAY - elapsed)

    # Faire la requete
    _last_request_time = time.time()
    _request_count += 1

    # Log tous les 100 requetes
    if _request_count % 100 == 0:
        logger.info(f"  [CanLII] {_request_count}/{DAILY_LIMIT} requetes utilisees aujourd'hui")
        _save_counter()

    return fetch_json(url, params, delay=0)  # delay=0 car on gere nous-memes


# Tribunaux pertinents pour les tickets routiers
DATABASES = {
    'QC': ['qcca', 'qccs', 'qccq', 'qccm', 'qctaq', 'qcctq'],
    'ON': ['onca', 'onscdc', 'oncj'],
}

# Mots-cles pour filtrage
KEYWORDS_QC = [
    'code de la sécurité routière', 'excès de vitesse', 'grand excès',
    'radar', 'constat d\'infraction', 'infraction routière',
    'article 328', 'article 327', 'article 329', 'conduite dangereuse',
    'vitesse', 'alcool au volant', 'points d\'inaptitude',
    'feu rouge', 'cellulaire', 'ceinture', 'stationnement',
    'code securite routiere', 'C-24.2',
]

KEYWORDS_ON = [
    'highway traffic act', 'speeding', 'stunt driving', 'racing',
    'provincial offences', 'speed detection', 'radar', 'lidar',
    'section 128', 'section 172', 'section 130', 'section 144',
    'dangerous driving', 'careless driving',
    'demerit points', 'traffic ticket', 'red light', 'seatbelt',
    'distracted driving', 'cell phone', 'HTA',
]


def is_ticket_related(title, keywords_list):
    """Verifie si un titre est lie aux tickets routiers."""
    title_lower = (title or '').lower()
    return any(kw.lower() in title_lower for kw in keywords_list)


def fetch_decisions_for_db(database_id, province):
    """Fetch les decisions d'un tribunal CanLII."""
    global _request_count
    lang = 'fr' if province == 'QC' else 'en'
    keywords = KEYWORDS_QC if province == 'QC' else KEYWORDS_ON

    logger.info(f"  Fetching {database_id} ({province})...")
    all_decisions = []
    offset = 0

    while offset < CANLII_MAX_PER_DB:
        if _request_count >= DAILY_LIMIT:
            logger.warning(f"  Limite quotidienne atteinte pendant fetch {database_id}")
            break

        url = f"{CANLII_BASE}/caseBrowse/{lang}/{database_id}/"
        params = {
            'api_key': CANLII_API_KEY,
            'offset': offset,
            'resultCount': CANLII_BATCH_SIZE,
        }
        try:
            data = _rate_limited_fetch(url, params)
            cases = data.get('cases', [])
            if not cases:
                break
            all_decisions.extend(cases)
            offset += CANLII_BATCH_SIZE
            if offset % 500 == 0:
                logger.info(f"    Fetched {len(all_decisions)} decisions... ({_request_count} API calls)")
        except RuntimeError:
            break
        except Exception as e:
            logger.error(f"    Error at offset {offset}: {e}")
            break

    # Filtrer les decisions liees aux tickets
    ticket_decisions = []
    for d in all_decisions:
        title = d.get('title', '')
        is_ticket = is_ticket_related(title, keywords)
        d['_province'] = province
        d['_database_id'] = database_id
        d['_is_ticket'] = is_ticket
        if is_ticket:
            ticket_decisions.append(d)

    logger.info(f"    {len(ticket_decisions)}/{len(all_decisions)} decisions liees aux tickets.")
    return ticket_decisions


def fetch_case_metadata(database_id, case_id, lang='en'):
    """Recupere les metadata completes d'un cas (keywords, topics, etc.)."""
    url = f"{CANLII_BASE}/caseBrowse/{lang}/{database_id}/{case_id}/"
    params = {'api_key': CANLII_API_KEY}
    try:
        data = _rate_limited_fetch(url, params)
        return data
    except RuntimeError:
        raise
    except Exception:
        return {}


def fetch_case_citations(database_id, case_id):
    """Recupere les citations d'un cas (cas cites + cas citants + legislations citees)."""
    citations = {'cited': [], 'citing': [], 'legislation': []}

    for ctype, key in [('citedCases', 'cited'), ('citingCases', 'citing'), ('citedLegislations', 'legislation')]:
        if _request_count >= DAILY_LIMIT:
            break
        url = f"{CANLII_BASE}/caseCitator/en/{database_id}/{case_id}/{ctype}"
        params = {'api_key': CANLII_API_KEY}
        try:
            data = _rate_limited_fetch(url, params)
            citations[key] = data.get(ctype, data.get('citedLegislations', []))
        except RuntimeError:
            break
        except Exception:
            pass

    return citations


def _update_keywords(canlii_id, keywords_str):
    """Met a jour les mots-cles d'un cas dans la table jurisprudence."""
    conn = get_connection()
    try:
        # keywords_str peut etre une string separee par virgules ou point-virgules
        if isinstance(keywords_str, list):
            kw_list = keywords_str
        else:
            kw_list = [k.strip() for k in keywords_str.replace(';', ',').split(',') if k.strip()]
        if not kw_list:
            return
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE jurisprudence
                    SET mots_cles = %s
                    WHERE canlii_id = %s AND (mots_cles IS NULL OR mots_cles = '{}')
                """, (kw_list, canlii_id))
    except Exception as e:
        logger.warning(f"    Keywords update error for {canlii_id}: {e}")
    finally:
        conn.close()


def insert_decisions(decisions):
    """Insere les decisions dans la table jurisprudence."""
    conn = get_connection()
    inserted = 0
    with conn:
        with conn.cursor() as cur:
            for d in decisions:
                case_id_obj = d.get('caseId', {})
                if isinstance(case_id_obj, dict):
                    canlii_id = case_id_obj.get('en', '') or case_id_obj.get('fr', '')
                else:
                    canlii_id = str(case_id_obj)

                if not canlii_id:
                    continue

                try:
                    cur.execute("""
                        INSERT INTO jurisprudence
                        (canlii_id, database_id, province, titre, citation,
                         numero_dossier, date_decision, url_canlii, tribunal,
                         langue, est_ticket_related, source, raw_metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (canlii_id) DO UPDATE SET
                            est_ticket_related = EXCLUDED.est_ticket_related,
                            raw_metadata = EXCLUDED.raw_metadata
                    """, (
                        canlii_id,
                        d.get('_database_id'),
                        d.get('_province'),
                        d.get('title'),
                        d.get('citation'),
                        d.get('docketNumber'),
                        d.get('decisionDate'),
                        d.get('url'),
                        d.get('_database_id'),
                        'fr' if d.get('_province') == 'QC' else 'en',
                        d.get('_is_ticket', False),
                        'canlii',
                        json.dumps(d),
                    ))
                    inserted += 1
                except Exception as e:
                    logger.warning(f"    Insert error for {canlii_id}: {e}")
                    conn.rollback()
    conn.close()
    return inserted


def insert_citations(source_canlii_id, citations_data):
    """Insere les citations dans la table jurisprudence_citations."""
    conn = get_connection()
    inserted = 0
    with conn:
        with conn.cursor() as cur:
            # Cas cites
            for c in citations_data.get('cited', []):
                case_id = c.get('caseId', {})
                target_id = case_id.get('en', '') if isinstance(case_id, dict) else str(case_id)
                try:
                    cur.execute("""
                        INSERT INTO jurisprudence_citations
                        (source_canlii_id, target_canlii_id, target_titre, target_citation,
                         target_database_id, type_citation, raw_data)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                    """, (
                        source_canlii_id, target_id,
                        c.get('title'), c.get('citation'),
                        c.get('databaseId'), 'cited_by',
                        json.dumps(c),
                    ))
                    inserted += 1
                except Exception:
                    conn.rollback()

            # Cas citants
            for c in citations_data.get('citing', []):
                case_id = c.get('caseId', {})
                target_id = case_id.get('en', '') if isinstance(case_id, dict) else str(case_id)
                try:
                    cur.execute("""
                        INSERT INTO jurisprudence_citations
                        (source_canlii_id, target_canlii_id, target_titre, target_citation,
                         target_database_id, type_citation, raw_data)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                    """, (
                        source_canlii_id, target_id,
                        c.get('title'), c.get('citation'),
                        c.get('databaseId'), 'cites',
                        json.dumps(c),
                    ))
                    inserted += 1
                except Exception:
                    conn.rollback()

            # Legislations citees
            for leg in citations_data.get('legislation', []):
                leg_id = leg.get('legislationId', '')
                try:
                    cur.execute("""
                        INSERT INTO jurisprudence_legislation
                        (case_canlii_id, legislation_id, titre_legislation,
                         database_id, type_legislation, url_canlii, raw_data)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        source_canlii_id, leg_id,
                        leg.get('title'), leg.get('databaseId'),
                        leg.get('type'), leg.get('url'),
                        json.dumps(leg),
                    ))
                    inserted += 1
                except Exception:
                    conn.rollback()
    conn.close()
    return inserted


def run():
    """Point d'entree du module CanLII."""
    global _request_count
    logger.info("=" * 50)
    logger.info("MODULE CANLII JURISPRUDENCE (API)")
    logger.info("=" * 50)
    logger.info(f"  Limites: {DAILY_LIMIT} req/jour, {MIN_DELAY}s entre requetes, 1 req a la fois")

    if not CANLII_API_KEY:
        logger.warning("!!! CLE API CANLII NON CONFIGUREE !!!")
        logger.warning("Demander une cle gratuite : https://www.canlii.org/en/feedback/feedback.html")
        logger.warning("Puis definir CANLII_API_KEY dans l'environnement ou config.py")
        log_import('canlii', '', 'canlii', 0, 0, 'skipped', 'API key missing')
        return {}

    # Charger compteur existant
    _load_counter()
    logger.info(f"  Requetes restantes aujourd'hui: {DAILY_LIMIT - _request_count}")

    results = {}
    total_inserted = 0
    total_citations = 0
    limit_reached = False

    for province, dbs in DATABASES.items():
        if limit_reached:
            break
        for db_id in dbs:
            if _request_count >= DAILY_LIMIT:
                logger.warning(f"  LIMITE QUOTIDIENNE ATTEINTE. Arret apres {db_id}.")
                limit_reached = True
                break

            decisions = fetch_decisions_for_db(db_id, province)
            if decisions:
                count = insert_decisions(decisions)
                total_inserted += count
                results[db_id] = count
                log_import(f'canlii_{db_id}', f'api.canlii.org/{db_id}', 'canlii',
                           len(decisions), count)

                # Fetch metadata + citations pour les decisions ticket-related
                # metadata = 1 req, citations = 3 req → 4 req par cas
                max_enrich = min(20, len(decisions))
                lang = 'fr' if province == 'QC' else 'en'
                for d in decisions[:max_enrich]:
                    if _request_count >= DAILY_LIMIT:
                        break
                    case_id_obj = d.get('caseId', {})
                    if isinstance(case_id_obj, dict):
                        canlii_id = case_id_obj.get('en', '') or case_id_obj.get('fr', '')
                    else:
                        canlii_id = str(case_id_obj)
                    if not canlii_id:
                        continue

                    # Fetch keywords via metadata individuel
                    try:
                        meta = fetch_case_metadata(db_id, canlii_id, lang)
                        if meta:
                            kw = meta.get('keywords', '')
                            if kw:
                                _update_keywords(canlii_id, kw)
                    except RuntimeError:
                        break
                    except Exception:
                        pass

                    # Fetch citations
                    cit = fetch_case_citations(db_id, canlii_id)
                    c_count = insert_citations(canlii_id, cit)
                    total_citations += c_count

    # Sauvegarder compteur
    _save_counter()

    logger.info(f"CanLII total: {total_inserted} decisions, {total_citations} citations")
    logger.info(f"CanLII requetes utilisees: {_request_count}/{DAILY_LIMIT}")
    return results
