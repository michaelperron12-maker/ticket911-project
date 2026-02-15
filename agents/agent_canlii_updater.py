#!/usr/bin/env python3
"""
Agent CanLII Updater — Import automatique quotidien des jurisprudences QC traffic
Appelé par systemd timer (canlii-updater.service) chaque nuit à 4AM
Rate limit: 4700 req/jour max (marge 300 sous quota CanLII 5000)
Backend: PostgreSQL (tickets_qc_on)
"""

import os
import sys
import json
import subprocess
from datetime import datetime, date

# Chemin du projet
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(PROJECT_DIR, "logs")
USAGE_FILE = os.path.join(LOGS_DIR, "canlii_usage.json")
STATE_FILE = os.path.join(PROJECT_DIR, "db", "canlii_updater_state.json")
IMPORT_SCRIPT = os.path.join(PROJECT_DIR, "import_canlii_traffic.py")
LOG_FILE = os.path.join(LOGS_DIR, "canlii_import.log")

# Rate limit CanLII — marge 300 sous quota 5000
MAX_REQUESTS_PER_DAY = 4700


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


def load_state():
    """Charge l'état du dernier import"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_run": None, "total_added": 0, "runs": 0}


def save_state(state):
    """Sauvegarde l'état de l'import"""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def check_daily_quota():
    """Vérifie si le quota daily est déjà atteint"""
    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE) as f:
                usage = json.load(f)
            today_yday = date.today().timetuple().tm_yday
            if usage.get("day") == today_yday:
                used = usage.get("count", 0)
                if used >= MAX_REQUESTS_PER_DAY:
                    log(f"[SKIP] Quota daily déjà atteint: {used}/{MAX_REQUESTS_PER_DAY}")
                    return 0
                remaining = MAX_REQUESTS_PER_DAY - used
                log(f"[INFO] Quota partiel: {used} utilisés, {remaining} restants")
                return remaining
        except (json.JSONDecodeError, KeyError):
            pass
    return MAX_REQUESTS_PER_DAY


def run_import(max_requests):
    """Lance l'import CanLII QC-only via import_canlii_traffic.py"""
    cmd = [
        sys.executable, IMPORT_SCRIPT,
        "--qc-only",
        "--max-requests", str(max_requests),
    ]

    log(f"Lancement import QC: max {max_requests} requêtes")
    log(f"Commande: {' '.join(cmd)}")

    result = subprocess.run(
        cmd,
        cwd=PROJECT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=1800,  # 30 min max
    )

    # Afficher et logger la sortie
    for line in result.stdout.splitlines():
        log(line)

    return result.returncode


def main():
    log("=" * 60)
    log("  Agent CanLII Updater — AITicketInfo")
    log(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log(f"  Max: {MAX_REQUESTS_PER_DAY} req/jour (quota 5000)")
    log(f"  Mode: QC seulement (qccm, qccq, qccs, qcca)")
    log("=" * 60)

    # Vérifier clé API
    api_key = os.environ.get("CANLII_API_KEY", "")
    if not api_key:
        log("[FATAL] CANLII_API_KEY manquant dans .env")
        sys.exit(1)

    # Charger état
    state = load_state()
    log(f"Run #{state.get('runs', 0) + 1} | Dernier: {state.get('last_run', 'jamais')}")

    # Vérifier quota
    remaining = check_daily_quota()
    if remaining <= 0:
        log("[DONE] Quota épuisé, rien à faire")
        sys.exit(0)

    max_req = min(remaining, MAX_REQUESTS_PER_DAY)

    # Lancer l'import
    exit_code = run_import(max_req)

    # Lire les stats du fichier usage
    new_imported = 0
    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE) as f:
                usage = json.load(f)
            new_imported = usage.get("new_imported", 0)
        except Exception:
            pass

    # Sauvegarder l'état
    state["last_run"] = datetime.now().isoformat()
    state["last_exit_code"] = exit_code
    state["last_max_requests"] = max_req
    state["total_added"] = state.get("total_added", 0) + new_imported
    state["runs"] = state.get("runs", 0) + 1
    save_state(state)

    if exit_code == 0:
        log(f"[OK] Import terminé: +{new_imported} dossiers QC")
    else:
        log(f"[WARN] Import terminé avec code {exit_code}")

    log("=" * 60)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
