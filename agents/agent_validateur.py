"""
Agent Phase 1: VALIDATEUR — Cross-check des donnees du ticket
Verifie: code = description? Amende = bareme? Dates coherentes?
"""

import time
import re
from datetime import datetime, timedelta
from agents.base_agent import BaseAgent


class AgentValidateur(BaseAgent):

    def __init__(self):
        super().__init__("Validateur")

    # Baremes amendes approximatifs
    BAREMES_QC = {
        "vitesse_1_20": (100, 200),
        "vitesse_21_30": (200, 300),
        "vitesse_31_45": (300, 450),
        "vitesse_46_plus": (450, 3000),
        "feu_rouge": (150, 300),
        "stop": (100, 200),
        "cellulaire": (300, 600),
        "ceinture": (80, 200),
    }

    BAREMES_ON = {
        "vitesse_1_15": (0, 100),
        "vitesse_16_29": (100, 260),
        "vitesse_30_49": (260, 500),
        "vitesse_50_plus": (500, 10000),
        "red_light": (260, 500),
        "stop": (110, 200),
        "handheld": (615, 1000),
    }

    def valider(self, ticket, classification):
        """
        Input: ticket dict + classification du Classificateur
        Output: rapport de validation avec anomalies detectees
        """
        self.log("Validation des donnees du ticket...", "STEP")
        start = time.time()

        anomalies = []
        validations = []

        # 1. Verifier coherence juridiction
        v = self._verifier_juridiction(ticket, classification)
        validations.append(v)
        if not v["valide"]:
            anomalies.append(v)

        # 2. Verifier amende vs bareme
        v = self._verifier_amende(ticket, classification)
        validations.append(v)
        if not v["valide"]:
            anomalies.append(v)

        # 3. Verifier date (pas future, pas trop ancienne)
        v = self._verifier_date(ticket)
        validations.append(v)
        if not v["valide"]:
            anomalies.append(v)

        # 4. Verifier points vs type d'infraction
        v = self._verifier_points(ticket, classification)
        validations.append(v)
        if not v["valide"]:
            anomalies.append(v)

        # 5. Verifier vitesse (captee > permise)
        v = self._verifier_vitesse(ticket)
        validations.append(v)
        if not v["valide"]:
            anomalies.append(v)

        # 6. Verifier delai de contestation
        v = self._verifier_delai(ticket, classification)
        validations.append(v)

        result = {
            "valide": len(anomalies) == 0,
            "nb_validations": len(validations),
            "nb_anomalies": len(anomalies),
            "anomalies": anomalies,
            "validations": validations,
            "score_fiabilite": round((1 - len(anomalies) / max(len(validations), 1)) * 100),
        }

        duration = time.time() - start
        self.log(f"Validation: {result['score_fiabilite']}% fiable | {len(anomalies)} anomalies", "OK")
        self.log_run("valider", f"{ticket.get('infraction', '')[:80]}",
                     f"Score={result['score_fiabilite']}% Anomalies={len(anomalies)}", duration=duration)
        return result

    def _verifier_juridiction(self, ticket, classification):
        jur_ticket = ticket.get("juridiction", "").upper()[:2]
        jur_class = classification.get("juridiction", "")
        match = jur_ticket == jur_class or not jur_ticket
        return {
            "test": "juridiction",
            "valide": match,
            "detail": f"Ticket={jur_ticket} vs Classification={jur_class}" if not match else "Coherent"
        }

    def _verifier_amende(self, ticket, classification):
        amende_str = str(ticket.get("amende", ""))
        # Extraire le montant numerique
        montants = re.findall(r"(\d+(?:\.\d{2})?)", amende_str.replace(",", ""))
        if not montants:
            return {"test": "amende", "valide": True, "detail": "Pas de montant detecte"}

        montant = float(montants[0])
        juridiction = classification.get("juridiction", "QC")
        type_inf = classification.get("type_infraction", "")

        bareme = None
        if juridiction == "QC":
            if type_inf == "cellulaire":
                bareme = self.BAREMES_QC["cellulaire"]
            elif type_inf == "feu_rouge":
                bareme = self.BAREMES_QC["feu_rouge"]
            elif type_inf == "vitesse":
                exces = (ticket.get("vitesse_captee", 0) or 0) - (ticket.get("vitesse_permise", 0) or 0)
                if exces <= 20:
                    bareme = self.BAREMES_QC["vitesse_1_20"]
                elif exces <= 30:
                    bareme = self.BAREMES_QC["vitesse_21_30"]
                elif exces <= 45:
                    bareme = self.BAREMES_QC["vitesse_31_45"]
                else:
                    bareme = self.BAREMES_QC["vitesse_46_plus"]

        if bareme:
            dans_bareme = bareme[0] <= montant <= bareme[1] * 1.5  # marge pour frais
            return {
                "test": "amende",
                "valide": dans_bareme,
                "detail": f"${montant} {'dans' if dans_bareme else 'HORS'} bareme (${bareme[0]}-${bareme[1]})"
            }

        return {"test": "amende", "valide": True, "detail": f"${montant} — bareme non verifie"}

    def _verifier_date(self, ticket):
        date_str = ticket.get("date", "")
        if not date_str:
            return {"test": "date", "valide": True, "detail": "Pas de date fournie"}

        try:
            date_ticket = datetime.strptime(date_str, "%Y-%m-%d")
            now = datetime.now()

            if date_ticket > now:
                return {"test": "date", "valide": False, "detail": "Date future — impossible"}
            if date_ticket < now - timedelta(days=365 * 2):
                return {"test": "date", "valide": False, "detail": "Date > 2 ans — probablement prescrit"}

            return {"test": "date", "valide": True, "detail": f"Date valide: {date_str}"}
        except ValueError:
            return {"test": "date", "valide": True, "detail": f"Format de date non reconnu: {date_str}"}

    def _verifier_points(self, ticket, classification):
        points = ticket.get("points_inaptitude", 0) or 0
        type_inf = classification.get("type_infraction", "")
        juridiction = classification.get("juridiction", "QC")

        max_pts = {"QC": 15, "ON": 9, "NY": 11}.get(juridiction, 15)
        if points > max_pts:
            return {"test": "points", "valide": False, "detail": f"{points} pts > max {max_pts} pour {juridiction}"}

        return {"test": "points", "valide": True, "detail": f"{points} pts — coherent pour {juridiction}"}

    def _verifier_vitesse(self, ticket):
        captee = ticket.get("vitesse_captee", 0) or 0
        permise = ticket.get("vitesse_permise", 0) or 0

        if not captee or not permise:
            return {"test": "vitesse", "valide": True, "detail": "Pas de donnees vitesse"}

        if captee <= permise:
            return {"test": "vitesse", "valide": False, "detail": f"Captee {captee} <= permise {permise} — incoherent"}

        return {"test": "vitesse", "valide": True, "detail": f"Exces: {captee - permise} km/h"}

    def _verifier_delai(self, ticket, classification):
        date_str = ticket.get("date", "")
        if not date_str:
            return {"test": "delai", "valide": True, "detail": "Pas de date — delai non calcule"}

        try:
            date_ticket = datetime.strptime(date_str, "%Y-%m-%d")
            jours_ecoules = (datetime.now() - date_ticket).days
            juridiction = classification.get("juridiction", "QC")

            delais = {"QC": 30, "ON": 15, "NY": 30}
            delai_max = delais.get(juridiction, 30)

            expire = jours_ecoules > delai_max
            return {
                "test": "delai",
                "valide": not expire,
                "detail": f"{jours_ecoules} jours / {delai_max} jours max ({juridiction})" +
                          (" — EXPIRE" if expire else " — dans les delais")
            }
        except ValueError:
            return {"test": "delai", "valide": True, "detail": "Date non parseable"}
