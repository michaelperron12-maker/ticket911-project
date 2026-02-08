"""
Agent 1: LECTEUR — Parse et structure les donnees du ticket
"""

from agents.base_agent import BaseAgent


class AgentLecteur(BaseAgent):

    def __init__(self):
        super().__init__("Lecteur")

    def parse_ticket(self, ticket_input):
        """
        Input: texte brut OU dict avec infos du ticket
        Output: dict structure normalise
        """
        self.log("Analyse du ticket...", "STEP")
        start_time = __import__('time').time()

        # Si deja un dict structure, normaliser
        if isinstance(ticket_input, dict):
            result = self._normalize_dict(ticket_input)
            duration = __import__('time').time() - start_time
            self.log_run("parse_ticket", str(ticket_input)[:200], str(result)[:200], duration=duration)
            self.log(f"Ticket parse: {result.get('infraction', '?')} — {result.get('juridiction', '?')}", "OK")
            return result

        # Si texte brut, utiliser DeepSeek pour extraire
        prompt = f"""Extrais les informations de ce ticket de contravention.
Reponds UNIQUEMENT en JSON:
{{
    "infraction": "type d'infraction",
    "juridiction": "Quebec|Ontario|New York",
    "loi": "article de loi applicable",
    "amende": "montant",
    "points_inaptitude": 0,
    "lieu": "lieu de l'infraction",
    "date": "YYYY-MM-DD",
    "appareil": "type d'appareil de mesure",
    "vitesse_captee": 0,
    "vitesse_permise": 0
}}

TICKET:
{ticket_input}"""

        response = self.call_ai(prompt, system_prompt="Extrais les donnees structurees. JSON uniquement.")
        duration = __import__('time').time() - start_time

        if response["success"]:
            try:
                result = self.parse_json_response(response["text"])
                result = self._normalize_dict(result)
                self.log_run("parse_ticket", ticket_input[:200], str(result)[:200],
                             tokens=response["tokens"], duration=duration)
                self.log(f"Ticket parse: {result.get('infraction', '?')}", "OK")
                return result
            except Exception as e:
                self.log(f"Erreur parsing: {e}", "FAIL")
                self.log_run("parse_ticket", ticket_input[:200], "", duration=duration, success=False, error=str(e))
                return None
        else:
            self.log(f"Erreur AI: {response.get('error', '?')}", "FAIL")
            self.log_run("parse_ticket", ticket_input[:200], "", duration=duration, success=False, error=response.get("error"))
            return None

    def _normalize_dict(self, data):
        """Normalise les champs du ticket"""
        normalized = {
            "infraction": data.get("infraction", ""),
            "juridiction": self._normalize_juridiction(data.get("juridiction", "")),
            "loi": data.get("loi", ""),
            "amende": data.get("amende", ""),
            "points_inaptitude": int(data.get("points_inaptitude", 0) or 0),
            "lieu": data.get("lieu", ""),
            "date": data.get("date", ""),
            "appareil": data.get("appareil", ""),
            "vitesse_captee": int(data.get("vitesse_captee", 0) or 0),
            "vitesse_permise": int(data.get("vitesse_permise", 0) or 0),
        }
        return normalized

    def _normalize_juridiction(self, j):
        j_lower = str(j).lower().strip()
        if "qc" in j_lower or "quebec" in j_lower or "québec" in j_lower:
            return "QC"
        elif "on" in j_lower or "ontario" in j_lower:
            return "ON"
        elif "ny" in j_lower or "new york" in j_lower:
            return "NY"
        return j.upper()[:2]
