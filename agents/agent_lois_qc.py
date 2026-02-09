"""
Agent QC: LOIS QUEBEC — Code de la securite routiere (CSR) + Code criminel
Recherche FTS specifique Quebec (articles CSR, C-24.2, reglements municipaux)
"""

import sqlite3
import time
from agents.base_agent import BaseAgent, DB_PATH


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

        conn = self.get_db()
        c = conn.cursor()

        infraction = ticket.get("infraction", "")
        mots_cles = self._extraire_mots_cles_qc(infraction)

        try:
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lois_fts'")
            if c.fetchone():
                for query in mots_cles:
                    try:
                        c.execute("""SELECT l.id, l.juridiction, l.article, l.texte, l.source
                                     FROM lois_fts fts
                                     JOIN lois l ON fts.rowid = l.id
                                     WHERE lois_fts MATCH ?
                                     AND l.juridiction = 'QC'
                                     LIMIT 5""", (query,))
                        for row in c.fetchall():
                            resultats.append({
                                "id": row[0], "juridiction": row[1],
                                "article": row[2], "texte": row[3][:500],
                                "source": row[4], "recherche": query
                            })
                            self.log(f"  CSR art. {row[2]} trouve", "OK")
                    except sqlite3.OperationalError:
                        pass

                # Aussi chercher dans lois federales (Code criminel si applicable)
                if any(w in infraction.lower() for w in ["alcool", "ivresse", "facultes", "capacites"]):
                    try:
                        c.execute("""SELECT l.id, l.juridiction, l.article, l.texte, l.source
                                     FROM lois_fts fts
                                     JOIN lois l ON fts.rowid = l.id
                                     WHERE lois_fts MATCH 'alcool OR capacites OR ivresse'
                                     AND l.juridiction = 'CA'
                                     LIMIT 3""")
                        for row in c.fetchall():
                            resultats.append({
                                "id": row[0], "juridiction": "CA",
                                "article": row[2], "texte": row[3][:500],
                                "source": row[4], "recherche": "Code criminel"
                            })
                    except sqlite3.OperationalError:
                        pass
            else:
                self.log("Table lois_fts non trouvee — recherche directe", "WARN")
                c.execute("""SELECT id, juridiction, article, texte, source FROM lois
                             WHERE juridiction = 'QC' LIMIT 10""")
                for row in c.fetchall():
                    resultats.append({
                        "id": row[0], "juridiction": row[1],
                        "article": row[2], "texte": row[3][:500],
                        "source": row[4]
                    })
        except Exception as e:
            self.log(f"Erreur recherche lois QC: {e}", "FAIL")

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
        self.log_run("chercher_loi_qc", f"QC {infraction[:100]}", f"{len(unique)} articles CSR", duration=duration)
        self.log(f"{len(unique)} articles CSR trouves en {duration:.1f}s", "OK")
        return unique

    def _extraire_mots_cles_qc(self, infraction):
        """Mots-cles specifiques au Code de la securite routiere du Quebec"""
        queries = []
        lower = infraction.lower()

        if any(w in lower for w in ["vitesse", "excès", "exces", "km/h", "radar", "cinémomètre", "cinematometre"]):
            queries.extend(["vitesse", "excès vitesse", "art 299", "art 303",
                           "cinémomètre", "radar photo"])
        if any(w in lower for w in ["feu rouge", "feu", "signalisation"]):
            queries.extend(["feu rouge", "art 328", "signalisation lumineuse", "art 359"])
        if any(w in lower for w in ["cellulaire", "telephone", "portable", "textos"]):
            queries.extend(["cellulaire", "art 396", "appareil portatif", "art 443.1"])
        if any(w in lower for w in ["stop", "arrêt", "arret"]):
            queries.extend(["arrêt", "art 368", "panneau arret", "art 360"])
        if any(w in lower for w in ["ceinture", "securite"]):
            queries.extend(["ceinture securite", "art 396", "art 397"])
        if any(w in lower for w in ["alcool", "ivresse", "facultes", "soufflé", "alcootest"]):
            queries.extend(["facultes affaiblies", "alcool", "art 202", "Code criminel 320"])
        if any(w in lower for w in ["depassement", "depasser", "interdit"]):
            queries.extend(["depassement", "art 344", "art 345"])
        if any(w in lower for w in ["permis", "licence", "conduire sans"]):
            queries.extend(["permis conduire", "art 65", "art 93"])
        if any(w in lower for w in ["zone scolaire", "ecole"]):
            queries.extend(["zone scolaire", "art 329"])
        if any(w in lower for w in ["construction", "chantier"]):
            queries.extend(["zone construction", "art 329.2"])

        if not queries:
            words = [w for w in lower.split() if len(w) > 3][:3]
            queries = words if words else ["code securite routiere"]

        return queries
