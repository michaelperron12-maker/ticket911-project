"""
Agent 5: VERIFICATEUR — Verifie que chaque citation existe dans la DB
Donne un score de confiance global
PostgreSQL backend
"""

import re
import time
from agents.base_agent import BaseAgent


class AgentVerificateur(BaseAgent):

    def __init__(self):
        super().__init__("Verificateur")

    def verifier(self, analyse, precedents_db):
        """
        Input: analyse de Agent 4 + precedents trouves par Agent 3
        Output: rapport de verification avec score de confiance
        """
        self.log("Verification des citations...", "STEP")
        start = time.time()

        if not analyse or isinstance(analyse, str):
            return {"confiance_globale": 0, "verifications": [], "erreur": "Analyse invalide"}

        # Extraire les citations de l'analyse
        citations_analysees = analyse.get("precedents_cites", [])
        precedents_db_citations = {p.get("citation", ""): p for p in (precedents_db or [])}

        verifications = []
        nb_verifies = 0
        nb_non_trouves = 0

        for cite in citations_analysees:
            citation = cite.get("citation", "")
            if not citation:
                continue

            # Verifier si la citation existe dans les precedents de la DB
            found = False
            match_info = None

            # Correspondance exacte
            if citation in precedents_db_citations:
                found = True
                match_info = precedents_db_citations[citation]

            # Correspondance partielle (le modele peut reformuler legerement)
            if not found:
                for db_cite, db_info in precedents_db_citations.items():
                    # Extraire l'annee et le numero de la citation
                    cite_pattern = re.findall(r"(\d{4})\s*(\w+)\s*(\d+)", citation)
                    db_pattern = re.findall(r"(\d{4})\s*(\w+)\s*(\d+)", db_cite)
                    if cite_pattern and db_pattern and cite_pattern[0] == db_pattern[0]:
                        found = True
                        match_info = db_info
                        break

            # Verifier aussi dans PostgreSQL directement
            if not found:
                found, match_info = self._verifier_dans_db(citation)

            verification = {
                "citation": citation,
                "verifie": found,
                "status": "VERIFIE" if found else "NON TROUVE",
                "pertinence": cite.get("pertinence", ""),
                "resultat_cite": cite.get("resultat", ""),
            }

            if found and match_info:
                verification["resultat_db"] = match_info.get("resultat", "")
                verification["tribunal_db"] = match_info.get("tribunal", "")
                verification["date_db"] = match_info.get("date", "")
                nb_verifies += 1
                self.log(f"  [VERIFIE] {citation[:60]}", "OK")
            else:
                nb_non_trouves += 1
                self.log(f"  [NON TROUVE] {citation[:60]}", "FAIL")

            verifications.append(verification)

        # Calculer le score de confiance
        total = len(verifications)
        if total > 0:
            confiance = round((nb_verifies / total) * 100)
        else:
            # Pas de citations = confiance basee sur l'analyse generale
            confiance = 30 if not precedents_db else 50

        # Ajustements
        if not precedents_db:
            confiance = min(confiance, 40)  # Plafonner si aucun precedent en DB

        rapport = {
            "confiance_globale": confiance,
            "citations_total": total,
            "citations_verifiees": nb_verifies,
            "citations_non_trouvees": nb_non_trouves,
            "verifications": verifications,
            "avertissement": self._generer_avertissement(confiance, nb_non_trouves, total, precedents_db)
        }

        duration = time.time() - start
        self.log(f"Confiance: {confiance}% ({nb_verifies}/{total} verifies)", "OK")
        self.log_run("verifier", f"{total} citations", f"Confiance={confiance}%", duration=duration)

        return rapport

    def _verifier_dans_db(self, citation):
        """Cherche la citation directement dans PostgreSQL"""
        try:
            conn = self.get_db()
            c = conn.cursor()

            # Recherche par citation
            c.execute("SELECT id, citation, tribunal, date_decision, resume, resultat FROM jurisprudence WHERE citation ILIKE %s",
                      (f"%{citation}%",))
            row = c.fetchone()
            conn.close()

            if row:
                return True, {
                    "id": row[0], "citation": row[1], "tribunal": row[2],
                    "date": row[3], "resume": row[4], "resultat": row[5]
                }
        except Exception:
            pass
        return False, None

    def _generer_avertissement(self, confiance, nb_non_trouves, total, precedents_db):
        if not precedents_db:
            return "ATTENTION: Aucun precedent dans notre base. L'analyse est basee sur les connaissances generales de l'IA et NON sur des cas verifies."
        if confiance >= 80:
            return None
        if confiance >= 50:
            return f"{nb_non_trouves}/{total} citations n'ont pas ete trouvees dans notre base. Verification manuelle recommandee."
        return f"ATTENTION: Seulement {confiance}% des citations sont verifiees. Ne pas utiliser sans verification par un avocat."
