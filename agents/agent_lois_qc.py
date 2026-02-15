"""
Agent QC: LOIS QUEBEC — Code de la securite routiere (CSR) + Code criminel
Recherche PostgreSQL tsvector specifique Quebec (articles CSR, C-24.2, reglements municipaux)
"""

import time
from agents.base_agent import BaseAgent


class AgentLoisQC(BaseAgent):

    def __init__(self):
        super().__init__("Lois_QC")

    def chercher_loi(self, ticket):
        """
        Input: ticket QC
        Output: articles CSR et reglements applicables au Quebec
        """
        self.log(f"Recherche lois QC/CSR: {ticket.get('infraction', '?')}", "STEP")
        start = time.time()
        resultats = []

        infraction = ticket.get("infraction", "")
        mots_cles = self._extraire_mots_cles_qc(infraction)

        try:
            conn = self.get_db()
            cur = conn.cursor()

            for query in mots_cles:
                try:
                    # Recherche tsvector PostgreSQL — lois_articles
                    tsquery = " | ".join(query.split())
                    cur.execute("""
                        SELECT id, province, article, titre_article,
                               texte_complet, loi, code_loi,
                               ts_rank(tsv, to_tsquery('french', %s)) AS rank
                        FROM lois_articles
                        WHERE province = 'QC'
                          AND tsv @@ to_tsquery('french', %s)
                        ORDER BY rank DESC
                        LIMIT 5
                    """, (tsquery, tsquery))
                    for row in cur.fetchall():
                        resultats.append({
                            "id": row[0], "juridiction": row[1],
                            "article": row[2],
                            "texte": (row[4] or row[3] or "")[:500],
                            "source": row[5] or row[6] or "CSR",
                            "recherche": query
                        })
                        self.log(f"  CSR art. {row[2]} trouve", "OK")
                except Exception:
                    pass

            # Aussi chercher dans lois federales (Code criminel si applicable)
            if any(w in infraction.lower() for w in ["alcool", "ivresse", "facultes", "capacites"]):
                try:
                    cur.execute("""
                        SELECT id, province, article, titre_article, texte_complet, loi
                        FROM lois_articles
                        WHERE province = 'CA'
                          AND tsv @@ to_tsquery('french', 'alcool | capacites | ivresse | conduite')
                        LIMIT 3
                    """)
                    for row in cur.fetchall():
                        resultats.append({
                            "id": row[0], "juridiction": "CA",
                            "article": row[2],
                            "texte": (row[4] or row[3] or "")[:500],
                            "source": row[5] or "Code criminel",
                            "recherche": "Code criminel"
                        })
                except Exception:
                    pass

            # Fallback: recherche directe si aucun resultat tsvector
            if not resultats:
                self.log("Pas de resultats tsvector — recherche directe", "WARN")
                cur.execute("""
                    SELECT id, province, article, titre_article, texte_complet, loi
                    FROM lois_articles
                    WHERE province = 'QC'
                    LIMIT 10
                """)
                for row in cur.fetchall():
                    resultats.append({
                        "id": row[0], "juridiction": row[1],
                        "article": row[2],
                        "texte": (row[4] or row[3] or "")[:500],
                        "source": row[5] or "CSR"
                    })

            conn.close()
        except Exception as e:
            self.log(f"Erreur recherche lois QC: {e}", "FAIL")

        # Deduplication
        seen = set()
        unique = []
        for r in resultats:
            key = f"{r['juridiction']}_{r['article']}"
            if key not in seen:
                seen.add(key)
                unique.append(r)

        duration = time.time() - start
        self.log_run("chercher_loi_qc", f"QC {infraction[:100]}", f"{len(unique)} articles CSR", duration=duration)
        self.log(f"{len(unique)} articles CSR trouves en {duration:.1f}s", "OK")
        return unique

    def _extraire_mots_cles_qc(self, infraction):
        """Mots-cles specifiques au Code de la securite routiere du Quebec"""
        queries = []
        lower = infraction.lower()

        if any(w in lower for w in ["vitesse", "excès", "exces", "km/h", "radar", "cinémomètre", "cinematometre"]):
            queries.extend(["vitesse", "exces & vitesse", "radar & photo",
                           "cinematometre"])
        if any(w in lower for w in ["feu rouge", "feu", "signalisation"]):
            queries.extend(["feu & rouge", "signalisation & lumineuse"])
        if any(w in lower for w in ["cellulaire", "telephone", "portable", "textos"]):
            queries.extend(["cellulaire", "appareil & portatif"])
        if any(w in lower for w in ["stop", "arrêt", "arret"]):
            queries.extend(["arret", "panneau & arret"])
        if any(w in lower for w in ["ceinture", "securite"]):
            queries.extend(["ceinture & securite"])
        if any(w in lower for w in ["alcool", "ivresse", "facultes", "soufflé", "alcootest"]):
            queries.extend(["facultes & affaiblies", "alcool"])
        if any(w in lower for w in ["depassement", "depasser", "interdit"]):
            queries.extend(["depassement"])
        if any(w in lower for w in ["permis", "licence", "conduire sans"]):
            queries.extend(["permis & conduire"])
        if any(w in lower for w in ["zone scolaire", "ecole"]):
            queries.extend(["zone & scolaire"])
        if any(w in lower for w in ["construction", "chantier"]):
            queries.extend(["zone & construction"])

        if not queries:
            words = [w for w in lower.split() if len(w) > 3][:3]
            queries = [" & ".join(words)] if words else ["securite & routiere"]

        return queries
