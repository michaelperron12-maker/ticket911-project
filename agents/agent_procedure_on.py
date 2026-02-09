"""
Agent ON: PROCEDURE ONTARIO — Provincial Offences Act, HTA Part I/III
Specifique au systeme ontarien: early resolution, disclosure, trial
"""

import time
from datetime import datetime, timedelta
from agents.base_agent import BaseAgent


class AgentProcedureON(BaseAgent):

    def __init__(self):
        super().__init__("Procedure_ON")

    def determiner_procedure(self, ticket):
        """
        Input: ticket ON
        Output: procedure Ontario detaillee (POA, disclosure, early resolution)
        """
        self.log("Determination procedure ON...", "STEP")
        start = time.time()

        lieu = (ticket.get("lieu", "") or "").lower()
        infraction = (ticket.get("infraction", "") or "").lower()
        date_ticket = ticket.get("date", "")
        exces = ticket.get("exces_vitesse", 0) or 0

        # Part I vs Part III
        is_part3 = any(w in infraction for w in [
            "careless", "dangereuse", "stunt", "racing", "course",
            "impaired", "suspended", "fail to remain"
        ])
        ticket_type = "Part III" if is_part3 else "Part I"

        # Stunt driving?
        is_stunt = exces >= 50 or any(w in infraction for w in ["stunt", "racing", "course"])

        # Calculer delai
        jours_restants = 15
        urgence = "normal"
        if date_ticket:
            try:
                dt = datetime.strptime(date_ticket, "%Y-%m-%d")
                deadline = dt + timedelta(days=15)
                jours_restants = (deadline - datetime.now()).days
                if jours_restants < 0:
                    urgence = "EXPIRE"
                elif jours_restants <= 3:
                    urgence = "URGENT"
                elif jours_restants <= 7:
                    urgence = "attention"
            except ValueError:
                pass

        if is_stunt:
            result = self._procedure_stunt(ticket, jours_restants, urgence, lieu)
        elif ticket_type == "Part III":
            result = self._procedure_part3(ticket, jours_restants, urgence, lieu)
        else:
            result = self._procedure_part1(ticket, jours_restants, urgence, lieu)

        result["ticket_type"] = ticket_type
        result["is_stunt"] = is_stunt

        duration = time.time() - start
        self.log(f"ON {ticket_type} | {jours_restants}j restants | {urgence} | Stunt: {is_stunt}", "OK")
        self.log_run("determiner_procedure_on", f"ON {ticket_type} lieu={lieu[:50]}",
                     f"Jours={jours_restants} Stunt={is_stunt}", duration=duration)
        return result

    def _procedure_part1(self, ticket, jours_restants, urgence, lieu):
        """Part I — offences mineures (speeding, red light, etc.)"""
        return {
            "juridiction": "ON",
            "tribunal": "Provincial Offences Court",
            "loi_reference": "Provincial Offences Act, R.S.O. 1990 + HTA",
            "delai_contestation": 15,
            "jours_restants": jours_restants,
            "urgence": urgence,
            "etapes": [
                "1. Choisir Option 3 sur le ticket: 'Trial option' (dans les 15 jours)",
                "   - Remplir le verso du ticket et envoyer par courrier au tribunal indique",
                "   - OU deposer en personne au greffe du Provincial Offences Court",
                "2. Recevoir un avis avec la date de votre Early Resolution Meeting OU Trial",
                "3. EARLY RESOLUTION (recommande):",
                "   - Rencontre avec le procureur pour negocier une reduction",
                "   - Reductions courantes: charge reduite (moins de points), amende reduite",
                "   - Vous pouvez accepter ou refuser l'offre",
                "4. Si pas d'accord en Early Resolution: demander un Trial",
                "5. DISCLOSURE (tres important):",
                "   - Envoyer une demande ecrite de disclosure au procureur",
                "   - Le procureur DOIT fournir: notes de l'agent, calibration radar, etc.",
                "   - Si disclosure incomplete = motion to dismiss possible",
                "6. TRIAL: procureur presente sa preuve, vous presentez votre defense",
                "7. Jugement: coupable ou non coupable"
            ],
            "documents": [
                "Original du ticket (Part I)",
                "Piece d'identite / permis de conduire",
                "Lettre de demande de disclosure (template disponible)",
                "Preuves de defense (photos, videos, temoins)",
                "Driving record (si bon dossier, aide pour negociation)"
            ],
            "notes": [
                "Demander disclosure est TOUJOURS recommande — c'est votre droit",
                "Early Resolution: souvent reduction de 2-4 points + amende reduite",
                "Si l'officier ne se presente pas au trial: NOT GUILTY automatique",
                "Vous pouvez engager un paralegal (moins cher qu'un avocat, licence LSO)",
                "Red light cameras ($325): PAS de points, infraction au proprietaire"
            ],
            "frais_typiques": {
                "contestation": "Gratuit",
                "amende_si_coupable": ticket.get("amende", "variable"),
                "victim_fine_surcharge": "20% de l'amende",
                "court_costs": "$5 si reconnu coupable"
            }
        }

    def _procedure_part3(self, ticket, jours_restants, urgence, lieu):
        """Part III — offences serieuses (careless, fail to remain, etc.)"""
        return {
            "juridiction": "ON",
            "tribunal": "Ontario Court of Justice",
            "loi_reference": "Provincial Offences Act Part III + HTA",
            "delai_contestation": 15,
            "jours_restants": jours_restants,
            "urgence": urgence,
            "etapes": [
                "1. IMPORTANT: Part III = infraction serieuse — AVOCAT FORTEMENT recommande",
                "2. First appearance au tribunal (comparution)",
                "3. Disclosure: demander TOUTE la preuve du procureur",
                "4. Negociation pre-trial avec le procureur (Crown)",
                "5. Si pas d'accord: trial complet devant un juge",
                "6. Jugement: coupable ou non coupable",
                "7. Si coupable: amende + points + possibilite de prison pour certaines offences"
            ],
            "documents": [
                "Original du ticket/summons (Part III)",
                "Piece d'identite",
                "Demande de disclosure complete",
                "Tout document favorable"
            ],
            "notes": [
                "Part III: consequences serieuses — prison possible pour certaines offences",
                "AVOCAT ou PARALEGAL OBLIGATOIRE recommande",
                "Careless driving (s.130): max $2,000 + 6 mois prison + 2 ans suspension",
                "La Crown doit prouver au-dela du doute raisonnable"
            ],
            "frais_typiques": {
                "contestation": "Gratuit",
                "amende_max": "Jusqu'a $50,000 selon l'offense",
                "avocat": "$1,500-$5,000 selon complexite"
            }
        }

    def _procedure_stunt(self, ticket, jours_restants, urgence, lieu):
        """Stunt driving / Street racing — HTA s.172"""
        return {
            "juridiction": "ON",
            "tribunal": "Ontario Court of Justice",
            "loi_reference": "HTA s.172 (Stunt driving / Racing)",
            "delai_contestation": 15,
            "jours_restants": jours_restants,
            "urgence": urgence,
            "etapes": [
                "1. VEHICULE SAISI 14 JOURS + PERMIS SUSPENDU 30 JOURS (immediat)",
                "2. AVOCAT OBLIGATOIRE — consequences tres serieuses",
                "3. First appearance au tribunal",
                "4. Disclosure: demander calibration radar, dash cam police, notes agent",
                "5. Negociation: reduction a speeding possible si bon avocat",
                "6. Trial si necessaire",
                "7. Si coupable: amende $2,000-$10,000 + suspension 1-3 ans + 6 points"
            ],
            "documents": [
                "Original du ticket/summons",
                "Recu de saisie du vehicule",
                "Avis de suspension du permis",
                "Demande de disclosure complete"
            ],
            "notes": [
                "STUNT DRIVING = offense la plus serieuse du HTA",
                "50+ km/h au-dessus de la limite = stunt automatique",
                "Saisie vehicule 14 jours + suspension permis 30 jours IMMEDIATEMENT",
                "Premiere offense: amende $2,000-$10,000",
                "Deuxieme offense: amende $2,000-$10,000 + prison max 6 mois",
                "Troisieme: amende $2,000-$10,000 + prison max 6 mois + suspension 10 ans",
                "Avocat ESSENTIEL — reduction a simple speeding souvent possible",
                "Defense: erreur de calibration, signalisation, conditions routieres"
            ],
            "frais_typiques": {
                "amende_min": "$2,000",
                "amende_max": "$10,000",
                "remorquage_saisie": "$500-$1,000",
                "avocat": "$3,000-$10,000",
                "augmentation_assurance": "100-300% pendant 3+ ans"
            }
        }
