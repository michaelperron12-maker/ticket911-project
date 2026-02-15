"""
Agent NY: VERIFICATEUR/AUDIT NEW YORK — Verifie coherence analyse NY
Valide citations, TVB rules, points DMV, VTL references
"""

import time
from agents.base_agent import BaseAgent


class AgentVerificateurNY(BaseAgent):

    def __init__(self):
        super().__init__("Verificateur_NY")

    def verifier(self, analyse, precedents, ticket=None):
        """
        Input: analyse NY + precedents + ticket original
        Output: verification avec score de confiance
        """
        self.log("Audit NY: verification citations et coherence...", "STEP")
        start = time.time()

        if not analyse or not isinstance(analyse, dict):
            self.log("Pas d'analyse a verifier", "WARN")
            return {"confiance_globale": 0, "avertissement": "Analyse manquante"}

        validations = []
        confiance = 100

        # 1. Verifier que les precedents cites existent dans la base
        cites = analyse.get("precedents_cites", [])
        precedents_db = {p.get("citation", ""): p for p in (precedents or [])}

        for cite in cites:
            citation = cite.get("citation", "")
            if citation in precedents_db:
                validations.append({
                    "test": f"Citation '{citation[:50]}'",
                    "valide": True,
                    "detail": "Existe dans la base NY"
                })
            else:
                # Verifier en DB directement
                found = self._chercher_en_db(citation)
                if found:
                    validations.append({
                        "test": f"Citation '{citation[:50]}'",
                        "valide": True,
                        "detail": "Trouve en base SQLite (pas dans resultats initiaux)"
                    })
                else:
                    validations.append({
                        "test": f"Citation '{citation[:50]}'",
                        "valide": False,
                        "detail": "NON TROUVE — potentiellement hallucine"
                    })
                    confiance -= 15

        # 2. Verifier coherence score vs recommandation
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

        # 3. Verifier regles TVB
        tvb = analyse.get("tvb_applicable", None)
        plea = analyse.get("plea_bargain_possible", None)
        if tvb is True and plea is True:
            validations.append({
                "test": "Regles TVB",
                "valide": False,
                "detail": "ERREUR: TVB=true mais plea_bargain=true — TVB ne permet PAS le plea bargaining"
            })
            confiance -= 25
        elif tvb is True and plea is False:
            validations.append({
                "test": "Regles TVB",
                "valide": True,
                "detail": "Correct: TVB sans plea bargaining"
            })
        elif tvb is False and plea is True:
            validations.append({
                "test": "Regles TVB",
                "valide": True,
                "detail": "Correct: hors NYC, plea bargaining disponible"
            })

        # 4. Verifier points DMV
        points_analyse = analyse.get("driver_responsibility_assessment", "")
        if isinstance(points_analyse, str) and "11" in points_analyse:
            validations.append({
                "test": "Seuil points DMV",
                "valide": True,
                "detail": "Reference correcte au seuil de 11 points"
            })

        # 5. Avertissement si peu de precedents
        nb_precedents = analyse.get("nb_precedents_utilises", 0)
        base_sur = analyse.get("base_sur_precedents", False)
        if not base_sur or nb_precedents == 0:
            validations.append({
                "test": "Base de precedents",
                "valide": False,
                "detail": "Analyse sans precedents reels NY — confiance reduite"
            })
            confiance -= 20

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
            result["avertissement"] = "Confiance moyenne. Quelques elements a verifier manuellement."

        duration = time.time() - start
        nb_ok = sum(1 for v in validations if v["valide"])
        self.log(f"Audit NY: {nb_ok}/{len(validations)} OK | Confiance: {confiance}%", "OK")
        self.log_run("verifier_ny", f"{len(cites)} citations",
                     f"Confiance={confiance}% {nb_ok}/{len(validations)} OK", duration=duration)
        return result

    def _chercher_en_db(self, citation):
        """Cherche une citation dans la DB jurisprudence"""
        try:
            conn = self.get_db()
            cur = conn.cursor()
            cur.execute("SELECT id FROM jurisprudence WHERE citation ILIKE %s LIMIT 1",
                      (f"%{citation[:50]}%",))
            found = cur.fetchone()
            conn.close()
            return found is not None
        except Exception:
            return False
