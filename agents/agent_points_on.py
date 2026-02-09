"""
Agent ON: POINTS ONTARIO — MTO demerit points + insurance impact
Ministry of Transportation Ontario, novice driver program, insurance
"""

import time
import re
from agents.base_agent import BaseAgent


# Points de demerite MTO Ontario
MTO_POINTS = {
    "speeding_1_15": 0,      # No points for 1-15 km/h over
    "speeding_16_29": 3,
    "speeding_30_49": 4,
    "speeding_50_plus": 6,   # Also stunt driving territory
    "red_light": 3,
    "stop_sign": 3,
    "handheld_device": 3,
    "seatbelt": 2,
    "careless_driving": 6,
    "stunt_driving": 6,
    "racing": 6,
    "following_closely": 4,
    "improper_passing": 3,
    "failure_yield": 3,
    "improper_turn": 2,
    "failure_signal": 2,
    "red_light_camera": 0,   # Pas de points (infraction au proprietaire)
    "no_insurance": 0,       # Pas de points mais amende $5,000-$25,000
}

# Seuils MTO
SEUILS_MTO = {
    "full_licence": {
        "warning_letter": 6,
        "interview": 9,
        "suspension_30d": 15,
    },
    "novice_g1": {
        "warning_letter": 2,
        "suspension_60d": 6,
        "cancel": 9,
    },
    "novice_g2": {
        "warning_letter": 2,
        "suspension_60d": 6,
        "cancel": 9,
    },
}


class AgentPointsON(BaseAgent):

    def __init__(self):
        super().__init__("Points_ON")

    def calculer(self, ticket, analyse=None):
        """
        Input: ticket ON + analyse optionnelle
        Output: calcul points MTO, consequences, assurance ON
        """
        self.log("Calcul points MTO Ontario...", "STEP")
        start = time.time()

        infraction = (ticket.get("infraction", "") or "").lower()
        points_ticket = ticket.get("points_inaptitude", 0)
        amende = self._parse_amende(ticket.get("amende", ""))
        exces = ticket.get("exces_vitesse", 0) or 0
        vitesse_captee = ticket.get("vitesse_captee", 0) or 0
        vitesse_permise = ticket.get("vitesse_permise", 0) or 0
        if not exces and vitesse_captee and vitesse_permise:
            exces = vitesse_captee - vitesse_permise

        # Red light camera?
        appareil = (ticket.get("appareil", "") or "").lower()
        is_camera = any(w in appareil for w in ["camera", "photo", "automated"])

        # Determiner points
        if is_camera and "red light" in infraction:
            points = 0
        elif points_ticket > 0:
            points = points_ticket
        else:
            points = self._estimer_points(infraction, exces)

        # Stunt driving?
        is_stunt = exces >= 50 or "stunt" in infraction or "racing" in infraction

        # Consequences MTO
        consequences = self._evaluer_consequences_mto(points, is_stunt)

        # Impact assurance Ontario
        assurance = self._impact_assurance_on(points, infraction, is_stunt, is_camera)

        # Frais specifiques Ontario
        victim_surcharge = int(amende * 0.20) if amende else 0

        # Economie
        economie_assurance = assurance.get("cout_supplementaire_3ans", 0)
        economie = {
            "amende": amende,
            "victim_surcharge": victim_surcharge,
            "assurance_3ans": economie_assurance,
            "total": amende + victim_surcharge + economie_assurance
        }

        result = {
            "juridiction": "ON",
            "points_mto": points,
            "is_camera": is_camera,
            "is_stunt": is_stunt,
            "echelle": "15 points = suspension 30j (permis complet)",
            "seuils": SEUILS_MTO,
            "consequences_mto": consequences,
            "impact_assurance": assurance,
            "victim_fine_surcharge": victim_surcharge,
            "economie_si_acquitte": economie,
        }

        duration = time.time() - start
        self.log(f"Points MTO: {points} | Stunt: {is_stunt} | Camera: {is_camera} | Economie: ${economie['total']}", "OK")
        self.log_run("calculer_on", f"Points={points} Stunt={is_stunt}",
                     f"Economie=${economie['total']}", duration=duration)
        return result

    def _estimer_points(self, infraction, exces=0):
        if "speed" in infraction or "vitesse" in infraction:
            if exces >= 50:
                return MTO_POINTS["speeding_50_plus"]
            elif exces >= 30:
                return MTO_POINTS["speeding_30_49"]
            elif exces >= 16:
                return MTO_POINTS["speeding_16_29"]
            else:
                return MTO_POINTS["speeding_1_15"]

        if "red light" in infraction or "feu rouge" in infraction:
            return MTO_POINTS["red_light"]
        if "handheld" in infraction or "cell" in infraction or "phone" in infraction:
            return MTO_POINTS["handheld_device"]
        if "stop" in infraction:
            return MTO_POINTS["stop_sign"]
        if "careless" in infraction or "dangereuse" in infraction:
            return MTO_POINTS["careless_driving"]
        if "stunt" in infraction or "racing" in infraction:
            return MTO_POINTS["stunt_driving"]
        if "seatbelt" in infraction or "ceinture" in infraction:
            return MTO_POINTS["seatbelt"]
        if "following" in infraction or "tailgating" in infraction:
            return MTO_POINTS["following_closely"]

        return 3  # Default

    def _evaluer_consequences_mto(self, points, is_stunt):
        consequences = []

        if is_stunt:
            consequences.append("STUNT DRIVING: saisie vehicule 14 jours IMMEDIATE")
            consequences.append("Suspension administrative du permis 30 jours IMMEDIATE")
            consequences.append("Si reconnu coupable: amende $2,000-$10,000 + suspension 1-3 ans")

        if points >= 15:
            consequences.append("Suspension du permis 30 jours (seuil 15 points)")
        if points >= 9:
            consequences.append("Entrevue MTO obligatoire — risque de suspension")
        if points >= 6:
            consequences.append("Lettre d'avertissement du MTO")
            consequences.append("NOVICE (G1/G2): suspension 60 jours + 6 mois de probation")

        consequences.append(f"+{points} points de demerite (duree: 2 ans)")

        if points == 0 and not is_stunt:
            consequences.append("0 points de demerite — aucune consequence sur le permis")

        return consequences

    def _impact_assurance_on(self, points, infraction, is_stunt, is_camera):
        """Impact assurance auto Ontario — une des plus cheres au Canada"""
        prime_moyenne_on = 1650  # Moyenne Ontario annuelle

        if is_camera:
            return {
                "prime_moyenne_on": prime_moyenne_on,
                "augmentation_pct": 0,
                "augmentation_annuelle": 0,
                "cout_supplementaire_3ans": 0,
                "note": "Camera: aucun impact sur l'assurance (0 points)"
            }

        if is_stunt:
            pct = 150  # Stunt driving = catastrophique pour l'assurance
        elif points == 0:
            pct = 0
        elif points <= 2:
            pct = 10
        elif points <= 3:
            pct = 20
        elif points <= 4:
            pct = 35
        elif points <= 6:
            pct = 50
        else:
            pct = 75

        if "careless" in infraction:
            pct += 50
        if "no insurance" in infraction:
            pct += 100

        augmentation = int(prime_moyenne_on * pct / 100)

        return {
            "prime_moyenne_on": prime_moyenne_on,
            "augmentation_pct": pct,
            "augmentation_annuelle": augmentation,
            "cout_supplementaire_3ans": augmentation * 3,
            "note": f"+{pct}% soit +${augmentation}/an pendant 3 ans"
        }

    def _parse_amende(self, amende_str):
        if isinstance(amende_str, (int, float)):
            return int(amende_str)
        if isinstance(amende_str, str):
            nums = re.findall(r'\d+', amende_str.replace(",", ""))
            if nums:
                return int(nums[0])
        return 300  # Default ON
