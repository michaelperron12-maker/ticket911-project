"""
Agent Phase 1: CLASSIFICATEUR — Detecte juridiction, type d'infraction, gravite
Moteur d'inference rapide — pas besoin de raisonnement profond
"""

import time
import re
from agents.base_agent import BaseAgent


class AgentClassificateur(BaseAgent):

    def __init__(self):
        super().__init__("Classificateur")

    # Mapping des types d'infraction
    TYPES = {
        "vitesse": ["vitesse", "speed", "excès", "exces", "km/h", "mph", "radar"],
        "feu_rouge": ["feu rouge", "red light", "feu", "signal"],
        "stop": ["stop", "arrêt", "arret", "panneau"],
        "cellulaire": ["cellulaire", "cell", "phone", "handheld", "texting", "telephone"],
        "ceinture": ["ceinture", "seatbelt", "seat belt"],
        "alcool": ["alcool", "alcohol", "ivresse", "impaired", "dui", "dwi", "taux"],
        "conduite_dangereuse": ["dangereuse", "dangerous", "careless", "stunt", "racing", "course"],
        "stationnement": ["stationnement", "parking", "parcometre"],
        "permis": ["permis", "license", "licence", "suspendu", "suspended", "revoque"],
        "assurance": ["assurance", "insurance", "preuve"],
    }

    # Gravite par type
    GRAVITE = {
        "vitesse": "moyen",
        "feu_rouge": "moyen",
        "stop": "faible",
        "cellulaire": "eleve",
        "ceinture": "faible",
        "alcool": "critique",
        "conduite_dangereuse": "critique",
        "stationnement": "faible",
        "permis": "eleve",
        "assurance": "eleve",
    }

    def classifier(self, ticket):
        """
        Input: ticket dict (parsed par Lecteur ou OCR)
        Output: dict avec juridiction, type, gravite, sous-type
        """
        self.log("Classification du ticket...", "STEP")
        start = time.time()

        infraction = ticket.get("infraction", "").lower()
        juridiction_raw = ticket.get("juridiction", "")

        # 1. Detecter juridiction
        juridiction = self._detecter_juridiction(juridiction_raw, ticket)

        # 2. Detecter type d'infraction
        type_infraction = self._detecter_type(infraction)

        # 3. Evaluer gravite
        gravite = self._evaluer_gravite(type_infraction, ticket)

        # 4. Points max par juridiction
        points = ticket.get("points_inaptitude", 0)
        points_max = {"QC": 15, "ON": 9, "NY": 11}.get(juridiction, 15)

        result = {
            "juridiction": juridiction,
            "type_infraction": type_infraction,
            "gravite": gravite,
            "points": points,
            "points_max": points_max,
            "risque_suspension": points >= (points_max * 0.6),
            "code_applicable": self._code_applicable(juridiction),
            "tribunal": self._tribunal(juridiction),
        }

        duration = time.time() - start
        self.log(f"Juridiction: {juridiction} | Type: {type_infraction} | Gravite: {gravite}", "OK")
        self.log_run("classifier", f"{infraction[:100]}", f"{juridiction}/{type_infraction}/{gravite}", duration=duration)
        return result

    def _detecter_juridiction(self, juridiction_raw, ticket):
        j = str(juridiction_raw).lower().strip()
        if any(w in j for w in ["qc", "quebec", "québec"]):
            return "QC"
        elif any(w in j for w in ["on", "ontario"]):
            return "ON"
        elif any(w in j for w in ["ny", "new york"]):
            return "NY"

        # Detection par indices dans les champs
        all_text = " ".join([str(v) for v in ticket.values()]).lower()
        if any(w in all_text for w in ["saaq", "csr", "securite routiere", "cour municipale"]):
            return "QC"
        elif any(w in all_text for w in ["hta", "highway traffic", "provincial offences"]):
            return "ON"
        elif any(w in all_text for w in ["vtl", "vehicle traffic", "dmv", "tvb"]):
            return "NY"

        return "QC"  # Default

    def _detecter_type(self, infraction):
        for type_name, keywords in self.TYPES.items():
            if any(kw in infraction for kw in keywords):
                return type_name
        return "autre"

    def _evaluer_gravite(self, type_infraction, ticket):
        base = self.GRAVITE.get(type_infraction, "moyen")

        # Ajustements
        points = ticket.get("points_inaptitude", 0)
        if points >= 6:
            base = "critique"
        elif points >= 4 and base == "moyen":
            base = "eleve"

        # Vitesse excessive (>40 km/h au dessus)
        captee = ticket.get("vitesse_captee", 0) or 0
        permise = ticket.get("vitesse_permise", 0) or 0
        if captee and permise and (captee - permise) > 40:
            base = "critique"

        return base

    def _code_applicable(self, juridiction):
        return {
            "QC": "Code de la securite routiere (C-24.2)",
            "ON": "Highway Traffic Act (HTA)",
            "NY": "Vehicle and Traffic Law (VTL)",
        }.get(juridiction, "")

    def _tribunal(self, juridiction):
        return {
            "QC": "Cour municipale du Quebec",
            "ON": "Provincial Offences Court",
            "NY": "Traffic Violations Bureau (TVB)",
        }.get(juridiction, "")
