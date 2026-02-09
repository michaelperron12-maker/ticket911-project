"""
Agent Phase 2: PROCEDURE — Delais, etapes, tribunal pour chaque juridiction
QC: art. 160 C-24.2 | ON: HTA Part III | NY: VTL sec. 226
"""

import time
from agents.base_agent import BaseAgent


class AgentProcedure(BaseAgent):

    def __init__(self):
        super().__init__("Procedure")

    PROCEDURES = {
        "QC": {
            "delai_contestation": 30,
            "unite_delai": "jours",
            "tribunal": "Cour municipale du Quebec",
            "etapes": [
                "Recevoir le constat d'infraction",
                "Plaider non coupable dans les 30 jours (art. 160 C-24.2)",
                "Recevoir la date d'audience par courrier",
                "Preparer sa defense (preuves, temoins)",
                "Se presenter a la Cour municipale a la date fixee",
                "Presenter sa defense devant le juge",
                "Recevoir le jugement (sur place ou par courrier)",
            ],
            "documents_requis": [
                "Copie du constat d'infraction",
                "Piece d'identite avec photo",
                "Preuves (photos, videos, temoignages)",
                "Preuve d'immatriculation du vehicule",
            ],
            "frais": "Aucun frais pour contester. Frais de justice si reconnu coupable.",
            "loi_reference": "Code de la securite routiere, art. 160-163",
            "notes": "Le plaidoyer de non-culpabilite doit etre fait par ecrit ou en personne au greffe de la cour.",
        },
        "ON": {
            "delai_contestation": 15,
            "unite_delai": "jours",
            "tribunal": "Provincial Offences Court (POC)",
            "etapes": [
                "Recevoir le Part I ou Part III ticket",
                "Choisir: payer, demander audience, ou demander revision de l'amende",
                "Deposer un avis d'intention de comparaitre dans les 15 jours",
                "Recevoir la date d'audience",
                "Option: demander la divulgation de la preuve (disclosure)",
                "Se presenter au Provincial Offences Court",
                "Presenter sa defense",
                "Recevoir le jugement",
            ],
            "documents_requis": [
                "Copie du ticket (Part I ou Part III)",
                "Piece d'identite",
                "Demande de divulgation (si applicable)",
                "Preuves de defense",
            ],
            "frais": "Pas de frais pour contester. Surcharge de $5 si reconnu coupable.",
            "loi_reference": "Provincial Offences Act, R.S.O. 1990",
            "notes": "En Ontario, vous avez le droit de demander la divulgation complete de la preuve du procureur.",
        },
        "NY": {
            "delai_contestation": 30,
            "unite_delai": "jours",
            "tribunal": "Traffic Violations Bureau (TVB)",
            "etapes": [
                "Recevoir le traffic ticket",
                "Plaider non coupable en ligne (tvb.nycourts.gov) ou par courrier dans les 30 jours",
                "Recevoir la date d'audience au TVB",
                "Note: PAS de plea bargaining au TVB (NYC uniquement)",
                "Se presenter a l'audience",
                "Le policier doit etre present (sinon dismissal possible)",
                "Presenter sa defense devant l'Administrative Law Judge",
                "Recevoir la decision",
            ],
            "documents_requis": [
                "Original du traffic ticket",
                "Piece d'identite (license)",
                "Preuves de defense",
                "Preuve d'assurance du vehicule",
            ],
            "frais": "Pas de frais pour contester. DMV surcharge si reconnu coupable.",
            "loi_reference": "Vehicle and Traffic Law, sec. 226-227",
            "notes": "A NYC, le TVB ne permet PAS de negociation de plea. C'est coupable ou non coupable. Hors NYC, les tribunaux locaux permettent la negociation.",
        },
    }

    def obtenir_procedure(self, ticket, classification):
        """
        Input: ticket + classification
        Output: procedure detaillee pour la juridiction
        """
        self.log("Recherche procedure applicable...", "STEP")
        start = time.time()

        juridiction = classification.get("juridiction", "QC")
        procedure = self.PROCEDURES.get(juridiction, self.PROCEDURES["QC"]).copy()

        # Calculer le delai restant
        date_str = ticket.get("date", "")
        if date_str:
            try:
                from datetime import datetime
                date_ticket = datetime.strptime(date_str, "%Y-%m-%d")
                jours_ecoules = (datetime.now() - date_ticket).days
                jours_restants = max(0, procedure["delai_contestation"] - jours_ecoules)
                procedure["jours_ecoules"] = jours_ecoules
                procedure["jours_restants"] = jours_restants
                procedure["delai_expire"] = jours_restants == 0

                if jours_restants <= 5 and jours_restants > 0:
                    procedure["urgence"] = "URGENT — moins de 5 jours pour contester"
                elif jours_restants == 0:
                    procedure["urgence"] = "EXPIRE — delai de contestation depasse"
            except ValueError:
                pass

        duration = time.time() - start
        self.log(f"Procedure {juridiction}: {procedure['tribunal']} | Delai: {procedure['delai_contestation']}j", "OK")
        self.log_run("obtenir_procedure", f"{juridiction}",
                     f"Delai={procedure['delai_contestation']}j", duration=duration)
        return procedure
