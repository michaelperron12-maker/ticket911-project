"""
Agent QC: POINTS SAAQ QUEBEC — Bareme complet + impact assurance QC
Regime de points d'inaptitude SAAQ, permis probatoire, suspension
"""

import time
import re
from agents.base_agent import BaseAgent


# Points d'inaptitude SAAQ (Quebec)
SAAQ_POINTS = {
    "vitesse_1_20": 1,
    "vitesse_21_30": 2,
    "vitesse_31_45": 3,
    "vitesse_46_60": 5,
    "vitesse_61_80": 7,
    "vitesse_81_100": 10,
    "vitesse_101_120": 12,
    "vitesse_121_plus": 15,  # = revocation immediate
    "feu_rouge": 3,
    "stop": 3,
    "cellulaire": 5,
    "ceinture": 3,
    "depassement_interdit": 3,
    "conduite_dangereuse": 6,
    "course_rue": 12,
    "delit_fuite": 9,
    "non_respect_agent": 3,
    "photo_radar": 0,  # Pas de points pour photo radar (infraction au vehicule)
}

# Seuils SAAQ
SEUILS_SAAQ = {
    "permis_probatoire": 4,     # Suspension pour nouveaux conducteurs
    "avertissement": 8,          # Lettre SAAQ
    "suspension_12pts": 12,      # Suspension 3 mois
    "revocation": 15,            # Revocation du permis
}


class AgentPointsQC(BaseAgent):

    def __init__(self):
        super().__init__("Points_QC")

    def calculer(self, ticket, analyse=None, contexte_enrichi=None):
        """
        Input: ticket QC + analyse optionnelle + contexte enrichi (meteo/routes)
        Output: calcul points SAAQ, impact assurance QC
        """
        self.log("Calcul points SAAQ Quebec...", "STEP")
        start = time.time()

        infraction = (ticket.get("infraction", "") or "").lower()
        points_ticket = ticket.get("points_inaptitude", 0)
        amende = self._parse_amende(ticket.get("amende", ""))
        vitesse_captee = ticket.get("vitesse_captee", 0) or 0
        vitesse_permise = ticket.get("vitesse_permise", 0) or 0
        exces = max(0, vitesse_captee - vitesse_permise) if vitesse_captee else 0
        appareil = (ticket.get("appareil", "") or "").lower()

        # Photo radar = 0 points
        is_photo_radar = any(w in appareil for w in ["photo", "radar fixe", "automatique"])

        # Determiner les points
        if is_photo_radar:
            points = 0
        elif points_ticket > 0:
            points = points_ticket
        else:
            points = self._estimer_points(infraction, exces)

        # Amendes specifiques QC
        amende_info = self._calculer_amende_qc(infraction, exces)

        # Consequences SAAQ
        consequences = self._evaluer_consequences_saaq(points, is_photo_radar)

        # Grand exces de vitesse
        grand_exces = self._evaluer_grand_exces(exces)

        # Impact assurance QC
        assurance = self._impact_assurance_qc(points, infraction, is_photo_radar)

        # Contribution au FAVR
        contribution_favr = self._calculer_favr(amende)

        # Economie si acquitte
        economie_assurance = assurance.get("cout_supplementaire_3ans", 0)
        economie = {
            "amende": amende,
            "contribution_favr": contribution_favr,
            "assurance_3ans": economie_assurance,
            "total": amende + contribution_favr + economie_assurance
        }

        # Ajouter contexte conditions routieres si disponible
        notes_contexte = []
        if contexte_enrichi:
            roads = contexte_enrichi.get("road_conditions", [])
            for r in roads:
                if r.get("type") in ("construction", "travaux", "chantier", "chantiers"):
                    notes_contexte.append(f"Zone travaux active: {r.get('road', '')} — amende potentiellement doublee (art. 329.2 CSR)")
            w = contexte_enrichi.get("weather")
            if w:
                precip = w.get("precipitation_mm") or 0
                snow = w.get("snow_cm") or 0
                if precip > 5 or snow > 2:
                    notes_contexte.append(f"Conditions meteo defavorables: precip {precip}mm, neige {snow}cm — argument de defense possible")

        result = {
            "juridiction": "QC",
            "points_saaq": points,
            "is_photo_radar": is_photo_radar,
            "echelle": "15 points = revocation automatique",
            "seuils": SEUILS_SAAQ,
            "consequences_saaq": consequences,
            "grand_exces": grand_exces,
            "amende_info": amende_info,
            "contribution_favr": contribution_favr,
            "impact_assurance": assurance,
            "economie_si_acquitte": economie,
            "notes_contexte": notes_contexte,
        }

        duration = time.time() - start
        self.log(f"Points SAAQ: {points} | Photo radar: {is_photo_radar} | Economie: ${economie['total']}", "OK")
        self.log_run("calculer_qc", f"Points={points} PhotoRadar={is_photo_radar}",
                     f"Economie=${economie['total']}", duration=duration)
        return result

    def _estimer_points(self, infraction, exces=0):
        """Estime les points SAAQ selon l'infraction et l'exces"""
        if "vitesse" in infraction or "exces" in infraction or "km/h" in infraction:
            if exces >= 121: return SAAQ_POINTS["vitesse_121_plus"]
            elif exces >= 101: return SAAQ_POINTS["vitesse_101_120"]
            elif exces >= 81: return SAAQ_POINTS["vitesse_81_100"]
            elif exces >= 61: return SAAQ_POINTS["vitesse_61_80"]
            elif exces >= 46: return SAAQ_POINTS["vitesse_46_60"]
            elif exces >= 31: return SAAQ_POINTS["vitesse_31_45"]
            elif exces >= 21: return SAAQ_POINTS["vitesse_21_30"]
            else: return SAAQ_POINTS["vitesse_1_20"]

        if "feu rouge" in infraction:
            return SAAQ_POINTS["feu_rouge"]
        if "cellulaire" in infraction or "telephone" in infraction:
            return SAAQ_POINTS["cellulaire"]
        if "stop" in infraction or "arret" in infraction:
            return SAAQ_POINTS["stop"]
        if "ceinture" in infraction:
            return SAAQ_POINTS["ceinture"]
        if "dangereuse" in infraction:
            return SAAQ_POINTS["conduite_dangereuse"]
        if "course" in infraction:
            return SAAQ_POINTS["course_rue"]
        if "delit de fuite" in infraction or "fuite" in infraction:
            return SAAQ_POINTS["delit_fuite"]
        if "depassement" in infraction:
            return SAAQ_POINTS["depassement_interdit"]

        return 2  # Default

    def _calculer_amende_qc(self, infraction, exces):
        """Bareme d'amendes Quebec (approximatif)"""
        if "vitesse" in infraction or "exces" in infraction:
            if exces <= 20:
                return {"min": 15 + exces * 10, "max": 15 + exces * 10, "note": f"Exces {exces} km/h: $10/km"}
            elif exces <= 30:
                return {"min": 220, "max": 320, "note": f"Exces {exces} km/h"}
            elif exces <= 45:
                return {"min": 320, "max": 480, "note": f"Exces {exces} km/h — double en zone"}
            elif exces <= 60:
                return {"min": 480, "max": 720, "note": f"Exces {exces} km/h + saisie possible"}
            else:
                return {"min": 720, "max": 1230, "note": f"Grand exces {exces} km/h + saisie 7-30j"}

        if "cellulaire" in infraction:
            return {"min": 300, "max": 600, "note": "Premiere offense. Recidive: $600-$1200"}
        if "feu rouge" in infraction:
            return {"min": 150, "max": 300, "note": "Feu rouge"}
        if "stop" in infraction:
            return {"min": 100, "max": 200, "note": "Non-respect du stop"}
        if "ceinture" in infraction:
            return {"min": 200, "max": 300, "note": "Ceinture non bouclee"}

        return {"min": 100, "max": 500, "note": "Variable selon l'infraction"}

    def _evaluer_consequences_saaq(self, points, is_photo_radar):
        """Consequences specifiques SAAQ"""
        consequences = []

        if is_photo_radar:
            consequences.append("Photo radar: 0 points d'inaptitude (infraction au vehicule, pas au conducteur)")
            consequences.append("Proprietaire responsable de l'amende, mais peut nommer le conducteur")
            return consequences

        if points >= 15:
            consequences.append("REVOCATION du permis — convocation SAAQ obligatoire")
            consequences.append("Interdiction de conduire minimum 3 mois")
            consequences.append("Examen theorique + pratique pour recupérer le permis")
        elif points >= 12:
            consequences.append("Suspension du permis 3 mois — lettre SAAQ")
            consequences.append("Avis de sanction par courrier recommande")
        elif points >= 8:
            consequences.append("Lettre d'avertissement de la SAAQ")
            consequences.append("Prochaine infraction pourrait mener a la suspension")
        elif points >= 4:
            consequences.append("Risque pour permis probatoire (seuil: 4 points)")
            consequences.append("Si nouveau conducteur: suspension immediate")

        consequences.append(f"+{points} points au dossier SAAQ (duree: 2 ans a compter de la declaration de culpabilite)")

        return consequences

    def _evaluer_grand_exces(self, exces):
        """Grand exces de vitesse — saisie du vehicule"""
        if exces >= 50:
            return {
                "applicable": True,
                "type": "tres_grand_exces",
                "saisie_jours": 30,
                "note": f"Exces de {exces} km/h: saisie 30 jours + amende majoree + suspension possible"
            }
        elif exces >= 40:
            return {
                "applicable": True,
                "type": "grand_exces",
                "saisie_jours": 7,
                "note": f"Exces de {exces} km/h: saisie 7 jours + amende majoree"
            }
        return {"applicable": False, "type": "normal", "saisie_jours": 0, "note": ""}

    def _impact_assurance_qc(self, points, infraction, is_photo_radar):
        """Impact assurance automobile au Quebec"""
        prime_moyenne_qc = 900  # Moyenne QC annuelle

        if is_photo_radar:
            return {
                "prime_moyenne_qc": prime_moyenne_qc,
                "augmentation_pct": 0,
                "augmentation_annuelle": 0,
                "cout_supplementaire_3ans": 0,
                "note": "Photo radar: aucun impact sur l'assurance (0 points)"
            }

        if points == 0:
            pct = 0
        elif points <= 2:
            pct = 10
        elif points <= 4:
            pct = 20
        elif points <= 6:
            pct = 35
        elif points <= 9:
            pct = 50
        else:
            pct = 75

        if "alcool" in infraction or "facultes" in infraction:
            pct += 100
        if "dangereuse" in infraction or "course" in infraction:
            pct += 40

        augmentation = int(prime_moyenne_qc * pct / 100)

        return {
            "prime_moyenne_qc": prime_moyenne_qc,
            "augmentation_pct": pct,
            "augmentation_annuelle": augmentation,
            "cout_supplementaire_3ans": augmentation * 3,
            "note": f"+{pct}% soit +${augmentation}/an pendant 3 ans"
        }

    def _calculer_favr(self, amende):
        """Contribution au Fonds d'aide aux victimes (FAVR)"""
        if amende <= 100:
            return 87
        elif amende <= 500:
            return 107
        else:
            return 127

    def _parse_amende(self, amende_str):
        if isinstance(amende_str, (int, float)):
            return int(amende_str)
        if isinstance(amende_str, str):
            nums = re.findall(r'\d+', amende_str.replace(",", ""))
            if nums:
                return int(nums[0])
        return 200  # Default QC
