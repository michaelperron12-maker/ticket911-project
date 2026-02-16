#!/usr/bin/env python3
"""
RECENSEMENT DES STATS — Détecteur d'anomalies statistiques
===========================================================
Cron: dimanche 5:30AM (après les imports de 2-3AM)
Usage:
    python3 recensement_stats_runner.py             # run complet
    python3 recensement_stats_runner.py --dry-run    # affiche sans insérer
    python3 recensement_stats_runner.py --type spike  # un seul détecteur

28 types d'anomalies détectées:
  A. spike_fin_mois        — Quotas policiers (jours 26-31 vs 1-25)
  B. hotspot_geo           — Lieux avec plus de constats que 95e percentile
  C. radar_disproportionne — Radar avec constats > 2x la moyenne
  D. piege_vitesse         — Lieux avec excès marginaux (11-15 km/h) surreprésentés
  E. pattern_jour          — Jour de semaine anormalement élevé par lieu
  F. article_surrepresente — Article local > 2x la proportion provinciale
  G. anomalie_saisonniere  — Trimestre anormal vs historique
  H. taux_acquittement     — Articles avec taux acquittement > 1.5x la moyenne
  I. vehicule_lourd_anomal — Véhicules lourds surreprésentés
  J. intervention_anomale  — Type d'intervention dominant anormal
  K. concentration_articles— Un seul article > 70% des constats = ciblage
  L. tendance_annuelle     — Hausse brutale année sur année (+80%+)
  M. heure_pointe_anomale  — Constats concentrés à une heure précise
  N. amende_disproportionnee— Amendes supérieures à la moyenne provinciale
  O. collision_vs_enforce  — Beaucoup de tickets mais peu d'accidents
  P. tolerance_radar       — Excès très faibles (1-10 km/h) dans marge erreur
  Q. points_anormaux       — Points d'inaptitude moyens anormalement élevés
  R. spike_debut_mois      — Objectifs mensuels (jours 1-5 élevés)
  S. exces_distribution    — Profil de distribution d'excès atypique
  T. multi_infraction      — Nombre élevé d'articles différents = piège
  U. recidive_municipale   — 3+ années consécutives de hausse
  V. weekend_ratio         — Ratio week-end/semaine anormal
  W. loi_anomale           — Loi appliquée de façon disproportionnée
  X. vitesse_benford       — Loi de Benford: manipulation des lectures vitesse
  Y. bracketing_vitesse    — Clustering aux seuils d'amende (21, 31, 46 km/h)
  Z. blitz_vacances        — Spikes de constats pendant vacances/congés
  AA. zone_scolaire        — Art. 329 émis hors heures/périodes scolaires
  AB. profilage_veil       — Test voile de noirceur (biais jour vs nuit)

Zéro dépendance externe (stdlib + psycopg2).
"""

import argparse
import json
import math
import os
import sys
import time
import uuid
from datetime import datetime, date

import decimal
import psycopg2
import psycopg2.extras


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder qui gère les Decimal de PostgreSQL."""
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return float(o)
        return super().default(o)

# ── Config DB ──────────────────────────────────────────────
PG_CONFIG = {
    'host': os.environ.get('TICKETS_DB_HOST', '172.18.0.3'),
    'port': int(os.environ.get('TICKETS_DB_PORT', 5432)),
    'dbname': os.environ.get('TICKETS_DB_NAME', 'tickets_qc_on'),
    'user': os.environ.get('TICKETS_DB_USER', 'ticketdb_user'),
    'password': os.environ.get('TICKETS_DB_PASS', 'Tk911PgSecure2026'),
}

# ── Seuils ─────────────────────────────────────────────────
SEUILS = {
    'spike_min_constats': 500,         # min constats par lieu pour quotas
    'spike_ratio_pct': 130,            # fin mois > 130% du reste
    'spike_z_score': 2.0,
    'hotspot_percentile': 0.95,        # top 5%
    'hotspot_z_score': 2.5,
    'hotspot_min_constats': 100,
    'radar_ratio': 2.0,               # > 2x la moyenne
    'radar_z_score': 2.0,
    'piege_min_vitesse': 50,           # min constats vitesse par lieu
    'piege_min_marginaux': 20,         # min excès 11-15 km/h
    'piege_z_score': 2.0,
    'jour_min_constats': 500,
    'jour_z_score': 2.0,
    'article_ratio': 2.0,             # local > 2x provincial
    'article_min_constats': 50,
    'saison_z_score': 2.0,
    'saison_min_annees': 3,
    'acquit_ratio': 1.5,              # > 1.5x la moyenne
    'acquit_min_decisions': 5,
}


def log(msg, level="INFO"):
    symbols = {"INFO": "ℹ", "OK": "✓", "WARN": "⚠", "FAIL": "✗", "STEP": "►"}
    sym = symbols.get(level, "·")
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"  [{ts}] {sym} {msg}")


def get_db():
    return psycopg2.connect(**PG_CONFIG)


def z_score(value, mean, stddev):
    """Calcule z-score. Retourne 0 si stddev=0."""
    if not stddev or stddev == 0:
        return 0.0
    return round((value - mean) / stddev, 2)


def severity_from_z(z):
    """Détermine la sévérité basée sur le z-score."""
    z = abs(z)
    if z >= 3.5:
        return 'high'
    elif z >= 2.5:
        return 'medium'
    return 'low'


def confidence_from_sample(n, min_for_high=500, min_for_medium=100):
    """Détermine la confiance basée sur la taille de l'échantillon."""
    if n >= min_for_high:
        return 'high'
    elif n >= min_for_medium:
        return 'medium'
    return 'low'


# ══════════════════════════════════════════════════════════════
#  A. SPIKE FIN DE MOIS (quotas policiers)
# ══════════════════════════════════════════════════════════════
def detect_spike_fin_mois(cur, dry_run=False):
    """Compare jours 26-31 vs jours 1-25 par municipalité."""
    log("Détection: spike_fin_mois (quotas)", "STEP")

    cur.execute("""
        WITH stats_par_lieu AS (
            SELECT
                lieu_infraction,
                COUNT(*) AS total,
                SUM(CASE WHEN EXTRACT(DAY FROM date_infraction) >= 26 THEN 1 ELSE 0 END) AS fin_mois,
                SUM(CASE WHEN EXTRACT(DAY FROM date_infraction) < 26 THEN 1 ELSE 0 END) AS reste_mois
            FROM qc_constats_infraction
            WHERE date_infraction IS NOT NULL
                AND lieu_infraction IS NOT NULL
                AND lieu_infraction != ''
            GROUP BY lieu_infraction
            HAVING COUNT(*) >= %s
        ),
        global_stats AS (
            SELECT
                AVG(fin_mois::float / NULLIF(total, 0)) AS avg_ratio,
                STDDEV(fin_mois::float / NULLIF(total, 0)) AS std_ratio
            FROM stats_par_lieu
        )
        SELECT
            s.lieu_infraction,
            s.total,
            s.fin_mois,
            s.reste_mois,
            ROUND((s.fin_mois::numeric / 6) / NULLIF(s.reste_mois::numeric / 25, 0) * 100, 1) AS ratio_pct,
            g.avg_ratio,
            g.std_ratio
        FROM stats_par_lieu s, global_stats g
        WHERE s.fin_mois > 0 AND s.reste_mois > 0
        ORDER BY ratio_pct DESC
    """, (SEUILS['spike_min_constats'],))

    anomalies = []
    rows = cur.fetchall()
    if not rows:
        log("Aucune donnée suffisante", "WARN")
        return anomalies

    # Calculer stats globales pour z-score
    ratios = []
    for r in rows:
        lieu, total, fin, reste, ratio_pct, avg_ratio, std_ratio = r
        daily_fin = fin / 6
        daily_reste = reste / 25
        ratio = daily_fin / daily_reste if daily_reste > 0 else 0
        ratios.append((lieu, total, fin, reste, ratio_pct, ratio))

    mean_ratio = sum(r[5] for r in ratios) / len(ratios) if ratios else 0
    std_ratio = math.sqrt(sum((r[5] - mean_ratio) ** 2 for r in ratios) / len(ratios)) if len(ratios) > 1 else 0

    for lieu, total, fin, reste, ratio_pct, ratio in ratios:
        z = z_score(ratio, mean_ratio, std_ratio)
        if ratio_pct >= SEUILS['spike_ratio_pct'] and z >= SEUILS['spike_z_score']:
            anomalies.append({
                'anomaly_type': 'spike_fin_mois',
                'region': lieu,
                'article': None,
                'observed_value': float(ratio_pct),
                'expected_value': 100.0,
                'deviation_pct': float(ratio_pct - 100),
                'z_score': z,
                'severity': severity_from_z(z),
                'confidence_level': confidence_from_sample(total),
                'defense_text_fr': (
                    f"Le lieu {lieu} montre un volume de constats {ratio_pct:.0f}% plus élevé "
                    f"en fin de mois (jours 26-31) vs le reste du mois. "
                    f"Sur {total:,} constats, {fin:,} tombent en fin de mois. "
                    f"Ce pattern (z-score={z:.1f}) suggère un système de quotas. "
                    f"Argument: application sélective et intensification non justifiée."
                ),
                'legal_reference': 'Charte canadienne, art. 7 et 15 — traitement arbitraire',
                'sample_size': total,
                'computation_details': {
                    'fin_mois': fin, 'reste_mois': reste,
                    'daily_avg_fin': round(fin / 6, 1),
                    'daily_avg_reste': round(reste / 25, 1),
                    'mean_ratio': round(mean_ratio, 4),
                    'std_ratio': round(std_ratio, 4),
                }
            })

    log(f"  → {len(anomalies)} anomalies détectées sur {len(rows)} lieux", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  B. HOTSPOT GÉOGRAPHIQUE
# ══════════════════════════════════════════════════════════════
def detect_hotspot_geo(cur, dry_run=False):
    """Identifie les lieux avec plus de constats que le 95e percentile."""
    log("Détection: hotspot_geo", "STEP")

    cur.execute("""
        SELECT lieu_infraction, COUNT(*) AS total
        FROM qc_constats_infraction
        WHERE lieu_infraction IS NOT NULL AND lieu_infraction != ''
        GROUP BY lieu_infraction
        HAVING COUNT(*) >= %s
        ORDER BY total DESC
    """, (SEUILS['hotspot_min_constats'],))

    rows = cur.fetchall()
    if not rows:
        log("Aucune donnée suffisante", "WARN")
        return []

    counts = [r[1] for r in rows]
    mean_count = sum(counts) / len(counts)
    std_count = math.sqrt(sum((c - mean_count) ** 2 for c in counts) / len(counts)) if len(counts) > 1 else 0

    # Percentile 95
    sorted_counts = sorted(counts)
    idx_95 = int(len(sorted_counts) * SEUILS['hotspot_percentile'])
    threshold_95 = sorted_counts[min(idx_95, len(sorted_counts) - 1)]

    anomalies = []
    for lieu, total in rows:
        if total >= threshold_95:
            z = z_score(total, mean_count, std_count)
            if z >= SEUILS['hotspot_z_score']:
                pct_rank = sum(1 for c in counts if c <= total) / len(counts) * 100
                anomalies.append({
                    'anomaly_type': 'hotspot_geo',
                    'region': lieu,
                    'article': None,
                    'observed_value': float(total),
                    'expected_value': round(mean_count, 1),
                    'deviation_pct': round((total - mean_count) / mean_count * 100, 1),
                    'z_score': z,
                    'severity': severity_from_z(z),
                    'confidence_level': confidence_from_sample(total),
                    'defense_text_fr': (
                        f"Le lieu {lieu} est dans le top {100 - pct_rank:.1f}% des plus verbalisés "
                        f"au Québec avec {total:,} constats (moyenne: {mean_count:.0f}). "
                        f"Z-score={z:.1f}. Argument: ciblage disproportionné, "
                        f"vérifier signalisation et conditions routières."
                    ),
                    'legal_reference': 'CSR art. 303 — signalisation conforme requise',
                    'sample_size': total,
                    'computation_details': {
                        'percentile_rank': round(pct_rank, 1),
                        'threshold_95': threshold_95,
                        'mean': round(mean_count, 1),
                        'std': round(std_count, 1),
                        'nb_lieux_total': len(rows),
                    }
                })

    log(f"  → {len(anomalies)} hotspots (seuil 95e: {threshold_95:,})", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  C. RADAR DISPROPORTIONNÉ
# ══════════════════════════════════════════════════════════════
def detect_radar_disproportionne(cur, dry_run=False):
    """Compare chaque radar vs la moyenne provinciale."""
    log("Détection: radar_disproportionne", "STEP")

    # Joindre radar_lieux + radar_stats via municipalite + route
    cur.execute("""
        SELECT
            l.id AS site_id,
            l.municipalite,
            l.route,
            l.emplacement,
            l.vitesse_limite,
            COALESCE(s.total_constats, 0) AS total_constats
        FROM qc_radar_photo_lieux l
        LEFT JOIN (
            SELECT municipalite, route, SUM(nombre_constats) AS total_constats
            FROM qc_radar_photo_stats
            WHERE municipalite IS NOT NULL
            GROUP BY municipalite, route
        ) s ON s.municipalite = l.municipalite AND s.route = l.route
        WHERE l.actif = TRUE
    """)

    rows = cur.fetchall()
    if not rows:
        log("Aucun radar actif trouvé", "WARN")
        return []

    # Si les stats ne matchent pas (municipalite NULL), essayer une distribution uniforme
    constats_list = [r[5] for r in rows if r[5] > 0]
    if not constats_list:
        # Pas de join possible — distribuer le total uniformément pour estimation
        cur.execute("SELECT SUM(nombre_constats) FROM qc_radar_photo_stats")
        total_global = cur.fetchone()[0] or 0
        if total_global == 0 or len(rows) == 0:
            log("  Pas de données radar stats utilisables", "WARN")
            return []
        avg_per_site = total_global / len(rows)
        log(f"  Stats sans détail par site — estimation: {avg_per_site:,.0f}/site ({total_global:,} total / {len(rows)} sites)", "WARN")

        anomalies = []
        # On ne peut pas détecter d'anomalie sans données par site
        log(f"  → 0 anomalies (données par site indisponibles)", "OK")
        return anomalies

    mean_constats = sum(constats_list) / len(constats_list)
    std_constats = math.sqrt(sum((c - mean_constats) ** 2 for c in constats_list) / len(constats_list)) if len(constats_list) > 1 else 0

    anomalies = []
    for site_id, muni, route, empl, vlim, total in rows:
        if total <= 0:
            continue
        z = z_score(total, mean_constats, std_constats)
        ratio = total / mean_constats if mean_constats > 0 else 0
        if ratio >= SEUILS['radar_ratio'] and z >= SEUILS['radar_z_score']:
            site_name = f"{muni} — {route}" + (f" ({empl})" if empl else "")
            anomalies.append({
                'anomaly_type': 'radar_disproportionne',
                'region': muni,
                'article': None,
                'radar_site_id': site_id,
                'radar_site_name': site_name,
                'observed_value': float(total),
                'expected_value': round(mean_constats, 1),
                'deviation_pct': round((total - mean_constats) / mean_constats * 100, 1),
                'z_score': z,
                'severity': severity_from_z(z),
                'confidence_level': confidence_from_sample(total, min_for_high=50000),
                'defense_text_fr': (
                    f"Le radar {site_name} (limite {vlim} km/h) génère {total:,} constats, "
                    f"soit {ratio:.1f}x la moyenne ({mean_constats:,.0f}). "
                    f"Z-score={z:.1f}. Argument: appareil de revenus, "
                    f"vérifier certification et signalisation en amont."
                ),
                'legal_reference': 'CSR art. 332-332.4 — photo radar, conditions de validité',
                'sample_size': total,
                'computation_details': {
                    'vitesse_limite': vlim,
                    'ratio_vs_mean': round(ratio, 2),
                    'mean_constats': round(mean_constats, 1),
                    'std_constats': round(std_constats, 1),
                    'nb_sites_total': len(rows),
                }
            })

    log(f"  → {len(anomalies)} radars disproportionnés sur {len(rows)} sites", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  D. PIÈGE À VITESSE (excès marginaux 11-15 km/h)
# ══════════════════════════════════════════════════════════════
def detect_piege_vitesse(cur, dry_run=False):
    """Identifie les lieux où les excès marginaux (11-15 km/h) sont surreprésentés."""
    log("Détection: piege_vitesse", "STEP")

    cur.execute("""
        WITH vitesse_par_lieu AS (
            SELECT
                lieu_infraction,
                COUNT(*) AS total_vitesse,
                SUM(CASE
                    WHEN (vitesse_constatee - vitesse_permise) BETWEEN 11 AND 15 THEN 1
                    ELSE 0
                END) AS nb_marginaux
            FROM qc_constats_infraction
            WHERE vitesse_permise IS NOT NULL
                AND vitesse_constatee IS NOT NULL
                AND vitesse_constatee > vitesse_permise
                AND lieu_infraction IS NOT NULL
                AND lieu_infraction != ''
            GROUP BY lieu_infraction
            HAVING COUNT(*) >= %s
        )
        SELECT
            lieu_infraction,
            total_vitesse,
            nb_marginaux,
            ROUND(nb_marginaux::numeric / total_vitesse * 100, 1) AS pct_marginaux
        FROM vitesse_par_lieu
        WHERE nb_marginaux >= %s
        ORDER BY pct_marginaux DESC
    """, (SEUILS['piege_min_vitesse'], SEUILS['piege_min_marginaux']))

    rows = cur.fetchall()
    if not rows:
        log("Pas assez de données vitesse par lieu", "WARN")
        return []

    pcts = [float(r[3]) for r in rows]
    mean_pct = sum(pcts) / len(pcts) if pcts else 0
    std_pct = math.sqrt(sum((p - mean_pct) ** 2 for p in pcts) / len(pcts)) if len(pcts) > 1 else 0

    anomalies = []
    for lieu, total_v, nb_marg, pct_marg in rows:
        z = z_score(float(pct_marg), mean_pct, std_pct)
        if z >= SEUILS['piege_z_score']:
            anomalies.append({
                'anomaly_type': 'piege_vitesse',
                'region': lieu,
                'article': None,
                'observed_value': float(pct_marg),
                'expected_value': round(mean_pct, 1),
                'deviation_pct': round(float(pct_marg) - mean_pct, 1),
                'z_score': z,
                'severity': severity_from_z(z),
                'confidence_level': confidence_from_sample(total_v, min_for_high=200),
                'defense_text_fr': (
                    f"{pct_marg}% des constats de vitesse au lieu {lieu} sont pour des excès "
                    f"de 11-15 km/h ({nb_marg}/{total_v} constats). Moyenne provinciale: {mean_pct:.1f}%. "
                    f"Z-score={z:.1f}. Argument: piège à vitesse, tolérance des appareils "
                    f"de mesure, limite potentiellement inadaptée."
                ),
                'legal_reference': 'CSR art. 443 — tolérance instrumentale, calibration requise',
                'sample_size': total_v,
                'computation_details': {
                    'nb_marginaux': nb_marg,
                    'total_vitesse': total_v,
                    'mean_pct': round(mean_pct, 1),
                    'std_pct': round(std_pct, 2),
                }
            })

    log(f"  → {len(anomalies)} pièges à vitesse sur {len(rows)} lieux", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  E. PATTERN JOUR DE SEMAINE
# ══════════════════════════════════════════════════════════════
def detect_pattern_jour(cur, dry_run=False):
    """Détecte les jours de semaine anormalement élevés par lieu."""
    log("Détection: pattern_jour", "STEP")

    cur.execute("""
        SELECT
            lieu_infraction,
            EXTRACT(DOW FROM date_infraction)::int AS dow,
            COUNT(*) AS nb
        FROM qc_constats_infraction
        WHERE date_infraction IS NOT NULL
            AND lieu_infraction IS NOT NULL
            AND lieu_infraction != ''
        GROUP BY lieu_infraction, dow
    """)

    # Organiser par lieu
    lieu_data = {}
    for lieu, dow, nb in cur.fetchall():
        if lieu not in lieu_data:
            lieu_data[lieu] = {}
        lieu_data[lieu][dow] = nb

    jours_noms = ['dimanche', 'lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi']
    anomalies = []

    for lieu, dow_counts in lieu_data.items():
        total = sum(dow_counts.values())
        if total < SEUILS['jour_min_constats']:
            continue

        counts = [dow_counts.get(d, 0) for d in range(7)]
        mean_dow = total / 7
        std_dow = math.sqrt(sum((c - mean_dow) ** 2 for c in counts) / 7) if total > 0 else 0

        for dow in range(7):
            val = counts[dow]
            z = z_score(val, mean_dow, std_dow)
            if z >= SEUILS['jour_z_score']:
                pct_above = round((val - mean_dow) / mean_dow * 100, 1) if mean_dow > 0 else 0
                anomalies.append({
                    'anomaly_type': 'pattern_jour',
                    'region': lieu,
                    'article': None,
                    'observed_value': float(val),
                    'expected_value': round(mean_dow, 1),
                    'deviation_pct': pct_above,
                    'z_score': z,
                    'severity': severity_from_z(z),
                    'confidence_level': confidence_from_sample(total),
                    'defense_text_fr': (
                        f"Les {jours_noms[dow]}s au lieu {lieu} montrent {val:,} constats, "
                        f"soit {pct_above:.0f}% au-dessus de la moyenne journalière ({mean_dow:.0f}). "
                        f"Z-score={z:.1f}. Argument: application sélective, "
                        f"blitz ciblé sur un jour spécifique."
                    ),
                    'legal_reference': 'Charte canadienne, art. 15 — égalité de traitement',
                    'sample_size': total,
                    'computation_details': {
                        'jour': jours_noms[dow],
                        'dow': dow,
                        'distribution': {jours_noms[d]: counts[d] for d in range(7)},
                        'mean_per_day': round(mean_dow, 1),
                        'std_per_day': round(std_dow, 1),
                    }
                })

    log(f"  → {len(anomalies)} patterns jour sur {len(lieu_data)} lieux", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  F. ARTICLE SURREPRÉSENTÉ PAR LIEU
# ══════════════════════════════════════════════════════════════
def detect_article_surrepresente(cur, dry_run=False):
    """Détecte les articles localement surreprésentés vs la proportion provinciale."""
    log("Détection: article_surrepresente", "STEP")

    # Proportions provinciales
    cur.execute("""
        SELECT article, COUNT(*) AS nb
        FROM qc_constats_infraction
        WHERE article IS NOT NULL AND article != ''
        GROUP BY article
    """)
    prov_data = {r[0]: r[1] for r in cur.fetchall()}
    total_prov = sum(prov_data.values())
    if total_prov == 0:
        log("Aucun constat avec article", "WARN")
        return []

    prov_pct = {art: nb / total_prov for art, nb in prov_data.items()}

    # Proportions locales
    cur.execute("""
        SELECT lieu_infraction, article, COUNT(*) AS nb
        FROM qc_constats_infraction
        WHERE article IS NOT NULL AND article != ''
            AND lieu_infraction IS NOT NULL AND lieu_infraction != ''
        GROUP BY lieu_infraction, article
        HAVING COUNT(*) >= %s
    """, (SEUILS['article_min_constats'],))

    # Totaux par lieu
    lieu_totals = {}
    lieu_articles = {}
    for lieu, article, nb in cur.fetchall():
        if lieu not in lieu_totals:
            lieu_totals[lieu] = 0
            lieu_articles[lieu] = {}
        lieu_totals[lieu] += nb
        lieu_articles[lieu][article] = nb

    anomalies = []
    for lieu, articles in lieu_articles.items():
        total_lieu = lieu_totals[lieu]
        for article, nb in articles.items():
            local_pct = nb / total_lieu if total_lieu > 0 else 0
            global_pct = prov_pct.get(article, 0)

            if global_pct <= 0:
                continue

            ratio = local_pct / global_pct
            if ratio >= SEUILS['article_ratio'] and nb >= SEUILS['article_min_constats']:
                anomalies.append({
                    'anomaly_type': 'article_surrepresente',
                    'region': lieu,
                    'article': article,
                    'observed_value': round(local_pct * 100, 1),
                    'expected_value': round(global_pct * 100, 1),
                    'deviation_pct': round((ratio - 1) * 100, 1),
                    'z_score': round(ratio, 2),  # ratio comme proxy de z-score
                    'severity': 'high' if ratio >= 4 else ('medium' if ratio >= 3 else 'low'),
                    'confidence_level': confidence_from_sample(nb),
                    'defense_text_fr': (
                        f"L'article {article} représente {local_pct * 100:.1f}% des constats "
                        f"au lieu {lieu}, vs {global_pct * 100:.1f}% au provincial ({ratio:.1f}x). "
                        f"Sur {nb:,} constats locaux. Argument: piège systématique, "
                        f"ciblage d'une infraction spécifique pour revenus."
                    ),
                    'legal_reference': 'Charte canadienne, art. 7 — justice fondamentale',
                    'sample_size': nb,
                    'computation_details': {
                        'local_pct': round(local_pct * 100, 2),
                        'provincial_pct': round(global_pct * 100, 2),
                        'ratio': round(ratio, 2),
                        'nb_local': nb,
                        'total_lieu': total_lieu,
                        'nb_provincial': prov_data.get(article, 0),
                    }
                })

    log(f"  → {len(anomalies)} articles surreprésentés", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  G. ANOMALIE SAISONNIÈRE
# ══════════════════════════════════════════════════════════════
def detect_anomalie_saisonniere(cur, dry_run=False):
    """Détecte les trimestres anormaux vs la moyenne historique par lieu."""
    log("Détection: anomalie_saisonniere", "STEP")

    cur.execute("""
        SELECT
            lieu_infraction,
            EXTRACT(YEAR FROM date_infraction)::int AS annee,
            EXTRACT(QUARTER FROM date_infraction)::int AS trimestre,
            COUNT(*) AS nb
        FROM qc_constats_infraction
        WHERE date_infraction IS NOT NULL
            AND lieu_infraction IS NOT NULL
            AND lieu_infraction != ''
        GROUP BY lieu_infraction, annee, trimestre
        ORDER BY lieu_infraction, annee, trimestre
    """)

    # Organiser: lieu -> {trimestre -> [nb par année]}
    lieu_saisons = {}
    for lieu, annee, trim, nb in cur.fetchall():
        if lieu not in lieu_saisons:
            lieu_saisons[lieu] = {'years': set(), 'quarters': {}}
        lieu_saisons[lieu]['years'].add(annee)
        q_key = trim
        if q_key not in lieu_saisons[lieu]['quarters']:
            lieu_saisons[lieu]['quarters'][q_key] = []
        lieu_saisons[lieu]['quarters'][q_key].append((annee, nb))

    trim_noms = {1: 'Q1 (jan-mar)', 2: 'Q2 (avr-jun)', 3: 'Q3 (jul-sep)', 4: 'Q4 (oct-dec)'}
    anomalies = []

    for lieu, data in lieu_saisons.items():
        if len(data['years']) < SEUILS['saison_min_annees']:
            continue

        for q, entries in data['quarters'].items():
            if len(entries) < SEUILS['saison_min_annees']:
                continue

            values = [e[1] for e in entries]
            mean_q = sum(values) / len(values)
            std_q = math.sqrt(sum((v - mean_q) ** 2 for v in values) / len(values)) if len(values) > 1 else 0

            # Vérifier chaque année-trimestre
            for annee, nb in entries:
                z = z_score(nb, mean_q, std_q)
                if z >= SEUILS['saison_z_score']:
                    pct_above = round((nb - mean_q) / mean_q * 100, 1) if mean_q > 0 else 0
                    anomalies.append({
                        'anomaly_type': 'anomalie_saisonniere',
                        'region': lieu,
                        'article': None,
                        'observed_value': float(nb),
                        'expected_value': round(mean_q, 1),
                        'deviation_pct': pct_above,
                        'z_score': z,
                        'severity': severity_from_z(z),
                        'confidence_level': confidence_from_sample(nb, min_for_high=300),
                        'defense_text_fr': (
                            f"Le volume au {trim_noms[q]} {annee} au lieu {lieu} est de {nb:,} constats, "
                            f"soit {pct_above:.0f}% au-dessus de la moyenne saisonnière ({mean_q:.0f}). "
                            f"Z-score={z:.1f} sur {len(entries)} années. "
                            f"Argument: blitz ciblé, intensification non justifiée."
                        ),
                        'legal_reference': 'Charte canadienne, art. 7 — proportionnalité',
                        'sample_size': nb,
                        'period_start': date(annee, (q - 1) * 3 + 1, 1),
                        'period_end': date(annee, q * 3, 28),
                        'computation_details': {
                            'trimestre': q,
                            'annee': annee,
                            'historique': {str(e[0]): e[1] for e in entries},
                            'nb_annees': len(entries),
                            'mean': round(mean_q, 1),
                            'std': round(std_q, 1),
                        }
                    })

    log(f"  → {len(anomalies)} anomalies saisonnières sur {len(lieu_saisons)} lieux", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  H. TAUX D'ACQUITTEMENT ANORMAL
# ══════════════════════════════════════════════════════════════
def detect_taux_acquittement(cur, dry_run=False):
    """Identifie les articles avec un taux d'acquittement supérieur à la moyenne."""
    log("Détection: taux_acquittement", "STEP")

    # Calculer le taux par article (via jurisprudence)
    cur.execute("""
        SELECT
            UNNEST(lois_pertinentes) AS article_loi,
            COUNT(*) AS total,
            SUM(CASE WHEN resultat IN ('acquitte', 'rejete') THEN 1 ELSE 0 END) AS nb_acquitte
        FROM jurisprudence
        WHERE est_ticket_related = TRUE
            AND resultat IS NOT NULL
            AND lois_pertinentes IS NOT NULL
        GROUP BY article_loi
        HAVING COUNT(*) >= %s
    """, (SEUILS['acquit_min_decisions'],))

    rows = cur.fetchall()
    if not rows:
        # Fallback: utiliser resultat directement sans unnest
        cur.execute("""
            SELECT
                'global' AS article_loi,
                COUNT(*) AS total,
                SUM(CASE WHEN resultat IN ('acquitte', 'rejete') THEN 1 ELSE 0 END) AS nb_acquitte
            FROM jurisprudence
            WHERE est_ticket_related = TRUE AND resultat IS NOT NULL
        """)
        rows = cur.fetchall()

    if not rows:
        log("Aucune donnée jurisprudence suffisante", "WARN")
        return []

    # Taux global moyen
    total_all = sum(r[1] for r in rows)
    acquit_all = sum(r[2] for r in rows)
    global_rate = acquit_all / total_all if total_all > 0 else 0

    anomalies = []
    for art, total, nb_acquit in rows:
        if not art or art == 'global':
            continue
        rate = nb_acquit / total if total > 0 else 0
        ratio = rate / global_rate if global_rate > 0 else 0

        if ratio >= SEUILS['acquit_ratio'] and total >= SEUILS['acquit_min_decisions']:
            anomalies.append({
                'anomaly_type': 'taux_acquittement',
                'region': None,
                'article': str(art)[:50],
                'observed_value': round(rate * 100, 1),
                'expected_value': round(global_rate * 100, 1),
                'deviation_pct': round((rate - global_rate) / global_rate * 100, 1) if global_rate > 0 else 0,
                'z_score': round(ratio, 2),
                'severity': 'high' if ratio >= 2.5 else ('medium' if ratio >= 2.0 else 'low'),
                'confidence_level': confidence_from_sample(total, min_for_high=20, min_for_medium=10),
                'defense_text_fr': (
                    f"L'article/loi « {art[:80]} » a un taux d'acquittement de {rate * 100:.0f}% "
                    f"({nb_acquit}/{total} décisions), soit {ratio:.1f}x la moyenne globale "
                    f"({global_rate * 100:.0f}%). Chances de succès supérieures à la moyenne."
                ),
                'legal_reference': f'Jurisprudence: {total} décisions analysées',
                'sample_size': total,
                'computation_details': {
                    'nb_acquitte': nb_acquit,
                    'total_decisions': total,
                    'rate': round(rate, 4),
                    'global_rate': round(global_rate, 4),
                    'ratio_vs_global': round(ratio, 2),
                }
            })

    # Aussi analyser par catégorie d'infraction (via résumé)
    cur.execute("""
        SELECT categorie, total, nb_acquitte FROM (
            SELECT
                CASE
                    WHEN resume ILIKE '%%excès de vitesse%%' OR resume ILIKE '%%excess%%speed%%' THEN 'exces_vitesse'
                    WHEN resume ILIKE '%%cellulaire%%' OR resume ILIKE '%%téléphone%%' THEN 'cellulaire'
                    WHEN resume ILIKE '%%feu rouge%%' OR resume ILIKE '%%arrêt%%' THEN 'feu_arret'
                    WHEN resume ILIKE '%%alcool%%' OR resume ILIKE '%%facultés%%' THEN 'alcool'
                    WHEN resume ILIKE '%%ceinture%%' THEN 'ceinture'
                    WHEN resume ILIKE '%%stationnement%%' THEN 'stationnement'
                    ELSE NULL
                END AS categorie,
                COUNT(*) AS total,
                SUM(CASE WHEN resultat IN ('acquitte', 'rejete') THEN 1 ELSE 0 END) AS nb_acquitte
            FROM jurisprudence
            WHERE est_ticket_related = TRUE AND resultat IS NOT NULL
            GROUP BY 1
        ) sub
        WHERE categorie IS NOT NULL AND total >= %s
    """, (SEUILS['acquit_min_decisions'],))

    for cat, total, nb_acquit in cur.fetchall():
        rate = nb_acquit / total if total > 0 else 0
        ratio = rate / global_rate if global_rate > 0 else 0
        if ratio >= SEUILS['acquit_ratio']:
            anomalies.append({
                'anomaly_type': 'taux_acquittement',
                'region': None,
                'article': cat,
                'observed_value': round(rate * 100, 1),
                'expected_value': round(global_rate * 100, 1),
                'deviation_pct': round((rate - global_rate) / global_rate * 100, 1) if global_rate > 0 else 0,
                'z_score': round(ratio, 2),
                'severity': 'high' if ratio >= 2.5 else ('medium' if ratio >= 2.0 else 'low'),
                'confidence_level': confidence_from_sample(total, min_for_high=20, min_for_medium=10),
                'defense_text_fr': (
                    f"Les infractions de type « {cat} » ont un taux d'acquittement de "
                    f"{rate * 100:.0f}% ({nb_acquit}/{total} décisions), "
                    f"soit {ratio:.1f}x la moyenne ({global_rate * 100:.0f}%)."
                ),
                'legal_reference': f'Jurisprudence: {total} décisions catégorie {cat}',
                'sample_size': total,
                'computation_details': {
                    'categorie': cat,
                    'nb_acquitte': nb_acquit,
                    'total_decisions': total,
                    'rate': round(rate, 4),
                    'global_rate': round(global_rate, 4),
                }
            })

    log(f"  → {len(anomalies)} articles avec taux acquittement anormal (taux global: {global_rate * 100:.1f}%)", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  I. VÉHICULE LOURD ANOMAL
# ══════════════════════════════════════════════════════════════
def detect_vehicule_lourd(cur, dry_run=False):
    """Lieux où les véhicules lourds sont surreprésentés dans les constats."""
    log("Détection: vehicule_lourd_anomal", "STEP")

    cur.execute("""
        WITH stats AS (
            SELECT
                lieu_infraction,
                COUNT(*) AS total,
                SUM(CASE WHEN categorie_vehicule ILIKE '%%lourd%%'
                         OR categorie_vehicule ILIKE '%%camion%%'
                         OR categorie_vehicule ILIKE '%%commercial%%'
                    THEN 1 ELSE 0 END) AS nb_lourds
            FROM qc_constats_infraction
            WHERE lieu_infraction IS NOT NULL AND lieu_infraction != ''
                AND categorie_vehicule IS NOT NULL
            GROUP BY lieu_infraction
            HAVING COUNT(*) >= 100
        )
        SELECT lieu_infraction, total, nb_lourds,
               ROUND(nb_lourds::numeric / total * 100, 1) AS pct_lourds
        FROM stats
        WHERE nb_lourds >= 10
        ORDER BY pct_lourds DESC
    """)

    rows = cur.fetchall()
    if not rows:
        log("Pas assez de données véhicules lourds", "WARN")
        return []

    pcts = [float(r[3]) for r in rows]
    mean_pct = sum(pcts) / len(pcts) if pcts else 0
    std_pct = math.sqrt(sum((p - mean_pct) ** 2 for p in pcts) / len(pcts)) if len(pcts) > 1 else 0

    anomalies = []
    for lieu, total, nb_lourds, pct in rows:
        z = z_score(float(pct), mean_pct, std_pct)
        if z >= 2.0:
            anomalies.append({
                'anomaly_type': 'vehicule_lourd_anomal',
                'region': lieu, 'article': None,
                'observed_value': float(pct),
                'expected_value': round(mean_pct, 1),
                'deviation_pct': round(float(pct) - mean_pct, 1),
                'z_score': z,
                'severity': severity_from_z(z),
                'confidence_level': confidence_from_sample(total),
                'defense_text_fr': (
                    f"{pct}% des constats au lieu {lieu} visent des véhicules lourds "
                    f"({nb_lourds}/{total}), vs {mean_pct:.1f}% en moyenne provinciale. "
                    f"Z-score={z:.1f}. Argument: ciblage disproportionné des transporteurs, "
                    f"vérifier si la route est un corridor de transport légitime."
                ),
                'legal_reference': 'CSR art. 519 — contrôle routier véhicules lourds',
                'sample_size': total,
                'computation_details': {
                    'nb_lourds': nb_lourds, 'total': total,
                    'mean_pct': round(mean_pct, 1), 'std_pct': round(std_pct, 2),
                }
            })

    log(f"  → {len(anomalies)} anomalies véhicules lourds", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  J. INTERVENTION ANOMALE
# ══════════════════════════════════════════════════════════════
def detect_intervention_anomale(cur, dry_run=False):
    """Lieux avec un type d'intervention anormalement dominant."""
    log("Détection: intervention_anomale", "STEP")

    cur.execute("""
        SELECT lieu_infraction, type_intervention, COUNT(*) AS nb
        FROM qc_constats_infraction
        WHERE lieu_infraction IS NOT NULL AND lieu_infraction != ''
            AND type_intervention IS NOT NULL AND type_intervention != ''
        GROUP BY lieu_infraction, type_intervention
    """)

    # Organiser par lieu
    lieu_data = {}
    for lieu, interv, nb in cur.fetchall():
        if lieu not in lieu_data:
            lieu_data[lieu] = {}
        lieu_data[lieu][interv] = nb

    # Proportions globales
    global_totals = {}
    for lieu, intervs in lieu_data.items():
        for interv, nb in intervs.items():
            global_totals[interv] = global_totals.get(interv, 0) + nb
    total_global = sum(global_totals.values())
    global_pcts = {i: n / total_global for i, n in global_totals.items()} if total_global > 0 else {}

    anomalies = []
    for lieu, intervs in lieu_data.items():
        total_lieu = sum(intervs.values())
        if total_lieu < 200:
            continue
        for interv, nb in intervs.items():
            local_pct = nb / total_lieu
            global_pct = global_pcts.get(interv, 0)
            if global_pct <= 0:
                continue
            ratio = local_pct / global_pct
            if ratio >= 2.5 and nb >= 50:
                anomalies.append({
                    'anomaly_type': 'intervention_anomale',
                    'region': lieu, 'article': None,
                    'observed_value': round(local_pct * 100, 1),
                    'expected_value': round(global_pct * 100, 1),
                    'deviation_pct': round((ratio - 1) * 100, 1),
                    'z_score': round(ratio, 2),
                    'severity': 'high' if ratio >= 4 else ('medium' if ratio >= 3 else 'low'),
                    'confidence_level': confidence_from_sample(nb),
                    'defense_text_fr': (
                        f"Le type d'intervention « {interv} » représente {local_pct * 100:.1f}% "
                        f"au lieu {lieu} vs {global_pct * 100:.1f}% au provincial ({ratio:.1f}x). "
                        f"Sur {nb:,} constats. Argument: application ciblée d'un type d'intervention."
                    ),
                    'legal_reference': 'Charte canadienne, art. 7 — arbitraire',
                    'sample_size': nb,
                    'computation_details': {
                        'type_intervention': interv, 'nb': nb,
                        'local_pct': round(local_pct * 100, 2),
                        'global_pct': round(global_pct * 100, 2),
                        'ratio': round(ratio, 2), 'total_lieu': total_lieu,
                    }
                })

    log(f"  → {len(anomalies)} interventions anomales", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  K. CONCENTRATION D'ARTICLES (faible diversité)
# ══════════════════════════════════════════════════════════════
def detect_concentration_articles(cur, dry_run=False):
    """Lieux où un seul article domine > 70% des constats = ciblage systématique."""
    log("Détection: concentration_articles", "STEP")

    cur.execute("""
        WITH stats AS (
            SELECT
                lieu_infraction,
                article,
                COUNT(*) AS nb,
                SUM(COUNT(*)) OVER (PARTITION BY lieu_infraction) AS total_lieu
            FROM qc_constats_infraction
            WHERE lieu_infraction IS NOT NULL AND lieu_infraction != ''
                AND article IS NOT NULL AND article != ''
            GROUP BY lieu_infraction, article
        )
        SELECT lieu_infraction, article, nb, total_lieu,
               ROUND(nb::numeric / total_lieu * 100, 1) AS dominance_pct
        FROM stats
        WHERE total_lieu >= 200
            AND nb::numeric / total_lieu >= 0.70
        ORDER BY dominance_pct DESC
    """)

    rows = cur.fetchall()
    anomalies = []
    for lieu, article, nb, total, pct in rows:
        severity = 'high' if float(pct) >= 85 else ('medium' if float(pct) >= 75 else 'low')
        anomalies.append({
            'anomaly_type': 'concentration_articles',
            'region': lieu, 'article': article,
            'observed_value': float(pct),
            'expected_value': 30.0,  # normal: top article ~30% max
            'deviation_pct': float(pct) - 30.0,
            'z_score': round(float(pct) / 30.0, 2),
            'severity': severity,
            'confidence_level': confidence_from_sample(total),
            'defense_text_fr': (
                f"L'article {article} représente {pct}% de TOUS les constats au lieu {lieu} "
                f"({nb:,}/{total:,}). Cette concentration extrême suggère un ciblage systématique "
                f"d'une infraction spécifique pour maximiser les revenus. "
                f"Argument: application non uniforme du CSR, profilage d'infraction."
            ),
            'legal_reference': 'Charte canadienne, art. 7, 15 — application sélective du droit',
            'sample_size': total,
            'computation_details': {
                'article_dominant': article, 'nb_dominant': nb,
                'total_lieu': total, 'pct': float(pct),
            }
        })

    log(f"  → {len(anomalies)} concentrations d'articles", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  L. TENDANCE ANNUELLE (hausse brutale)
# ══════════════════════════════════════════════════════════════
def detect_tendance_annuelle(cur, dry_run=False):
    """Détecte les hausses brutales année sur année par municipalité."""
    log("Détection: tendance_annuelle", "STEP")

    cur.execute("""
        SELECT
            lieu_infraction,
            EXTRACT(YEAR FROM date_infraction)::int AS annee,
            COUNT(*) AS nb
        FROM qc_constats_infraction
        WHERE date_infraction IS NOT NULL
            AND lieu_infraction IS NOT NULL AND lieu_infraction != ''
        GROUP BY lieu_infraction, annee
        ORDER BY lieu_infraction, annee
    """)

    lieu_years = {}
    for lieu, annee, nb in cur.fetchall():
        if lieu not in lieu_years:
            lieu_years[lieu] = {}
        lieu_years[lieu][annee] = nb

    anomalies = []
    for lieu, years in lieu_years.items():
        sorted_years = sorted(years.keys())
        if len(sorted_years) < 2:
            continue

        for i in range(1, len(sorted_years)):
            prev_year = sorted_years[i - 1]
            curr_year = sorted_years[i]
            prev_nb = years[prev_year]
            curr_nb = years[curr_year]

            if prev_nb < 50:  # minimum pour comparaison
                continue

            pct_change = (curr_nb - prev_nb) / prev_nb * 100
            if pct_change >= 80:  # hausse de 80%+ = anomalie
                severity = 'high' if pct_change >= 150 else ('medium' if pct_change >= 100 else 'low')
                anomalies.append({
                    'anomaly_type': 'tendance_annuelle',
                    'region': lieu, 'article': None,
                    'observed_value': float(curr_nb),
                    'expected_value': float(prev_nb),
                    'deviation_pct': round(pct_change, 1),
                    'z_score': round(pct_change / 50, 2),  # proxy
                    'severity': severity,
                    'confidence_level': confidence_from_sample(curr_nb),
                    'defense_text_fr': (
                        f"Le lieu {lieu} montre une hausse de {pct_change:.0f}% des constats "
                        f"entre {prev_year} ({prev_nb:,}) et {curr_year} ({curr_nb:,}). "
                        f"Cette augmentation brutale suggère un changement de politique "
                        f"d'application ou un objectif de revenus accru."
                    ),
                    'legal_reference': 'Charte canadienne, art. 7 — proportionnalité',
                    'sample_size': curr_nb,
                    'period_start': date(curr_year, 1, 1),
                    'period_end': date(curr_year, 12, 31),
                    'computation_details': {
                        'prev_year': prev_year, 'prev_nb': prev_nb,
                        'curr_year': curr_year, 'curr_nb': curr_nb,
                        'pct_change': round(pct_change, 1),
                    }
                })

    log(f"  → {len(anomalies)} tendances annuelles anormales", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  M. HEURE DE POINTE ANOMALE
# ══════════════════════════════════════════════════════════════
def detect_heure_pointe(cur, dry_run=False):
    """Détecte les lieux avec une concentration anormale de constats à certaines heures."""
    log("Détection: heure_pointe_anomale", "STEP")

    cur.execute("""
        SELECT
            lieu_infraction,
            EXTRACT(HOUR FROM heure_infraction)::int AS heure,
            COUNT(*) AS nb
        FROM qc_constats_infraction
        WHERE heure_infraction IS NOT NULL
            AND lieu_infraction IS NOT NULL AND lieu_infraction != ''
        GROUP BY lieu_infraction, heure
    """)

    lieu_heures = {}
    for lieu, heure, nb in cur.fetchall():
        if lieu not in lieu_heures:
            lieu_heures[lieu] = {}
        lieu_heures[lieu][heure] = nb

    anomalies = []
    for lieu, heures in lieu_heures.items():
        total = sum(heures.values())
        if total < 200:
            continue

        counts = [heures.get(h, 0) for h in range(24)]
        mean_h = total / 24
        std_h = math.sqrt(sum((c - mean_h) ** 2 for c in counts) / 24) if total > 0 else 0

        for h in range(24):
            val = counts[h]
            z = z_score(val, mean_h, std_h)
            if z >= 2.5 and val >= 30:
                pct = round(val / total * 100, 1)
                anomalies.append({
                    'anomaly_type': 'heure_pointe_anomale',
                    'region': lieu, 'article': None,
                    'observed_value': float(val),
                    'expected_value': round(mean_h, 1),
                    'deviation_pct': round((val - mean_h) / mean_h * 100, 1) if mean_h > 0 else 0,
                    'z_score': z,
                    'severity': severity_from_z(z),
                    'confidence_level': confidence_from_sample(total),
                    'defense_text_fr': (
                        f"Le lieu {lieu} montre {val:,} constats à {h}h ({pct}% du total), "
                        f"soit {(val / mean_h - 1) * 100:.0f}% au-dessus de la moyenne horaire. "
                        f"Z-score={z:.1f}. Argument: embuscade ciblée à une heure précise, "
                        f"application sélective plutôt que prévention."
                    ),
                    'legal_reference': 'Charte canadienne, art. 9 — détention arbitraire',
                    'sample_size': total,
                    'computation_details': {
                        'heure': h, 'nb': val, 'pct': pct,
                        'mean_hourly': round(mean_h, 1),
                        'std_hourly': round(std_h, 1),
                        'distribution_top5': sorted(
                            [(hh, counts[hh]) for hh in range(24)],
                            key=lambda x: x[1], reverse=True
                        )[:5],
                    }
                })

    log(f"  → {len(anomalies)} anomalies heure de pointe", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  N. AMENDE DISPROPORTIONNÉE
# ══════════════════════════════════════════════════════════════
def detect_amende_disproportionnee(cur, dry_run=False):
    """Détecte les lieux où l'amende moyenne est significativement supérieure."""
    log("Détection: amende_disproportionnee", "STEP")

    cur.execute("""
        SELECT
            lieu_infraction,
            article,
            COUNT(*) AS nb,
            AVG(montant_amende) AS avg_amende
        FROM qc_constats_infraction
        WHERE montant_amende IS NOT NULL AND montant_amende > 0
            AND lieu_infraction IS NOT NULL AND lieu_infraction != ''
            AND article IS NOT NULL AND article != ''
        GROUP BY lieu_infraction, article
        HAVING COUNT(*) >= 20 AND AVG(montant_amende) > 0
    """)

    rows = cur.fetchall()
    if not rows:
        log("Pas de données d'amendes", "WARN")
        return []

    # Moyenne provinciale par article
    cur.execute("""
        SELECT article, AVG(montant_amende) AS avg_amende, STDDEV(montant_amende) AS std_amende
        FROM qc_constats_infraction
        WHERE montant_amende IS NOT NULL AND montant_amende > 0
            AND article IS NOT NULL AND article != ''
        GROUP BY article
        HAVING COUNT(*) >= 50
    """)
    prov_stats = {r[0]: (float(r[1]), float(r[2]) if r[2] else 0) for r in cur.fetchall()}

    anomalies = []
    for lieu, article, nb, avg_local in rows:
        if article not in prov_stats:
            continue
        avg_prov, std_prov = prov_stats[article]
        if avg_prov <= 0:
            continue
        z = z_score(float(avg_local), avg_prov, std_prov)
        ratio = float(avg_local) / avg_prov
        if ratio >= 1.5 and z >= 2.0:
            anomalies.append({
                'anomaly_type': 'amende_disproportionnee',
                'region': lieu, 'article': article,
                'observed_value': round(float(avg_local), 2),
                'expected_value': round(avg_prov, 2),
                'deviation_pct': round((ratio - 1) * 100, 1),
                'z_score': z,
                'severity': severity_from_z(z),
                'confidence_level': confidence_from_sample(nb),
                'defense_text_fr': (
                    f"L'amende moyenne pour l'article {article} au lieu {lieu} est de "
                    f"{float(avg_local):.0f}$, soit {ratio:.1f}x la moyenne provinciale "
                    f"({avg_prov:.0f}$). Z-score={z:.1f}. "
                    f"Argument: municipalité perçoit des amendes majorées, revenus disproportionnés."
                ),
                'legal_reference': 'CSR — amendes prévues par la loi, pas par la municipalité',
                'sample_size': nb,
                'computation_details': {
                    'avg_local': round(float(avg_local), 2),
                    'avg_provincial': round(avg_prov, 2),
                    'std_provincial': round(std_prov, 2),
                    'ratio': round(ratio, 2), 'nb': nb,
                }
            })

    log(f"  → {len(anomalies)} amendes disproportionnées", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  O. COLLISION VS APPLICATION (revenus vs sécurité)
# ══════════════════════════════════════════════════════════════
def detect_collision_vs_enforcement(cur, dry_run=False):
    """Compare constats vs collisions par municipalité — beaucoup de tickets mais peu d'accidents = revenus."""
    log("Détection: collision_vs_enforcement", "STEP")

    # Vérifier si table collisions existe
    cur.execute("""
        SELECT EXISTS(
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'qc_collisions_mtl'
        )
    """)
    if not cur.fetchone()[0]:
        log("  Table collisions non trouvée", "WARN")
        return []

    cur.execute("""
        WITH constats_par_lieu AS (
            SELECT lieu_infraction, COUNT(*) AS nb_constats
            FROM qc_constats_infraction
            WHERE lieu_infraction IS NOT NULL AND lieu_infraction != ''
            GROUP BY lieu_infraction
            HAVING COUNT(*) >= 100
        ),
        collisions_count AS (
            SELECT COUNT(*) AS nb_collisions FROM qc_collisions_mtl
        )
        SELECT c.lieu_infraction, c.nb_constats, col.nb_collisions
        FROM constats_par_lieu c, collisions_count col
        ORDER BY c.nb_constats DESC
        LIMIT 50
    """)

    rows = cur.fetchall()
    if not rows or not rows[0][2]:
        log("  Pas de données collisions exploitables par lieu", "WARN")
        return []

    # Ratio constats/collisions global pour benchmark
    anomalies = []
    # Note: collisions MTL sont agrégées, pas par municipalité code
    # On signale les lieux avec énormément de constats vs la moyenne comme "revenus-oriented"
    constats_list = [r[1] for r in rows]
    mean_c = sum(constats_list) / len(constats_list)
    std_c = math.sqrt(sum((c - mean_c) ** 2 for c in constats_list) / len(constats_list)) if len(constats_list) > 1 else 0

    for lieu, nb_constats, nb_collisions in rows:
        z = z_score(nb_constats, mean_c, std_c)
        if z >= 3.0:  # seuil élevé
            anomalies.append({
                'anomaly_type': 'collision_vs_enforcement',
                'region': lieu, 'article': None,
                'observed_value': float(nb_constats),
                'expected_value': round(mean_c, 1),
                'deviation_pct': round((nb_constats - mean_c) / mean_c * 100, 1) if mean_c > 0 else 0,
                'z_score': z,
                'severity': severity_from_z(z),
                'confidence_level': confidence_from_sample(nb_constats),
                'defense_text_fr': (
                    f"Le lieu {lieu} génère {nb_constats:,} constats, soit "
                    f"{nb_constats / mean_c:.1f}x la moyenne. Avec {nb_collisions:,} collisions "
                    f"totales dans la région, le ratio constats/sécurité est questionnable. "
                    f"Argument: application orientée revenus plutôt que sécurité routière."
                ),
                'legal_reference': 'Objectif du CSR: sécurité routière, pas revenus municipaux',
                'sample_size': nb_constats,
                'computation_details': {
                    'nb_constats': nb_constats,
                    'nb_collisions_region': nb_collisions,
                    'mean_constats': round(mean_c, 1),
                }
            })

    log(f"  → {len(anomalies)} anomalies collision vs enforcement", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  P. TOLÉRANCE RADAR (excès de 1-5 km/h)
# ══════════════════════════════════════════════════════════════
def detect_tolerance_radar(cur, dry_run=False):
    """Détecte les lieux qui verbalisent pour des excès très faibles (1-10 km/h)."""
    log("Détection: tolerance_radar", "STEP")

    cur.execute("""
        WITH vitesse AS (
            SELECT
                lieu_infraction,
                COUNT(*) AS total,
                SUM(CASE WHEN (vitesse_constatee - vitesse_permise) BETWEEN 1 AND 10 THEN 1 ELSE 0 END) AS nb_faible,
                SUM(CASE WHEN (vitesse_constatee - vitesse_permise) BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS nb_tres_faible
            FROM qc_constats_infraction
            WHERE vitesse_permise IS NOT NULL AND vitesse_constatee IS NOT NULL
                AND vitesse_constatee > vitesse_permise
                AND lieu_infraction IS NOT NULL AND lieu_infraction != ''
            GROUP BY lieu_infraction
            HAVING COUNT(*) >= 30
        )
        SELECT lieu_infraction, total, nb_faible, nb_tres_faible,
               ROUND(nb_faible::numeric / total * 100, 1) AS pct_faible,
               ROUND(nb_tres_faible::numeric / total * 100, 1) AS pct_tres_faible
        FROM vitesse
        WHERE nb_faible >= 5
        ORDER BY pct_faible DESC
    """)

    rows = cur.fetchall()
    if not rows:
        log("Pas de données excès faibles", "WARN")
        return []

    pcts = [float(r[4]) for r in rows]
    mean_pct = sum(pcts) / len(pcts) if pcts else 0
    std_pct = math.sqrt(sum((p - mean_pct) ** 2 for p in pcts) / len(pcts)) if len(pcts) > 1 else 0

    anomalies = []
    for lieu, total, nb_faible, nb_tres_faible, pct_faible, pct_tres_faible in rows:
        z = z_score(float(pct_faible), mean_pct, std_pct)
        if z >= 2.0:
            anomalies.append({
                'anomaly_type': 'tolerance_radar',
                'region': lieu, 'article': None,
                'observed_value': float(pct_faible),
                'expected_value': round(mean_pct, 1),
                'deviation_pct': round(float(pct_faible) - mean_pct, 1),
                'z_score': z,
                'severity': severity_from_z(z),
                'confidence_level': confidence_from_sample(total, min_for_high=100),
                'defense_text_fr': (
                    f"{pct_faible}% des constats de vitesse au lieu {lieu} sont pour des excès "
                    f"de 1-10 km/h ({nb_faible}/{total}), dont {nb_tres_faible} pour 1-5 km/h. "
                    f"Z-score={z:.1f}. Argument: la tolérance standard des appareils est ±5 km/h "
                    f"(art. 443 CSR). Ces constats sont dans la marge d'erreur instrumentale."
                ),
                'legal_reference': 'CSR art. 443 — tolérance appareils de mesure ±5 km/h',
                'sample_size': total,
                'computation_details': {
                    'nb_faible_1_10': nb_faible, 'nb_tres_faible_1_5': nb_tres_faible,
                    'total_vitesse': total, 'pct_faible': float(pct_faible),
                    'pct_tres_faible': float(pct_tres_faible),
                    'mean_pct': round(mean_pct, 1), 'std_pct': round(std_pct, 2),
                }
            })

    log(f"  → {len(anomalies)} anomalies tolérance radar", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  Q. POINTS D'INAPTITUDE ANORMAUX
# ══════════════════════════════════════════════════════════════
def detect_points_anormaux(cur, dry_run=False):
    """Détecte les lieux où les points d'inaptitude moyens sont anormalement élevés."""
    log("Détection: points_anormaux", "STEP")

    cur.execute("""
        SELECT
            lieu_infraction,
            COUNT(*) AS nb,
            AVG(points_inaptitude) AS avg_pts,
            SUM(CASE WHEN points_inaptitude >= 4 THEN 1 ELSE 0 END) AS nb_severe
        FROM qc_constats_infraction
        WHERE points_inaptitude IS NOT NULL AND points_inaptitude > 0
            AND lieu_infraction IS NOT NULL AND lieu_infraction != ''
        GROUP BY lieu_infraction
        HAVING COUNT(*) >= 20
    """)

    rows = cur.fetchall()
    if not rows:
        log("Pas de données points inaptitude", "WARN")
        return []

    avgs = [float(r[2]) for r in rows]
    mean_avg = sum(avgs) / len(avgs) if avgs else 0
    std_avg = math.sqrt(sum((a - mean_avg) ** 2 for a in avgs) / len(avgs)) if len(avgs) > 1 else 0

    anomalies = []
    for lieu, nb, avg_pts, nb_severe in rows:
        z = z_score(float(avg_pts), mean_avg, std_avg)
        if z >= 2.0:
            anomalies.append({
                'anomaly_type': 'points_anormaux',
                'region': lieu, 'article': None,
                'observed_value': round(float(avg_pts), 1),
                'expected_value': round(mean_avg, 1),
                'deviation_pct': round((float(avg_pts) - mean_avg) / mean_avg * 100, 1) if mean_avg > 0 else 0,
                'z_score': z,
                'severity': severity_from_z(z),
                'confidence_level': confidence_from_sample(nb),
                'defense_text_fr': (
                    f"Le lieu {lieu} donne en moyenne {float(avg_pts):.1f} points d'inaptitude par constat "
                    f"(vs {mean_avg:.1f} provincial), avec {nb_severe} constats à 4+ points. "
                    f"Z-score={z:.1f}. Argument: ciblage d'infractions sévères pour maximiser "
                    f"l'impact sur les permis, application disproportionnée."
                ),
                'legal_reference': 'SAAQ — seuils points inaptitude, proportionnalité',
                'sample_size': nb,
                'computation_details': {
                    'avg_points': round(float(avg_pts), 2),
                    'nb_severe': nb_severe, 'total': nb,
                    'mean_provincial': round(mean_avg, 2),
                    'std_provincial': round(std_avg, 2),
                }
            })

    log(f"  → {len(anomalies)} anomalies points inaptitude", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  R. SPIKE DÉBUT DE MOIS (objectifs mensuels)
# ══════════════════════════════════════════════════════════════
def detect_spike_debut_mois(cur, dry_run=False):
    """Comme spike_fin_mois mais pour jours 1-5 (objectifs mensuels, départ rapide)."""
    log("Détection: spike_debut_mois", "STEP")

    cur.execute("""
        WITH stats AS (
            SELECT
                lieu_infraction,
                COUNT(*) AS total,
                SUM(CASE WHEN EXTRACT(DAY FROM date_infraction) <= 5 THEN 1 ELSE 0 END) AS debut_mois,
                SUM(CASE WHEN EXTRACT(DAY FROM date_infraction) > 5 THEN 1 ELSE 0 END) AS reste_mois
            FROM qc_constats_infraction
            WHERE date_infraction IS NOT NULL
                AND lieu_infraction IS NOT NULL AND lieu_infraction != ''
            GROUP BY lieu_infraction
            HAVING COUNT(*) >= 500
        )
        SELECT lieu_infraction, total, debut_mois, reste_mois,
               ROUND((debut_mois::numeric / 5) / NULLIF(reste_mois::numeric / 26, 0) * 100, 1) AS ratio_pct
        FROM stats
        WHERE debut_mois > 0 AND reste_mois > 0
        ORDER BY ratio_pct DESC
    """)

    rows = cur.fetchall()
    if not rows:
        log("Aucune donnée suffisante", "WARN")
        return []

    ratios = [float(r[4]) for r in rows if r[4] is not None]
    mean_r = sum(ratios) / len(ratios) if ratios else 100
    std_r = math.sqrt(sum((r - mean_r) ** 2 for r in ratios) / len(ratios)) if len(ratios) > 1 else 0

    anomalies = []
    for lieu, total, debut, reste, ratio_pct in rows:
        if ratio_pct is None:
            continue
        z = z_score(float(ratio_pct), mean_r, std_r)
        if float(ratio_pct) >= 140 and z >= 2.0:
            anomalies.append({
                'anomaly_type': 'spike_debut_mois',
                'region': lieu, 'article': None,
                'observed_value': float(ratio_pct),
                'expected_value': 100.0,
                'deviation_pct': float(ratio_pct) - 100,
                'z_score': z,
                'severity': severity_from_z(z),
                'confidence_level': confidence_from_sample(total),
                'defense_text_fr': (
                    f"Le lieu {lieu} montre {ratio_pct}% plus de constats les jours 1-5 du mois "
                    f"(début de mois). Sur {total:,} constats, {debut:,} tombent en début de mois. "
                    f"Z-score={z:.1f}. Argument: objectifs mensuels, pression de performance."
                ),
                'legal_reference': 'Charte canadienne, art. 7 — application arbitraire',
                'sample_size': total,
                'computation_details': {
                    'debut_mois': debut, 'reste_mois': reste,
                    'daily_debut': round(debut / 5, 1),
                    'daily_reste': round(reste / 26, 1),
                }
            })

    log(f"  → {len(anomalies)} spikes début de mois", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  S. EXCÈS DE VITESSE PAR TRANCHE (distribution)
# ══════════════════════════════════════════════════════════════
def detect_exces_distribution(cur, dry_run=False):
    """Analyse la distribution des excès de vitesse par lieu — détecte les profils anormaux."""
    log("Détection: exces_distribution", "STEP")

    cur.execute("""
        SELECT
            lieu_infraction,
            COUNT(*) AS total,
            SUM(CASE WHEN (vitesse_constatee - vitesse_permise) BETWEEN 1 AND 10 THEN 1 ELSE 0 END) AS t_1_10,
            SUM(CASE WHEN (vitesse_constatee - vitesse_permise) BETWEEN 11 AND 20 THEN 1 ELSE 0 END) AS t_11_20,
            SUM(CASE WHEN (vitesse_constatee - vitesse_permise) BETWEEN 21 AND 30 THEN 1 ELSE 0 END) AS t_21_30,
            SUM(CASE WHEN (vitesse_constatee - vitesse_permise) BETWEEN 31 AND 45 THEN 1 ELSE 0 END) AS t_31_45,
            SUM(CASE WHEN (vitesse_constatee - vitesse_permise) > 45 THEN 1 ELSE 0 END) AS t_45_plus,
            AVG(vitesse_constatee - vitesse_permise) AS avg_exces
        FROM qc_constats_infraction
        WHERE vitesse_permise IS NOT NULL AND vitesse_constatee IS NOT NULL
            AND vitesse_constatee > vitesse_permise
            AND lieu_infraction IS NOT NULL AND lieu_infraction != ''
        GROUP BY lieu_infraction
        HAVING COUNT(*) >= 30
    """)

    rows = cur.fetchall()
    if not rows:
        log("Pas de données distribution vitesse", "WARN")
        return []

    # Calculer le profil moyen provincial
    prov_totals = [0, 0, 0, 0, 0]
    prov_count = 0
    for row in rows:
        prov_totals[0] += row[2]
        prov_totals[1] += row[3]
        prov_totals[2] += row[4]
        prov_totals[3] += row[5]
        prov_totals[4] += row[6]
        prov_count += row[1]

    prov_pcts = [t / prov_count * 100 for t in prov_totals] if prov_count > 0 else [20, 40, 25, 10, 5]
    tranches = ['1-10 km/h', '11-20 km/h', '21-30 km/h', '31-45 km/h', '45+ km/h']

    anomalies = []
    for row in rows:
        lieu, total = row[0], row[1]
        counts = [row[2], row[3], row[4], row[5], row[6]]
        local_pcts = [c / total * 100 for c in counts] if total > 0 else [0] * 5

        # Calculer la déviation maximale par tranche
        max_dev = 0
        max_tranche_idx = 0
        for i in range(5):
            if prov_pcts[i] > 0:
                dev = (local_pcts[i] - prov_pcts[i]) / prov_pcts[i] * 100
                if abs(dev) > abs(max_dev):
                    max_dev = dev
                    max_tranche_idx = i

        if abs(max_dev) >= 100 and total >= 50:  # déviation de 100%+
            severity = 'high' if abs(max_dev) >= 200 else ('medium' if abs(max_dev) >= 150 else 'low')
            tranche_name = tranches[max_tranche_idx]
            anomalies.append({
                'anomaly_type': 'exces_distribution',
                'region': lieu, 'article': None,
                'observed_value': round(local_pcts[max_tranche_idx], 1),
                'expected_value': round(prov_pcts[max_tranche_idx], 1),
                'deviation_pct': round(max_dev, 1),
                'z_score': round(abs(max_dev) / 50, 2),
                'severity': severity,
                'confidence_level': confidence_from_sample(total, min_for_high=100),
                'defense_text_fr': (
                    f"La tranche {tranche_name} représente {local_pcts[max_tranche_idx]:.1f}% "
                    f"des excès au lieu {lieu} vs {prov_pcts[max_tranche_idx]:.1f}% au provincial "
                    f"(déviation {max_dev:+.0f}%). Profil de vitesse atypique. "
                    f"Argument: configuration routière inadaptée à la limite affichée."
                ),
                'legal_reference': 'CSR art. 303 — limites de vitesse doivent refléter les conditions',
                'sample_size': total,
                'computation_details': {
                    'distribution_locale': {t: round(p, 1) for t, p in zip(tranches, local_pcts)},
                    'distribution_provinciale': {t: round(p, 1) for t, p in zip(tranches, prov_pcts)},
                    'max_deviation_tranche': tranche_name,
                    'max_deviation_pct': round(max_dev, 1),
                    'avg_exces': round(float(row[7]), 1) if row[7] else None,
                }
            })

    log(f"  → {len(anomalies)} distributions d'excès anormales", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  T. MULTI-INFRACTION PAR LIEU (ciblage multiple)
# ══════════════════════════════════════════════════════════════
def detect_multi_infraction(cur, dry_run=False):
    """Lieux avec un nombre anormalement élevé d'articles différents = piège multi-infractions."""
    log("Détection: multi_infraction", "STEP")

    cur.execute("""
        SELECT
            lieu_infraction,
            COUNT(*) AS total,
            COUNT(DISTINCT article) AS nb_articles
        FROM qc_constats_infraction
        WHERE lieu_infraction IS NOT NULL AND lieu_infraction != ''
            AND article IS NOT NULL AND article != ''
        GROUP BY lieu_infraction
        HAVING COUNT(*) >= 200 AND COUNT(DISTINCT article) >= 5
    """)

    rows = cur.fetchall()
    if not rows:
        log("Pas de données multi-infraction", "WARN")
        return []

    nb_arts = [r[2] for r in rows]
    mean_a = sum(nb_arts) / len(nb_arts)
    std_a = math.sqrt(sum((a - mean_a) ** 2 for a in nb_arts) / len(nb_arts)) if len(nb_arts) > 1 else 0

    anomalies = []
    for lieu, total, nb_art in rows:
        z = z_score(nb_art, mean_a, std_a)
        if z >= 2.5:
            anomalies.append({
                'anomaly_type': 'multi_infraction',
                'region': lieu, 'article': None,
                'observed_value': float(nb_art),
                'expected_value': round(mean_a, 1),
                'deviation_pct': round((nb_art - mean_a) / mean_a * 100, 1) if mean_a > 0 else 0,
                'z_score': z,
                'severity': severity_from_z(z),
                'confidence_level': confidence_from_sample(total),
                'defense_text_fr': (
                    f"Le lieu {lieu} applique {nb_art} articles différents du CSR "
                    f"(moyenne: {mean_a:.0f}), sur {total:,} constats. Z-score={z:.1f}. "
                    f"Argument: lieu de surveillance multi-infractions, piège à contraventions."
                ),
                'legal_reference': 'CSR — application proportionnelle requise',
                'sample_size': total,
                'computation_details': {
                    'nb_articles': nb_art, 'total': total,
                    'mean': round(mean_a, 1), 'std': round(std_a, 1),
                }
            })

    log(f"  → {len(anomalies)} multi-infractions", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  U. RÉCIDIVE MUNICIPALE (même lieu, même article, pire chaque année)
# ══════════════════════════════════════════════════════════════
def detect_recidive_municipale(cur, dry_run=False):
    """Lieux qui augmentent constamment les constats année après année = politique délibérée."""
    log("Détection: recidive_municipale", "STEP")

    cur.execute("""
        SELECT
            lieu_infraction,
            EXTRACT(YEAR FROM date_infraction)::int AS annee,
            COUNT(*) AS nb
        FROM qc_constats_infraction
        WHERE date_infraction IS NOT NULL
            AND lieu_infraction IS NOT NULL AND lieu_infraction != ''
        GROUP BY lieu_infraction, annee
        ORDER BY lieu_infraction, annee
    """)

    lieu_years = {}
    for lieu, annee, nb in cur.fetchall():
        if lieu not in lieu_years:
            lieu_years[lieu] = []
        lieu_years[lieu].append((annee, nb))

    anomalies = []
    for lieu, years in lieu_years.items():
        if len(years) < 3:
            continue

        # Vérifier 3+ années consécutives de hausse
        sorted_y = sorted(years, key=lambda x: x[0])
        consecutive_up = 0
        max_consecutive = 0
        first_year = None
        last_year = None

        for i in range(1, len(sorted_y)):
            if sorted_y[i][1] > sorted_y[i - 1][1] * 1.05:  # hausse > 5%
                if consecutive_up == 0:
                    first_year = sorted_y[i - 1]
                consecutive_up += 1
                last_year = sorted_y[i]
                max_consecutive = max(max_consecutive, consecutive_up)
            else:
                consecutive_up = 0

        if max_consecutive >= 3 and first_year and last_year:
            total_increase = (last_year[1] - first_year[1]) / first_year[1] * 100
            anomalies.append({
                'anomaly_type': 'recidive_municipale',
                'region': lieu, 'article': None,
                'observed_value': float(last_year[1]),
                'expected_value': float(first_year[1]),
                'deviation_pct': round(total_increase, 1),
                'z_score': round(max_consecutive * 1.5, 2),
                'severity': 'high' if max_consecutive >= 5 else ('medium' if max_consecutive >= 4 else 'low'),
                'confidence_level': confidence_from_sample(last_year[1]),
                'defense_text_fr': (
                    f"Le lieu {lieu} montre {max_consecutive} années consécutives de hausse des constats "
                    f"({first_year[0]}: {first_year[1]:,} → {last_year[0]}: {last_year[1]:,}, "
                    f"+{total_increase:.0f}%). Politique d'intensification délibérée. "
                    f"Argument: revenus municipaux en croissance planifiée."
                ),
                'legal_reference': 'Droit municipal — indépendance du pouvoir policier',
                'sample_size': last_year[1],
                'period_start': date(first_year[0], 1, 1),
                'period_end': date(last_year[0], 12, 31),
                'computation_details': {
                    'consecutive_years_up': max_consecutive,
                    'start': {'year': first_year[0], 'nb': first_year[1]},
                    'end': {'year': last_year[0], 'nb': last_year[1]},
                    'total_increase_pct': round(total_increase, 1),
                    'yearly_data': {str(y): n for y, n in sorted_y},
                }
            })

    log(f"  → {len(anomalies)} récidives municipales", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  V. WEEK-END vs SEMAINE RATIO
# ══════════════════════════════════════════════════════════════
def detect_weekend_ratio(cur, dry_run=False):
    """Lieux avec un ratio week-end/semaine anormal — certains ne verbalisent que la semaine."""
    log("Détection: weekend_ratio", "STEP")

    cur.execute("""
        SELECT
            lieu_infraction,
            COUNT(*) AS total,
            SUM(CASE WHEN EXTRACT(DOW FROM date_infraction) IN (0, 6) THEN 1 ELSE 0 END) AS nb_weekend,
            SUM(CASE WHEN EXTRACT(DOW FROM date_infraction) BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS nb_semaine
        FROM qc_constats_infraction
        WHERE date_infraction IS NOT NULL
            AND lieu_infraction IS NOT NULL AND lieu_infraction != ''
        GROUP BY lieu_infraction
        HAVING COUNT(*) >= 300
    """)

    rows = cur.fetchall()
    if not rows:
        return []

    # Ratio normal: 2/7 jours = ~28.6% week-end
    ratios = []
    for lieu, total, nb_we, nb_sem in rows:
        pct_we = nb_we / total * 100 if total > 0 else 0
        ratios.append((lieu, total, nb_we, nb_sem, pct_we))

    mean_pct = sum(r[4] for r in ratios) / len(ratios) if ratios else 28.6
    std_pct = math.sqrt(sum((r[4] - mean_pct) ** 2 for r in ratios) / len(ratios)) if len(ratios) > 1 else 0

    anomalies = []
    for lieu, total, nb_we, nb_sem, pct_we in ratios:
        z = z_score(pct_we, mean_pct, std_pct)
        # Anomalie si TRÈS PEU de constats le week-end (z négatif important)
        # OU si BEAUCOUP plus le week-end (ciblage touristes, bars)
        if abs(z) >= 2.5:
            if pct_we < mean_pct:
                defense = (
                    f"Au lieu {lieu}, seulement {pct_we:.1f}% des constats tombent le week-end "
                    f"(vs {mean_pct:.1f}% attendu). Sur {total:,} constats, {nb_we:,} le week-end. "
                    f"Z-score={z:.1f}. Argument: application concentrée en semaine = ciblage "
                    f"des travailleurs/navetteurs, pas de prévention le week-end."
                )
            else:
                defense = (
                    f"Au lieu {lieu}, {pct_we:.1f}% des constats tombent le week-end "
                    f"(vs {mean_pct:.1f}% attendu). Sur {total:,} constats, {nb_we:,} le week-end. "
                    f"Z-score={z:.1f}. Argument: ciblage des fins de semaine (bars, tourisme)."
                )

            anomalies.append({
                'anomaly_type': 'weekend_ratio',
                'region': lieu, 'article': None,
                'observed_value': round(pct_we, 1),
                'expected_value': round(mean_pct, 1),
                'deviation_pct': round(pct_we - mean_pct, 1),
                'z_score': z,
                'severity': severity_from_z(z),
                'confidence_level': confidence_from_sample(total),
                'defense_text_fr': defense,
                'legal_reference': 'Charte canadienne, art. 15 — égalité de traitement',
                'sample_size': total,
                'computation_details': {
                    'nb_weekend': nb_we, 'nb_semaine': nb_sem,
                    'pct_weekend': round(pct_we, 1),
                    'mean_pct': round(mean_pct, 1),
                    'std_pct': round(std_pct, 2),
                }
            })

    log(f"  → {len(anomalies)} anomalies ratio week-end", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  W. LOI APPLIQUÉE ANORMALE
# ══════════════════════════════════════════════════════════════
def detect_loi_anomale(cur, dry_run=False):
    """Lieux qui appliquent une loi (CSR, municipal, etc.) de façon disproportionnée."""
    log("Détection: loi_anomale", "STEP")

    cur.execute("""
        SELECT lieu_infraction, loi, COUNT(*) AS nb
        FROM qc_constats_infraction
        WHERE lieu_infraction IS NOT NULL AND lieu_infraction != ''
            AND loi IS NOT NULL AND loi != ''
        GROUP BY lieu_infraction, loi
    """)

    lieu_lois = {}
    for lieu, loi, nb in cur.fetchall():
        if lieu not in lieu_lois:
            lieu_lois[lieu] = {}
        lieu_lois[lieu][loi] = nb

    # Global proportions
    global_lois = {}
    for lieu, lois in lieu_lois.items():
        for loi, nb in lois.items():
            global_lois[loi] = global_lois.get(loi, 0) + nb
    total_global = sum(global_lois.values())
    global_pcts = {l: n / total_global for l, n in global_lois.items()} if total_global > 0 else {}

    anomalies = []
    for lieu, lois in lieu_lois.items():
        total_lieu = sum(lois.values())
        if total_lieu < 200:
            continue
        for loi, nb in lois.items():
            local_pct = nb / total_lieu
            global_pct = global_pcts.get(loi, 0)
            if global_pct <= 0 or nb < 30:
                continue
            ratio = local_pct / global_pct
            if ratio >= 3.0:
                anomalies.append({
                    'anomaly_type': 'loi_anomale',
                    'region': lieu, 'article': str(loi)[:50],
                    'observed_value': round(local_pct * 100, 1),
                    'expected_value': round(global_pct * 100, 1),
                    'deviation_pct': round((ratio - 1) * 100, 1),
                    'z_score': round(ratio, 2),
                    'severity': 'high' if ratio >= 5 else ('medium' if ratio >= 4 else 'low'),
                    'confidence_level': confidence_from_sample(nb),
                    'defense_text_fr': (
                        f"La loi « {loi[:60]} » représente {local_pct * 100:.1f}% au lieu {lieu} "
                        f"vs {global_pct * 100:.1f}% provincial ({ratio:.1f}x). "
                        f"Argument: application sélective d'une loi spécifique."
                    ),
                    'legal_reference': 'Charte, art. 7 — application uniforme du droit',
                    'sample_size': nb,
                    'computation_details': {
                        'loi': str(loi), 'nb': nb, 'ratio': round(ratio, 2),
                        'local_pct': round(local_pct * 100, 2),
                        'global_pct': round(global_pct * 100, 2),
                    }
                })

    log(f"  → {len(anomalies)} lois anomales", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  X. LOI DE BENFORD SUR LES VITESSES (manipulation données)
# ══════════════════════════════════════════════════════════════
def detect_vitesse_benford(cur, dry_run=False):
    """Applique la loi de Benford aux vitesses constatées — déviation = manipulation possible."""
    log("Détection: vitesse_benford", "STEP")

    cur.execute("""
        SELECT lieu_infraction, vitesse_constatee
        FROM qc_constats_infraction
        WHERE vitesse_constatee IS NOT NULL AND vitesse_constatee >= 10
            AND lieu_infraction IS NOT NULL AND lieu_infraction != ''
    """)

    rows = cur.fetchall()
    if len(rows) < 100:
        log("Pas assez de données vitesse pour Benford", "WARN")
        return []

    # Organiser par lieu
    lieu_speeds = {}
    for lieu, speed in rows:
        if lieu not in lieu_speeds:
            lieu_speeds[lieu] = []
        lieu_speeds[lieu].append(int(speed))

    # Distribution de Benford attendue pour le premier chiffre
    benford_expected = {
        1: 30.1, 2: 17.6, 3: 12.5, 4: 9.7, 5: 7.9,
        6: 6.7, 7: 5.8, 8: 5.1, 9: 4.6
    }

    anomalies = []
    for lieu, speeds in lieu_speeds.items():
        if len(speeds) < 50:
            continue

        # Premier chiffre de chaque vitesse
        first_digits = {}
        for s in speeds:
            fd = int(str(s)[0])
            first_digits[fd] = first_digits.get(fd, 0) + 1

        n = len(speeds)
        # Test chi-carré
        chi_sq = 0
        for d in range(1, 10):
            observed = first_digits.get(d, 0) / n * 100
            expected = benford_expected[d]
            chi_sq += (observed - expected) ** 2 / expected

        # chi_sq > 20.09 = p < 0.01 avec 8 degrés de liberté
        if chi_sq > 20.09:
            # Trouver le chiffre le plus déviant
            max_dev_digit = 0
            max_dev_val = 0
            for d in range(1, 10):
                obs = first_digits.get(d, 0) / n * 100
                dev = abs(obs - benford_expected[d])
                if dev > max_dev_val:
                    max_dev_val = dev
                    max_dev_digit = d

            # Vérifier aussi les terminaisons (0 et 5 = arrondissement)
            endings = {}
            for s in speeds:
                last = s % 10
                endings[last] = endings.get(last, 0) + 1
            pct_0_5 = (endings.get(0, 0) + endings.get(5, 0)) / n * 100

            severity = 'high' if chi_sq > 40 else ('medium' if chi_sq > 30 else 'low')
            anomalies.append({
                'anomaly_type': 'vitesse_benford',
                'region': lieu, 'article': None,
                'observed_value': round(chi_sq, 1),
                'expected_value': 15.5,  # seuil nominal chi2(8)
                'deviation_pct': round((chi_sq - 15.5) / 15.5 * 100, 1),
                'z_score': round(chi_sq / 10, 2),
                'severity': severity,
                'confidence_level': confidence_from_sample(n, min_for_high=200),
                'defense_text_fr': (
                    f"Les vitesses enregistrées au lieu {lieu} ({n:,} mesures) échouent le test "
                    f"de Benford (chi²={chi_sq:.1f}, p<0.01). Le chiffre {max_dev_digit} dévie de "
                    f"{max_dev_val:.1f}% vs l'attendu. {pct_0_5:.0f}% des vitesses se terminent par 0 ou 5 "
                    f"(attendu: 20%). Argument: biais d'arrondissement ou manipulation des lectures."
                ),
                'legal_reference': 'Loi de Benford — admise comme preuve (Nigrini 1996, cours fédérales US)',
                'sample_size': n,
                'computation_details': {
                    'chi_squared': round(chi_sq, 2),
                    'nb_mesures': n,
                    'pct_terminant_0_5': round(pct_0_5, 1),
                    'digit_max_deviation': max_dev_digit,
                    'digit_max_dev_pct': round(max_dev_val, 1),
                    'first_digit_distribution': {str(d): round(first_digits.get(d, 0) / n * 100, 1) for d in range(1, 10)},
                    'benford_expected': benford_expected,
                    'ending_distribution': {str(d): round(endings.get(d, 0) / n * 100, 1) for d in range(10)},
                }
            })

    log(f"  → {len(anomalies)} anomalies Benford vitesse", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  Y. BRACKETING VITESSE (clustering aux seuils d'amende)
# ══════════════════════════════════════════════════════════════
def detect_bracketing_vitesse(cur, dry_run=False):
    """Détecte le clustering de vitesse juste au-dessus des seuils d'amende (21, 31, 46 km/h)."""
    log("Détection: bracketing_vitesse", "STEP")

    # Seuils d'amende QC: 1-20 km/h, 21-30, 31-45, 46-60, 60+
    brackets = [21, 31, 46]  # juste au-dessus du bracket

    cur.execute("""
        SELECT
            lieu_infraction,
            (vitesse_constatee - vitesse_permise) AS exces
        FROM qc_constats_infraction
        WHERE vitesse_permise IS NOT NULL AND vitesse_constatee IS NOT NULL
            AND vitesse_constatee > vitesse_permise
            AND lieu_infraction IS NOT NULL AND lieu_infraction != ''
    """)

    lieu_exces = {}
    for lieu, exces in cur.fetchall():
        if lieu not in lieu_exces:
            lieu_exces[lieu] = []
        lieu_exces[lieu].append(int(exces))

    anomalies = []
    for lieu, exces_list in lieu_exces.items():
        if len(exces_list) < 30:
            continue

        n = len(exces_list)
        for bracket in brackets:
            # Compter les excès à exactement bracket et bracket+1 vs bracket-1 et bracket-2
            at_bracket = sum(1 for e in exces_list if e == bracket)
            at_bracket_plus1 = sum(1 for e in exces_list if e == bracket + 1)
            at_bracket_minus1 = sum(1 for e in exces_list if e == bracket - 1)
            at_bracket_minus2 = sum(1 for e in exces_list if e == bracket - 2)

            above = at_bracket + at_bracket_plus1
            below = at_bracket_minus1 + at_bracket_minus2

            if below == 0 or above < 3:
                continue

            ratio = above / below
            if ratio >= 3.0:  # 3x plus de tickets juste au-dessus vs juste en-dessous
                anomalies.append({
                    'anomaly_type': 'bracketing_vitesse',
                    'region': lieu, 'article': None,
                    'observed_value': float(above),
                    'expected_value': float(below),
                    'deviation_pct': round((ratio - 1) * 100, 1),
                    'z_score': round(ratio, 2),
                    'severity': 'high' if ratio >= 5 else ('medium' if ratio >= 4 else 'low'),
                    'confidence_level': confidence_from_sample(n, min_for_high=100),
                    'defense_text_fr': (
                        f"Au lieu {lieu}, {above} constats sont à {bracket}-{bracket + 1} km/h au-dessus vs "
                        f"seulement {below} à {bracket - 2}-{bracket - 1} km/h (ratio {ratio:.1f}x). "
                        f"Ce clustering juste au-dessus du seuil {bracket} km/h (passage au bracket d'amende "
                        f"supérieur) est statistiquement impossible sous une distribution naturelle. "
                        f"Argument: arrondissement systématique vers le haut."
                    ),
                    'legal_reference': 'CSR art. 443 — précision des appareils de mesure',
                    'sample_size': n,
                    'computation_details': {
                        'bracket_threshold': bracket,
                        'at_bracket': at_bracket,
                        'at_bracket_plus1': at_bracket_plus1,
                        'at_bracket_minus1': at_bracket_minus1,
                        'at_bracket_minus2': at_bracket_minus2,
                        'ratio': round(ratio, 2),
                    }
                })

    log(f"  → {len(anomalies)} anomalies bracketing vitesse", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  Z. BLITZ VACANCES (congés fériés + vacances scolaires)
# ══════════════════════════════════════════════════════════════
def detect_blitz_vacances(cur, dry_run=False):
    """Détecte les spikes d'émission de constats pendant les vacances/congés fériés."""
    log("Détection: blitz_vacances", "STEP")

    # Périodes de vacances/congés QC (approximatif, récurrent)
    # Semaine de relâche (fin fév - début mars), Vacances été (jul-août),
    # Long weekends: Pâques, Fête nationale, Fête du Canada, Action de grâces
    cur.execute("""
        WITH daily_stats AS (
            SELECT
                lieu_infraction,
                date_infraction,
                EXTRACT(MONTH FROM date_infraction)::int AS mois,
                EXTRACT(DOW FROM date_infraction)::int AS dow,
                COUNT(*) AS nb
            FROM qc_constats_infraction
            WHERE date_infraction IS NOT NULL
                AND lieu_infraction IS NOT NULL AND lieu_infraction != ''
            GROUP BY lieu_infraction, date_infraction, mois, dow
        ),
        lieu_avg AS (
            SELECT lieu_infraction, AVG(nb) AS avg_daily, STDDEV(nb) AS std_daily
            FROM daily_stats
            GROUP BY lieu_infraction
            HAVING COUNT(*) >= 30
        )
        SELECT
            d.lieu_infraction,
            d.mois,
            SUM(d.nb) AS total_mois,
            a.avg_daily,
            a.std_daily,
            COUNT(DISTINCT d.date_infraction) AS nb_jours
        FROM daily_stats d
        JOIN lieu_avg a ON a.lieu_infraction = d.lieu_infraction
        WHERE d.mois IN (7, 8, 12)  -- été + Noël = périodes vacances
        GROUP BY d.lieu_infraction, d.mois, a.avg_daily, a.std_daily
    """)

    rows = cur.fetchall()
    mois_noms = {7: 'Juillet (vacances été)', 8: 'Août (vacances été)', 12: 'Décembre (Noël)'}

    anomalies = []
    for lieu, mois, total_mois, avg_daily, std_daily, nb_jours in rows:
        if not avg_daily or not std_daily or float(avg_daily) == 0 or nb_jours == 0:
            continue

        avg_mois_daily = float(total_mois) / float(nb_jours)
        z = z_score(avg_mois_daily, float(avg_daily), float(std_daily))

        if z >= 2.5:
            pct_above = round((avg_mois_daily - float(avg_daily)) / float(avg_daily) * 100, 1)
            anomalies.append({
                'anomaly_type': 'blitz_vacances',
                'region': lieu, 'article': None,
                'observed_value': round(avg_mois_daily, 1),
                'expected_value': round(float(avg_daily), 1),
                'deviation_pct': pct_above,
                'z_score': z,
                'severity': severity_from_z(z),
                'confidence_level': confidence_from_sample(total_mois),
                'defense_text_fr': (
                    f"En {mois_noms.get(mois, f'mois {mois}')} au lieu {lieu}, la moyenne quotidienne "
                    f"est {avg_mois_daily:.1f} constats vs {float(avg_daily):.1f} habituellement "
                    f"(+{pct_above:.0f}%, z={z:.1f}). Argument: blitz ciblé pendant les vacances, "
                    f"ciblage des touristes et voyageurs."
                ),
                'legal_reference': 'Charte canadienne, art. 7 — application proportionnelle',
                'sample_size': total_mois,
                'computation_details': {
                    'mois': mois, 'mois_nom': mois_noms.get(mois, ''),
                    'total_mois': total_mois, 'nb_jours': nb_jours,
                    'avg_mois_daily': round(avg_mois_daily, 2),
                    'avg_annuel_daily': round(float(avg_daily), 2),
                    'std_annuel_daily': round(float(std_daily), 2),
                }
            })

    log(f"  → {len(anomalies)} blitz vacances", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  AA. ZONE SCOLAIRE HORS HEURES
# ══════════════════════════════════════════════════════════════
def detect_zone_scolaire(cur, dry_run=False):
    """Détecte les constats d'art. 329 (zone scolaire) émis hors heures/périodes scolaires."""
    log("Détection: zone_scolaire_hors_heures", "STEP")

    cur.execute("""
        SELECT
            lieu_infraction,
            date_infraction,
            heure_infraction,
            EXTRACT(MONTH FROM date_infraction)::int AS mois,
            EXTRACT(DOW FROM date_infraction)::int AS dow,
            EXTRACT(HOUR FROM heure_infraction)::int AS heure
        FROM qc_constats_infraction
        WHERE (article LIKE '329%%' OR description_infraction ILIKE '%%scolaire%%')
            AND lieu_infraction IS NOT NULL AND lieu_infraction != ''
            AND date_infraction IS NOT NULL
    """)

    rows = cur.fetchall()
    if not rows:
        log("  Pas de constats zone scolaire trouvés", "WARN")
        return []

    # Analyser: hors heures = juillet-août, week-end, avant 7h ou après 18h
    lieu_stats = {}
    for lieu, dt, ht, mois, dow, heure in rows:
        if lieu not in lieu_stats:
            lieu_stats[lieu] = {'total': 0, 'hors_heures': 0, 'details': []}
        lieu_stats[lieu]['total'] += 1

        is_hors = False
        raison = None
        if mois in (7, 8):
            is_hors = True
            raison = 'vacances été'
        elif dow in (0, 6):  # dim, sam
            is_hors = True
            raison = 'week-end'
        elif heure is not None and (heure < 7 or heure >= 18):
            is_hors = True
            raison = f'{heure}h (hors heures école)'

        if is_hors:
            lieu_stats[lieu]['hors_heures'] += 1
            if len(lieu_stats[lieu]['details']) < 5:
                lieu_stats[lieu]['details'].append(raison)

    anomalies = []
    for lieu, stats in lieu_stats.items():
        if stats['total'] < 5:
            continue
        pct_hors = stats['hors_heures'] / stats['total'] * 100
        if pct_hors >= 30 and stats['hors_heures'] >= 3:
            severity = 'high' if pct_hors >= 60 else ('medium' if pct_hors >= 40 else 'low')
            anomalies.append({
                'anomaly_type': 'zone_scolaire_hors_heures',
                'region': lieu, 'article': '329',
                'observed_value': round(pct_hors, 1),
                'expected_value': 10.0,  # on s'attend à ~10% hors heures max
                'deviation_pct': round(pct_hors - 10, 1),
                'z_score': round(pct_hors / 10, 2),
                'severity': severity,
                'confidence_level': confidence_from_sample(stats['total'], min_for_high=20),
                'defense_text_fr': (
                    f"{pct_hors:.0f}% des constats zone scolaire (art. 329) au lieu {lieu} "
                    f"sont émis hors heures scolaires ({stats['hors_heures']}/{stats['total']}). "
                    f"Motifs: {', '.join(set(stats['details'][:3]))}. "
                    f"Argument: l'objectif des amendes doublées est la sécurité des enfants — "
                    f"pas applicable quand aucun enfant n'est présent."
                ),
                'legal_reference': 'CSR art. 329 — zone scolaire, finalité sécurité enfants',
                'sample_size': stats['total'],
                'computation_details': {
                    'total_constats': stats['total'],
                    'nb_hors_heures': stats['hors_heures'],
                    'pct_hors_heures': round(pct_hors, 1),
                    'exemples_raisons': list(set(stats['details'])),
                }
            })

    log(f"  → {len(anomalies)} anomalies zone scolaire hors heures", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  AB. PROFILAGE — TEST VOILE DE NOIRCEUR
# ══════════════════════════════════════════════════════════════
def detect_profilage_veil(cur, dry_run=False):
    """Test 'veil of darkness': compare les interceptions de jour vs nuit.
    Si les arrêts en personne baissent significativement après le coucher du soleil
    (quand la race du conducteur est moins visible), c'est un indicateur de profilage."""
    log("Détection: profilage_veil_darkness", "STEP")

    cur.execute("""
        SELECT
            lieu_infraction,
            type_intervention,
            EXTRACT(HOUR FROM heure_infraction)::int AS heure,
            EXTRACT(MONTH FROM date_infraction)::int AS mois,
            COUNT(*) AS nb
        FROM qc_constats_infraction
        WHERE heure_infraction IS NOT NULL
            AND lieu_infraction IS NOT NULL AND lieu_infraction != ''
            AND type_intervention IS NOT NULL
        GROUP BY lieu_infraction, type_intervention, heure, mois
    """)

    # Organiser par lieu et intervention
    data = {}
    for lieu, interv, heure, mois, nb in cur.fetchall():
        if lieu not in data:
            data[lieu] = {}
        if interv not in data[lieu]:
            data[lieu][interv] = {'jour': 0, 'nuit': 0, 'total': 0,
                                  'crep_ete_jour': 0, 'crep_ete_nuit': 0,
                                  'crep_hiver_jour': 0, 'crep_hiver_nuit': 0}

        d = data[lieu][interv]
        d['total'] += nb

        # Approximation crépuscule: été (mai-sept) = 5h-21h jour / hiver (oct-avr) = 7h-17h jour
        if mois in (5, 6, 7, 8, 9):  # été
            if 5 <= heure <= 20:
                d['jour'] += nb
                # Crépuscule été: 19h-20h (test principal)
                if heure in (19, 20):
                    d['crep_ete_jour'] += nb
            else:
                d['nuit'] += nb
                if heure in (21, 22):
                    d['crep_ete_nuit'] += nb
        else:  # hiver
            if 7 <= heure <= 16:
                d['jour'] += nb
                if heure in (16, 17):
                    d['crep_hiver_jour'] += nb
            else:
                d['nuit'] += nb
                if heure in (17, 18):
                    d['crep_hiver_nuit'] += nb

    anomalies = []
    for lieu, intervs in data.items():
        for interv, stats in intervs.items():
            if stats['total'] < 100:
                continue
            if stats['jour'] == 0 or stats['nuit'] == 0:
                continue

            # Ratio jour/nuit
            total_heures_jour = 14  # approx
            total_heures_nuit = 10
            rate_jour = stats['jour'] / total_heures_jour
            rate_nuit = stats['nuit'] / total_heures_nuit

            if rate_nuit == 0:
                continue

            ratio = rate_jour / rate_nuit

            # Un ratio > 2 ou < 0.5 est significatif
            if ratio >= 2.0 and stats['total'] >= 200:
                pct_drop = round((1 - rate_nuit / rate_jour) * 100, 1) if rate_jour > 0 else 0
                anomalies.append({
                    'anomaly_type': 'profilage_veil_darkness',
                    'region': lieu, 'article': None,
                    'observed_value': round(ratio, 2),
                    'expected_value': 1.2,  # légère prédominance jour = normal
                    'deviation_pct': round((ratio - 1.2) / 1.2 * 100, 1),
                    'z_score': round(ratio, 2),
                    'severity': 'high' if ratio >= 3.0 else ('medium' if ratio >= 2.5 else 'low'),
                    'confidence_level': confidence_from_sample(stats['total']),
                    'defense_text_fr': (
                        f"Au lieu {lieu}, les {interv} montrent {pct_drop}% moins d'interceptions "
                        f"la nuit vs le jour (ratio jour/nuit: {ratio:.1f}x, ajusté par heures). "
                        f"Total: {stats['jour']:,} jour, {stats['nuit']:,} nuit sur {stats['total']:,}. "
                        f"Le test 'voile de noirceur' (Stanford/Nature 2020) montre que cette baisse "
                        f"nocturne est un indicateur de profilage visuel. Argument: biais de sélection "
                        f"basé sur l'apparence visible du conducteur."
                    ),
                    'legal_reference': (
                        'Charte canadienne art. 15 — égalité | '
                        'Pierson et al. 2020 Nature Human Behaviour | '
                        'Rapport Armony SPVM 2019'
                    ),
                    'sample_size': stats['total'],
                    'computation_details': {
                        'type_intervention': interv,
                        'nb_jour': stats['jour'], 'nb_nuit': stats['nuit'],
                        'rate_jour': round(rate_jour, 2),
                        'rate_nuit': round(rate_nuit, 2),
                        'ratio_jour_nuit': round(ratio, 2),
                        'pct_drop_nuit': pct_drop,
                    }
                })

    log(f"  → {len(anomalies)} indicateurs profilage (veil of darkness)", "OK")
    return anomalies


# ══════════════════════════════════════════════════════════════
#  RUNNER PRINCIPAL
# ══════════════════════════════════════════════════════════════

DETECTORS = {
    'spike': ('spike_fin_mois', detect_spike_fin_mois),
    'hotspot': ('hotspot_geo', detect_hotspot_geo),
    'radar': ('radar_disproportionne', detect_radar_disproportionne),
    'piege': ('piege_vitesse', detect_piege_vitesse),
    'jour': ('pattern_jour', detect_pattern_jour),
    'article': ('article_surrepresente', detect_article_surrepresente),
    'saison': ('anomalie_saisonniere', detect_anomalie_saisonniere),
    'acquit': ('taux_acquittement', detect_taux_acquittement),
    # ── Nouveaux détecteurs v2 ──
    'vehicule': ('vehicule_lourd_anomal', detect_vehicule_lourd),
    'interv': ('intervention_anomale', detect_intervention_anomale),
    'concentr': ('concentration_articles', detect_concentration_articles),
    'tendance': ('tendance_annuelle', detect_tendance_annuelle),
    'heure': ('heure_pointe_anomale', detect_heure_pointe),
    'amende': ('amende_disproportionnee', detect_amende_disproportionnee),
    'collision': ('collision_vs_enforcement', detect_collision_vs_enforcement),
    'tolerance': ('tolerance_radar', detect_tolerance_radar),
    'points': ('points_anormaux', detect_points_anormaux),
    'debut': ('spike_debut_mois', detect_spike_debut_mois),
    'distrib': ('exces_distribution', detect_exces_distribution),
    'multi': ('multi_infraction', detect_multi_infraction),
    'recidive': ('recidive_municipale', detect_recidive_municipale),
    'weekend': ('weekend_ratio', detect_weekend_ratio),
    'loi': ('loi_anomale', detect_loi_anomale),
    # ── Détecteurs v3 (recherche internet) ──
    'benford': ('vitesse_benford', detect_vitesse_benford),
    'bracket': ('bracketing_vitesse', detect_bracketing_vitesse),
    'blitz': ('blitz_vacances', detect_blitz_vacances),
    'scolaire': ('zone_scolaire_hors_heures', detect_zone_scolaire),
    'profil': ('profilage_veil_darkness', detect_profilage_veil),
}


def run_recensement(dry_run=False, only_type=None):
    """Exécute tous les détecteurs et insère les anomalies."""
    start = time.time()
    batch_id = str(uuid.uuid4())

    print("=" * 60)
    print(f"  RECENSEMENT DES STATS — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Batch: {batch_id}")
    print(f"  Mode: {'DRY-RUN' if dry_run else 'PRODUCTION'}")
    if only_type:
        print(f"  Détecteur: {only_type}")
    print("=" * 60)

    conn = get_db()
    cur = conn.cursor()

    # Logger le début du run
    if not dry_run:
        cur.execute("""
            INSERT INTO recensement_runs (batch_id, started_at, status)
            VALUES (%s, NOW(), 'running')
        """, (batch_id,))
        conn.commit()

    all_anomalies = []
    detectors_to_run = {}
    if only_type:
        if only_type in DETECTORS:
            detectors_to_run = {only_type: DETECTORS[only_type]}
        else:
            print(f"\n  ERREUR: détecteur '{only_type}' inconnu. Choix: {', '.join(DETECTORS.keys())}")
            conn.close()
            return
    else:
        detectors_to_run = DETECTORS

    for key, (name, func) in detectors_to_run.items():
        try:
            anomalies = func(cur, dry_run)
            all_anomalies.extend(anomalies)
        except Exception as e:
            log(f"ERREUR {name}: {e}", "FAIL")
            conn.rollback()

    # Résumé
    counts = {'high': 0, 'medium': 0, 'low': 0}
    for a in all_anomalies:
        counts[a.get('severity', 'low')] += 1

    print(f"\n{'=' * 60}")
    print(f"  TOTAL: {len(all_anomalies)} anomalies")
    print(f"  High: {counts['high']} | Medium: {counts['medium']} | Low: {counts['low']}")

    # Résumé par type
    type_counts = {}
    for a in all_anomalies:
        t = a['anomaly_type']
        type_counts[t] = type_counts.get(t, 0) + 1
    for t, c in sorted(type_counts.items()):
        print(f"    {t:30s} {c:>4}")

    if dry_run:
        print(f"\n  DRY-RUN — rien inséré en DB")
        # Afficher les top 5 par sévérité
        print(f"\n  TOP 10 ANOMALIES (par z-score):")
        sorted_anom = sorted(all_anomalies, key=lambda x: abs(x.get('z_score', 0)), reverse=True)
        for i, a in enumerate(sorted_anom[:10]):
            print(f"    {i + 1}. [{a['severity']:6s}] {a['anomaly_type']:25s} "
                  f"z={a['z_score']:5.1f} region={a.get('region', '-'):10s} "
                  f"art={a.get('article', '-')}")
        conn.close()
        return

    # Désactiver l'ancien batch
    cur.execute("UPDATE recensement_stats SET is_active = FALSE WHERE is_active = TRUE")
    old_deactivated = cur.rowcount
    if old_deactivated:
        log(f"Ancien batch: {old_deactivated} anomalies désactivées", "INFO")

    # Insérer les nouvelles anomalies
    inserted = 0
    for a in all_anomalies:
        cur.execute("""
            INSERT INTO recensement_stats (
                batch_id, anomaly_type, region, article,
                radar_site_id, radar_site_name,
                observed_value, expected_value, deviation_pct, z_score,
                confidence_level, severity, defense_text_fr, legal_reference,
                computation_details, period_start, period_end, sample_size,
                is_active
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                TRUE
            )
        """, (
            batch_id, a['anomaly_type'], a.get('region'), a.get('article'),
            a.get('radar_site_id'), a.get('radar_site_name'),
            a.get('observed_value'), a.get('expected_value'),
            a.get('deviation_pct'), a.get('z_score'),
            a.get('confidence_level', 'medium'), a.get('severity', 'low'),
            a['defense_text_fr'], a.get('legal_reference'),
            json.dumps(a.get('computation_details', {}), cls=DecimalEncoder),
            a.get('period_start'), a.get('period_end'),
            a.get('sample_size'),
        ))
        inserted += 1

    # Mettre à jour le run log
    duration = round(time.time() - start, 1)
    cur.execute("""
        UPDATE recensement_runs SET
            completed_at = NOW(),
            anomalies_computed = %s,
            anomalies_high = %s,
            anomalies_medium = %s,
            anomalies_low = %s,
            duration_seconds = %s,
            status = 'completed',
            details = %s
        WHERE batch_id = %s
    """, (
        len(all_anomalies),
        counts['high'], counts['medium'], counts['low'],
        duration,
        json.dumps(type_counts),
        batch_id,
    ))

    conn.commit()
    conn.close()

    print(f"\n  Inséré: {inserted} anomalies (batch {batch_id[:8]}...)")
    print(f"  Durée: {duration}s")
    print("=" * 60)


# ══════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Recensement des Stats — Détection anomalies')
    parser.add_argument('--dry-run', action='store_true', help='Affiche sans insérer en DB')
    parser.add_argument('--type', choices=list(DETECTORS.keys()),
                        help='Exécuter un seul détecteur')
    args = parser.parse_args()

    run_recensement(dry_run=args.dry_run, only_type=args.type)
