#!/usr/bin/env python3
"""
Enrichissement des dossiers jurisprudence existants
- Extrait mots-cles depuis raw_metadata.keywords
- Detecte resultat depuis keywords (culpabilite/acquitte/rejete/reduit)
- Detecte type infraction depuis titre + keywords
- Ne fait AUCUN appel API — tout en local/DB
"""

import json
import re
import psycopg2
import psycopg2.extras
import os

PG_CONFIG = {
    'host': os.environ.get('TICKETS_DB_HOST', '172.18.0.3'),
    'port': int(os.environ.get('TICKETS_DB_PORT', 5432)),
    'dbname': os.environ.get('TICKETS_DB_NAME', 'tickets_qc_on'),
    'user': os.environ.get('TICKETS_DB_USER', 'ticketdb_user'),
    'password': os.environ.get('TICKETS_DB_PASS', 'Tk911PgSecure2026'),
}


# ── Detection du resultat ──────────────────────────
RESULTAT_PATTERNS = {
    'acquitte': [
        r'acquitt[ée]', r'acquittal', r'not guilty', r'non[- ]coupable',
        r'infraction rejet[ée]e', r'accus[ée] acquitt', r'charge[s]? dismissed',
        r'appel accueilli.*acquitt', r'verdict.*acquitt'
    ],
    'coupable': [
        r'coupable', r'guilty', r'culpabilit[ée]', r'conviction',
        r'condamn[ée]', r'd[ée]claration de culpabilit', r'found guilty',
        r'culpabilit[ée] confirm[ée]e', r'culpabilit[ée] maintenue'
    ],
    'rejete': [
        r'appel rejet[ée]', r'appeal dismissed', r'demande rejet[ée]e',
        r'requete rejet', r'requ[êe]te rejet', r'pourvoi rejet',
        r'dismissed', r'contestation rejet'
    ],
    'reduit': [
        r'amende r[ée]duite', r'sentence r[ée]duite', r'peine r[ée]duite',
        r'fine reduced', r'reduced', r'att[ée]nu', r'r[ée]duction',
        r'absolution', r'conditional discharge', r'sursis'
    ],
}


def detect_resultat(text):
    """Detecte le resultat depuis le texte (keywords + titre)"""
    if not text:
        return 'inconnu'
    text_lower = text.lower()

    scores = {}
    for resultat, patterns in RESULTAT_PATTERNS.items():
        count = 0
        for pat in patterns:
            if re.search(pat, text_lower):
                count += 1
        if count > 0:
            scores[resultat] = count

    if not scores:
        return 'inconnu'

    # Priorite: acquitte > reduit > rejete > coupable
    # (si "appel rejete" + "culpabilite confirmee" => coupable, pas rejete)
    if 'acquitte' in scores and scores['acquitte'] >= scores.get('coupable', 0):
        return 'acquitte'
    if 'reduit' in scores:
        return 'reduit'
    if 'coupable' in scores and scores['coupable'] >= scores.get('rejete', 0):
        return 'coupable'
    if 'rejete' in scores:
        return 'rejete'

    return max(scores, key=scores.get)


# ── Detection du type d'infraction ──────────────────
INFRACTION_PATTERNS = {
    'vitesse': [
        r'vitesse', r'exc[eè]s', r'speed', r'speeding', r'cin[ée]mom[eè]tre',
        r'radar', r'km/h', r'limite.*vitesse', r'speed limit',
        r'photo.*radar', r'lidar'
    ],
    'cellulaire': [
        r'cell', r't[ée]l[ée]phone', r'phone', r'distracted',
        r'distraction', r'appareil.*main', r'hand.*held',
        r'texting', r'[ée]cran'
    ],
    'alcool': [
        r'alcool', r'alcohol', r'ivresse', r'impaired', r'dui', r'dwi',
        r'alcootest', r'breathalyzer', r'taux.*alcool[ée]mie',
        r'blood.*alcohol', r'bac', r'facult[ée]s.*affaiblies',
        r'capacit[ée].*affaiblies', r'conduite.*[ée]tat.*[ée]bri[ée]t[ée]'
    ],
    'feu_rouge': [
        r'feu rouge', r'red light', r'traffic light', r'signalis',
        r'feu.*circulation'
    ],
    'ceinture': [
        r'ceinture', r'seat.*belt', r'seatbelt'
    ],
    'stop': [
        r'arr[eê]t', r'stop sign', r'panneau.*arr[eê]t'
    ],
    'conduite_dangereuse': [
        r'dangereuse', r'dangerous', r'imprudente', r'negligent',
        r'careless', r'reckless'
    ],
    'stationnement': [
        r'stationnement', r'parking', r'parcm[eè]tre'
    ],
    'permis': [
        r'permis', r'licence', r'license', r'sans permis',
        r'suspended.*license', r'permis.*suspendu'
    ],
}


def detect_infraction_type(text):
    """Detecte le type d'infraction depuis titre + keywords"""
    if not text:
        return 'autre'
    text_lower = text.lower()

    scores = {}
    for inftype, patterns in INFRACTION_PATTERNS.items():
        count = 0
        for pat in patterns:
            if re.search(pat, text_lower):
                count += 1
        if count > 0:
            scores[inftype] = count

    if not scores:
        return 'autre'
    return max(scores, key=scores.get)


def main():
    conn = psycopg2.connect(**PG_CONFIG)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Fetch all dossiers
    cur.execute("""
        SELECT id, titre, raw_metadata, resultat, mots_cles
        FROM jurisprudence
    """)
    rows = cur.fetchall()
    print(f"Total dossiers: {len(rows)}")

    updated_resultat = 0
    updated_mots_cles = 0
    updated_type = 0
    types_count = {}

    for row in rows:
        rid = row['id']
        titre = row['titre'] or ''
        raw_meta = row['raw_metadata']
        current_resultat = row['resultat']
        current_mots_cles = row['mots_cles']

        # Parse raw_metadata
        if isinstance(raw_meta, str):
            try:
                raw_meta = json.loads(raw_meta)
            except:
                raw_meta = {}
        elif raw_meta is None:
            raw_meta = {}

        keywords_text = raw_meta.get('keywords', '') or ''
        topics_text = raw_meta.get('topics', '') or ''
        combined_text = f"{titre} {keywords_text} {topics_text}"

        updates = {}

        # 1. Detect resultat if missing
        if not current_resultat or current_resultat == 'inconnu':
            new_resultat = detect_resultat(combined_text)
            if new_resultat != 'inconnu':
                updates['resultat'] = new_resultat
                updated_resultat += 1

        # 2. Extract mots_cles from raw_metadata if missing
        if not current_mots_cles or str(current_mots_cles) in ('[]', 'null', 'None'):
            if keywords_text:
                # Parse keywords: pipe-separated sections, each with sub-items
                kw_list = []
                for section in keywords_text.split('|'):
                    section = section.strip()
                    if ' — ' in section:
                        parts = section.split(' — ')
                        kw_list.extend([p.strip() for p in parts if p.strip()])
                    elif section:
                        kw_list.append(section[:100])
                if kw_list:
                    updates['mots_cles'] = json.dumps(kw_list[:20], ensure_ascii=False)
                    updated_mots_cles += 1

        # 3. Detect infraction type (store in a field we can use)
        infraction_type = detect_infraction_type(combined_text)
        types_count[infraction_type] = types_count.get(infraction_type, 0) + 1

        # Apply updates
        if updates:
            set_parts = []
            vals = []
            for k, v in updates.items():
                set_parts.append(f"{k} = %s")
                vals.append(v)
            vals.append(rid)
            cur.execute(f"UPDATE jurisprudence SET {', '.join(set_parts)} WHERE id = %s", vals)

    conn.commit()
    conn.close()

    print(f"\n{'='*50}")
    print(f"  ENRICHISSEMENT TERMINE")
    print(f"{'='*50}")
    print(f"  Resultats mis a jour: {updated_resultat}")
    print(f"  Mots-cles extraits:  {updated_mots_cles}")
    print(f"\n  Types d'infraction detectes:")
    for t, c in sorted(types_count.items(), key=lambda x: -x[1]):
        print(f"    {t:25s} {c}")
    print(f"{'='*50}")


if __name__ == '__main__':
    main()
