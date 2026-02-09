"""
Agent Phase 4: SUPERVISEUR — Verifie que tous les agents ont complete
Valide la qualite finale du dossier avant livraison
"""

import time
from agents.base_agent import BaseAgent


class AgentSuperviseur(BaseAgent):

    def __init__(self):
        super().__init__("Superviseur")

    def superviser(self, rapport_complet):
        """
        Input: rapport complet avec resultats de tous les agents
        Output: validation finale + score qualite
        """
        self.log("Supervision finale du dossier...", "STEP")
        start = time.time()

        checks = []
        score_qualite = 100

        # 1. Verifier que chaque phase a complete
        phases = rapport_complet.get("phases", {})

        # Phase 1: Intake
        intake = phases.get("intake", {})
        if intake.get("ocr", {}).get("status") == "OK":
            checks.append({"agent": "OCR Master", "status": "OK"})
        else:
            checks.append({"agent": "OCR Master", "status": "SKIP", "note": "Pas de photo fournie"})

        for agent in ["classificateur", "validateur", "routing"]:
            data = intake.get(agent, {})
            if data:
                checks.append({"agent": agent.capitalize(), "status": "OK"})
            else:
                checks.append({"agent": agent.capitalize(), "status": "FAIL"})
                score_qualite -= 10

        # Phase 2: Analyse juridique
        analyse = phases.get("analyse", {})
        for agent in ["lecteur", "lois", "precedents", "analyste", "verificateur", "procedure", "points"]:
            data = analyse.get(agent, {})
            status = data.get("status", "FAIL") if isinstance(data, dict) else "FAIL"
            checks.append({"agent": agent.capitalize(), "status": status})
            if status != "OK":
                score_qualite -= 8

        # Phase 3: Audit qualite
        audit = phases.get("audit", {})
        cross = audit.get("cross_verification", {})
        if cross:
            concordance = cross.get("concordance", False)
            checks.append({
                "agent": "CrossVerification",
                "status": "OK" if concordance else "WARN",
                "note": f"Fiabilite: {cross.get('fiabilite', '?')}"
            })
            if not concordance:
                score_qualite -= 15
        else:
            checks.append({"agent": "CrossVerification", "status": "SKIP"})

        # Phase 4: Livraison
        livraison = phases.get("livraison", {})
        for agent in ["rapport_client", "rapport_avocat"]:
            data = livraison.get(agent, {})
            if data:
                checks.append({"agent": agent.replace("_", " ").title(), "status": "OK"})
            else:
                checks.append({"agent": agent.replace("_", " ").title(), "status": "FAIL"})
                score_qualite -= 5

        notif = livraison.get("notification", {})
        checks.append({"agent": "Notification", "status": "OK" if notif else "SKIP"})

        # Score final
        score_qualite = max(0, min(100, score_qualite))
        nb_ok = sum(1 for c in checks if c["status"] == "OK")
        nb_total = len(checks)

        # Decision finale
        if score_qualite >= 80:
            decision = "APPROUVE — Dossier pret pour livraison"
        elif score_qualite >= 50:
            decision = "APPROUVE AVEC RESERVES — Verification manuelle recommandee"
        else:
            decision = "REJETE — Qualite insuffisante, revoir l'analyse"

        result = {
            "score_qualite": score_qualite,
            "decision": decision,
            "agents_verifies": f"{nb_ok}/{nb_total}",
            "checks": checks,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        duration = time.time() - start
        self.log(f"Qualite: {score_qualite}% | {nb_ok}/{nb_total} agents OK | {decision}", "OK")
        self.log_run("superviser", f"{nb_total} agents",
                     f"Qualite={score_qualite}% Decision={decision[:30]}", duration=duration)
        return result
