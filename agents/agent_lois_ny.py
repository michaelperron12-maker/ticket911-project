"""
Agent NY: LOIS NEW YORK — Vehicle and Traffic Law (VTL) + NYC Traffic Rules
Recherche FTS dans les lois indexees pour New York
"""

import sqlite3
import time
from agents.base_agent import BaseAgent, DB_PATH


class AgentLoisNY(BaseAgent):

    def __init__(self):
        super().__init__("Lois_NY")

    def chercher_loi(self, ticket):
        """
        Input: ticket structure (dict) avec juridiction=NY
        Output: articles VTL et NYC Traffic Rules pertinents
        """
        self.log(f"Recherche lois NY/VTL: {ticket.get('infraction', '?')}", "STEP")
        start = time.time()
        resultats = []

        conn = self.get_db()
        c = conn.cursor()

        infraction = ticket.get("infraction", "")
        mots_cles = self._extraire_mots_cles_ny(infraction)

        try:
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lois_fts'")
            if c.fetchone():
                for query in mots_cles:
                    try:
                        c.execute("""SELECT l.id, l.juridiction, l.article, l.texte, l.source
                                     FROM lois_fts fts
                                     JOIN lois l ON fts.rowid = l.id
                                     WHERE lois_fts MATCH ?
                                     AND l.juridiction = 'NY'
                                     LIMIT 5""", (query,))
                        for row in c.fetchall():
                            resultats.append({
                                "id": row[0], "juridiction": row[1],
                                "article": row[2], "texte": row[3][:500],
                                "source": row[4], "recherche": query
                            })
                            self.log(f"  VTL {row[2]} trouve", "OK")
                    except sqlite3.OperationalError:
                        pass
            else:
                self.log("Table lois_fts non trouvee — recherche directe", "WARN")
                c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lois'")
                if c.fetchone():
                    c.execute("""SELECT id, juridiction, article, texte, source FROM lois
                                 WHERE juridiction = 'NY' LIMIT 10""")
                    for row in c.fetchall():
                        resultats.append({
                            "id": row[0], "juridiction": row[1],
                            "article": row[2], "texte": row[3][:500],
                            "source": row[4]
                        })
        except Exception as e:
            self.log(f"Erreur recherche lois NY: {e}", "FAIL")

        conn.close()

        # Deduplication
        seen = set()
        unique = []
        for r in resultats:
            key = f"{r['juridiction']}_{r['article']}"
            if key not in seen:
                seen.add(key)
                unique.append(r)

        duration = time.time() - start
        self.log_run("chercher_loi_ny", f"NY {infraction[:100]}", f"{len(unique)} articles VTL", duration=duration)
        self.log(f"{len(unique)} articles VTL trouves en {duration:.1f}s", "OK")
        return unique

    def _extraire_mots_cles_ny(self, infraction):
        """Mots-cles specifiques au VTL et NYC Traffic Rules"""
        queries = []
        lower = infraction.lower()

        if any(w in lower for w in ["speed", "vitesse", "mph", "speeding"]):
            queries.extend(["VTL 1180", "speed", "speeding", "radar"])
        if any(w in lower for w in ["red light", "feu rouge", "traffic signal"]):
            queries.extend(["VTL 1111", "red light", "traffic signal"])
        if any(w in lower for w in ["cell", "phone", "texting", "handheld", "cellulaire"]):
            queries.extend(["VTL 1225", "cell phone", "handheld", "texting"])
        if any(w in lower for w in ["stop sign", "arret", "stop"]):
            queries.extend(["VTL 1172", "stop sign"])
        if any(w in lower for w in ["seatbelt", "ceinture", "belt"]):
            queries.extend(["VTL 1229", "seatbelt"])
        if any(w in lower for w in ["reckless", "dangerous", "imprudent"]):
            queries.extend(["VTL 1212", "reckless driving"])
        if any(w in lower for w in ["dui", "dwi", "alcool", "alcohol", "intoxicated"]):
            queries.extend(["VTL 1192", "DWI", "intoxicated"])
        if any(w in lower for w in ["license", "permis", "unlicensed"]):
            queries.extend(["VTL 509", "license", "unlicensed"])

        if not queries:
            words = [w for w in lower.split() if len(w) > 3][:3]
            queries = words if words else ["VTL violation"]

        return queries
