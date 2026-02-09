"""
Agent QC: PROCEDURE QUEBEC — Art. 160 C-24.2, Cour municipale, delais
Specifique au systeme judiciaire quebecois
"""

import time
from datetime import datetime, timedelta
from agents.base_agent import BaseAgent


class AgentProcedureQC(BaseAgent):

    def __init__(self):
        super().__init__("Procedure_QC")

    def determiner_procedure(self, ticket):
        """
        Input: ticket QC
        Output: procedure QC detaillee (Cour municipale, SAAQ, delais)
        """
        self.log("Determination procedure QC...", "STEP")
        start = time.time()

        lieu = (ticket.get("lieu", "") or "").lower()
        infraction = (ticket.get("infraction", "") or "").lower()
        date_ticket = ticket.get("date", "")
        exces = ticket.get("exces_vitesse", 0) or 0
        vitesse_captee = ticket.get("vitesse_captee", 0) or 0
        vitesse_permise = ticket.get("vitesse_permise", 0) or 0
        if not exces and vitesse_captee and vitesse_permise:
            exces = vitesse_captee - vitesse_permise

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
                elif jours_restants <= 5:
                    urgence = "URGENT"
                elif jours_restants <= 15:
                    urgence = "attention"
            except ValueError:
                pass

        # Determiner la cour municipale
        ville = self._determiner_ville(lieu)
        tribunal = f"Cour municipale de {ville}" if ville else "Cour municipale du Quebec"

        # Grand exces de vitesse?
        grand_exces = exces >= 40
        tres_grand_exces = exces >= 50

        # Photo radar / cinematometre automatique?
        appareil = (ticket.get("appareil", "") or "").lower()
        photo_radar = any(w in appareil for w in ["photo", "radar fixe", "automatique", "cinematometre"])

        result = {
            "juridiction": "QC",
            "tribunal": tribunal,
            "loi_reference": "Code de la securite routiere (C-24.2), art. 160-163",
            "delai_contestation": 30,
            "jours_restants": jours_restants,
            "urgence": urgence,
            "etapes": [
                "1. Verifier le constat d'infraction (erreurs = motif de contestation)",
                "2. Plaider non coupable dans les 30 jours (art. 160 CSR)",
                "   - Par courrier: envoyer le formulaire de plaidoyer au greffe",
                "   - En personne: se presenter au greffe de la Cour municipale",
                "   - En ligne: certaines villes (Montreal, Quebec) permettent le depot en ligne",
                "3. Recevoir la date d'audience par courrier recommande",
                "4. Demander la divulgation de la preuve au procureur (disclosure)",
                "   - Rapport de l'agent, certificat de calibration, notes de l'agent",
                "5. Preparer sa defense:",
                "   - Photos/videos du lieu au moment de l'infraction",
                "   - Temoins (si applicable)",
                "   - Rapport d'expert (si vitesse contestee)",
                "6. Se presenter a la Cour municipale a la date fixee",
                "7. Audience: procureur presente sa preuve, puis vous presentez votre defense",
                "8. Jugement (souvent rendu seance tenante, parfois par courrier)"
            ],
            "documents": [
                "Original du constat d'infraction",
                "Piece d'identite avec photo",
                "Permis de conduire",
                "Certificat d'immatriculation du vehicule",
                "Toute preuve favorable (photos, videos, temoignages)",
                "Divulgation de preuve du procureur (demander avant l'audience)"
            ],
            "notes": [],
            "frais_typiques": {
                "contestation": "Gratuit (pas de frais de cour au QC)",
                "amende_si_coupable": ticket.get("amende", "variable"),
                "frais_contribution": "$87-$127 (contribution au FAVR)",
            }
        }

        # Notes specifiques
        if grand_exces:
            result["notes"].append(
                f"GRAND EXCES DE VITESSE ({exces} km/h au-dessus): saisie du vehicule 7 jours "
                f"+ amende majoree + possibilite de suspension immediate"
            )
        if tres_grand_exces:
            result["notes"].append(
                "TRES GRAND EXCES (50+ km/h): saisie 30 jours + amende $615-$1,230 "
                "+ possible suspension de permis 3-12 mois"
            )
        if photo_radar:
            result["notes"].append(
                "PHOTO RADAR: Proprietaire presume conducteur (art. 592 CSR). "
                "Vous pouvez nommer le vrai conducteur dans les 10 jours. "
                "Si vous etiez conducteur, PAS de points (photo radar = infraction au vehicule)."
            )
            result["notes"].append(
                "Defenses photo radar: erreur d'identification du vehicule, "
                "vehicule vole, erreur technique de l'appareil, signalisation inadequate."
            )
        if any(w in infraction for w in ["cellulaire", "telephone", "portable"]):
            result["notes"].append(
                "CELLULAIRE: 5 points + amende $300-$600. Recidive: $600-$1,200. "
                "Defense: utilisation mains-libres, arret complet du vehicule, urgence."
            )
        if any(w in infraction for w in ["zone scolaire", "ecole"]):
            result["notes"].append(
                "ZONE SCOLAIRE: Amende doublee (art. 329 CSR). "
                "Les heures de zone scolaire doivent etre clairement affichees."
            )
        if jours_restants <= 0:
            result["notes"].append(
                "DELAI EXPIRE: Vous pouvez demander une prorogation de delai (art. 163 CSR) "
                "si vous avez un motif valable (maladie, absence, etc.)"
            )

        result["grand_exces"] = grand_exces
        result["photo_radar"] = photo_radar

        duration = time.time() - start
        self.log(f"QC Cour municipale | {jours_restants}j restants | {urgence} | Grand exces: {grand_exces}", "OK")
        self.log_run("determiner_procedure_qc", f"QC lieu={lieu[:50]}",
                     f"Jours={jours_restants} GrandExces={grand_exces}", duration=duration)
        return result

    def _determiner_ville(self, lieu):
        """Determine la ville pour la Cour municipale"""
        villes_qc = {
            "montreal": "Montreal", "laval": "Laval", "quebec": "Quebec",
            "gatineau": "Gatineau", "longueuil": "Longueuil", "sherbrooke": "Sherbrooke",
            "levis": "Levis", "trois-rivieres": "Trois-Rivieres", "terrebonne": "Terrebonne",
            "saint-jean": "Saint-Jean-sur-Richelieu", "repentigny": "Repentigny",
            "brossard": "Brossard", "drummondville": "Drummondville",
            "saint-jerome": "Saint-Jerome", "granby": "Granby",
            "blainville": "Blainville", "rimouski": "Rimouski",
            "victoriaville": "Victoriaville", "saguenay": "Saguenay",
        }
        lieu_lower = lieu.lower()
        for key, ville in villes_qc.items():
            if key in lieu_lower:
                return ville
        return None
