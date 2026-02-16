"""
Agent Recensement Stats — Match ticket vs anomalies pré-calculées
=================================================================
100% déterministe (SQL), zéro AI.
Cherche dans recensement_stats les anomalies qui correspondent au ticket du client:
  - Par lieu (code municipal)
  - Par article
  - Anomalies globales (acquittement)
Retourne les textes de défense pré-rédigés + contexte statistique.
"""

import time
from agents.base_agent import BaseAgent


class AgentRecensementStats(BaseAgent):

    def __init__(self):
        super().__init__("RecensementStats")

    def match_anomalies(self, ticket, classification=None):
        """
        Match le ticket du client contre les anomalies pré-calculées.
        Input: ticket dict (lieu, article, date, etc.)
        Output: {
            "nb_anomalies": int,
            "nb_high": int,
            "anomalies": [...],
            "defense_texts": [...],
            "contexte_social": str,
            "resume": str
        }
        """
        start = time.time()
        self.log("Matching ticket vs anomalies pré-calculées", "STEP")

        # Extraire les champs de matching du ticket
        lieu = self._extract_lieu(ticket)
        article = self._extract_article(ticket)

        conn = self.get_db()
        cur = conn.cursor()

        try:
            anomalies = []

            # 1. Match par lieu (code municipal)
            if lieu:
                cur.execute("""
                    SELECT id, anomaly_type, region, article, observed_value,
                           expected_value, deviation_pct, z_score, severity,
                           confidence_level, defense_text_fr, legal_reference,
                           computation_details, sample_size
                    FROM recensement_stats
                    WHERE is_active = TRUE AND region = %s
                    ORDER BY
                        CASE severity WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                        z_score DESC
                """, (lieu,))
                for row in cur.fetchall():
                    anomalies.append(self._row_to_dict(row))

            # 2. Match par article
            if article:
                cur.execute("""
                    SELECT id, anomaly_type, region, article, observed_value,
                           expected_value, deviation_pct, z_score, severity,
                           confidence_level, defense_text_fr, legal_reference,
                           computation_details, sample_size
                    FROM recensement_stats
                    WHERE is_active = TRUE AND article = %s
                        AND (region IS NULL OR region = %s)
                    ORDER BY
                        CASE severity WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                        z_score DESC
                """, (article, lieu or ''))
                for row in cur.fetchall():
                    a = self._row_to_dict(row)
                    # Éviter les doublons
                    if a['id'] not in [x['id'] for x in anomalies]:
                        anomalies.append(a)

            # 3. Anomalies globales (taux acquittement) sans filtre lieu
            if article:
                cur.execute("""
                    SELECT id, anomaly_type, region, article, observed_value,
                           expected_value, deviation_pct, z_score, severity,
                           confidence_level, defense_text_fr, legal_reference,
                           computation_details, sample_size
                    FROM recensement_stats
                    WHERE is_active = TRUE
                        AND anomaly_type = 'taux_acquittement'
                        AND region IS NULL
                    ORDER BY z_score DESC
                    LIMIT 5
                """)
                for row in cur.fetchall():
                    a = self._row_to_dict(row)
                    if a['id'] not in [x['id'] for x in anomalies]:
                        anomalies.append(a)

            # 4. Stats globales du recensement
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN severity = 'high' THEN 1 ELSE 0 END) AS high,
                    SUM(CASE WHEN severity = 'medium' THEN 1 ELSE 0 END) AS medium,
                    SUM(CASE WHEN severity = 'low' THEN 1 ELSE 0 END) AS low
                FROM recensement_stats
                WHERE is_active = TRUE
            """)
            global_stats = cur.fetchone()

        finally:
            conn.close()

        # Construire le résultat
        nb_high = sum(1 for a in anomalies if a['severity'] == 'high')
        nb_medium = sum(1 for a in anomalies if a['severity'] == 'medium')
        defense_texts = [a['defense_text_fr'] for a in anomalies if a['severity'] in ('high', 'medium')]

        # Générer le contexte social
        contexte = self._build_contexte_social(anomalies, lieu, article, global_stats)

        duration = round(time.time() - start, 3)
        self.log(f"  → {len(anomalies)} anomalies matchées ({nb_high} high, {nb_medium} medium) en {duration}s", "OK")

        result = {
            "nb_anomalies": len(anomalies),
            "nb_high": nb_high,
            "nb_medium": nb_medium,
            "anomalies": anomalies[:20],  # Limiter à 20 max
            "defense_texts": defense_texts[:10],
            "contexte_social": contexte,
            "resume": self._build_resume(anomalies, lieu, article),
            "stats_globales": {
                "total_anomalies_qc": global_stats[0] if global_stats else 0,
                "high": global_stats[1] if global_stats else 0,
                "medium": global_stats[2] if global_stats else 0,
                "low": global_stats[3] if global_stats else 0,
            },
            "duration": duration,
        }

        self.log_run(
            action="match_anomalies",
            input_summary=f"lieu={lieu} article={article}",
            output_summary=f"{len(anomalies)} anomalies, {nb_high} high",
            duration=duration
        )

        return result

    def _extract_lieu(self, ticket):
        """Extrait le code municipal du ticket."""
        # Le lieu peut être dans différents champs
        for field in ['code_municipal', 'lieu_infraction', 'lieu', 'municipalite', 'ville']:
            val = ticket.get(field)
            if val and str(val).strip():
                return str(val).strip()
        return None

    def _extract_article(self, ticket):
        """Extrait l'article de loi du ticket."""
        for field in ['article', 'article_csr', 'article_loi', 'numero_article']:
            val = ticket.get(field)
            if val and str(val).strip():
                return str(val).strip()
        return None

    def _row_to_dict(self, row):
        """Convertit une row SQL en dict."""
        return {
            'id': row[0],
            'anomaly_type': row[1],
            'region': row[2],
            'article': row[3],
            'observed_value': float(row[4]) if row[4] else None,
            'expected_value': float(row[5]) if row[5] else None,
            'deviation_pct': float(row[6]) if row[6] else None,
            'z_score': float(row[7]) if row[7] else None,
            'severity': row[8],
            'confidence_level': row[9],
            'defense_text_fr': row[10],
            'legal_reference': row[11],
            'computation_details': row[12],
            'sample_size': row[13],
        }

    def _build_contexte_social(self, anomalies, lieu, article, global_stats):
        """Construit le texte de contexte social pour le rapport."""
        if not anomalies:
            return "Aucune anomalie statistique détectée pour ce ticket."

        parts = []
        total_qc = global_stats[0] if global_stats else 0
        parts.append(f"Le système a détecté {total_qc:,} anomalies statistiques actives au Québec.")

        # Par type d'anomalie trouvée
        types_found = set(a['anomaly_type'] for a in anomalies)

        if 'spike_fin_mois' in types_found:
            spike = next(a for a in anomalies if a['anomaly_type'] == 'spike_fin_mois')
            parts.append(
                f"QUOTA POSSIBLE: Ce lieu montre un pic de {spike['deviation_pct']:.0f}% "
                f"en fin de mois — pattern suggérant des quotas policiers."
            )

        if 'hotspot_geo' in types_found:
            hot = next(a for a in anomalies if a['anomaly_type'] == 'hotspot_geo')
            parts.append(
                f"HOTSPOT: Ce lieu est dans le top {100 - (hot.get('computation_details', {}).get('percentile_rank', 95)):.0f}% "
                f"des plus verbalisés au QC ({hot['observed_value']:,.0f} constats)."
            )

        if 'article_surrepresente' in types_found:
            arts = [a for a in anomalies if a['anomaly_type'] == 'article_surrepresente']
            for a in arts[:3]:
                parts.append(
                    f"ARTICLE CIBLÉ: L'article {a['article']} est {a['z_score']:.1f}x "
                    f"plus fréquent ici vs la moyenne provinciale."
                )

        if 'anomalie_saisonniere' in types_found:
            sais = [a for a in anomalies if a['anomaly_type'] == 'anomalie_saisonniere']
            parts.append(
                f"BLITZ SAISONNIER: {len(sais)} trimestres anormaux détectés pour ce lieu."
            )

        if 'taux_acquittement' in types_found:
            acq = next(a for a in anomalies if a['anomaly_type'] == 'taux_acquittement')
            parts.append(
                f"CHANCES DE SUCCÈS: Taux d'acquittement de {acq['observed_value']:.0f}% "
                f"pour ce type d'infraction (moyenne: {acq['expected_value']:.0f}%)."
            )

        if 'piege_vitesse' in types_found:
            piege = next(a for a in anomalies if a['anomaly_type'] == 'piege_vitesse')
            parts.append(
                f"PIÈGE À VITESSE: {piege['observed_value']:.0f}% des tickets ici sont "
                f"pour des excès marginaux (11-15 km/h)."
            )

        return " ".join(parts)

    def _build_resume(self, anomalies, lieu, article):
        """Construit un résumé court pour affichage rapide."""
        if not anomalies:
            return "Aucune anomalie détectée pour ce ticket."

        nb = len(anomalies)
        high = sum(1 for a in anomalies if a['severity'] == 'high')
        types = set(a['anomaly_type'] for a in anomalies)

        resume = f"{nb} anomalie{'s' if nb > 1 else ''} statistique{'s' if nb > 1 else ''} détectée{'s' if nb > 1 else ''}"
        if high:
            resume += f" dont {high} critique{'s' if high > 1 else ''}"
        resume += f" ({', '.join(sorted(types))})"

        return resume
