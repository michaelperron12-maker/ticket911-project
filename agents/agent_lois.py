"""
Agent 2: CHERCHEUR DE LOIS — Trouve les articles de loi applicables
Cherche dans PostgreSQL via tsvector full-text search
"""

import time
from agents.base_agent import BaseAgent


class AgentLois(BaseAgent):

    def __init__(self):
        super().__init__("Lois")

    def chercher_loi(self, ticket):
        """
        Input: ticket structure (dict)
        Output: liste d'articles de loi pertinents
        """
        self.log(f"Recherche lois pour: {ticket.get('juridiction', '?')} — {ticket.get('infraction', '?')}", "STEP")
        start = time.time()
        resultats = []

        conn = self.get_db()
        c = conn.cursor()

        juridiction = ticket.get("juridiction", "")
        infraction = ticket.get("infraction", "")

        # Recherche FTS dans la table des lois
        try:
            # Construire la requete FTS
            mots_cles = self._extraire_mots_cles(infraction, juridiction)
            for query in mots_cles:
                try:
                    c.execute("""SELECT l.id, l.province, l.article, l.texte_complet, l.loi
                                 FROM lois_articles l
                                 WHERE l.tsv @@ to_tsquery('french', %s)
                                 LIMIT 5""", (query,))
                    rows = c.fetchall()
                    for row in rows:
                        resultats.append({
                            "id": row[0], "juridiction": row[1],
                            "article": row[2], "texte": row[3][:500] if row[3] else "",
                            "source": row[4], "recherche": query
                        })
                        self.log(f"  Art. {row[2]} ({row[1]}) trouve", "OK")
                except Exception:
                    pass

            if not resultats:
                self.log("Aucun resultat FTS — recherche directe", "WARN")
                # Fallback: recherche directe dans la table lois_articles
                c.execute("""SELECT id, province, article, texte_complet, loi FROM lois_articles
                             WHERE province = %s LIMIT 10""", (juridiction,))
                for row in c.fetchall():
                    resultats.append({
                        "id": row[0], "juridiction": row[1],
                        "article": row[2], "texte": row[3][:500] if row[3] else "",
                        "source": row[4]
                    })
        except Exception as e:
            self.log(f"Erreur recherche lois: {e}", "FAIL")

        conn.close()

        # Deduplication par article
        seen = set()
        unique = []
        for r in resultats:
            key = f"{r['juridiction']}_{r['article']}"
            if key not in seen:
                seen.add(key)
                unique.append(r)

        duration = time.time() - start
        self.log_run("chercher_loi", f"{juridiction} {infraction[:100]}", f"{len(unique)} articles trouves", duration=duration)
        self.log(f"{len(unique)} articles de loi trouves en {duration:.1f}s", "OK")
        return unique

    def _extraire_mots_cles(self, infraction, juridiction):
        """Genere des requetes FTS a partir de l'infraction"""
        queries = []
        infraction_lower = infraction.lower()

        # Mapping infraction -> mots-cles de recherche
        if any(w in infraction_lower for w in ["vitesse", "speed", "excès", "exces"]):
            if juridiction == "QC":
                queries.extend(["vitesse", "299", "excès & vitesse"])
            elif juridiction == "ON":
                queries.extend(["speed", "128", "speeding"])
            else:
                queries.extend(["speed", "vitesse"])

        if any(w in infraction_lower for w in ["feu rouge", "red light", "feu"]):
            if juridiction == "QC":
                queries.extend(["feu & rouge", "328", "signalisation"])
            elif juridiction == "ON":
                queries.extend(["red & light", "144"])

        if any(w in infraction_lower for w in ["cellulaire", "cell", "phone", "handheld", "texting"]):
            if juridiction == "QC":
                queries.extend(["cellulaire", "396", "appareil"])
            elif juridiction == "ON":
                queries.extend(["handheld", "78.1", "device"])

        if any(w in infraction_lower for w in ["stop", "arrêt", "arret"]):
            if juridiction == "QC":
                queries.extend(["arrêt", "443", "stop"])

        # Fallback generique
        if not queries:
            words = [w for w in infraction_lower.split() if len(w) > 3]
            queries = words[:3]

        return queries
