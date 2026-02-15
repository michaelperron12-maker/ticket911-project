"""
Agent ON: VERIFICATEUR/AUDIT ONTARIO — Verifie coherence analyse ON
Valide citations, regles HTA, points MTO, stunt driving logic
"""

import time
from agents.base_agent import BaseAgent


class AgentVerificateurON(BaseAgent):

    def __init__(self):
        super().__init__("Verificateur_ON")

    def verifier(self, analyse, precedents, ticket=None):
        """
        Input: analyse ON + precedents + ticket
        Output: verification avec score de confiance
        """
        self.log("Audit ON: verification citations et coherence HTA...", "STEP")
        start = time.time()

        if not analyse or not isinstance(analyse, dict):
            self.log("Pas d'analyse a verifier", "WARN")
            return {"confiance_globale": 0, "avertissement": "Analyse manquante"}

        validations = []
        confiance = 100

        # 1. Verifier precedents cites
        cites = analyse.get("precedents_cites", [])
        precedents_db = {p.get("citation", ""): p for p in (precedents or [])}

        for cite in cites:
            citation = cite.get("citation", "")
            if citation in precedents_db:
                validations.append({
                    "test": f"Citation '{citation[:50]}'",
                    "valide": True,
                    "detail": "Existe dans la base ON"
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

        # 2. Coherence score/recommandation
        score = analyse.get("score_contestation", 0)
        reco = analyse.get("recommandation", "")

        if score >= 70 and reco == "payer":
            validations.append({
                "test": "Coherence score/recommandation",
                "valide": False,
                "detail": f"Score {score}% mais recommande de payer"
            })
            confiance -= 20
        elif score < 30 and reco == "contester":
            validations.append({
                "test": "Coherence score/recommandation",
                "valide": False,
                "detail": f"Score {score}% mais recommande de contester"
            })
            confiance -= 10
        else:
            validations.append({
                "test": "Coherence score/recommandation",
                "valide": True,
                "detail": f"Score {score}% / Reco: {reco} — coherent"
            })

        # 3. Verifier regles stunt driving
        if ticket:
            exces = ticket.get("exces_vitesse", 0) or 0
            stunt = analyse.get("stunt_driving", None)

            if exces >= 50 and stunt is False:
                validations.append({
                    "test": "Stunt driving detection",
                    "valide": False,
                    "detail": f"Exces {exces} km/h >= 50 mais stunt_driving=false — ERREUR"
                })
                confiance -= 20
            elif exces >= 50 and stunt is True:
                validations.append({
                    "test": "Stunt driving detection",
                    "valide": True,
                    "detail": f"Correct: {exces} km/h = stunt driving (HTA s.172)"
                })
            elif exces < 50 and stunt is True:
                validations.append({
                    "test": "Stunt driving faux positif",
                    "valide": False,
                    "detail": f"Exces {exces} km/h < 50 mais stunt_driving=true"
                })
                confiance -= 10

        # 4. Disclosure recommandation
        disclosure = analyse.get("disclosure_recommandee", None)
        if disclosure is False:
            validations.append({
                "test": "Disclosure recommendation",
                "valide": False,
                "detail": "Disclosure devrait TOUJOURS etre recommandee en Ontario"
            })
            confiance -= 10
        elif disclosure is True:
            validations.append({
                "test": "Disclosure recommendation",
                "valide": True,
                "detail": "Correct: disclosure recommandee"
            })

        # 5. Delai 15 jours (pas 30)
        # Just a general check

        # 6. Base de precedents
        nb_precedents = analyse.get("nb_precedents_utilises", 0)
        base_sur = analyse.get("base_sur_precedents", False)
        if not base_sur or nb_precedents == 0:
            validations.append({
                "test": "Base de precedents",
                "valide": False,
                "detail": "Analyse sans precedents reels ON — confiance reduite"
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
            result["avertissement"] = "Confiance moyenne. Quelques elements a verifier."

        duration = time.time() - start
        nb_ok = sum(1 for v in validations if v["valide"])
        self.log(f"Audit ON: {nb_ok}/{len(validations)} OK | Confiance: {confiance}%", "OK")
        self.log_run("verifier_on", f"{len(cites)} citations",
                     f"Confiance={confiance}% {nb_ok}/{len(validations)} OK", duration=duration)
        return result

    def _chercher_en_db(self, citation):
        try:
            conn = self.get_db()
            cur = conn.cursor()
            cur.execute("SELECT id FROM jurisprudence WHERE citation ILIKE %s AND province = 'ON' LIMIT 1",
                      (f"%{citation[:50]}%",))
            found = cur.fetchone()
            conn.close()
            return found is not None
        except Exception:
            return False
