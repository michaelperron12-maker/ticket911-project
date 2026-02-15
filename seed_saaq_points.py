#!/usr/bin/env python3
"""
Seed SAAQ Points d'inaptitude — Table officielle
Source: saaq.gouv.qc.ca/permis-conduire/points-inaptitude/
Données publiques du gouvernement du Québec
"""

import os
import sys
import psycopg2
import psycopg2.extras
from datetime import datetime

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

# ═══════════════════════════════════════════════════════════
# TABLE: saaq_points_inaptitude
# ═══════════════════════════════════════════════════════════

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS saaq_points_inaptitude (
    id SERIAL PRIMARY KEY,
    categorie TEXT NOT NULL,
    article TEXT NOT NULL,
    loi TEXT NOT NULL DEFAULT 'CSR',
    description_fr TEXT NOT NULL,
    points INTEGER NOT NULL,
    amende_min NUMERIC(10,2),
    amende_max NUMERIC(10,2),
    zone_scolaire BOOLEAN DEFAULT FALSE,
    grand_exces BOOLEAN DEFAULT FALSE,
    suspension_immediate BOOLEAN DEFAULT FALSE,
    saisie_vehicule BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(article, categorie, zone_scolaire)
);

CREATE INDEX IF NOT EXISTS idx_saaq_points_categorie ON saaq_points_inaptitude(categorie);
CREATE INDEX IF NOT EXISTS idx_saaq_points_article ON saaq_points_inaptitude(article);
"""

# ═══════════════════════════════════════════════════════════
# DONNÉES OFFICIELLES SAAQ — Points d'inaptitude
# Source: saaq.gouv.qc.ca (février 2026)
# ═══════════════════════════════════════════════════════════

INFRACTIONS = [
    # === EXCÈS DE VITESSE (art. 299-303 CSR) ===
    {"categorie": "vitesse", "article": "299 CSR", "loi": "CSR",
     "description_fr": "Excès de vitesse de 11 à 20 km/h", "points": 1,
     "amende_min": 105, "amende_max": 135},
    {"categorie": "vitesse", "article": "299 CSR", "loi": "CSR",
     "description_fr": "Excès de vitesse de 21 à 30 km/h", "points": 2,
     "amende_min": 135, "amende_max": 175},
    {"categorie": "vitesse", "article": "299 CSR", "loi": "CSR",
     "description_fr": "Excès de vitesse de 31 à 45 km/h", "points": 3,
     "amende_min": 210, "amende_max": 315},
    {"categorie": "vitesse", "article": "299 CSR", "loi": "CSR",
     "description_fr": "Excès de vitesse de 46 à 60 km/h", "points": 5,
     "amende_min": 315, "amende_max": 525},
    {"categorie": "vitesse", "article": "299 CSR", "loi": "CSR",
     "description_fr": "Excès de vitesse de 61 à 80 km/h", "points": 10,
     "amende_min": 525, "amende_max": 1050, "grand_exces": True,
     "suspension_immediate": True},
    {"categorie": "vitesse", "article": "299 CSR", "loi": "CSR",
     "description_fr": "Excès de vitesse de 81 à 100 km/h", "points": 12,
     "amende_min": 1050, "amende_max": 1575, "grand_exces": True,
     "suspension_immediate": True, "saisie_vehicule": True},
    {"categorie": "vitesse", "article": "299 CSR", "loi": "CSR",
     "description_fr": "Excès de vitesse de 101 à 120 km/h", "points": 15,
     "amende_min": 1575, "amende_max": 2100, "grand_exces": True,
     "suspension_immediate": True, "saisie_vehicule": True},
    {"categorie": "vitesse", "article": "299 CSR", "loi": "CSR",
     "description_fr": "Excès de vitesse de plus de 120 km/h", "points": 15,
     "amende_min": 2100, "amende_max": 3150, "grand_exces": True,
     "suspension_immediate": True, "saisie_vehicule": True},

    # === EXCÈS VITESSE ZONE SCOLAIRE (double amende) ===
    {"categorie": "vitesse", "article": "299 CSR", "loi": "CSR",
     "description_fr": "Excès de vitesse de 11 à 20 km/h en zone scolaire", "points": 2,
     "amende_min": 210, "amende_max": 270, "zone_scolaire": True},
    {"categorie": "vitesse", "article": "299 CSR", "loi": "CSR",
     "description_fr": "Excès de vitesse de 21 à 30 km/h en zone scolaire", "points": 4,
     "amende_min": 270, "amende_max": 350, "zone_scolaire": True},
    {"categorie": "vitesse", "article": "299 CSR", "loi": "CSR",
     "description_fr": "Excès de vitesse de 31 à 45 km/h en zone scolaire", "points": 6,
     "amende_min": 420, "amende_max": 630, "zone_scolaire": True},
    {"categorie": "vitesse", "article": "299 CSR", "loi": "CSR",
     "description_fr": "Excès de vitesse de 46 à 60 km/h en zone scolaire", "points": 10,
     "amende_min": 630, "amende_max": 1050, "zone_scolaire": True,
     "grand_exces": True, "suspension_immediate": True},

    # === CELLULAIRE (art. 443.1 CSR) ===
    {"categorie": "cellulaire", "article": "443.1 CSR", "loi": "CSR",
     "description_fr": "Utilisation d'un appareil tenu en main (cellulaire)", "points": 5,
     "amende_min": 300, "amende_max": 600},

    # === ALCOOL / CAPACITÉ AFFAIBLIE ===
    {"categorie": "alcool", "article": "253 C.cr.", "loi": "Code criminel",
     "description_fr": "Conduite avec capacités affaiblies", "points": 0,
     "amende_min": 1000, "amende_max": None,
     "suspension_immediate": True,
     "notes": "Suspension 90 jours immédiate, casier judiciaire"},
    {"categorie": "alcool", "article": "253 C.cr.", "loi": "Code criminel",
     "description_fr": "Conduite avec taux d'alcoolémie supérieur à 80 mg", "points": 0,
     "amende_min": 1000, "amende_max": None,
     "suspension_immediate": True,
     "notes": "Suspension 90 jours immédiate"},
    {"categorie": "alcool", "article": "254 C.cr.", "loi": "Code criminel",
     "description_fr": "Refus de fournir un échantillon d'haleine", "points": 0,
     "amende_min": 2000, "amende_max": None,
     "suspension_immediate": True},

    # === FEU ROUGE (art. 359 CSR) ===
    {"categorie": "feu_rouge", "article": "359 CSR", "loi": "CSR",
     "description_fr": "Ne pas s'arrêter à un feu rouge", "points": 3,
     "amende_min": 150, "amende_max": 300},
    {"categorie": "feu_rouge", "article": "359 CSR", "loi": "CSR",
     "description_fr": "Ne pas s'arrêter à un feu rouge (photo)", "points": 0,
     "amende_min": 150, "amende_max": 300,
     "notes": "Pas de points si constat par photo (propriétaire véhicule)"},

    # === ARRÊT OBLIGATOIRE / STOP (art. 368 CSR) ===
    {"categorie": "stop", "article": "368 CSR", "loi": "CSR",
     "description_fr": "Ne pas s'immobiliser à un panneau d'arrêt", "points": 3,
     "amende_min": 150, "amende_max": 300},

    # === CEINTURE DE SÉCURITÉ (art. 396 CSR) ===
    {"categorie": "ceinture", "article": "396 CSR", "loi": "CSR",
     "description_fr": "Défaut de port de la ceinture de sécurité", "points": 3,
     "amende_min": 200, "amende_max": 300},
    {"categorie": "ceinture", "article": "397 CSR", "loi": "CSR",
     "description_fr": "Enfant mal attaché dans un véhicule", "points": 3,
     "amende_min": 200, "amende_max": 300},

    # === CONDUITE DANGEREUSE (art. 327-328 CSR + C.cr.) ===
    {"categorie": "conduite_dangereuse", "article": "327 CSR", "loi": "CSR",
     "description_fr": "Conduite imprudente", "points": 2,
     "amende_min": 200, "amende_max": 300},
    {"categorie": "conduite_dangereuse", "article": "249 C.cr.", "loi": "Code criminel",
     "description_fr": "Conduite dangereuse (Code criminel)", "points": 0,
     "amende_min": None, "amende_max": None,
     "notes": "Casier judiciaire, suspension, emprisonnement possible"},

    # === COURSE DE RUE / GRAND EXCÈS ===
    {"categorie": "grand_exces", "article": "303.2 CSR", "loi": "CSR",
     "description_fr": "Grand excès de vitesse (40+ km/h au-dessus en zone 60 ou moins)", "points": 12,
     "amende_min": 600, "amende_max": 3000,
     "grand_exces": True, "suspension_immediate": True, "saisie_vehicule": True},
    {"categorie": "grand_exces", "article": "303.2 CSR", "loi": "CSR",
     "description_fr": "Grand excès de vitesse (50+ km/h au-dessus en zone 60-90)", "points": 12,
     "amende_min": 600, "amende_max": 3000,
     "grand_exces": True, "suspension_immediate": True, "saisie_vehicule": True},
    {"categorie": "grand_exces", "article": "303.2 CSR", "loi": "CSR",
     "description_fr": "Grand excès de vitesse (60+ km/h au-dessus en zone 100+)", "points": 12,
     "amende_min": 600, "amende_max": 3000,
     "grand_exces": True, "suspension_immediate": True, "saisie_vehicule": True},
    {"categorie": "grand_exces", "article": "303.3 CSR", "loi": "CSR",
     "description_fr": "Course de rue / conduite de véhicule lors d'une course", "points": 15,
     "amende_min": 1000, "amende_max": 3000,
     "grand_exces": True, "suspension_immediate": True, "saisie_vehicule": True},

    # === PERMIS / SUSPENSION ===
    {"categorie": "permis", "article": "93.1 CSR", "loi": "CSR",
     "description_fr": "Conduire durant une suspension de permis", "points": 0,
     "amende_min": 300, "amende_max": 600,
     "notes": "Saisie immédiate du véhicule 30 jours"},
    {"categorie": "permis", "article": "65 CSR", "loi": "CSR",
     "description_fr": "Conduire sans permis valide", "points": 0,
     "amende_min": 300, "amende_max": 600},

    # === DÉLIT DE FUITE (art. 252 C.cr.) ===
    {"categorie": "delit_fuite", "article": "252 C.cr.", "loi": "Code criminel",
     "description_fr": "Délit de fuite (quitter les lieux d'un accident)", "points": 0,
     "amende_min": None, "amende_max": None,
     "notes": "Casier judiciaire, emprisonnement possible"},

    # === SIGNALISATION / DIVERS ===
    {"categorie": "signalisation", "article": "310 CSR", "loi": "CSR",
     "description_fr": "Ne pas respecter la signalisation", "points": 2,
     "amende_min": 100, "amende_max": 200},
    {"categorie": "priorite", "article": "349 CSR", "loi": "CSR",
     "description_fr": "Ne pas céder le passage à un piéton", "points": 3,
     "amende_min": 150, "amende_max": 300},
    {"categorie": "priorite", "article": "350 CSR", "loi": "CSR",
     "description_fr": "Ne pas céder le passage à un véhicule d'urgence", "points": 3,
     "amende_min": 200, "amende_max": 300},
    {"categorie": "depassement", "article": "344 CSR", "loi": "CSR",
     "description_fr": "Dépassement interdit / ligne continue", "points": 3,
     "amende_min": 200, "amende_max": 300},
    {"categorie": "depassement", "article": "344.2 CSR", "loi": "CSR",
     "description_fr": "Dépassement interdit d'un cycliste (1 mètre)", "points": 3,
     "amende_min": 200, "amende_max": 300},
    {"categorie": "autobus", "article": "460 CSR", "loi": "CSR",
     "description_fr": "Dépassement d'un autobus scolaire arrêté", "points": 9,
     "amende_min": 200, "amende_max": 300},
]

# ═══════════════════════════════════════════════════════════
# SEUILS POINTS D'INAPTITUDE
# ═══════════════════════════════════════════════════════════

CREATE_SEUILS = """
CREATE TABLE IF NOT EXISTS saaq_seuils_points (
    id SERIAL PRIMARY KEY,
    type_permis TEXT NOT NULL,
    description_fr TEXT NOT NULL,
    seuil_points INTEGER NOT NULL,
    consequence TEXT NOT NULL,
    duree_suspension TEXT,
    notes TEXT,
    UNIQUE(type_permis, seuil_points)
);
"""

SEUILS = [
    {"type_permis": "probatoire", "description_fr": "Permis probatoire (nouveau conducteur)",
     "seuil_points": 4, "consequence": "Suspension du permis",
     "duree_suspension": "3 mois (1re), 6 mois (2e), 12 mois (3e+)"},
    {"type_permis": "apprenti", "description_fr": "Permis d'apprenti conducteur",
     "seuil_points": 4, "consequence": "Suspension du permis",
     "duree_suspension": "3 mois (1re), 6 mois (2e), 12 mois (3e+)"},
    {"type_permis": "regulier", "description_fr": "Permis régulier (classe 5)",
     "seuil_points": 15, "consequence": "Suspension du permis",
     "duree_suspension": "3 mois (1re), 6 mois (2e), 12 mois (3e+)"},
    {"type_permis": "regulier", "description_fr": "Permis régulier - alerte",
     "seuil_points": 8, "consequence": "Lettre d'avertissement SAAQ",
     "duree_suspension": None, "notes": "Pas de suspension, avertissement seulement"},
    {"type_permis": "regulier", "description_fr": "Permis régulier - 2e alerte",
     "seuil_points": 12, "consequence": "2e lettre d'avertissement SAAQ",
     "duree_suspension": None},
]


def main():
    print("=" * 60)
    print("  SEED SAAQ POINTS D'INAPTITUDE")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    conn = psycopg2.connect(**PG_CONFIG)
    cur = conn.cursor()

    # Créer les tables
    cur.execute(CREATE_TABLE)
    cur.execute(CREATE_SEUILS)
    conn.commit()
    print("\n  Tables créées: saaq_points_inaptitude, saaq_seuils_points")

    # Insérer les infractions
    inserted = 0
    for inf in INFRACTIONS:
        try:
            cur.execute("""
                INSERT INTO saaq_points_inaptitude
                    (categorie, article, loi, description_fr, points,
                     amende_min, amende_max, zone_scolaire, grand_exces,
                     suspension_immediate, saisie_vehicule, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (article, categorie, zone_scolaire) DO UPDATE SET
                    description_fr = EXCLUDED.description_fr,
                    points = EXCLUDED.points,
                    amende_min = EXCLUDED.amende_min,
                    amende_max = EXCLUDED.amende_max,
                    grand_exces = EXCLUDED.grand_exces,
                    suspension_immediate = EXCLUDED.suspension_immediate,
                    saisie_vehicule = EXCLUDED.saisie_vehicule,
                    notes = EXCLUDED.notes
            """, (
                inf["categorie"], inf["article"], inf.get("loi", "CSR"),
                inf["description_fr"], inf["points"],
                inf.get("amende_min"), inf.get("amende_max"),
                inf.get("zone_scolaire", False), inf.get("grand_exces", False),
                inf.get("suspension_immediate", False), inf.get("saisie_vehicule", False),
                inf.get("notes")
            ))
            inserted += 1
        except Exception as e:
            print(f"  [ERR] {inf['article']}: {e}")
            conn.rollback()
            continue
    conn.commit()
    print(f"  Infractions insérées: {inserted}/{len(INFRACTIONS)}")

    # Insérer les seuils
    seuils_inserted = 0
    for s in SEUILS:
        try:
            cur.execute("""
                INSERT INTO saaq_seuils_points
                    (type_permis, description_fr, seuil_points, consequence,
                     duree_suspension, notes)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (type_permis, seuil_points) DO UPDATE SET
                    description_fr = EXCLUDED.description_fr,
                    consequence = EXCLUDED.consequence,
                    duree_suspension = EXCLUDED.duree_suspension
            """, (
                s["type_permis"], s["description_fr"], s["seuil_points"],
                s["consequence"], s.get("duree_suspension"), s.get("notes")
            ))
            seuils_inserted += 1
        except Exception as e:
            print(f"  [ERR] Seuil {s['type_permis']}: {e}")
            conn.rollback()
    conn.commit()
    print(f"  Seuils insérés: {seuils_inserted}/{len(SEUILS)}")

    # Stats
    cur.execute("SELECT categorie, count(*), min(points), max(points) FROM saaq_points_inaptitude GROUP BY categorie ORDER BY categorie")
    print("\n  Par catégorie:")
    for row in cur.fetchall():
        print(f"    {row[0]:25s} {row[1]:>3} entrées  ({row[2]}-{row[3]} pts)")

    conn.close()
    print(f"\n{'='*60}")
    print("  DONE")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
