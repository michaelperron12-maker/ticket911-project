"""
Agent Phase 1: ROUTING — Route vers le bon team juridictionnel (QC, ON ou NY)
Determine quel pipeline d'agents utiliser
"""

import time
from agents.base_agent import BaseAgent


class AgentRouting(BaseAgent):

    def __init__(self):
        super().__init__("Routing")

    def router(self, ticket, classification):
        """
        Input: ticket + classification
        Output: dict avec le routing (quel team, quelles APIs, quels agents)
        """
        self.log("Routing vers le team juridictionnel...", "STEP")
        start = time.time()

        juridiction = classification.get("juridiction", "QC")
        type_inf = classification.get("type_infraction", "autre")
        gravite = classification.get("gravite", "moyen")

        route = {
            "juridiction": juridiction,
            "team": self._get_team(juridiction),
            "apis": self._get_apis(juridiction),
            "agents_actifs": self._get_agents(juridiction),
            "loi_principale": self._get_loi(juridiction),
            "bases_jurisprudence": self._get_bases(juridiction),
            "priorite": self._get_priorite(gravite),
            "tokens_estimes": self._estimer_tokens(gravite),
        }

        duration = time.time() - start
        self.log(f"Route: {juridiction} | Team: {route['team']} | Priorite: {route['priorite']}", "OK")
        self.log_run("router", f"{juridiction}/{type_inf}/{gravite}",
                     f"Team={route['team']} APIs={len(route['apis'])}", duration=duration)
        return route

    def _get_team(self, juridiction):
        return {
            "QC": "Team Quebec (CSR)",
            "ON": "Team Ontario (HTA)",
            "NY": "Team New York (VTL)",
        }.get(juridiction, "Team Quebec (CSR)")

    def _get_apis(self, juridiction):
        # APIs communes
        apis = ["Mindee OCR", "Stripe", "Twilio", "SendGrid", "Docassemble"]

        # APIs par juridiction
        if juridiction == "QC":
            apis.extend(["CanLII QC", "SOQUIJ", "Lois federales Canada"])
        elif juridiction == "ON":
            apis.extend(["CanLII ON", "Lois federales Canada"])
        elif juridiction == "NY":
            apis.extend(["NYC Open Data (SODA)", "NYS Open Data", "CourtListener"])

        return apis

    def _get_agents(self, juridiction):
        # 8 agents partages
        partages = [
            "OCR Master", "Classificateur", "Validateur", "Routing",
            "Rapport Client", "Rapport Avocat", "Notification", "Superviseur"
        ]

        # 6 agents juridictionnels
        specifiques = {
            "QC": ["Analyse CSR", "Jurisprudence CanLII-QC", "Strategie Cour municipale",
                   "Procedure art.160", "Calcul SAAQ", "Audit QC"],
            "ON": ["Analyse HTA", "Jurisprudence CanLII-ON", "Strategie POC",
                   "Procedure HTA-III", "Calcul ON pts", "Audit ON"],
            "NY": ["Analyse VTL", "Jurisprudence CourtListener", "Strategie TVB",
                   "Procedure VTL-226", "Calcul DMV pts", "Audit NY"],
        }

        return partages + specifiques.get(juridiction, specifiques["QC"])

    def _get_loi(self, juridiction):
        return {
            "QC": "Code de la securite routiere (C-24.2)",
            "ON": "Highway Traffic Act (R.S.O. 1990, c. H.8)",
            "NY": "Vehicle and Traffic Law (VTL)",
        }.get(juridiction, "")

    def _get_bases(self, juridiction):
        return {
            "QC": ["CanLII QC", "SOQUIJ", "LegisQuebec", "FTS5", "ChromaDB"],
            "ON": ["CanLII ON", "Ontario Courts", "FTS5", "ChromaDB"],
            "NY": ["CourtListener", "NYC Open Data", "NYS Open Data", "FTS5", "ChromaDB"],
        }.get(juridiction, [])

    def _get_priorite(self, gravite):
        return {
            "faible": "normale",
            "moyen": "normale",
            "eleve": "haute",
            "critique": "urgente",
        }.get(gravite, "normale")

    def _estimer_tokens(self, gravite):
        return {
            "faible": 800000,
            "moyen": 1000000,
            "eleve": 1200000,
            "critique": 1500000,
        }.get(gravite, 1200000)
