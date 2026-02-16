#!/usr/bin/env python3
"""
fetch_missing_resumes.py — Récupère les résumés/textes manquants
3 phases:
  1. A2AJ fetch (gratuit, pas de quota) — texte complet des cas fédéraux
  2. CanLII metadata fetch (4700/jour) — résumés QC
  3. Mixtral résumé IA — résumer texte_complet → resume pour les cas qui ont du texte mais pas de résumé
  4. Reclassifier les non_determine qui ont maintenant du texte
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
CANLII_API_KEY = os.environ.get('CANLII_API_KEY', '')
LOG_FILE = "/var/www/aiticketinfo/logs/fetch_resumes.log"
STATE_FILE = "/var/www/aiticketinfo/db/fetch_resumes_state.json"

running = True

def signal_handler(sig, frame):
    global running
    log("Signal recu, arret...")
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


def save_state(state):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════
# PHASE 1: A2AJ — Fetch texte complet (gratuit)
# ═══════════════════════════════════════════════════════

def fetch_a2aj_text(citation):
    """Fetch texte complet via A2AJ API (gratuit, pas de quota)"""
    try:
        r = requests.get(
            "https://api.a2aj.ca/fetch",
            params={
                "citation": citation,
                "doc_type": "cases",
                "output_language": "both",
                "end_char": 6000,
            },
            timeout=30,
        )
        if r.status_code == 200:
            data = r.json()
            text = data.get("content", "") or data.get("text", "") or ""
            if len(text) > 50:
                return text
        return None
    except Exception:
        return None


def phase1_a2aj(conn):
    """Phase 1: Récupérer texte via A2AJ pour les cas sans résumé"""
    log("\n" + "=" * 60)
    log("PHASE 1: A2AJ — Fetch texte complet (gratuit)")
    log("=" * 60)

    cur = conn.cursor()
    cur.execute("""
        SELECT id, citation FROM jurisprudence
        WHERE (resume IS NULL OR resume = '' OR LENGTH(resume) < 30)
          AND (texte_complet IS NULL OR texte_complet = '' OR LENGTH(texte_complet) < 50)
          AND citation IS NOT NULL AND citation != ''
        ORDER BY id
        LIMIT 5000
    """)
    rows = cur.fetchall()
    log(f"  Cas sans texte avec citation: {len(rows)}")

    fetched = 0
    errors = 0

    for i, (row_id, citation) in enumerate(rows):
        if not running:
            break

        text = fetch_a2aj_text(citation)
        if text:
            resume = text[:2000]
            cur.execute("""
                UPDATE jurisprudence
                SET texte_complet = %s, resume = %s
                WHERE id = %s AND (resume IS NULL OR resume = '' OR LENGTH(resume) < 30)
            """, (text, resume, row_id))
            conn.commit()
            fetched += 1
        else:
            errors += 1

        if (i + 1) % 50 == 0:
            log(f"  A2AJ: {i+1}/{len(rows)} | fetched={fetched} | errors={errors}")

        time.sleep(0.5)  # Respecter le rate limit A2AJ

    log(f"  PHASE 1 TERMINE: {fetched} textes recuperes, {errors} erreurs")
    return fetched


# ═══════════════════════════════════════════════════════
# PHASE 2: CanLII — Fetch metadata/résumé
# ═══════════════════════════════════════════════════════

def fetch_canlii_metadata(canlii_id, database_id, lang="fr"):
    """Fetch metadata CanLII pour obtenir le résumé"""
    if not CANLII_API_KEY:
        return None

    url = f"https://api.canlii.org/v1/caseBrowse/{lang}/{database_id}/{canlii_id}/"
    try:
        r = requests.get(
            url,
            params={"api_key": CANLII_API_KEY},
            timeout=20,
        )
        if r.status_code == 200:
            data = r.json()
            summary = data.get("decisionSummary", "") or ""
            keywords = data.get("keywords", "") or ""
            # Combiner summary + keywords comme résumé
            text_parts = []
            if summary and len(summary) > 20:
                text_parts.append(summary)
            if keywords and len(keywords) > 10:
                text_parts.append(f"Mots-cles: {keywords}")
            return " ".join(text_parts) if text_parts else None
        elif r.status_code == 429:
            time.sleep(5)
            return "RATE_LIMIT"
        return None
    except Exception:
        return None


def phase2_canlii(conn):
    """Phase 2: Fetch résumés CanLII pour les cas QC sans résumé"""
    log("\n" + "=" * 60)
    log("PHASE 2: CanLII — Fetch metadata/resume")
    log("=" * 60)

    if not CANLII_API_KEY:
        log("  SKIP: Pas de CANLII_API_KEY")
        return 0

    cur = conn.cursor()
    cur.execute("""
        SELECT id, canlii_id, database_id, langue FROM jurisprudence
        WHERE (resume IS NULL OR resume = '' OR LENGTH(resume) < 30)
          AND canlii_id IS NOT NULL AND canlii_id != ''
          AND database_id IS NOT NULL AND database_id != '' AND database_id != 'N/A'
        ORDER BY id
        LIMIT 4000
    """)
    rows = cur.fetchall()
    log(f"  Cas sans resume avec canlii_id: {len(rows)}")

    fetched = 0
    errors = 0
    rate_limits = 0

    for i, (row_id, canlii_id, database_id, langue) in enumerate(rows):
        if not running:
            break

        lang = "fr" if langue == "fr" else "en"
        result = fetch_canlii_metadata(canlii_id, database_id, lang)

        if result == "RATE_LIMIT":
            rate_limits += 1
            if rate_limits >= 5:
                log(f"  STOP: Trop de rate limits ({rate_limits})")
                break
            continue

        if result and len(result) > 20:
            cur.execute("""
                UPDATE jurisprudence SET resume = %s
                WHERE id = %s AND (resume IS NULL OR resume = '' OR LENGTH(resume) < 30)
            """, (result, row_id))
            conn.commit()
            fetched += 1
        else:
            errors += 1

        if (i + 1) % 100 == 0:
            log(f"  CanLII: {i+1}/{len(rows)} | fetched={fetched} | errors={errors} | 429={rate_limits}")

        time.sleep(0.5)  # 2 req/sec max

    log(f"  PHASE 2 TERMINE: {fetched} resumes recuperes, {errors} erreurs, {rate_limits} rate limits")
    return fetched


# ═══════════════════════════════════════════════════════
# PHASE 3: Mixtral — Résumé IA des textes complets
# ═══════════════════════════════════════════════════════

def generate_resume_ia(texte, titre=""):
    """Genere un resume IA avec Mixtral 8x22B"""
    if not FIREWORKS_API_KEY:
        return None

    system_prompt = """Tu es un resumeur de jugements juridiques canadiens.
Tu recois le titre et un extrait d'un jugement.
Genere un resume concis de 2-3 phrases (max 200 mots) qui capture:
- Le type d'infraction
- La decision du tribunal (acquitte, coupable, rejete, etc.)
- Les elements cles du jugement

Reponds UNIQUEMENT avec le resume. Pas de titre, pas de bullet points."""

    user_prompt = f"Titre: {titre}\n\nExtrait:\n{texte[:2000]}"

    try:
        r = requests.post(
            "https://api.fireworks.ai/inference/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {FIREWORKS_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "accounts/fireworks/models/mixtral-8x22b-instruct",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 300,
                "temperature": 0.1,
            },
            timeout=30,
        )
        r.raise_for_status()
        answer = r.json()["choices"][0]["message"]["content"].strip()
        if len(answer) > 30:
            return answer
        return None
    except requests.exceptions.HTTPError as e:
        if e.response and e.response.status_code == 429:
            time.sleep(10)
        return None
    except Exception:
        return None


def phase3_resume_ia(conn):
    """Phase 3: Generer resume IA pour les cas avec texte_complet mais sans resume"""
    log("\n" + "=" * 60)
    log("PHASE 3: Mixtral — Resume IA")
    log("=" * 60)

    if not FIREWORKS_API_KEY:
        log("  SKIP: Pas de FIREWORKS_API_KEY")
        return 0

    cur = conn.cursor()
    cur.execute("""
        SELECT id, titre, texte_complet FROM jurisprudence
        WHERE (resume IS NULL OR resume = '' OR LENGTH(resume) < 30)
          AND texte_complet IS NOT NULL AND LENGTH(texte_complet) > 100
        ORDER BY id
        LIMIT 3000
    """)
    rows = cur.fetchall()
    log(f"  Cas avec texte mais sans resume: {len(rows)}")

    generated = 0
    errors = 0

    for i, (row_id, titre, texte) in enumerate(rows):
        if not running:
            break

        resume = generate_resume_ia(texte, titre or "")
        if resume:
            cur.execute("""
                UPDATE jurisprudence SET resume = %s
                WHERE id = %s AND (resume IS NULL OR resume = '' OR LENGTH(resume) < 30)
            """, (resume, row_id))
            conn.commit()
            generated += 1
        else:
            errors += 1

        if (i + 1) % 50 == 0:
            log(f"  Mixtral: {i+1}/{len(rows)} | generated={generated} | errors={errors}")

        time.sleep(0.2)

    log(f"  PHASE 3 TERMINE: {generated} resumes generes, {errors} erreurs")
    return generated


# ═══════════════════════════════════════════════════════
# PHASE 4: Reclassifier les non_determine
# ═══════════════════════════════════════════════════════

def classify_result(text, titre=""):
    """Classifie un jugement avec Mixtral"""
    if not FIREWORKS_API_KEY:
        return None

    system_prompt = """Tu es un classificateur de jugements juridiques canadiens.
REPONDS UNIQUEMENT avec un objet JSON: {"resultat": "X"}
ou X est UN des mots suivants:
- acquitte (acquitte, not guilty, charges retirees, stayed)
- coupable (guilty, condamne, convicted)
- rejete (demande/appel rejete, dismissed, irrecevable)
- reduit (peine/amende reduite, absolution, conditional discharge)
- inconnu (impossible a determiner)
RIEN D'AUTRE que le JSON."""

    user_prompt = f"Titre: {titre}\n\nExtrait:\n{text[:1500]}"

    try:
        r = requests.post(
            "https://api.fireworks.ai/inference/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {FIREWORKS_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "accounts/fireworks/models/mixtral-8x22b-instruct",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 20,
                "temperature": 0.0,
            },
            timeout=30,
        )
        r.raise_for_status()
        answer = r.json()["choices"][0]["message"]["content"].strip()
        try:
            data = json.loads(answer)
            result = data.get("resultat", "inconnu").lower().strip()
        except json.JSONDecodeError:
            answer_lower = answer.lower()
            if "acquitt" in answer_lower or "not guilty" in answer_lower:
                result = "acquitte"
            elif "coupable" in answer_lower or "guilty" in answer_lower:
                result = "coupable"
            elif "rejet" in answer_lower or "dismissed" in answer_lower:
                result = "rejete"
            elif "reduit" in answer_lower or "reduced" in answer_lower:
                result = "reduit"
            else:
                result = "inconnu"

        normalize = {
            'acquitte': 'acquitte', 'coupable': 'coupable',
            'rejete': 'rejete', 'reduit': 'reduit', 'inconnu': 'inconnu',
        }
        return normalize.get(result, 'inconnu')
    except Exception:
        return None


def phase4_reclassify(conn):
    """Phase 4: Reclassifier les non_determine qui ont maintenant du texte"""
    log("\n" + "=" * 60)
    log("PHASE 4: Reclassifier non_determine")
    log("=" * 60)

    cur = conn.cursor()
    cur.execute("""
        SELECT id, titre, resume FROM jurisprudence
        WHERE resultat = 'non_determine'
          AND resume IS NOT NULL AND LENGTH(resume) > 30
        ORDER BY id
        LIMIT 5000
    """)
    rows = cur.fetchall()
    log(f"  non_determine avec resume: {len(rows)}")

    classified = 0
    still_unknown = 0
    errors = 0

    for i, (row_id, titre, resume) in enumerate(rows):
        if not running:
            break

        result = classify_result(resume, titre or "")
        if result is None:
            errors += 1
            continue

        if result != 'inconnu':
            cur.execute("UPDATE jurisprudence SET resultat = %s WHERE id = %s", (result, row_id))
            classified += 1
        else:
            still_unknown += 1

        conn.commit()

        if (i + 1) % 50 == 0:
            log(f"  Reclass: {i+1}/{len(rows)} | classified={classified} | unknown={still_unknown}")

        time.sleep(0.2)

    log(f"  PHASE 4 TERMINE: {classified} reclassifies, {still_unknown} toujours inconnu, {errors} erreurs")
    return classified


# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════

def main():
    log("\n" + "=" * 60)
    log("FETCH MISSING RESUMES — Demarrage")
    log("=" * 60)

    conn = get_conn()
    cur = conn.cursor()

    # Stats initiales
    cur.execute("SELECT COUNT(*) FROM jurisprudence WHERE resume IS NULL OR resume = '' OR LENGTH(resume) < 30")
    missing_resume = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM jurisprudence WHERE resultat = 'non_determine'")
    non_determine = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM jurisprudence")
    total = cur.fetchone()[0]

    log(f"  Total: {total}")
    log(f"  Sans resume: {missing_resume}")
    log(f"  Non determine: {non_determine}")

    results = {}

    # Phase 1: A2AJ — SKIP (API down, 100% errors)
    # if running:
    #     results["a2aj"] = phase1_a2aj(conn)
    results["a2aj"] = 0
    log("  Phase 1 A2AJ: SKIPPED (API non fonctionnelle)")

    # Phase 2: CanLII
    if running:
        results["canlii"] = phase2_canlii(conn)

    # Phase 3: Resume IA
    if running:
        results["resume_ia"] = phase3_resume_ia(conn)

    # Phase 4: Reclassifier
    if running:
        results["reclassified"] = phase4_reclassify(conn)

    # Stats finales
    cur.execute("SELECT COUNT(*) FROM jurisprudence WHERE resume IS NULL OR resume = '' OR LENGTH(resume) < 30")
    missing_after = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM jurisprudence WHERE resultat = 'non_determine'")
    non_det_after = cur.fetchone()[0]

    cur.close()
    conn.close()

    state = {
        "last_run": datetime.now().isoformat(),
        "results": results,
        "before": {"missing_resume": missing_resume, "non_determine": non_determine},
        "after": {"missing_resume": missing_after, "non_determine": non_det_after},
        "status": "complete" if running else "interrupted",
    }
    save_state(state)

    log(f"\n{'=' * 60}")
    log(f"FETCH RESUMES — {'Termine' if running else 'Interrompu'}")
    log(f"  Resumes: {missing_resume} -> {missing_after} ({missing_resume - missing_after} recuperes)")
    log(f"  Non determine: {non_determine} -> {non_det_after} ({non_determine - non_det_after} reclassifies)")
    log(f"  Details: {results}")
    log(f"{'=' * 60}")


if __name__ == "__main__":
    main()
