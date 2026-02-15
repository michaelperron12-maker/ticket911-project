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
        "feu_rouge": ["feu rouge", "red light", "brule un feu", "brûlé un feu", "grille un feu", "feu de circulation"],
        "signal": ["signalisation non respectee", "signal d'arret"],
        "stop": ["stop", "arrêt", "arret", "panneau d'arret", "panneau d'arrêt"],
        "cellulaire": ["cellulaire", "cell", "phone", "handheld", "texting", "telephone"],
        "ceinture": ["ceinture", "seatbelt", "seat belt"],
        "alcool": ["alcool", "alcohol", "ivresse", "impaired", "dui", "dwi", "taux"],
        "conduite_dangereuse": ["dangereuse", "dangerous", "careless", "stunt", "racing", "course"],
        "stationnement": ["stationnement", "stationne", "stationné", "parking", "parcometre", "parcomètre", "interdit de stationner"],
        "permis": ["permis", "license", "licence", "suspendu", "suspended", "revoque"],
        "assurance": ["assurance", "insurance", "preuve"],
    }

    # Gravite par type
    GRAVITE = {
        "vitesse": "moyen",
        "feu_rouge": "moyen",
        "signal": "moyen",
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

    # Villes et indices QC (pour detection juridiction)
    VILLES_QC = [
        "montreal", "montréal", "quebec", "québec", "laval", "gatineau", "longueuil",
        "sherbrooke", "levis", "lévis", "saguenay", "trois-rivieres", "trois-rivières",
        "terrebonne", "repentigny", "brossard", "drummondville", "saint-jean",
        "saint-jerome", "saint-jérôme", "granby", "blainville", "rimouski",
        "victoriaville", "mascouche", "shawinigan", "chateauguay", "châteauguay",
        "anjou", "rosemont", "verdun", "lachine", "lasalle", "outremont",
        "villeray", "hochelaga", "ahuntsic", "mercier", "riviere-des-prairies",
        "rivière-des-prairies", "pointe-aux-trembles", "saint-laurent", "saint-leonard",
        "saint-léonard", "plateau", "mont-royal", "westmount", "cote-des-neiges",
        "côte-des-neiges", "dorval", "pierrefonds", "beaconsfield",
    ]

    INDICES_QC = [
        "saaq", "csr", "securite routiere", "sécurité routière", "cour municipale",
        "district judiciaire", "code de la securite", "code de la sécurité",
        "c-24.2", "art.", "constat d'infraction", "constat d infraction",
        "ville de", "arrondissement", "municipalite", "municipalité",
        "procureur general du quebec", "procureur général du québec",
        "spvm", "sq ", "surete du quebec", "sûreté du québec",
    ]

    def _detecter_juridiction(self, juridiction_raw, ticket):
        """Detection robuste: TOUJOURS verifier les indices dans les champs du ticket,
        meme si juridiction_raw a une valeur. L'adresse et le texte trumpent la valeur OCR."""

        # ETAPE 1: Collecter TOUT le texte du ticket pour analyse
        all_text = " ".join([str(v) for v in ticket.values()]).lower()
        lieu = str(ticket.get("lieu", "")).lower()
        infraction = str(ticket.get("infraction", "")).lower()

        # ETAPE 2: Detection forte par adresse/lieu — PRIORITAIRE
        # Si le lieu contient une ville du Quebec, c'est QC peu importe ce que l'OCR dit
        if any(v in lieu for v in self.VILLES_QC):
            self.log(f"Juridiction QC detectee par lieu: {lieu[:80]}", "OK")
            return "QC"

        # Texte en francais dans l'infraction → forte probabilite QC
        mots_francais = ["stationné", "stationne", "véhicule", "vehicule", "routier",
                         "signalisation", "prohibe", "interdit", "endroit", "ayant",
                         "excès", "exces", "conduite", "circulation"]
        nb_mots_fr = sum(1 for m in mots_francais if m in infraction)
        if nb_mots_fr >= 2:
            self.log(f"Juridiction QC detectee par langue francaise ({nb_mots_fr} mots)", "OK")
            return "QC"

        # Villes QC dans TOUS les champs
        if any(v in all_text for v in self.VILLES_QC):
            self.log("Juridiction QC detectee par ville dans les champs", "OK")
            return "QC"

        # Indices QC (institutions, lois, termes)
        if any(w in all_text for w in self.INDICES_QC):
            self.log("Juridiction QC detectee par indices institutionnels", "OK")
            return "QC"

        # ETAPE 3: Verifier la valeur brute du champ juridiction
        j = str(juridiction_raw).lower().strip()

        if any(w in j for w in ["qc", "quebec", "québec"]):
            return "QC"
        if any(v in j for v in self.VILLES_QC):
            return "QC"
        if "district judiciaire" in j or "district" in j:
            return "QC"

        # ETAPE 4: Indices Ontario (seulement si aucun indice QC)
        villes_on = ["toronto", "ottawa", "mississauga", "hamilton", "brampton",
                     "markham", "vaughan", "london", "kitchener", "windsor"]
        if any(v in lieu for v in villes_on):
            return "ON"
        if any(w in j for w in ["on", "ontario"]):
            # Verifier que c'est vraiment Ontario et pas un faux positif OCR
            if not any(v in all_text for v in self.VILLES_QC):
                return "ON"
        if any(w in all_text for w in ["hta", "highway traffic", "provincial offences"]):
            return "ON"

        # ETAPE 5: Indices New York
        if any(w in j for w in ["ny", "new york"]):
            return "NY"
        if any(w in all_text for w in ["vtl", "vehicle traffic", "dmv", "tvb",
                                        "new york", "brooklyn", "manhattan", "bronx"]):
            return "NY"

        return "QC"  # Default = Quebec

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
