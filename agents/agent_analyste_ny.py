"""
Agent NY: ANALYSTE NEW YORK — Strategie TVB/court specifique NY
Vehicle and Traffic Law, Traffic Violations Bureau, plea bargaining rules
"""

import json
import time
from agents.base_agent import BaseAgent, DEEPSEEK_MODEL


class AgentAnalysteNY(BaseAgent):

    def __init__(self):
        super().__init__("Analyste_NY")

    def analyser(self, ticket, lois, precedents):
        """
        Input: ticket NY + lois VTL + precedents NY
        Output: analyse juridique specifique au systeme NY
        """
        self.log("Analyse juridique NY (VTL/TVB)...", "STEP")
        start = time.time()

        ctx_lois = "\n".join([
            f"- {l.get('article','?')}: {l.get('texte','')[:200]}"
            for l in (lois or [])[:5]
        ])

        ctx_precedents = "\n".join([
            f"- [{p.get('citation','?')}] Score:{p.get('score',0)}% | {p.get('tribunal','?')} | "
            f"{p.get('date','?')} | {p.get('resultat','?')}\n  {p.get('resume','')[:200]}"
            for p in (precedents or [])[:10]
        ])

        prompt = f"""Tu es un avocat specialise en traffic law a New York.

REGLES SPECIFIQUES NEW YORK:
- NYC Traffic Violations Bureau (TVB): PAS de plea bargaining pour les 5 boroughs
- Hors NYC: plea bargaining possible, reduction a "parking on pavement" ou ACD courant
- Appareil radar/lidar: calibration records obligatoires (People v. Dusing)
- Speed cameras: NYC school zones, 50$ fixe, PAS de points
- Red light cameras: $50, responsabilite proprietaire pas conducteur

REGLE ABSOLUE: Cite UNIQUEMENT les precedents fournis. N'invente AUCUN cas.

## TICKET
- Infraction: {ticket.get('infraction', '')}
- VTL Section: {ticket.get('loi', '')}
- Amende: {ticket.get('amende', '')}
- Points DMV: {ticket.get('points_inaptitude', 0)}
- Lieu: {ticket.get('lieu', '')}
- Date: {ticket.get('date', '')}
- Appareil: {ticket.get('appareil', '')}

## LOIS VTL APPLICABLES
{ctx_lois if ctx_lois else "Aucun article VTL specifique indexe."}

## PRECEDENTS NY (DE NOTRE BASE)
{ctx_precedents if ctx_precedents else "AUCUN precedent NY dans la base. Analyse sur principes generaux."}

## REPONDS EN JSON:
{{
    "score_contestation": 0-100,
    "confiance": "faible|moyen|eleve",
    "base_sur_precedents": true/false,
    "nb_precedents_utilises": 0,
    "loi_applicable": "VTL section et resume",
    "tvb_applicable": true/false,
    "plea_bargain_possible": true/false,
    "strategie": "description detaillee pour NY",
    "arguments": ["arg1 specifique NY", "arg2"],
    "precedents_cites": [
        {{"citation": "EXACTEMENT comme fourni", "pertinence": "desc", "resultat": "acquitte|reduit|rejete"}}
    ],
    "recommandation": "contester|payer|negocier",
    "explication": "2-3 phrases",
    "driver_responsibility_assessment": "points sur le permis NY",
    "avertissement": "note si TVB ou autre particularite"
}}"""

        system = ("Avocat NY specialise VTL/TVB. Cite UNIQUEMENT les precedents fournis. "
                  "Connais les regles TVB (pas de plea bargain dans NYC). JSON uniquement.")

        response = self.call_ai(prompt, system_prompt=system, temperature=0.1, max_tokens=3000)
        duration = time.time() - start

        if response["success"]:
            try:
                analyse = self.parse_json_response(response["text"])
                if not precedents:
                    analyse["confiance"] = "faible"
                    analyse["base_sur_precedents"] = False
                    analyse["avertissement"] = "Analyse sur principes generaux. Aucun precedent NY reel dans la base."

                self.log(f"Score NY: {analyse.get('score_contestation', '?')}% | TVB: {analyse.get('tvb_applicable', '?')}", "OK")
                self.log_run("analyser_ny", f"NY {ticket.get('infraction', '')}",
                             f"Score={analyse.get('score_contestation', '?')}%",
                             tokens=response["tokens"], duration=duration)
                return analyse
            except Exception as e:
                self.log(f"Erreur parsing: {e}", "FAIL")
                self.log_run("analyser_ny", "", "", duration=duration, success=False, error=str(e))
                return {"raw_response": response["text"], "error": str(e)}
        else:
            self.log(f"Erreur AI: {response.get('error', '?')}", "FAIL")
            self.log_run("analyser_ny", "", "", duration=duration, success=False, error=response.get("error"))
            return None
