"""
Agent NY: PROCEDURE NEW YORK — VTL-226, TVB rules, court deadlines
Specifique a NYC Traffic Violations Bureau et NY courts hors NYC
"""

import time
from datetime import datetime, timedelta
from agents.base_agent import BaseAgent


class AgentProcedureNY(BaseAgent):

    def __init__(self):
        super().__init__("Procedure_NY")

    def determiner_procedure(self, ticket):
        """
        Input: ticket NY
        Output: procedure NY specifique (TVB vs regular court)
        """
        self.log("Determination procedure NY...", "STEP")
        start = time.time()

        lieu = (ticket.get("lieu", "") or "").lower()
        infraction = (ticket.get("infraction", "") or "").lower()
        date_ticket = ticket.get("date", "")

        # Determiner si NYC (5 boroughs = TVB) ou hors NYC
        nyc_boroughs = ["manhattan", "brooklyn", "bronx", "queens", "staten island",
                        "new york city", "nyc", "new york, ny"]
        is_nyc = any(b in lieu for b in nyc_boroughs)

        # Calculer delai
        jours_restants = 30
        urgence = "normal"
        if date_ticket:
            try:
                dt = datetime.strptime(date_ticket, "%Y-%m-%d")
                deadline = dt + timedelta(days=30)
                jours_restants = (deadline - datetime.now()).days
                if jours_restants < 0:
                    urgence = "EXPIRE"
                elif jours_restants <= 7:
                    urgence = "URGENT"
                elif jours_restants <= 15:
                    urgence = "attention"
            except ValueError:
                pass

        if is_nyc:
            result = self._procedure_tvb(ticket, jours_restants, urgence)
        else:
            result = self._procedure_hors_nyc(ticket, jours_restants, urgence, lieu)

        duration = time.time() - start
        tribunal = result.get("tribunal", "?")
        self.log(f"NY {'TVB' if is_nyc else 'Court'} | {jours_restants}j restants | {urgence}", "OK")
        self.log_run("determiner_procedure_ny", f"NY lieu={lieu[:50]}",
                     f"TVB={is_nyc} Jours={jours_restants}", duration=duration)
        return result

    def _procedure_tvb(self, ticket, jours_restants, urgence):
        """NYC Traffic Violations Bureau — PAS de plea bargaining"""
        return {
            "juridiction": "NY",
            "tribunal": "NYC Traffic Violations Bureau (TVB)",
            "tvb": True,
            "plea_bargain": False,
            "delai_contestation": 30,
            "jours_restants": jours_restants,
            "urgence": urgence,
            "etapes": [
                "1. Plaider 'Not Guilty' en ligne sur nyc.gov/pay-or-dispute ou par courrier dans 30 jours",
                "2. TVB assigne une date d'audience (hearing date) — generalement 4-8 semaines",
                "3. Demander disclosure: calibration records radar, maintenance logs, officer training",
                "4. Preparer defense: comparaitre devant Administrative Law Judge (ALJ)",
                "5. Audience TVB: pas de jury, ALJ decide — pas de plea bargain possible",
                "6. Si coupable: payer amende + points. Si acquitte: dossier ferme.",
                "7. Appel possible au TVB Appeals Board dans 30 jours si reconnu coupable"
            ],
            "documents": [
                "Copie du ticket original",
                "Preuve de calibration du radar (demander via disclosure)",
                "Photos/videos du lieu",
                "Temoignages (si applicable)",
                "Dossier de conduite DMV (driving abstract)"
            ],
            "notes": [
                "ATTENTION: NYC TVB = PAS de plea bargaining (reduction de charge impossible)",
                "ALJ peut only acquit or convict, pas reduire la charge",
                "Speed cameras ($50, 0 points) et red light cameras ($50) = pas de points",
                "Si vous ne repondez pas dans 30 jours = default conviction",
                "Driver Responsibility Assessment si 6+ points en 18 mois ($300/an x 3 ans)"
            ],
            "frais_typiques": {
                "amende": ticket.get("amende", "variable"),
                "surcharge": "$88-$93 (NYS mandatory surcharge)",
                "dra_possible": "$300/an si 6+ points en 18 mois",
            }
        }

    def _procedure_hors_nyc(self, ticket, jours_restants, urgence, lieu):
        """NY hors NYC — plea bargaining POSSIBLE"""
        return {
            "juridiction": "NY",
            "tribunal": f"Local Justice Court / Town Court ({lieu})",
            "tvb": False,
            "plea_bargain": True,
            "delai_contestation": 30,
            "jours_restants": jours_restants,
            "urgence": urgence,
            "etapes": [
                "1. Plaider 'Not Guilty' par courrier ou en personne dans 30 jours",
                "2. Pre-trial conference: negociation avec le procureur (DA) — reduction possible",
                "3. Plea bargain courant: reduction a 'Parking on Pavement' (0 points) ou autre non-moving",
                "4. Si pas d'accord: trial devant le juge (ou jury si demande)",
                "5. Demander disclosure: calibration, training records, radar logs",
                "6. Trial: procureur doit prouver beyond reasonable doubt",
                "7. Appel possible au County Court si reconnu coupable"
            ],
            "documents": [
                "Copie du ticket",
                "Preuve de calibration radar (discovery motion)",
                "Photos du lieu/signalisation",
                "Driving abstract (DMV)",
                "Tout document favorable (bon dossier, etc.)"
            ],
            "notes": [
                "Plea bargaining DISPONIBLE hors NYC — tres courant",
                "Reduction typique: speeding -> parking on pavement (0 points, ~$150-300)",
                "Certains DA acceptent ACD (Adjournment in Contemplation of Dismissal)",
                "Avocat fortement recommande pour negociation — resultat souvent meilleur",
                "Supporting deposition doit etre demandee dans 30 jours"
            ],
            "frais_typiques": {
                "amende": ticket.get("amende", "variable"),
                "surcharge": "$88-$93 (NYS mandatory surcharge)",
                "plea_deal_typique": "$150-400 (parking violation, 0 points)",
            }
        }
