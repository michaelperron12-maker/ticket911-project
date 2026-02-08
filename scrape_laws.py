#!/usr/bin/env python3
"""
SCRAPE LAWS — Telecharge et indexe TOUTES les lois routieres (QC + ON)
- QC: Code de la securite routiere (C-24.2) — LegisQuebec
- ON: Highway Traffic Act (R.S.O. 1990, c. H.8) — Ontario e-Laws

Usage: python3 scrape_laws.py
"""

import sqlite3
import re
import time
import os
import requests
from bs4 import BeautifulSoup

DB_PATH = "/var/www/ticket911/db/ticket911.db"
DATA_DIR = "/var/www/ticket911/data"


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS lois (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        juridiction TEXT,
        source TEXT,
        nom_loi TEXT,
        article TEXT,
        texte TEXT,
        categorie TEXT,
        created_at TEXT
    )""")
    # Vider les anciennes lois pour re-indexer
    c.execute("DELETE FROM lois")
    conn.commit()
    print("[+] Table lois videe pour re-indexation")
    return conn


def categoriser_article_qc(article_num, texte):
    """Categorise un article QC par type d'infraction"""
    t = texte.lower()
    num = str(article_num)

    # Vitesse
    if num in ["299", "299.1", "299.2", "300", "301", "302", "303", "303.1", "303.2", "328.1"]:
        return "vitesse"
    if "vitesse" in t or "km/h" in t or "cinémomètre" in t or "radar" in t:
        return "vitesse"

    # Feu rouge / signalisation
    if num in ["328", "329", "330", "331", "332", "359", "360", "361", "362"]:
        return "signalisation"
    if "feu rouge" in t or "feu de circulation" in t or "signal" in t:
        return "signalisation"

    # Cellulaire / distractions
    if num in ["439.1", "443.1", "443.2"]:
        return "cellulaire"
    if "cellulaire" in t or "appareil" in t and "main" in t:
        return "cellulaire"

    # Alcool / drogues
    if num in ["202.1", "202.2", "202.3", "202.4", "202.5", "202.6"]:
        return "alcool"
    if "alcool" in t or "ivresse" in t or "drogue" in t or "alcoolémie" in t:
        return "alcool"

    # Arret / stop
    if num in ["368", "369", "370", "371", "372"]:
        return "arret"
    if "arrêt" in t or "immobilis" in t or "panneau" in t:
        return "arret"

    # Points / permis
    if num in ["202", "209", "210", "211", "212", "213", "214"]:
        return "permis"
    if "permis" in t or "point" in t and "inaptitude" in t:
        return "permis"

    # Delit de fuite
    if num in ["252"]:
        return "delit_fuite"
    if "fuite" in t or "quitter" in t and "accident" in t:
        return "delit_fuite"

    # Stationnement
    if "stationnement" in t or "stationn" in t:
        return "stationnement"

    # Pietons / cyclistes
    if "piéton" in t or "cycliste" in t or "bicyclette" in t:
        return "pietons_cyclistes"

    # Immatriculation
    if "immatriculation" in t or "plaque" in t:
        return "immatriculation"

    return "general"


def categoriser_section_on(section_num, texte):
    """Categorise une section ON par type d'infraction"""
    t = texte.lower()
    num = str(section_num)

    if num in ["128", "128.1", "128.2", "128.3", "128.4"]:
        return "speed"
    if "speed" in t or "km/h" in t or "rate of speed" in t:
        return "speed"

    if num in ["144", "144.1"]:
        return "red_light"
    if "red light" in t or "traffic signal" in t:
        return "red_light"

    if num in ["78.1"]:
        return "handheld_device"
    if "handheld" in t or "wireless" in t or "display screen" in t:
        return "handheld_device"

    if num in ["172"]:
        return "stunt_driving"
    if "stunt" in t or "race" in t or "contest" in t:
        return "stunt_driving"

    if num in ["130"]:
        return "careless_driving"
    if "careless" in t:
        return "careless_driving"

    if num in ["200", "201", "202", "203", "204", "205", "206", "207", "208", "209", "210", "211", "212"]:
        return "licence_suspension"
    if "suspend" in t or "licence" in t:
        return "licence_suspension"

    if "impaired" in t or "alcohol" in t or "over 80" in t:
        return "impaired"

    if "stop sign" in t or "stop" in t and "sign" in t:
        return "stop_sign"

    if "parking" in t:
        return "parking"

    if "pedestrian" in t or "cyclist" in t or "bicycle" in t:
        return "pedestrians_cyclists"

    return "general"


def scrape_qc_csr(conn):
    """Scrape le Code de la securite routiere complet depuis LegisQuebec"""
    print("\n[+] Scraping QC — Code de la securite routiere (C-24.2)...")

    base_url = "https://www.legisquebec.gouv.qc.ca/fr/document/lc/C-24.2"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; Ticket911-Research/1.0)"}

    try:
        print("  Telechargement de la page principale...")
        resp = requests.get(base_url, headers=headers, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Sauver le HTML brut
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(f"{DATA_DIR}/loi_qc_csr_full.html", "w", encoding="utf-8") as f:
            f.write(resp.text)
        print(f"  HTML sauve ({len(resp.text)} chars)")

        # Extraire les articles
        c = conn.cursor()
        nb = 0

        # LegisQuebec structure: articles dans des divs avec id="se:xxx"
        # ou dans des elements avec class contenant "article"
        articles = soup.find_all(["div", "section", "p"], id=re.compile(r"^se:"))
        if not articles:
            articles = soup.find_all(attrs={"id": re.compile(r"(art|sec|a)\d+")})
        if not articles:
            # Fallback: chercher tous les textes qui commencent par un numero d'article
            text = soup.get_text()
            articles_raw = re.split(r'\n(?=\d{1,4}[\.\s])', text)
            print(f"  Parsing par regex: {len(articles_raw)} blocs trouves")

            for block in articles_raw:
                block = block.strip()
                if not block or len(block) < 20:
                    continue

                # Extraire le numero d'article
                match = re.match(r'^(\d{1,4}(?:\.\d+)?)\s*[\.\s](.*)', block, re.DOTALL)
                if match:
                    art_num = match.group(1)
                    art_text = match.group(2).strip()[:3000]

                    if len(art_text) < 10:
                        continue

                    categorie = categoriser_article_qc(art_num, art_text)

                    try:
                        c.execute("""INSERT INTO lois (juridiction, source, nom_loi, article, texte, categorie, created_at)
                                     VALUES (?,?,?,?,?,?,datetime('now'))""",
                                  ("QC", "LegisQuebec", "Code de la securite routiere (C-24.2)",
                                   art_num, art_text, categorie))
                        nb += 1
                    except sqlite3.IntegrityError:
                        pass
        else:
            print(f"  {len(articles)} elements d'articles trouves dans le HTML")
            for art_el in articles:
                art_id = art_el.get("id", "")
                art_text = art_el.get_text(strip=True)[:3000]

                # Extraire le numero
                num_match = re.search(r"(\d{1,4}(?:\.\d+)?)", art_id)
                if num_match:
                    art_num = num_match.group(1)
                else:
                    num_match = re.match(r'^(\d{1,4}(?:\.\d+)?)', art_text)
                    art_num = num_match.group(1) if num_match else art_id

                if len(art_text) < 10:
                    continue

                categorie = categoriser_article_qc(art_num, art_text)

                try:
                    c.execute("""INSERT INTO lois (juridiction, source, nom_loi, article, texte, categorie, created_at)
                                 VALUES (?,?,?,?,?,?,datetime('now'))""",
                              ("QC", "LegisQuebec", "Code de la securite routiere (C-24.2)",
                               art_num, art_text, categorie))
                    nb += 1
                except sqlite3.IntegrityError:
                    pass

        conn.commit()
        print(f"  [+] {nb} articles QC indexes")
        return nb

    except Exception as e:
        print(f"  [X] Erreur scraping QC: {e}")
        return 0


def scrape_on_hta(conn):
    """Scrape le Highway Traffic Act complet depuis Ontario e-Laws"""
    print("\n[+] Scraping ON — Highway Traffic Act...")

    # Ontario e-Laws a une version texte accessible
    base_url = "https://www.ontario.ca/laws/statute/90h08"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; Ticket911-Research/1.0)"}

    try:
        print("  Telechargement...")
        resp = requests.get(base_url, headers=headers, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        os.makedirs(DATA_DIR, exist_ok=True)
        with open(f"{DATA_DIR}/loi_on_hta_full.html", "w", encoding="utf-8") as f:
            f.write(resp.text)
        print(f"  HTML sauve ({len(resp.text)} chars)")

        c = conn.cursor()
        nb = 0

        # Ontario e-Laws structure: sections dans des elements avec id
        sections = soup.find_all(attrs={"id": re.compile(r"^(s|BK)")})

        if sections:
            print(f"  {len(sections)} elements de sections trouves")
            for sec_el in sections:
                sec_id = sec_el.get("id", "")
                sec_text = sec_el.get_text(strip=True)[:3000]

                num_match = re.search(r"[sS]\.?\s*(\d+(?:\.\d+)?)", sec_id)
                if not num_match:
                    num_match = re.match(r'^(\d+(?:\.\d+)?)', sec_text)
                if num_match:
                    sec_num = num_match.group(1)
                else:
                    continue

                if len(sec_text) < 10:
                    continue

                categorie = categoriser_section_on(sec_num, sec_text)

                try:
                    c.execute("""INSERT INTO lois (juridiction, source, nom_loi, article, texte, categorie, created_at)
                                 VALUES (?,?,?,?,?,?,datetime('now'))""",
                              ("ON", "Ontario e-Laws", "Highway Traffic Act (R.S.O. 1990, c. H.8)",
                               sec_num, sec_text, categorie))
                    nb += 1
                except sqlite3.IntegrityError:
                    pass
        else:
            # Fallback: parse le texte brut
            text = soup.get_text()
            sections_raw = re.split(r'\n(?=\d{1,3}[\.\s\(])', text)
            print(f"  Parsing par regex: {len(sections_raw)} blocs")

            for block in sections_raw:
                block = block.strip()
                if not block or len(block) < 20:
                    continue

                match = re.match(r'^(\d{1,3}(?:\.\d+)?)\s*[\.\s\(](.*)', block, re.DOTALL)
                if match:
                    sec_num = match.group(1)
                    sec_text = match.group(2).strip()[:3000]

                    if len(sec_text) < 10:
                        continue

                    categorie = categoriser_section_on(sec_num, sec_text)

                    try:
                        c.execute("""INSERT INTO lois (juridiction, source, nom_loi, article, texte, categorie, created_at)
                                     VALUES (?,?,?,?,?,?,datetime('now'))""",
                                  ("ON", "Ontario e-Laws", "Highway Traffic Act (R.S.O. 1990, c. H.8)",
                                   sec_num, sec_text, categorie))
                        nb += 1
                    except sqlite3.IntegrityError:
                        pass

        conn.commit()
        print(f"  [+] {nb} sections ON indexees")
        return nb

    except Exception as e:
        print(f"  [X] Erreur scraping ON: {e}")
        return 0


def rebuild_fts(conn):
    """Reconstruit les index FTS5 pour les lois"""
    print("\n[+] Reconstruction des index FTS5...")
    c = conn.cursor()
    try:
        c.execute("DROP TABLE IF EXISTS lois_fts")
        c.execute("""CREATE VIRTUAL TABLE lois_fts USING fts5(
            article, texte, nom_loi, categorie,
            content='lois', content_rowid='id'
        )""")
        c.execute("""INSERT INTO lois_fts(rowid, article, texte, nom_loi, categorie)
                     SELECT id, article, texte, nom_loi, categorie FROM lois""")
        conn.commit()
        print("  [+] lois_fts reconstruit")
    except Exception as e:
        print(f"  [X] Erreur FTS: {e}")


def print_stats(conn):
    c = conn.cursor()
    print("\n" + "="*50)
    print("  STATISTIQUES DES LOIS")
    print("="*50)

    c.execute("SELECT COUNT(*) FROM lois")
    print(f"  Total: {c.fetchone()[0]} articles/sections")

    c.execute("SELECT juridiction, COUNT(*) FROM lois GROUP BY juridiction")
    for row in c.fetchall():
        print(f"    {row[0]}: {row[1]}")

    c.execute("SELECT juridiction, categorie, COUNT(*) FROM lois GROUP BY juridiction, categorie ORDER BY juridiction, COUNT(*) DESC")
    print("\n  Par categorie:")
    for row in c.fetchall():
        print(f"    {row[0]} | {row[1]}: {row[2]}")

    print("="*50)


if __name__ == "__main__":
    print("""
+===========================================================+
|       TICKET911 — SCRAPE LOIS COMPLETES                   |
|       QC Code securite routiere + ON Highway Traffic Act   |
+===========================================================+
""")
    start = time.time()
    conn = init_db()

    nb_qc = scrape_qc_csr(conn)
    nb_on = scrape_on_hta(conn)

    rebuild_fts(conn)
    print_stats(conn)

    elapsed = time.time() - start
    print(f"\n  Scraping complete en {elapsed:.0f}s — {nb_qc + nb_on} articles/sections indexes")
    conn.close()
