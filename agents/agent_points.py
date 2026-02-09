"""
Agent Phase 2: CALCUL POINTS — Bareme par juridiction
QC: SAAQ (15 pts max) | ON: 9 pts suspension | NY: DMV (11 pts)
"""

import time
from agents.base_agent import BaseAgent


class AgentPoints(BaseAgent):

    def __init__(self):
        super().__init__("Points")

    # Baremes de points par juridiction et type d'infraction
    POINTS_QC = {
        "vitesse_1_20": 1,
        "vitesse_21_30": 2,
        "vitesse_31_45": 3,
        "vitesse_46_60": 5,
        "vitesse_61_plus": 10,
        "feu_rouge": 3,
        "stop": 3,
        "cellulaire": 5,
        "ceinture": 3,
        "conduite_dangereuse": 6,
        "delit_fuite": 9,
        "alcool": 0,  # Criminal, pas de points SAAQ
    }

    POINTS_ON = {
        "vitesse_1_15": 0,
        "vitesse_16_29": 3,
        "vitesse_30_49": 4,
        "vitesse_50_plus": 6,
        "red_light": 3,
        "stop": 3,
        "handheld": 3,
        "seatbelt": 2,
        "careless": 6,
        "racing": 6,
    }

    POINTS_NY = {
        "vitesse_1_10": 3,
        "vitesse_11_20": 4,
        "vitesse_21_30": 6,
        "vitesse_31_40": 8,
        "vitesse_41_plus": 11,
        "red_light": 3,
        "stop": 3,
        "cell_phone": 5,
        "texting": 5,
        "reckless": 5,
        "no_seatbelt": 0,
    }

    SEUILS = {
        "QC": {"suspension": 15, "lettre_avertissement": 8, "revocation_probatoire": 4},
        "ON": {"suspension_30j": 9, "suspension_6mois": 15, "novice_suspension": 2},
        "NY": {"suspension": 11, "surcharge": 6, "assessment_fee": 6},
    }

    def calculer(self, ticket, classification):
        """
        Input: ticket + classification
        Output: calcul detaille des points et consequences
        """
        self.log("Calcul des points d'inaptitude...", "STEP")
        start = time.time()

        juridiction = classification.get("juridiction", "QC")
        type_inf = classification.get("type_infraction", "autre")
        points_declares = ticket.get("points_inaptitude", 0) or 0

        # Calculer les points selon le bareme
        points_bareme = self._calculer_bareme(juridiction, type_inf, ticket)

        # Utiliser les points declares si fournis, sinon le bareme
        points_final = points_declares if points_declares else points_bareme

        # Consequences
        consequences = self._evaluer_consequences(juridiction, points_final)

        # Impact assurance
        impact_assurance = self._estimer_impact_assurance(juridiction, type_inf, points_final)

        result = {
            "juridiction": juridiction,
            "points_declares": points_declares,
            "points_bareme": points_bareme,
            "points_final": points_final,
            "max_juridiction": self.SEUILS.get(juridiction, {}).get("suspension", 15),
            "consequences": consequences,
            "impact_assurance": impact_assurance,
            "economie_si_acquitte": self._calculer_economie(ticket, impact_assurance),
        }

        duration = time.time() - start
        self.log(f"Points: {points_final} / {result['max_juridiction']} ({juridiction}) | Assurance: {impact_assurance}", "OK")
        self.log_run("calculer", f"{juridiction}/{type_inf}/{points_final}pts",
                     f"Consequences: {len(consequences)}", duration=duration)
        return result

    def _calculer_bareme(self, juridiction, type_inf, ticket):
        captee = ticket.get("vitesse_captee", 0) or 0
        permise = ticket.get("vitesse_permise", 0) or 0
        exces = max(0, captee - permise)

        if juridiction == "QC":
            if type_inf == "vitesse":
                if exces <= 20: return self.POINTS_QC["vitesse_1_20"]
                elif exces <= 30: return self.POINTS_QC["vitesse_21_30"]
                elif exces <= 45: return self.POINTS_QC["vitesse_31_45"]
                elif exces <= 60: return self.POINTS_QC["vitesse_46_60"]
                else: return self.POINTS_QC["vitesse_61_plus"]
            return self.POINTS_QC.get(type_inf, 2)

        elif juridiction == "ON":
            if type_inf == "vitesse":
                if exces <= 15: return self.POINTS_ON["vitesse_1_15"]
                elif exces <= 29: return self.POINTS_ON["vitesse_16_29"]
                elif exces <= 49: return self.POINTS_ON["vitesse_30_49"]
                else: return self.POINTS_ON["vitesse_50_plus"]
            mapping = {"feu_rouge": "red_light", "cellulaire": "handheld",
                       "ceinture": "seatbelt", "conduite_dangereuse": "careless"}
            on_type = mapping.get(type_inf, type_inf)
            return self.POINTS_ON.get(on_type, 3)

        elif juridiction == "NY":
            if type_inf == "vitesse":
                if exces <= 10: return self.POINTS_NY["vitesse_1_10"]
                elif exces <= 20: return self.POINTS_NY["vitesse_11_20"]
                elif exces <= 30: return self.POINTS_NY["vitesse_21_30"]
                elif exces <= 40: return self.POINTS_NY["vitesse_31_40"]
                else: return self.POINTS_NY["vitesse_41_plus"]
            mapping = {"feu_rouge": "red_light", "cellulaire": "cell_phone"}
            ny_type = mapping.get(type_inf, type_inf)
            return self.POINTS_NY.get(ny_type, 3)

        return 2  # Default

    def _evaluer_consequences(self, juridiction, points):
        consequences = []
        seuils = self.SEUILS.get(juridiction, {})

        if juridiction == "QC":
            if points >= 15:
                consequences.append("Suspension du permis (revocation SAAQ)")
            if points >= 8:
                consequences.append("Lettre d'avertissement de la SAAQ")
            if points >= 4:
                consequences.append("Risque de revocation pour permis probatoire")
            consequences.append(f"+{points} points d'inaptitude au dossier SAAQ (duree: 2 ans)")

        elif juridiction == "ON":
            if points >= 9:
                consequences.append("Suspension du permis 30 jours")
            if points >= 15:
                consequences.append("Suspension du permis 6 mois")
            if points >= 2:
                consequences.append("Risque pour permis G1/G2 (novice)")
            consequences.append(f"+{points} points de demeure au dossier (duree: 2 ans)")

        elif juridiction == "NY":
            if points >= 11:
                consequences.append("Suspension du permis DMV")
            if points >= 6:
                consequences.append("Driver Responsibility Assessment fee ($300/an x 3 ans)")
            consequences.append(f"+{points} points DMV au dossier (duree: 18 mois)")

        return consequences

    def _estimer_impact_assurance(self, juridiction, type_inf, points):
        # Estimations basees sur moyennes de l'industrie
        base_impact = {
            "vitesse": 15,  # +15% en moyenne
            "feu_rouge": 20,
            "stop": 10,
            "cellulaire": 25,
            "ceinture": 5,
            "conduite_dangereuse": 50,
            "alcool": 100,
        }
        pct = base_impact.get(type_inf, 10)

        # Ajuster selon points
        if points >= 6:
            pct = int(pct * 1.5)

        prime_moyenne = {"QC": 900, "ON": 1500, "NY": 2000}.get(juridiction, 1200)
        impact_annuel = round(prime_moyenne * pct / 100)

        return {
            "augmentation_pct": pct,
            "impact_annuel_estime": impact_annuel,
            "impact_3ans": impact_annuel * 3,
            "note": f"+{pct}% sur la prime pendant 3 ans (~${impact_annuel}/an)"
        }

    def _calculer_economie(self, ticket, impact_assurance):
        amende_str = str(ticket.get("amende", "0"))
        import re
        montants = re.findall(r"(\d+)", amende_str)
        amende = int(montants[0]) if montants else 0

        return {
            "amende": amende,
            "assurance_3ans": impact_assurance.get("impact_3ans", 0),
            "total": amende + impact_assurance.get("impact_3ans", 0),
            "note": f"Economie potentielle si acquitte: ${amende} (amende) + ${impact_assurance.get('impact_3ans', 0)} (assurance) = ${amende + impact_assurance.get('impact_3ans', 0)}"
        }
