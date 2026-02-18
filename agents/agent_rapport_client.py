"""
Agent Phase 4: RAPPORT CLIENT — Genere le rapport en langage simple
Pas de jargon juridique, comprehensible par tout le monde
"""

import time
import json
from agents.base_agent import BaseAgent, GROQ_LLAMA70B


class AgentRapportClient(BaseAgent):

    def __init__(self):
        super().__init__("Rapport_Client")

    def generer(self, ticket, analyse, procedure, points_calc, verification_cross, contexte_enrichi=None):
        """
        Input: toutes les donnees collectees par les agents precedents + contexte enrichi
        Output: rapport en langage simple pour le client
        """
        self.log("Generation du rapport client...", "STEP")
        start = time.time()

        score = analyse.get("score_contestation", 0) if isinstance(analyse, dict) else 0
        reco = analyse.get("recommandation", "?") if isinstance(analyse, dict) else "?"
        args = analyse.get("arguments", []) if isinstance(analyse, dict) else []

        # Formatter conditions contextuelles
        ctx_conditions = ""
        if contexte_enrichi:
            w = contexte_enrichi.get("weather")
            if w:
                temp = w.get("temperature_c", "?")
                precip = w.get("precipitation_mm", 0)
                snow = w.get("snow_cm", 0)
                conditions = []
                if temp != "?":
                    conditions.append(f"Temperature: {temp}°C")
                if precip:
                    conditions.append(f"Precipitation: {precip}mm")
                if snow:
                    conditions.append(f"Neige: {snow}cm")
                if conditions:
                    ctx_conditions += "- Meteo: " + ", ".join(conditions) + "\n"

            roads = contexte_enrichi.get("road_conditions", [])
            for r in roads:
                rtype = r.get("type", "")
                if rtype in ("construction", "travaux", "chantier", "chantiers", "CONSTRUCTION", "constructionprojects"):
                    ctx_conditions += f"- Zone travaux: {r.get('road', '')} — amendes possiblement doublees\n"

            notes = points_calc.get("notes_contexte", []) if points_calc else []
            for n in notes:
                ctx_conditions += f"- {n}\n"

        # Construire le prompt
        prompt = f"""Genere un rapport SIMPLE et CLAIR pour un client non-juriste.
Evite le jargon juridique. Utilise un ton professionnel mais accessible.

TICKET:
- Infraction: {ticket.get('infraction', '?')}
- Amende: {ticket.get('amende', '?')}
- Points: {ticket.get('points_inaptitude', 0)}
- Lieu: {ticket.get('lieu', '?')}

ANALYSE:
- Score de contestation: {score}%
- Recommandation: {reco}
- Arguments: {json.dumps(args, ensure_ascii=False)}

CONDITIONS AU MOMENT DE L'INFRACTION:
{ctx_conditions if ctx_conditions else "Aucune donnee disponible."}

PROCEDURE:
- Tribunal: {procedure.get('tribunal', '?') if procedure else '?'}
- Delai: {procedure.get('jours_restants', '?') if procedure else '?'} jours restants
- Etapes: {json.dumps(procedure.get('etapes', [])[:4], ensure_ascii=False) if procedure else '[]'}

POINTS:
- Impact assurance: {points_calc.get('impact_assurance', {}).get('note', '?') if points_calc else '?'}
- Economie potentielle: {points_calc.get('economie_si_acquitte', {}).get('total', 0) if points_calc else 0}$

REPONDS EN JSON:
{{
    "resume": "2-3 phrases resumant la situation",
    "verdict": "Ce que le client devrait faire en 1 phrase",
    "conditions_pertinentes": "resume des conditions meteo/route si pertinent",
    "prochaines_etapes": ["etape 1", "etape 2", "etape 3"],
    "attention": "un point important a ne pas oublier",
    "economie": "combien le client peut economiser"
}}"""

        # Groq Llama 70B — rapide, gratuit, no thinking
        jur = ticket.get("juridiction", "QC")
        model = GROQ_LLAMA70B
        lang = "Francais" if jur == "QC" else "English"

        response = self.call_ai(prompt,
                                system_prompt=f"Redige pour un client non-juriste. Clair, simple, direct. {lang}. JSON uniquement.",
                                model=model, temperature=0.2, max_tokens=1500)
        duration = time.time() - start

        if response["success"]:
            try:
                rapport = self.parse_json_response(response["text"])
                self.log(f"Rapport client genere — {len(rapport.get('prochaines_etapes', []))} etapes", "OK")
                self.log_run("generer", f"Score={score}% Reco={reco}",
                             f"Resume={rapport.get('resume', '')[:100]}",
                             tokens=response["tokens"], duration=duration)
                return rapport
            except Exception as e:
                self.log(f"Erreur parsing: {e}", "FAIL")
                self.log_run("generer", "", "", duration=duration, success=False, error=str(e))
        else:
            self.log(f"Erreur AI: {response.get('error', '?')}", "FAIL")
            self.log_run("generer", "", "", duration=duration, success=False, error=response.get("error"))

        # Fallback: rapport sans AI
        return {
            "resume": f"Votre contravention pour {ticket.get('infraction', '?')} a ete analysee. Score: {score}%.",
            "verdict": f"Recommandation: {reco}",
            "prochaines_etapes": procedure.get("etapes", [])[:3] if procedure else [],
            "attention": f"Delai de contestation: {procedure.get('delai_contestation', 30)} jours" if procedure else "",
            "economie": f"Economie potentielle: ${points_calc.get('economie_si_acquitte', {}).get('total', 0)}" if points_calc else ""
        }
