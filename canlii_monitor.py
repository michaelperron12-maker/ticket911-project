#!/usr/bin/env python3
"""
ScanTicket V1 — CanLII API Monitor
Usage:
    python3 canlii_monitor.py              # Status complet
    python3 canlii_monitor.py --live       # Refresh toutes les 30s
    python3 canlii_monitor.py --test-api   # Tester si l'API repond (1 requete)
"""

import sys
import os
import json
import time
import datetime
import psycopg2
import requests

CANLII_API_KEY = "9yC9kEpzDu4DLkhrkFtwmavjLi9RBqxm5Vp7wTxP"
CANLII_BASE_URL = "https://api.canlii.org/v1"
DAILY_LIMIT = 4800
USAGE_FILE = "/var/www/aiticketinfo/logs/canlii_usage.json"
IMPORT_LOG = "/var/www/aiticketinfo/logs/canlii_import.log"
EMBED_LOG = "/var/www/aiticketinfo/logs/embeddings.log"

DB_CONFIG = {
    "host": "172.18.0.3",
    "port": 5432,
    "dbname": "tickets_qc_on",
    "user": "ticketdb_user",
    "password": "Tk911PgSecure2026"
}


def get_usage():
    """Lit le fichier canlii_usage.json"""
    try:
        with open(USAGE_FILE) as f:
            data = json.load(f)
        today = datetime.datetime.now().timetuple().tm_yday
        if data.get("day") == today:
            return data.get("count", 0), data.get("last_update", "?")
        else:
            return 0, "nouveau jour"
    except Exception:
        return 0, "fichier absent"


def get_db_stats():
    """Stats DB"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("SELECT count(*) FROM jurisprudence")
    total = cur.fetchone()[0]

    cur.execute("SELECT count(*) FROM jurisprudence WHERE embedding IS NOT NULL")
    embedded = cur.fetchone()[0]

    cur.execute("SELECT count(*) FROM jurisprudence WHERE embedding IS NULL")
    no_embed = cur.fetchone()[0]

    cur.execute("""
        SELECT province, count(*) FROM jurisprudence
        GROUP BY province ORDER BY count(*) DESC
    """)
    by_prov = cur.fetchall()

    cur.execute("""
        SELECT date_trunc('day', imported_at) as jour, count(*)
        FROM jurisprudence
        WHERE imported_at > now() - interval '7 days'
        GROUP BY jour ORDER BY jour DESC
    """)
    by_day = cur.fetchall()

    cur.execute("""
        SELECT max(imported_at) FROM jurisprudence
    """)
    last_import = cur.fetchone()[0]

    cur.close()
    conn.close()
    return {
        "total": total,
        "embedded": embedded,
        "no_embed": no_embed,
        "by_province": by_prov,
        "by_day": by_day,
        "last_import": last_import
    }


def test_api():
    """Teste 1 requete CanLII pour verifier si le quota est OK"""
    try:
        resp = requests.get(
            f"{CANLII_BASE_URL}/caseBrowse/en/qccm/",
            params={"api_key": CANLII_API_KEY, "resultCount": 1},
            timeout=10
        )
        return resp.status_code, resp.headers.get("X-RateLimit-Remaining", "?")
    except Exception as e:
        return 0, str(e)


def get_last_log_lines(filepath, n=5):
    """Dernieres lignes d'un log"""
    try:
        with open(filepath) as f:
            lines = f.readlines()
        return [l.strip() for l in lines[-n:]]
    except Exception:
        return ["(fichier non disponible)"]


def display_status():
    """Affiche le status complet"""
    now = datetime.datetime.now()
    used, last_update = get_usage()
    remaining = max(0, DAILY_LIMIT - used)
    pct = used / DAILY_LIMIT * 100

    # Heure du prochain cron
    next_import = now.replace(hour=1, minute=0, second=0, microsecond=0)
    if now.hour >= 1:
        next_import += datetime.timedelta(days=1)
    next_embed = next_import + datetime.timedelta(minutes=30)
    time_to_import = next_import - now

    print(f"\n{'='*60}")
    print(f"  CANLII API MONITOR — {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    # Quota bar
    bar_len = 40
    filled = int(bar_len * pct / 100)
    bar = "█" * filled + "░" * (bar_len - filled)
    color = "\033[92m" if pct < 50 else "\033[93m" if pct < 80 else "\033[91m"
    reset = "\033[0m"
    print(f"\n  Quota:  [{color}{bar}{reset}] {pct:.1f}%")
    print(f"  Utilise: {used} / {DAILY_LIMIT}")
    print(f"  Restant: {remaining}")
    print(f"  Dernier appel: {last_update}")

    # Cron schedule
    hours = int(time_to_import.total_seconds() // 3600)
    mins = int((time_to_import.total_seconds() % 3600) // 60)
    print(f"\n  Prochain import:     {next_import.strftime('%H:%M')} (dans {hours}h{mins:02d}m)")
    print(f"  Prochain embeddings: {next_embed.strftime('%H:%M')}")

    # DB Stats
    try:
        stats = get_db_stats()
        print(f"\n  --- BASE DE DONNEES ---")
        print(f"  Total dossiers:    {stats['total']}")
        print(f"  Avec embeddings:   {stats['embedded']}")
        print(f"  Sans embeddings:   {stats['no_embed']}")
        print(f"  Dernier import:    {stats['last_import']}")

        print(f"\n  Par province:")
        for prov, cnt in stats["by_province"]:
            print(f"    {prov or '?':5} : {cnt}")

        if stats["by_day"]:
            print(f"\n  Imports 7 derniers jours:")
            for jour, cnt in stats["by_day"]:
                print(f"    {jour.strftime('%Y-%m-%d') if jour else '?'} : +{cnt} dossiers")
    except Exception as e:
        print(f"\n  DB erreur: {e}")

    # Derniers logs
    print(f"\n  --- DERNIERS LOGS IMPORT ---")
    for line in get_last_log_lines(IMPORT_LOG, 3):
        print(f"    {line[:100]}")

    print(f"\n  --- DERNIERS LOGS EMBEDDINGS ---")
    for line in get_last_log_lines(EMBED_LOG, 3):
        print(f"    {line[:100]}")

    print(f"\n{'='*60}\n")


def live_mode():
    """Refresh toutes les 30s"""
    print("Mode LIVE — Ctrl+C pour quitter")
    try:
        while True:
            os.system("clear")
            display_status()
            time.sleep(30)
    except KeyboardInterrupt:
        print("\nArrete.")


def main():
    args = sys.argv[1:]

    if "--test-api" in args:
        print("Test API CanLII (1 requete)...")
        code, info = test_api()
        if code == 200:
            print(f"  OK — HTTP {code} | Remaining: {info}")
        elif code == 429:
            print(f"  QUOTA EPUISE — HTTP 429")
        else:
            print(f"  ERREUR — HTTP {code} | {info}")
        return

    if "--live" in args:
        live_mode()
        return

    display_status()


if __name__ == "__main__":
    main()
