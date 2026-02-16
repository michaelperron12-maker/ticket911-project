#!/usr/bin/env python3
"""
RECENSEMENT DES STATS — Détecteur d'anomalies statistiques
===========================================================
Cron: dimanche 5:30AM (après les imports de 2-3AM)
Usage:
    python3 recensement_stats_runner.py             # run complet
    python3 recensement_stats_runner.py --dry-run    # affiche sans insérer
    python3 recensement_stats_runner.py --type spike  # un seul détecteur

8 types d'anomalies détectées:
  A. spike_fin_mois     — Quotas policiers (jours 26-31 vs 1-25)
  B. hotspot_geo        — Lieux avec plus de constats que 95e percentile
  C. radar_disproportionne — Radar avec constats > 2x la moyenne
  D. piege_vitesse      — Lieux avec excès marginaux (11-15 km/h) surreprésentés
  E. pattern_jour       — Jour de semaine anormalement élevé par lieu
  F. article_surrepresente — Article local > 2x la proportion provinciale
  G. anomalie_saisonniere — Trimestre anormal vs historique
  H. taux_acquittement  — Articles avec taux acquittement > 1.5x la moyenne

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

import psycopg2
import psycopg2.extras

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
            json.dumps(a.get('computation_details', {})),
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
