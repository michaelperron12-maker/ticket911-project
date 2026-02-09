"""
Agent QC: VERIFICATEUR/AUDIT QUEBEC — Verifie coherence analyse QC
Valide citations, regles SAAQ, articles CSR, coherence
"""

import time
import sqlite3
from agents.base_agent import BaseAgent, DB_PATH


class AgentVerificateurQC(BaseAgent):

    def __init__(self):
        super().__init__("Verificateur_QC")

    def verifier(self, analyse, precedents, ticket=None):
        """
        Input: analyse QC + precedents + ticket
        Output: verification avec score de confiance
        """
        self.log("Audit QC: verification citations et coherence CSR...", "STEP")
        start = time.time()

        if not analyse or not isinstance(analyse, dict):
            self.log("Pas d'analyse a verifier", "WARN")
            return {"confiance_globale": 0, "avertissement": "Analyse manquante"}

        validations = []
        confiance = 100

        # 1. Verifier precedents cites existent dans la base
        cites = analyse.get("precedents_cites", [])
        precedents_db = {p.get("citation", ""): p for p in (precedents or [])}

        for cite in cites:
            citation = cite.get("citation", "")
            if citation in precedents_db:
                validations.append({
                    "test": f"Citation '{citation[:50]}'",
                    "valide": True,
                    "detail": "Existe dans la base QC"
                })
            else:
                found = self._chercher_en_db(citation)
                if found:
                    validations.append({
                        "test": f"Citation '{citation[:50]}'",
                        "valide": True,
                        "detail": "Trouve en base SQLite"
                    })
                else:
                    validations.append({
                        "test": f"Citation '{citation[:50]}'",
                        "valide": False,
                        "detail": "NON TROUVE — potentiellement hallucine"
                    })
                    confiance -= 15

        # 2. Coherence score vs recommandation
        score = analyse.get("score_contestation", 0)
        reco = analyse.get("recommandation", "")

        if score >= 70 and reco == "payer":
            validations.append({
                "test": "Coherence score/recommandation",
                "valide": False,
                "detail": f"Score {score}% mais recommande de payer — incoherent"
            })
            confiance -= 20
        elif score < 30 and reco == "contester":
            validations.append({
                "test": "Coherence score/recommandation",
                "valide": False,
                "detail": f"Score {score}% mais recommande de contester — risque"
            })
            confiance -= 10
        else:
            validations.append({
                "test": "Coherence score/recommandation",
                "valide": True,
                "detail": f"Score {score}% / Reco: {reco} — coherent"
            })

        # 3. Verifier regles SAAQ specifiques
        if ticket:
            appareil = (ticket.get("appareil", "") or "").lower()
            is_photo_radar = any(w in appareil for w in ["photo", "radar fixe", "automatique"])
            points_declares = ticket.get("points_inaptitude", 0) or 0

            if is_photo_radar and points_declares > 0:
                validations.append({
                    "test": "Photo radar + points",
                    "valide": False,
                    "detail": "ERREUR: Photo radar ne donne PAS de points SAAQ (art. 592 CSR)"
                })
                confiance -= 15
            elif is_photo_radar:
                validations.append({
                    "test": "Photo radar sans points",
                    "valide": True,
                    "detail": "Correct: photo radar = 0 points SAAQ"
                })

            # Grand exces
            exces = ticket.get("exces_vitesse", 0) or 0
            if exces >= 40 and not analyse.get("grand_exces"):
                validations.append({
                    "test": "Grand exces non detecte",
                    "valide": False,
                    "detail": f"Exces de {exces} km/h mais grand_exces non mentionne dans l'analyse"
                })
                confiance -= 10

        # 4. Base de precedents
        nb_precedents = analyse.get("nb_precedents_utilises", 0)
        base_sur = analyse.get("base_sur_precedents", False)
        if not base_sur or nb_precedents == 0:
            validations.append({
                "test": "Base de precedents",
                "valide": False,
                "detail": "Analyse sans precedents reels QC — confiance reduite"
            })
            confiance -= 20

        # 5. Verifier article CSR mentionne
        loi = analyse.get("loi_applicable", "")
        if loi and any(w in loi.lower() for w in ["csr", "c-24.2", "art", "code"]):
            validations.append({
                "test": "Reference CSR",
                "valide": True,
                "detail": f"Article CSR mentionne: {loi[:60]}"
            })
        elif loi:
            validations.append({
                "test": "Reference CSR",
                "valide": False,
                "detail": "Pas de reference au Code de la securite routiere (C-24.2)"
            })
            confiance -= 5

        confiance = max(0, min(100, confiance))

        result = {
            "confiance_globale": confiance,
            "nb_validations": len(validations),
            "validations": validations,
            "avertissement": None
        }

        if confiance < 50:
            result["avertissement"] = "ATTENTION: Confiance faible. Verification manuelle recommandee."
        elif confiance < 75:
            result["avertissement"] = "Confiance moyenne. Quelques elements a verifier."

        duration = time.time() - start
        nb_ok = sum(1 for v in validations if v["valide"])
        self.log(f"Audit QC: {nb_ok}/{len(validations)} OK | Confiance: {confiance}%", "OK")
        self.log_run("verifier_qc", f"{len(cites)} citations",
                     f"Confiance={confiance}% {nb_ok}/{len(validations)} OK", duration=duration)
        return result

    def _chercher_en_db(self, citation):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT id FROM jurisprudence WHERE citation LIKE ? AND juridiction = 'QC' LIMIT 1",
                      (f"%{citation[:50]}%",))
            found = c.fetchone()
            conn.close()
            return found is not None
        except Exception:
            return False
