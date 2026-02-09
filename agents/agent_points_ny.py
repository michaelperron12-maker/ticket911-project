"""
Agent NY: POINTS DMV NEW YORK — Calcul points, DRA, insurance impact
NYS DMV point system + Driver Responsibility Assessment
"""

import time
from agents.base_agent import BaseAgent


# Points DMV New York (VTL)
NY_POINTS = {
    "speeding_1_10": 3,     # 1-10 mph over
    "speeding_11_20": 4,    # 11-20 mph over
    "speeding_21_30": 6,    # 21-30 mph over
    "speeding_31_40": 8,    # 31-40 mph over
    "speeding_41_plus": 11, # 41+ mph over (license revocation)
    "red_light": 3,
    "stop_sign": 3,
    "improper_turn": 2,
    "failure_yield": 3,
    "following_too_closely": 4,
    "reckless_driving": 5,
    "cell_phone": 5,
    "texting": 5,
    "seatbelt": 0,          # Pas de points pour seatbelt NY
    "speed_camera": 0,      # $50, pas de points
    "red_light_camera": 0,  # $50, pas de points
    "improper_passing": 3,
    "unsafe_lane_change": 3,
    "child_safety_seat": 3,
}


class AgentPointsNY(BaseAgent):

    def __init__(self):
        super().__init__("Points_NY")

    def calculer(self, ticket, analyse=None):
        """
        Input: ticket NY + analyse optionnelle
        Output: calcul points DMV, DRA, impact assurance
        """
        self.log("Calcul points DMV New York...", "STEP")
        start = time.time()

        infraction = (ticket.get("infraction", "") or "").lower()
        points_ticket = ticket.get("points_inaptitude", 0)
        amende = self._parse_amende(ticket.get("amende", ""))
        exces = ticket.get("exces_vitesse", 0)

        # Determiner les points
        if points_ticket > 0:
            points = points_ticket
        else:
            points = self._estimer_points(infraction, exces)

        # Driver Responsibility Assessment (DRA)
        dra = self._calculer_dra(points)

        # Suspension/revocation
        suspension = self._evaluer_suspension(points, infraction)

        # Impact assurance NY
        assurance = self._impact_assurance_ny(points, infraction)

        # Economie si acquitte
        surcharge = 93  # NYS mandatory surcharge
        economie = {
            "amende": amende,
            "surcharge": surcharge,
            "dra_3ans": dra["montant_total"],
            "assurance_3ans": assurance["cout_supplementaire_3ans"],
            "total": amende + surcharge + dra["montant_total"] + assurance["cout_supplementaire_3ans"]
        }

        result = {
            "juridiction": "NY",
            "points_dmv": points,
            "echelle": "11 points = revocation automatique",
            "seuil_dra": "6 points en 18 mois = DRA ($300/an)",
            "seuil_suspension": "11 points en 18 mois = suspension",
            "driver_responsibility_assessment": dra,
            "suspension_info": suspension,
            "impact_assurance": assurance,
            "surcharge_ny": surcharge,
            "economie_si_acquitte": economie,
        }

        duration = time.time() - start
        self.log(f"Points DMV: {points} | DRA: {dra['applicable']} | Economie: ${economie['total']}", "OK")
        self.log_run("calculer_ny", f"Points={points}",
                     f"DRA={dra['applicable']} Economie=${economie['total']}", duration=duration)
        return result

    def _estimer_points(self, infraction, exces=0):
        """Estime les points DMV selon l'infraction"""
        if "speed" in infraction or "vitesse" in infraction or "mph" in infraction:
            if exces > 40:
                return NY_POINTS["speeding_41_plus"]
            elif exces > 30:
                return NY_POINTS["speeding_31_40"]
            elif exces > 20:
                return NY_POINTS["speeding_21_30"]
            elif exces > 10:
                return NY_POINTS["speeding_11_20"]
            else:
                return NY_POINTS["speeding_1_10"]

        if "red light" in infraction or "feu rouge" in infraction:
            if "camera" in infraction:
                return NY_POINTS["red_light_camera"]
            return NY_POINTS["red_light"]

        if "cell" in infraction or "phone" in infraction or "texting" in infraction:
            return NY_POINTS["cell_phone"]

        if "stop" in infraction:
            return NY_POINTS["stop_sign"]

        if "reckless" in infraction:
            return NY_POINTS["reckless_driving"]

        if "seatbelt" in infraction or "ceinture" in infraction:
            return NY_POINTS["seatbelt"]

        if "speed camera" in infraction or "school zone camera" in infraction:
            return NY_POINTS["speed_camera"]

        return 3  # Default

    def _calculer_dra(self, points):
        """Driver Responsibility Assessment — $300/an x 3 ans si 6+ points en 18 mois"""
        if points >= 6:
            base = 300
            extra_per_point = 75  # $75 par point au-dessus de 6
            extra_points = max(0, points - 6)
            annual = base + (extra_per_point * extra_points)
            return {
                "applicable": True,
                "raison": f"{points} points >= 6 en 18 mois",
                "montant_annuel": annual,
                "duree_ans": 3,
                "montant_total": annual * 3,
                "note": f"DRA: ${annual}/an x 3 ans = ${annual * 3} total"
            }
        return {
            "applicable": False,
            "raison": f"{points} points < 6 (seuil DRA)",
            "montant_annuel": 0,
            "duree_ans": 0,
            "montant_total": 0,
            "note": "Pas de DRA applicable"
        }

    def _evaluer_suspension(self, points, infraction):
        """Evaluer risque de suspension/revocation"""
        if points >= 11:
            return {
                "risque": "REVOCATION",
                "note": "11+ points en 18 mois = revocation automatique du permis NY",
                "duree": "Minimum 6 mois",
                "action": "Consulter avocat IMMEDIATEMENT"
            }
        elif points >= 8:
            return {
                "risque": "ELEVE",
                "note": f"{points} points — proche du seuil de 11 pour revocation",
                "duree": "N/A",
                "action": "Contester fortement recommande + Defensive Driving Course (-4 pts)"
            }
        elif points >= 6:
            return {
                "risque": "MOYEN",
                "note": f"{points} points — DRA applicable + proche suspension",
                "duree": "N/A",
                "action": "Defensive Driving Course recommande (-4 pts, -10% assurance)"
            }
        else:
            return {
                "risque": "FAIBLE",
                "note": f"{points} points — sous les seuils critiques",
                "duree": "N/A",
                "action": "Contester si possible pour eviter points"
            }

    def _impact_assurance_ny(self, points, infraction):
        """Impact sur les primes d'assurance a New York"""
        prime_moyenne_ny = 2200  # Moyenne NY annuelle (une des plus cheres aux US)

        if points == 0:
            pct = 0
        elif points <= 3:
            pct = 15
        elif points <= 5:
            pct = 30
        elif points <= 8:
            pct = 50
        else:
            pct = 80

        # Aggravants
        if "reckless" in infraction:
            pct += 30
        if "dui" in infraction or "dwi" in infraction:
            pct += 100

        augmentation = int(prime_moyenne_ny * pct / 100)

        return {
            "prime_moyenne_ny": prime_moyenne_ny,
            "augmentation_pct": pct,
            "augmentation_annuelle": augmentation,
            "cout_supplementaire_3ans": augmentation * 3,
            "note": f"+{pct}% soit +${augmentation}/an pendant 3-5 ans",
            "astuce": "Defensive Driving Course (DDC): -10% sur assurance pendant 3 ans"
        }

    def _parse_amende(self, amende_str):
        if isinstance(amende_str, (int, float)):
            return int(amende_str)
        if isinstance(amende_str, str):
            import re
            nums = re.findall(r'\d+', amende_str.replace(",", ""))
            if nums:
                return int(nums[0])
        return 200  # Default NY
