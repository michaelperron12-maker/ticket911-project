#!/usr/bin/env python3
"""
SETUP DATABASE — Telecharge A2AJ + indexe les cas de trafic dans SQLite FTS5
Aussi indexe les lois deja scrapees (QC CSR + ON HTA)

Usage: python3 setup_database.py [--skip-download]
"""

import sqlite3
import json
import os
import re
import sys
import time
from pathlib import Path

DB_PATH = "/var/www/ticket911/db/ticket911.db"
DATA_DIR = Path("/var/www/ticket911/data")
FEASIBILITY_DATA = Path("/var/www/ticket911/feasibility-test/data")

# Mots-cles pour filtrer les cas de trafic
# Mots-cles STRICTS — seulement les termes specifiques au trafic routier
# (eviter "vehicle", "driving", "licence" qui matchent trop de cas non-trafic)
TRAFFIC_KEYWORDS_FR = [
    "excès de vitesse", "radar", "cinémomètre",
    "code de la sécurité routière", "feu rouge",
    "cellulaire au volant", "alcool au volant", "ivresse au volant",
    "délit de fuite", "contravention routière",
    "points d'inaptitude", "limite de vitesse", "zone scolaire",
    "infraction routière", "code de la route"
]

TRAFFIC_KEYWORDS_EN = [
    "speeding", "highway traffic act", "traffic ticket",
    "red light", "stop sign", "traffic offence", "traffic offense",
    "impaired driving", "dui", "dwi", "hit and run",
    "demerit point", "speed limit", "school zone",
    "stunt driving", "careless driving", "dangerous driving",
    "motor vehicle act", "over 80", "breathalyzer",
    "radar", "photo radar"
]


def init_db():
    """Cree toutes les tables necessaires"""
    print("[+] Initialisation de la base SQLite...")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Table principale jurisprudence
    c.execute("""CREATE TABLE IF NOT EXISTS jurisprudence (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        citation TEXT UNIQUE,
        titre TEXT,
        tribunal TEXT,
        juridiction TEXT,
        date_decision TEXT,
        resume TEXT,
        texte_complet TEXT,
        resultat TEXT,
        mots_cles TEXT,
        source TEXT,
        langue TEXT,
        created_at TEXT
    )""")

    # Table lois
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

    # Table agent_runs (pour le logging)
    c.execute("""CREATE TABLE IF NOT EXISTS agent_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_name TEXT,
        action TEXT,
        input_summary TEXT,
        output_summary TEXT,
        tokens_used INTEGER,
        duration_seconds REAL,
        success INTEGER,
        error TEXT,
        created_at TEXT
    )""")

    conn.commit()
    return conn


def create_fts_indexes(conn):
    """Cree les index FTS5 pour la recherche full-text"""
    print("[+] Creation des index FTS5...")
    c = conn.cursor()

    # FTS pour jurisprudence
    try:
        c.execute("DROP TABLE IF EXISTS jurisprudence_fts")
        c.execute("""CREATE VIRTUAL TABLE jurisprudence_fts USING fts5(
            citation, titre, resume, texte_complet, mots_cles,
            content='jurisprudence', content_rowid='id'
        )""")
        c.execute("""INSERT INTO jurisprudence_fts(rowid, citation, titre, resume, texte_complet, mots_cles)
                     SELECT id, citation, titre, resume, texte_complet, mots_cles FROM jurisprudence""")
        print(f"  [+] jurisprudence_fts cree")
    except Exception as e:
        print(f"  [!] FTS jurisprudence: {e}")

    # FTS pour lois
    try:
        c.execute("DROP TABLE IF EXISTS lois_fts")
        c.execute("""CREATE VIRTUAL TABLE lois_fts USING fts5(
            article, texte, nom_loi, categorie,
            content='lois', content_rowid='id'
        )""")
        c.execute("""INSERT INTO lois_fts(rowid, article, texte, nom_loi, categorie)
                     SELECT id, article, texte, nom_loi, categorie FROM lois""")
        print(f"  [+] lois_fts cree")
    except Exception as e:
        print(f"  [!] FTS lois: {e}")

    conn.commit()


def indexer_lois_locales(conn):
    """Indexe les lois deja scrapees dans le test de faisabilite"""
    print("\n[+] Indexation des lois locales...")
    c = conn.cursor()
    nb = 0

    # --- Quebec CSR ---
    csr_path = FEASIBILITY_DATA / "loi_qc_csr.txt"
    if csr_path.exists():
        print(f"  Lecture {csr_path}...")
        with open(csr_path, "r", encoding="utf-8") as f:
            texte = f.read()

        # Extraire les articles numerotes
        # Le CSR a des articles numerotes de 1 a ~600+
        articles_importants = {
            "299": "vitesse",
            "328": "feu rouge",
            "329": "signalisation",
            "396": "cellulaire",
            "443": "arret",
            "462": "points inaptitude",
            "202": "permis de conduire",
            "209": "suspension permis"
        }

        for art_num, categorie in articles_importants.items():
            # Chercher l'article dans le texte
            pattern = rf"(?:^|\n)\s*{art_num}[\.\s](.{{50,500}}?)(?=\n\s*\d{{2,3}}[\.\s]|\Z)"
            match = re.search(pattern, texte, re.DOTALL)
            art_texte = match.group(1).strip() if match else f"Article {art_num} — {categorie}"

            try:
                c.execute("""INSERT OR IGNORE INTO lois (juridiction, source, nom_loi, article, texte, categorie, created_at)
                             VALUES (?,?,?,?,?,?,datetime('now'))""",
                          ("QC", "LegisQuebec", "Code de la securite routiere (C-24.2)",
                           art_num, art_texte[:2000], categorie))
                nb += 1
            except sqlite3.IntegrityError:
                pass

        print(f"  [+] {nb} articles QC indexes")
    else:
        print(f"  [!] {csr_path} non trouve")

    # --- Ontario HTA ---
    hta_path = FEASIBILITY_DATA / "loi_on_hta.txt"
    if hta_path.exists():
        print(f"  Lecture {hta_path}...")
        with open(hta_path, "r", encoding="utf-8") as f:
            texte = f.read()

        articles_on = {
            "128": "speed",
            "130": "careless driving",
            "144": "red light signal",
            "78.1": "handheld device",
            "172": "stunt driving",
            "200": "licence suspension"
        }

        nb_on = 0
        for sec, categorie in articles_on.items():
            pattern = rf"(?:^|\n)\s*{re.escape(sec)}[\.\s\(](.{{50,500}}?)(?=\n\s*\d{{2,3}}[\.\s]|\Z)"
            match = re.search(pattern, texte, re.DOTALL)
            sec_texte = match.group(1).strip() if match else f"Section {sec} — {categorie}"

            try:
                c.execute("""INSERT OR IGNORE INTO lois (juridiction, source, nom_loi, article, texte, categorie, created_at)
                             VALUES (?,?,?,?,?,?,datetime('now'))""",
                          ("ON", "Ontario e-Laws", "Highway Traffic Act (R.S.O. 1990, c. H.8)",
                           sec, sec_texte[:2000], categorie))
                nb_on += 1
            except sqlite3.IntegrityError:
                pass

        print(f"  [+] {nb_on} sections ON indexees")

    conn.commit()
    return nb


def is_traffic_case(text, title=""):
    """Determine si un cas est lie au trafic routier"""
    combined = ((text or "") + " " + (title or "")).lower()
    for kw in TRAFFIC_KEYWORDS_FR + TRAFFIC_KEYWORDS_EN:
        if kw.lower() in combined:
            return True
    return False


def download_and_index_a2aj(conn):
    """Telecharge le dataset A2AJ et indexe les cas de trafic"""
    print("\n[+] Telechargement du dataset A2AJ (HuggingFace)...")
    print("    Cela peut prendre plusieurs minutes...")

    try:
        from datasets import load_dataset
    except ImportError:
        print("  [!] 'datasets' non installe. Installation...")
        os.system("pip3 install --break-system-packages datasets 2>/dev/null")
        try:
            from datasets import load_dataset
        except ImportError:
            print("  [X] Impossible d'installer 'datasets'. Skip A2AJ.")
            return 0

    try:
        # Charger le dataset (streaming pour economiser la RAM)
        print("  Chargement du dataset...")
        dataset = load_dataset("a2aj/canadian-case-law", split="train", streaming=True)

        c = conn.cursor()
        nb_total = 0
        nb_traffic = 0
        batch = []

        for i, example in enumerate(dataset):
            nb_total += 1

            # Extraire les champs (format A2AJ reel)
            title = example.get("name_en", "") or example.get("name_fr", "")
            text_en = example.get("unofficial_text_en", "")
            text_fr = example.get("unofficial_text_fr", "")
            court = example.get("dataset", "")  # ex: "QCCM", "ONSC", "BCCA"
            date_en = example.get("document_date_en", "")
            date_fr = example.get("document_date_fr", "")
            date = str(date_en or date_fr or "")
            citation = example.get("citation_en", "") or example.get("citation_fr", "") or f"A2AJ-{i}"
            langue = "fr" if text_fr else "en"
            text = text_fr if text_fr else text_en

            # Filtrer: est-ce un cas de trafic?
            if is_traffic_case(text[:5000], title):
                nb_traffic += 1

                # Extraire un resume (premier paragraphe significatif)
                resume = ""
                for para in text.split("\n"):
                    para = para.strip()
                    if len(para) > 100:
                        resume = para[:500]
                        break

                # Determiner la juridiction (dataset = code tribunal, ex: QCCM, ONSC, SCC)
                juridiction = ""
                court_upper = court.upper()
                if court_upper.startswith("QC"):
                    juridiction = "QC"
                elif court_upper.startswith("ON"):
                    juridiction = "ON"
                elif court_upper in ("SCC", "CSC", "FCA", "CAF", "FC", "CF"):
                    juridiction = "CA"
                elif court_upper.startswith("BC"):
                    juridiction = "BC"
                elif court_upper.startswith("AB"):
                    juridiction = "AB"
                else:
                    juridiction = court_upper[:2] if court_upper else ""

                # Determiner le resultat (heuristique)
                resultat = "inconnu"
                text_lower = text[:3000].lower()
                if any(w in text_lower for w in ["acquitted", "acquitté", "dismissed", "rejeté"]):
                    resultat = "acquitte"
                elif any(w in text_lower for w in ["guilty", "coupable", "convicted"]):
                    resultat = "coupable"
                elif any(w in text_lower for w in ["reduced", "réduit", "lesser"]):
                    resultat = "reduit"

                batch.append((
                    citation, title[:500], court, juridiction, date,
                    resume, text[:10000], resultat,
                    " ".join([kw for kw in TRAFFIC_KEYWORDS_FR + TRAFFIC_KEYWORDS_EN if kw.lower() in text[:5000].lower()]),
                    "A2AJ", langue
                ))

                if nb_traffic % 50 == 0:
                    # Insert batch
                    for item in batch:
                        try:
                            c.execute("""INSERT OR IGNORE INTO jurisprudence
                                (citation, titre, tribunal, juridiction, date_decision,
                                 resume, texte_complet, resultat, mots_cles, source, langue, created_at)
                                VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now'))""", item)
                        except:
                            pass
                    conn.commit()
                    batch = []
                    print(f"  ... {nb_total} cas scannes, {nb_traffic} cas trafic trouves", end="\r")

            # Progress log tous les 5000 cas
            if nb_total % 5000 == 0:
                print(f"  ... {nb_total} cas scannes ({court}), {nb_traffic} cas trafic trouves", flush=True)

            # Scanner tout le dataset (~185K cas) pour couvrir ONCA, SCC, etc
            if nb_total >= 200000:
                print(f"\n  [i] Limite de 200K cas atteinte. {nb_traffic} cas trafic trouves.")
                break

        # Insert remaining
        for item in batch:
            try:
                c.execute("""INSERT OR IGNORE INTO jurisprudence
                    (citation, titre, tribunal, juridiction, date_decision,
                     resume, texte_complet, resultat, mots_cles, source, langue, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,datetime('now'))""", item)
            except:
                pass
        conn.commit()

        print(f"\n  [+] {nb_traffic} cas de trafic indexes sur {nb_total} scannes")
        return nb_traffic

    except Exception as e:
        print(f"  [X] Erreur A2AJ: {e}")
        return 0


def print_stats(conn):
    """Affiche les statistiques de la base"""
    c = conn.cursor()

    print("\n" + "="*50)
    print("  STATISTIQUES DE LA BASE")
    print("="*50)

    c.execute("SELECT COUNT(*) FROM jurisprudence")
    print(f"  Jurisprudence total: {c.fetchone()[0]}")

    c.execute("SELECT juridiction, COUNT(*) FROM jurisprudence GROUP BY juridiction")
    for row in c.fetchall():
        print(f"    - {row[0] or 'N/A'}: {row[1]} cas")

    c.execute("SELECT resultat, COUNT(*) FROM jurisprudence GROUP BY resultat")
    print("  Par resultat:")
    for row in c.fetchall():
        print(f"    - {row[0] or 'N/A'}: {row[1]}")

    c.execute("SELECT COUNT(*) FROM lois")
    print(f"\n  Lois indexees: {c.fetchone()[0]}")

    c.execute("SELECT juridiction, COUNT(*) FROM lois GROUP BY juridiction")
    for row in c.fetchall():
        print(f"    - {row[0]}: {row[1]} articles")

    # Taille de la base
    db_size = os.path.getsize(DB_PATH) / (1024*1024)
    print(f"\n  Taille DB: {db_size:.1f} MB")
    print(f"  Chemin: {DB_PATH}")
    print("="*50)


if __name__ == "__main__":
    start = time.time()
    skip_download = "--skip-download" in sys.argv

    print("""
+===========================================================+
|       TICKET911 — SETUP BASE DE DONNEES                   |
|       Indexation jurisprudence + lois                      |
+===========================================================+
""")

    conn = init_db()

    # 1. Indexer les lois locales
    indexer_lois_locales(conn)

    # 2. Telecharger et indexer A2AJ (sauf si skip)
    if not skip_download:
        download_and_index_a2aj(conn)
    else:
        print("\n[i] --skip-download: A2AJ ignore")

    # 3. Creer les index FTS5
    create_fts_indexes(conn)

    # 4. Stats
    print_stats(conn)

    elapsed = time.time() - start
    print(f"\n  Setup complete en {elapsed:.0f}s")
    conn.close()
