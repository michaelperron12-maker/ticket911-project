"""
Agent ON: LOIS ONTARIO — Highway Traffic Act (HTA) + Provincial Offences Act
Recherche PostgreSQL tsvector specifique Ontario
"""

import time
from agents.base_agent import BaseAgent


class AgentLoisON(BaseAgent):

    def __init__(self):
        super().__init__("Lois_ON")

    def chercher_loi(self, ticket):
        """
        Input: ticket ON
        Output: sections HTA et reglements Ontario applicables
        """
        self.log(f"Recherche lois ON/HTA: {ticket.get('infraction', '?')}", "STEP")
        start = time.time()
        resultats = []

        infraction = ticket.get("infraction", "")
        mots_cles = self._extraire_mots_cles_on(infraction)

        try:
            conn = self.get_db()
            cur = conn.cursor()

            for query in mots_cles:
                try:
                    tsquery = " | ".join(query.split())
                    cur.execute("""
                        SELECT id, province, article, titre_article,
                               texte_complet, loi, code_loi,
                               ts_rank(tsv, to_tsquery('english', %s)) AS rank
                        FROM lois_articles
                        WHERE province = 'ON'
                          AND tsv @@ to_tsquery('english', %s)
                        ORDER BY rank DESC
                        LIMIT 5
                    """, (tsquery, tsquery))
                    for row in cur.fetchall():
                        resultats.append({
                            "id": row[0], "juridiction": row[1],
                            "article": row[2],
                            "texte": (row[4] or row[3] or "")[:500],
                            "source": row[5] or row[6] or "HTA",
                            "recherche": query
                        })
                        self.log(f"  HTA s.{row[2]} trouve", "OK")
                except Exception:
                    pass

            # Fallback
            if not resultats:
                self.log("Pas de resultats tsvector — recherche directe", "WARN")
                cur.execute("""
                    SELECT id, province, article, titre_article, texte_complet, loi
                    FROM lois_articles
                    WHERE province = 'ON'
                    LIMIT 10
                """)
                for row in cur.fetchall():
                    resultats.append({
                        "id": row[0], "juridiction": row[1],
                        "article": row[2],
                        "texte": (row[4] or row[3] or "")[:500],
                        "source": row[5] or "HTA"
                    })

            conn.close()
        except Exception as e:
            self.log(f"Erreur recherche lois ON: {e}", "FAIL")

        seen = set()
        unique = []
        for r in resultats:
            key = f"{r['juridiction']}_{r['article']}"
            if key not in seen:
                seen.add(key)
                unique.append(r)

        duration = time.time() - start
        self.log_run("chercher_loi_on", f"ON {infraction[:100]}", f"{len(unique)} sections HTA", duration=duration)
        self.log(f"{len(unique)} sections HTA trouvees en {duration:.1f}s", "OK")
        return unique

    def _extraire_mots_cles_on(self, infraction):
        """Mots-cles specifiques au Highway Traffic Act de l'Ontario"""
        queries = []
        lower = infraction.lower()

        if any(w in lower for w in ["speed", "vitesse", "km/h", "speeding", "radar"]):
            queries.extend(["speed", "speeding", "radar"])
        if any(w in lower for w in ["red light", "feu rouge", "traffic signal"]):
            queries.extend(["red & light", "traffic & signal"])
        if any(w in lower for w in ["cell", "phone", "handheld", "cellulaire", "texting"]):
            queries.extend(["handheld", "distracted"])
        if any(w in lower for w in ["stop", "arrêt", "arret"]):
            queries.extend(["stop & sign"])
        if any(w in lower for w in ["seatbelt", "ceinture", "belt"]):
            queries.extend(["seatbelt"])
        if any(w in lower for w in ["careless", "dangereuse", "dangerous"]):
            queries.extend(["careless & driving"])
        if any(w in lower for w in ["stunt", "racing", "course", "street racing"]):
            queries.extend(["stunt & driving", "racing"])
        if any(w in lower for w in ["follow", "tailgating", "trop pres"]):
            queries.extend(["following & closely"])
        if any(w in lower for w in ["insurance", "assurance", "no insurance"]):
            queries.extend(["insurance"])
        if any(w in lower for w in ["licence", "license", "permis", "suspended"]):
            queries.extend(["licence", "suspended"])

        if not queries:
            words = [w for w in lower.split() if len(w) > 3][:3]
            queries = [" & ".join(words)] if words else ["highway & traffic"]

        return queries
