#!/usr/bin/env python3
"""
classify_inconnu.py v3 — Classifie les résultats "inconnu" avec Mixtral 8x22B
Mixtral suit les instructions JSON, rapide (~2s/appel), fiable.
"""

import os
import sys
import json
import time
import re
import signal
import psycopg2
import requests
from datetime import datetime

sys.path.insert(0, "/var/www/aiticketinfo")

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

PG_CONFIG = {
    'host': os.environ.get('TICKETS_DB_HOST', '172.18.0.3'),
    'port': int(os.environ.get('TICKETS_DB_PORT', 5432)),
    'dbname': os.environ.get('TICKETS_DB_NAME', 'tickets_qc_on'),
    'user': os.environ.get('TICKETS_DB_USER', 'ticketdb_user'),
    'password': os.environ.get('TICKETS_DB_PASS', 'Tk911PgSecure2026'),
}

FIREWORKS_API_KEY = os.environ.get('FIREWORKS_API_KEY', '')
MODEL = "accounts/fireworks/models/mixtral-8x22b-instruct"
LOG_FILE = "/var/www/aiticketinfo/logs/classify_inconnu.log"
STATE_FILE = "/var/www/aiticketinfo/db/classify_inconnu_state.json"

BATCH_SIZE = 100
SLEEP_BETWEEN = 0.15
SLEEP_BATCH = 2
MAX_TEXT_CHARS = 1500

running = True

def signal_handler(sig, frame):
    global running
    log("Signal recu, arret apres ce batch...")
    running = False

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def get_conn():
    return psycopg2.connect(**PG_CONFIG)


def call_classify(text, titre=""):
    """Appel Mixtral 8x22B pour classifier — prompt strict format JSON"""

    system_prompt = """Tu es un classificateur de jugements juridiques canadiens.
Tu reçois le titre et un extrait d'un jugement.
Tu dois déterminer le RÉSULTAT du jugement.

RÉPONDS UNIQUEMENT avec un objet JSON: {"resultat": "X"}
où X est UN des mots suivants:
- acquitte (acquitté, not guilty, charges retirées, stayed, appel accueilli qui annule condamnation)
- coupable (guilty, condamné, convicted, appel rejeté confirmant condamnation)
- rejete (demande/appel rejeté, dismissed, irrecevable)
- reduit (peine/amende réduite, absolution, conditional discharge)
- inconnu (impossible à déterminer avec le texte fourni)

RIEN D'AUTRE que le JSON. Pas d'explication."""

    user_prompt = f"Titre: {titre}\n\nExtrait:\n{text[:MAX_TEXT_CHARS]}"

    try:
        r = requests.post(
            "https://api.fireworks.ai/inference/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {FIREWORKS_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 30,
                "temperature": 0.0,
            },
            timeout=30,
        )
        r.raise_for_status()
        answer = r.json()["choices"][0]["message"]["content"].strip()

        # Parser le JSON
        try:
            data = json.loads(answer)
            result = data.get("resultat", "inconnu").lower().strip()
        except json.JSONDecodeError:
            # Fallback: chercher les mots-clés dans la réponse
            answer_lower = answer.lower()
            if "acquitt" in answer_lower or "not guilty" in answer_lower:
                result = "acquitte"
            elif "coupable" in answer_lower or "guilty" in answer_lower or "convicted" in answer_lower:
                result = "coupable"
            elif "rejet" in answer_lower or "dismissed" in answer_lower:
                result = "rejete"
            elif "reduit" in answer_lower or "reduced" in answer_lower or "discharge" in answer_lower:
                result = "reduit"
            else:
                result = "inconnu"

        # Normaliser
        normalize = {
            'acquitté': 'acquitte', 'acquitted': 'acquitte', 'acquitte': 'acquitte',
            'coupable': 'coupable', 'guilty': 'coupable', 'convicted': 'coupable',
            'rejeté': 'rejete', 'rejete': 'rejete', 'rejected': 'rejete', 'dismissed': 'rejete',
            'réduit': 'reduit', 'reduit': 'reduit', 'reduced': 'reduit',
            'inconnu': 'inconnu',
        }
        return normalize.get(result, result if result in ('acquitte','coupable','rejete','reduit') else 'inconnu')

    except requests.exceptions.HTTPError as e:
        if e.response and e.response.status_code == 429:
            log("    Rate limit — pause 10s")
            time.sleep(10)
            return None
        log(f"    API HTTP erreur: {e}")
        return None
    except Exception as e:
        log(f"    API erreur: {e}")
        return None


def main():
    log("=" * 60)
    log("CLASSIFY INCONNU v3 — Mixtral 8x22B")
    log(f"  Modele: {MODEL}")
    log(f"  Batch: {BATCH_SIZE}, Sleep: {SLEEP_BETWEEN}s")
    log("=" * 60)

    if not FIREWORKS_API_KEY:
        log("ERREUR: FIREWORKS_API_KEY manquant!")
        return

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""SELECT COUNT(*) FROM jurisprudence
                   WHERE resultat = 'inconnu'""")
    total_inconnu = cur.fetchone()[0]

    cur.execute("""SELECT COUNT(*) FROM jurisprudence
                   WHERE resultat IS NULL OR resultat = ''""")
    total_null = cur.fetchone()[0]

    log(f"  'inconnu': {total_inconnu}")
    log(f"  NULL/vide: {total_null}")
    log(f"  Total a traiter: {total_inconnu + total_null}")

    total_classified = 0
    total_still_inconnu = 0
    total_errors = 0
    batch_num = 0
    results_count = {'acquitte': 0, 'coupable': 0, 'rejete': 0, 'reduit': 0, 'inconnu': 0}

    while running:
        batch_num += 1

        # Fetch — priorité aux cas avec du texte
        cur.execute("""
            SELECT id, titre, resume, texte_complet, citation
            FROM jurisprudence
            WHERE (resultat = 'inconnu' OR resultat IS NULL OR resultat = '')
              AND (resume IS NOT NULL AND resume != '' AND LENGTH(resume) > 30)
            ORDER BY id
            LIMIT %s
        """, (BATCH_SIZE,))
        columns = [d[0] for d in cur.description]
        rows = [dict(zip(columns, r)) for r in cur.fetchall()]

        # Si plus de cas avec résumé, prendre ceux avec texte_complet
        if not rows:
            cur.execute("""
                SELECT id, titre, resume, texte_complet, citation
                FROM jurisprudence
                WHERE (resultat = 'inconnu' OR resultat IS NULL OR resultat = '')
                  AND (texte_complet IS NOT NULL AND texte_complet != '' AND LENGTH(texte_complet) > 50)
                ORDER BY id
                LIMIT %s
            """, (BATCH_SIZE,))
            columns = [d[0] for d in cur.description]
            rows = [dict(zip(columns, r)) for r in cur.fetchall()]

        # Si toujours rien, prendre les restants (titre seulement)
        if not rows:
            cur.execute("""
                SELECT id, titre, resume, texte_complet, citation
                FROM jurisprudence
                WHERE (resultat = 'inconnu' OR resultat IS NULL OR resultat = '')
                ORDER BY id
                LIMIT %s
            """, (BATCH_SIZE,))
            columns = [d[0] for d in cur.description]
            rows = [dict(zip(columns, r)) for r in cur.fetchall()]

        if not rows:
            log("  Plus rien a classifier!")
            break

        log(f"\n--- Batch {batch_num} ({len(rows)} dossiers) ---")

        classified_batch = 0

        for row in rows:
            if not running:
                break

            # Construire texte
            text = None
            if row.get("resume") and len(row["resume"]) > 30:
                text = row["resume"]
            elif row.get("texte_complet") and len(row["texte_complet"]) > 50:
                text = row["texte_complet"]

            if not text:
                # Pas assez de texte — marquer comme "non_determine" pour ne pas re-boucler
                cur.execute("UPDATE jurisprudence SET resultat = 'non_determine' WHERE id = %s", (row["id"],))
                conn.commit()
                total_still_inconnu += 1
                continue

            titre = row.get("titre", "") or ""
            result = call_classify(text, titre)

            if result is None:
                total_errors += 1
                continue

            # Mettre à jour
            if result != 'inconnu':
                cur.execute("UPDATE jurisprudence SET resultat = %s WHERE id = %s", (result, row["id"]))
                classified_batch += 1
                total_classified += 1
                results_count[result] = results_count.get(result, 0) + 1
            else:
                # LLM dit inconnu aussi — marquer pour ne pas re-traiter
                cur.execute("UPDATE jurisprudence SET resultat = 'non_determine' WHERE id = %s", (row["id"],))
                total_still_inconnu += 1

            conn.commit()
            time.sleep(SLEEP_BETWEEN)

        log(f"  Batch: +{classified_batch} classifies")
        log(f"  Total: {total_classified}/{total_inconnu + total_null} | "
            f"acq={results_count.get('acquitte',0)} coup={results_count.get('coupable',0)} "
            f"rej={results_count.get('rejete',0)} red={results_count.get('reduit',0)}")

        # Save state
        if batch_num % 10 == 0:
            state = {
                "last_update": datetime.now().isoformat(),
                "classified": total_classified,
                "still_inconnu": total_still_inconnu,
                "errors": total_errors,
                "results": results_count,
                "batch": batch_num,
            }
            try:
                with open(STATE_FILE, "w") as f:
                    json.dump(state, f, indent=2)
            except Exception:
                pass

        time.sleep(SLEEP_BATCH)

    cur.close()
    conn.close()

    # Final
    state = {
        "last_run": datetime.now().isoformat(),
        "classified": total_classified,
        "still_inconnu": total_still_inconnu,
        "errors": total_errors,
        "results": results_count,
        "status": "complete" if not running else "interrupted",
    }
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass

    log(f"\n{'=' * 60}")
    log(f"CLASSIFY INCONNU — {'Termine' if not running else 'Interrompu'}")
    log(f"  Classifies: {total_classified}")
    log(f"  Non determines: {total_still_inconnu}")
    log(f"  Erreurs: {total_errors}")
    log(f"  Resultats: {results_count}")
    log(f"{'=' * 60}")


if __name__ == "__main__":
    main()
