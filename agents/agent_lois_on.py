"""
Agent ON: LOIS ONTARIO — Highway Traffic Act (HTA) + Provincial Offences Act
Recherche FTS specifique Ontario
"""

import sqlite3
import time
from agents.base_agent import BaseAgent, DB_PATH


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

        conn = self.get_db()
        c = conn.cursor()

        infraction = ticket.get("infraction", "")
        mots_cles = self._extraire_mots_cles_on(infraction)

        try:
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lois_fts'")
            if c.fetchone():
                for query in mots_cles:
                    try:
                        c.execute("""SELECT l.id, l.juridiction, l.article, l.texte, l.source
                                     FROM lois_fts fts
                                     JOIN lois l ON fts.rowid = l.id
                                     WHERE lois_fts MATCH ?
                                     AND l.juridiction = 'ON'
                                     LIMIT 5""", (query,))
                        for row in c.fetchall():
                            resultats.append({
                                "id": row[0], "juridiction": row[1],
                                "article": row[2], "texte": row[3][:500],
                                "source": row[4], "recherche": query
                            })
                            self.log(f"  HTA s.{row[2]} trouve", "OK")
                    except sqlite3.OperationalError:
                        pass
            else:
                self.log("Table lois_fts non trouvee — recherche directe", "WARN")
                c.execute("""SELECT id, juridiction, article, texte, source FROM lois
                             WHERE juridiction = 'ON' LIMIT 10""")
                for row in c.fetchall():
                    resultats.append({
                        "id": row[0], "juridiction": row[1],
                        "article": row[2], "texte": row[3][:500],
                        "source": row[4]
                    })
        except Exception as e:
            self.log(f"Erreur recherche lois ON: {e}", "FAIL")

        conn.close()

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
            queries.extend(["speed", "s 128", "speeding", "radar", "HTA 128"])
        if any(w in lower for w in ["red light", "feu rouge", "traffic signal"]):
            queries.extend(["red light", "s 144", "traffic signal", "HTA 144"])
        if any(w in lower for w in ["cell", "phone", "handheld", "cellulaire", "texting"]):
            queries.extend(["handheld", "s 78.1", "distracted", "HTA 78.1"])
        if any(w in lower for w in ["stop", "arrêt", "arret"]):
            queries.extend(["stop sign", "s 136", "HTA 136"])
        if any(w in lower for w in ["seatbelt", "ceinture", "belt"]):
            queries.extend(["seatbelt", "s 106", "HTA 106"])
        if any(w in lower for w in ["careless", "dangereuse", "dangerous"]):
            queries.extend(["careless driving", "s 130", "HTA 130"])
        if any(w in lower for w in ["stunt", "racing", "course", "street racing"]):
            queries.extend(["stunt driving", "s 172", "racing", "HTA 172"])
        if any(w in lower for w in ["follow", "tailgating", "trop pres"]):
            queries.extend(["following too closely", "s 158", "HTA 158"])
        if any(w in lower for w in ["insurance", "assurance", "no insurance"]):
            queries.extend(["compulsory automobile insurance", "CAIA", "no insurance"])
        if any(w in lower for w in ["licence", "license", "permis", "suspended"]):
            queries.extend(["licence", "s 32", "s 53", "driving while suspended"])

        if not queries:
            words = [w for w in lower.split() if len(w) > 3][:3]
            queries = words if words else ["highway traffic act"]

        return queries
