#!/usr/bin/env python3
"""
CanLII Downloader — Téléchargement massif jurisprudence + lois
Pour AITicketInfo.ca — Infractions routières QC + ON + Fédéral
"""

import sqlite3
import requests
import time
import json
import os
import sys
from datetime import datetime

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_PROJECT_DIR, "db", "aiticketinfo.db")
API_KEY = os.environ.get("CANLII_API_KEY", "")
BASE_URL = "https://api.canlii.org/v1"
RATE_LIMIT_DELAY = 0.5

# ==========================================
# DATABASES DE JURISPRUDENCE
# ==========================================
CASE_DATABASES = {
    "qccm":   {"juridiction": "QC", "tribunal": "QCCM",   "name": "Cours municipales du Québec"},
    "qccq":   {"juridiction": "QC", "tribunal": "QCCQ",   "name": "Cour du Québec"},
    "qcca":   {"juridiction": "QC", "tribunal": "QCCA",   "name": "Cour d appel du Québec"},
    "qccs":   {"juridiction": "QC", "tribunal": "QCCS",   "name": "Cour supérieure du Québec"},
    "qctat":  {"juridiction": "QC", "tribunal": "QCTAT",  "name": "Tribunal administratif du travail QC"},
    "qctaq":  {"juridiction": "QC", "tribunal": "QCTAQ",  "name": "Tribunal administratif du Québec"},
    "oncj":   {"juridiction": "ON", "tribunal": "ONCJ",   "name": "Ontario Court of Justice"},
    "onsc":   {"juridiction": "ON", "tribunal": "ONSC",   "name": "Superior Court of Justice ON"},
    "onca":   {"juridiction": "ON", "tribunal": "ONCA",   "name": "Court of Appeal for Ontario"},
    "onscdc": {"juridiction": "ON", "tribunal": "ONSCDC", "name": "Divisional Court ON"},
    "onscsm": {"juridiction": "ON", "tribunal": "ONSCSM", "name": "Small Claims Court ON"},
    "csc-scc":{"juridiction": "CA", "tribunal": "CSC",    "name": "Cour suprême du Canada"},
}

TRAFFIC_KEYWORDS = [
    "vitesse", "excès", "radar", "cinémomètre", "alcool", "facultés",
    "conduite", "routier", "routière", "circulation", "infraction",
    "contravention", "permis", "suspension", "démérite", "constat",
    "automobile", "véhicule", "stationnement", "feu rouge", "arrêt",
    "cellulaire", "ceinture", "sécurité routière", "code de la route",
    "photo radar", "impaired", "dangerous driving", "highway",
    "traffic", "speeding", "stunt driving", "careless", "demerit",
    "licence suspension", "breathalyzer", "refusal", "red light",
    "seatbelt", "distracted", "racing", "novice",
    "alcootest", "éthylomètre", "interlock", "délit de fuite",
    "accident", "collision", "blessures", "négligence criminelle",
    "speed", "drunk", "dui", "dwi", "over 80",
]

# ==========================================
# LÉGISLATION À TÉLÉCHARGER
# ==========================================
LEGISLATION_TO_FETCH = [
    {"db": "cas", "leg_id": "lrc-1985-c-c-46", "name": "Code criminel", "juridiction": "CA", "lang": "fr"},
    {"db": "cas", "leg_id": "lc-1992-c-47", "name": "Loi sur les contraventions", "juridiction": "CA", "lang": "fr"},
    {"db": "qcs", "leg_id": "rlrq-c-a-25", "name": "Loi sur l assurance automobile", "juridiction": "QC", "lang": "fr"},
    {"db": "qcs", "leg_id": "rlrq-c-s-11.011", "name": "Loi sur la SAAQ", "juridiction": "QC", "lang": "fr"},
    {"db": "qcs", "leg_id": "rlrq-c-v-1.2", "name": "Loi sur les véhicules hors route", "juridiction": "QC", "lang": "fr"},
    {"db": "ons", "leg_id": "rso-1990-c-h8", "name": "Highway Traffic Act", "juridiction": "ON", "lang": "en"},
    {"db": "ons", "leg_id": "rso-1990-c-p33", "name": "Provincial Offences Act", "juridiction": "ON", "lang": "en"},
    {"db": "ons", "leg_id": "rso-1990-c-c25", "name": "Compulsory Automobile Insurance Act", "juridiction": "ON", "lang": "en"},
    {"db": "ons", "leg_id": "rso-1990-c-d1", "name": "Dangerous Goods Transportation Act", "juridiction": "ON", "lang": "en"},
    {"db": "ons", "leg_id": "rso-1990-c-m44", "name": "Motorized Snow Vehicles Act", "juridiction": "ON", "lang": "en"},
    {"db": "ons", "leg_id": "rso-1990-c-o4", "name": "Off-Road Vehicles Act", "juridiction": "ON", "lang": "en"},
]

# ==========================================
# RECHERCHES PAR MOTS-CLÉS
# ==========================================
SEARCH_QUERIES = [
    {"q": "exces vitesse contravention", "dbs": "qccm,qccq", "lang": "fr"},
    {"q": "cinemometre radar calibration", "dbs": "qccm,qccq", "lang": "fr"},
    {"q": "alcool volant facultes affaiblies", "dbs": "qccm,qccq,qcca,qccs", "lang": "fr"},
    {"q": "suspension permis conduire", "dbs": "qccm,qccq,qcca", "lang": "fr"},
    {"q": "constat infraction routiere", "dbs": "qccm,qccq", "lang": "fr"},
    {"q": "photo radar contestation", "dbs": "qccm,qccq", "lang": "fr"},
    {"q": "cellulaire conduite distraction", "dbs": "qccm,qccq", "lang": "fr"},
    {"q": "feu rouge intersection", "dbs": "qccm,qccq", "lang": "fr"},
    {"q": "delit fuite accident", "dbs": "qccm,qccq,qcca,qccs", "lang": "fr"},
    {"q": "points demerite SAAQ", "dbs": "qccm,qccq", "lang": "fr"},
    {"q": "conduite dangereuse negligence criminelle", "dbs": "qccm,qccq,qcca,qccs,csc-scc", "lang": "fr"},
    {"q": "grand exces vitesse 50 km", "dbs": "qccm,qccq,qcca", "lang": "fr"},
    {"q": "zone scolaire vitesse", "dbs": "qccm,qccq", "lang": "fr"},
    {"q": "ceinture securite", "dbs": "qccm,qccq", "lang": "fr"},
    {"q": "speeding ticket Highway Traffic Act", "dbs": "oncj,onsc,onca", "lang": "en"},
    {"q": "stunt driving racing 50 over", "dbs": "oncj,onsc,onca", "lang": "en"},
    {"q": "impaired driving breathalyzer refusal", "dbs": "oncj,onsc,onca,csc-scc", "lang": "en"},
    {"q": "careless driving Ontario", "dbs": "oncj,onsc,onca", "lang": "en"},
    {"q": "red light camera ticket", "dbs": "oncj,onsc,onca", "lang": "en"},
    {"q": "licence suspension demerit points", "dbs": "oncj,onsc,onca", "lang": "en"},
    {"q": "distracted driving handheld device", "dbs": "oncj,onsc,onca", "lang": "en"},
    {"q": "dangerous driving Criminal Code", "dbs": "oncj,onsc,onca,csc-scc", "lang": "en"},
    {"q": "novice driver G1 G2 suspension", "dbs": "oncj,onsc,onca", "lang": "en"},
    {"q": "fail to stop accident hit and run", "dbs": "oncj,onsc,onca", "lang": "en"},
]


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def api_get(endpoint, params=None):
    if params is None:
        params = {}
    params["api_key"] = API_KEY
    url = f"{BASE_URL}/{endpoint}"
    try:
        r = requests.get(url, params=params, timeout=30)
        time.sleep(RATE_LIMIT_DELAY)
        if r.status_code == 200:
            return r.json()
        elif r.status_code == 429:
            log("  Rate limited, attente 10s...")
            time.sleep(10)
            return api_get(endpoint, params)
        else:
            log(f"  HTTP {r.status_code}: {r.text[:200]}")
            return None
    except Exception as e:
        log(f"  Erreur: {e}")
        return None


def open_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def get_existing_citations(conn):
    c = conn.cursor()
    c.execute("SELECT citation FROM jurisprudence")
    return set(row[0] for row in c.fetchall())


def get_existing_laws(conn):
    c = conn.cursor()
    c.execute("SELECT nom_loi, article FROM lois")
    return set((row[0], row[1]) for row in c.fetchall())


def is_traffic_related(title):
    if not title:
        return False
    t = title.lower()
    for kw in TRAFFIC_KEYWORDS:
        if kw.lower() in t:
            return True
    return False


def download_jurisprudence():
    log("=" * 60)
    log("TELECHARGEMENT JURISPRUDENCE")
    log("=" * 60)

    conn = open_db()
    existing = get_existing_citations(conn)
    log(f"{len(existing)} decisions existantes en DB")
    total_new = 0

    for db_id, info in CASE_DATABASES.items():
        log(f"\n--- {info['name']} ({db_id}) ---")
        lang = "fr" if info["juridiction"] in ("QC", "CA") else "en"
        offset = 0
        batch_size = 100
        db_new = 0

        while True:
            data = api_get(f"caseBrowse/{lang}/{db_id}", {
                "offset": offset,
                "resultCount": batch_size
            })
            if not data or not data.get("cases"):
                break

            cases = data["cases"]
            log(f"  Offset {offset}: {len(cases)} decisions recues")

            for case in cases:
                case_id_obj = case.get("caseId", {})
                case_id = case_id_obj.get("fr", case_id_obj.get("en", ""))
                title = case.get("title", "")
                citation = case.get("citation", case_id)

                if citation in existing:
                    continue

                # QCCM et ONCJ: tout est pertinent
                if db_id in ("qccm", "oncj"):
                    relevant = True
                else:
                    relevant = is_traffic_related(title)

                if not relevant:
                    continue

                # Recuperer detail
                detail = api_get(f"caseBrowse/{lang}/{db_id}/{case_id}")
                date_decision = ""
                resume = title
                if detail:
                    date_decision = detail.get("dateModified", detail.get("dateScheme", ""))

                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO jurisprudence "
                        "(citation, titre, tribunal, juridiction, date_decision, resume, source, langue, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (citation, title, info["tribunal"], info["juridiction"],
                         date_decision, resume, f"canlii-{db_id}", lang,
                         datetime.now().isoformat())
                    )
                    db_new += 1
                    total_new += 1
                    existing.add(citation)
                except Exception as e:
                    log(f"  Insert error: {e}")

            conn.commit()
            if len(cases) < batch_size:
                break
            offset += batch_size
            if offset >= 5000:
                log(f"  Limite 5000 atteinte pour {db_id}")
                break

        log(f"  -> {db_new} nouvelles decisions pour {db_id}")

    conn.close()
    log(f"\nTOTAL JURISPRUDENCE: {total_new} nouvelles decisions")
    return total_new


def download_jurisprudence_by_search():
    log("\n" + "=" * 60)
    log("RECHERCHE PAR MOTS-CLES")
    log("=" * 60)

    conn = open_db()
    existing = get_existing_citations(conn)
    total_new = 0

    for sq in SEARCH_QUERIES:
        query = sq["q"]
        dbs = sq["dbs"]
        lang = sq["lang"]
        log(f'\nRecherche: "{query}" dans {dbs}')

        offset = 0
        search_new = 0
        max_results = 500

        while offset < max_results:
            data = api_get(f"search/{lang}/", {
                "q": query,
                "databases": dbs,
                "offset": offset,
                "resultCount": 100,
            })
            if not data or not data.get("results"):
                break

            results = data["results"]
            total_avail = data.get("totalResults", 0)
            if isinstance(total_avail, int) and total_avail > 0:
                max_results = min(total_avail, 500)

            for r in results:
                title = r.get("title", "")
                citation = r.get("citation", title)
                db_id = r.get("databaseId", "")

                if citation in existing or not citation:
                    continue

                jur = "QC" if db_id.startswith("qc") else ("ON" if db_id.startswith("on") else "CA")
                tribunal = db_id.upper()

                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO jurisprudence "
                        "(citation, titre, tribunal, juridiction, date_decision, resume, source, langue, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (citation, title, tribunal, jur,
                         "", title, "canlii-search", lang,
                         datetime.now().isoformat())
                    )
                    search_new += 1
                    total_new += 1
                    existing.add(citation)
                except:
                    pass

            conn.commit()
            if len(results) < 100:
                break
            offset += 100

        log(f"  -> {search_new} nouvelles decisions via recherche")

    conn.close()
    log(f"\nTOTAL RECHERCHE: {total_new} nouvelles decisions")
    return total_new


def categorize_article(text, law_name, lang):
    t = (text + " " + law_name).lower()
    if lang == "fr":
        cats = [
            (["vitesse", "radar", "cinemometre", "detection"], "vitesse"),
            (["alcool", "faculte", "ivresse", "drogue", "ethyl"], "alcool"),
            (["permis", "licence", "aptitude"], "permis"),
            (["signal", "feu", "panneau", "arret"], "signalisation"),
            (["immatricul", "plaque"], "immatriculation"),
            (["pieton", "cycliste", "velo"], "pietons_cyclistes"),
            (["stationnement"], "stationnement"),
            (["cellulaire", "telephone", "ecran"], "cellulaire"),
            (["fuite", "delit"], "delit_fuite"),
            (["ceinture", "siege", "enfant"], "ceinture"),
            (["assurance"], "assurance"),
            (["penale", "procedure", "poursuite", "amende"], "procedure"),
            (["criminel"], "criminel"),
        ]
    else:
        cats = [
            (["speed", "radar", "detection"], "speed"),
            (["impair", "alcohol", "intoxicat", "breath", "drug"], "impaired"),
            (["licence", "license", "permit", "demerit"], "licence"),
            (["signal", "light", "sign", "stop"], "signalisation"),
            (["registration", "plate"], "immatriculation"),
            (["pedestrian", "cyclist", "bicycle"], "pedestrians_cyclists"),
            (["parking"], "parking"),
            (["handheld", "device", "distract"], "handheld_device"),
            (["seatbelt", "seat belt", "child seat"], "seatbelt"),
            (["insurance"], "insurance"),
            (["stunt", "racing", "contest"], "stunt_driving"),
            (["careless"], "careless_driving"),
            (["offence", "penalty", "fine", "procedure"], "procedure"),
            (["criminal"], "criminal"),
        ]
    for keywords, cat in cats:
        for kw in keywords:
            if kw in t:
                return cat
    return "general"


def download_legislation():
    log("\n" + "=" * 60)
    log("TELECHARGEMENT LEGISLATION")
    log("=" * 60)

    conn = open_db()
    existing_laws = get_existing_laws(conn)
    log(f"{len(existing_laws)} articles de loi existants en DB")
    total_new = 0

    for leg in LEGISLATION_TO_FETCH:
        db = leg["db"]
        leg_id = leg["leg_id"]
        name = leg["name"]
        jur = leg["juridiction"]
        lang = leg["lang"]

        count_existing = sum(1 for (n, a) in existing_laws if n == name)
        if count_existing > 50:
            log(f"\nSkip {name}: deja {count_existing} articles")
            continue

        log(f"\n--- {name} ({leg_id}) ---")

        data = api_get(f"legislationBrowse/{lang}/{db}/{leg_id}")
        if not data:
            log(f"  Impossible de recuperer {name}")
            continue

        title = data.get("title", name)
        citation = data.get("citation", "")
        log(f"  {title} ({citation})")

        # Essayer TOC (table of contents)
        toc_data = api_get(f"legislationBrowse/{lang}/{db}/{leg_id}/toc")

        if toc_data and "sections" in toc_data:
            sections = toc_data["sections"]
            log(f"  {len(sections)} sections trouvees")

            leg_new = 0
            for section in sections:
                sec_id = section.get("sectionId", "")
                sec_title = section.get("title", "")

                if (name, sec_id) in existing_laws:
                    continue

                categorie = categorize_article(sec_title, name, lang)

                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO lois "
                        "(juridiction, source, nom_loi, article, texte, categorie, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (jur, f"canlii-{db}", name, sec_id,
                         sec_title, categorie, datetime.now().isoformat())
                    )
                    leg_new += 1
                    total_new += 1
                except:
                    pass

            conn.commit()
            log(f"  -> {leg_new} articles ajoutes pour {name}")
        else:
            # Pas de TOC dispo, ajouter comme entree unique
            if (name, leg_id) not in existing_laws:
                conn.execute(
                    "INSERT OR IGNORE INTO lois "
                    "(juridiction, source, nom_loi, article, texte, categorie, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (jur, f"canlii-{db}", name, leg_id,
                     f"{title} - {citation}", "general", datetime.now().isoformat())
                )
                total_new += 1
                conn.commit()
                log(f"  -> Loi ajoutee (sans detail sections)")

    conn.close()
    log(f"\nTOTAL LEGISLATION: {total_new} nouveaux articles")
    return total_new


def update_fts():
    log("\nMise a jour index FTS5...")
    conn = open_db()
    c = conn.cursor()
    try:
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jurisprudence_fts'")
        if c.fetchone():
            c.execute("INSERT INTO jurisprudence_fts(jurisprudence_fts) VALUES('rebuild')")
            conn.commit()
            log("  FTS5 jurisprudence reconstruit")
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lois_fts'")
        if c.fetchone():
            c.execute("INSERT INTO lois_fts(lois_fts) VALUES('rebuild')")
            conn.commit()
            log("  FTS5 lois reconstruit")
    except Exception as e:
        log(f"  FTS update error: {e}")
    conn.close()


def print_stats():
    conn = open_db()
    c = conn.cursor()
    log("\n" + "=" * 60)
    log("STATISTIQUES FINALES")
    log("=" * 60)

    c.execute("SELECT COUNT(*) FROM jurisprudence")
    log(f"  Jurisprudence total: {c.fetchone()[0]}")
    c.execute("SELECT juridiction, COUNT(*) FROM jurisprudence GROUP BY juridiction ORDER BY COUNT(*) DESC")
    for row in c.fetchall():
        log(f"    {row[0]}: {row[1]}")

    c.execute("SELECT COUNT(*) FROM lois")
    log(f"  Lois total: {c.fetchone()[0]}")
    c.execute("SELECT juridiction, nom_loi, COUNT(*) FROM lois GROUP BY juridiction, nom_loi ORDER BY juridiction, COUNT(*) DESC")
    for row in c.fetchall():
        log(f"    {row[0]} | {row[1]}: {row[2]} articles")

    conn.close()


def main():
    log("CanLII Downloader - AITicketInfo.ca")
    log(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if not API_KEY:
        log("ERREUR: CANLII_API_KEY non defini!")
        sys.exit(1)

    log(f"API Key: {API_KEY[:8]}...")

    j1 = download_jurisprudence()
    j2 = download_jurisprudence_by_search()
    l1 = download_legislation()
    update_fts()
    print_stats()

    log(f"\nTERMINE - {j1 + j2} jurisprudences + {l1} lois ajoutees")


if __name__ == "__main__":
    main()
