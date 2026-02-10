"""
Agent ON: ANALYSTE ONTARIO — Strategie HTA, Provincial Offences Court
Highway Traffic Act, stunt driving, disclosure rights, early resolution
Moteur: Qwen3-235B (meilleur knowledge/classification EN)
"""

import json
import time
from agents.base_agent import BaseAgent, QWEN3


class AgentAnalysteON(BaseAgent):

    def __init__(self):
        super().__init__("Analyste_ON")

    def analyser(self, ticket, lois, precedents):
        """
        Input: ticket ON + lois HTA + precedents ON
        Output: analyse juridique specifique Ontario
        """
        self.log("Analyse juridique ON (HTA/POA)...", "STEP")
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

        prompt = f"""Tu es un avocat specialise en traffic law en Ontario.

REGLES SPECIFIQUES ONTARIO:
- Highway Traffic Act (HTA), R.S.O. 1990, c. H.8
- Provincial Offences Act (POA) — procedure pour Part I et Part III offences
- 15 jours pour demander un trial (Part I) ou first appearance
- Disclosure rights: droit de recevoir TOUTE la preuve du procureur AVANT le trial
- Early Resolution Meeting: negociation possible avec le procureur — reduction frequente
- Stunt driving (HTA s.172): 50+ km/h over = saisie 14 jours, suspension 30 jours, amende $2000-$10000
- Careless driving (HTA s.130): 6 points, amende jusqu'a $2000, prison possible
- Red light cameras: $325, PAS de points (infraction au proprietaire)
- Handheld device (HTA s.78.1): 3 points + $615-$1000 (premiere offense)
- Demerit points: 9 points = suspension 30 jours (permis complet)
- G1/G2 novice: 2 points = avertissement, 6 = suspension 30 jours
- IMPORTANT: toujours demander disclosure — si preuve incomplete, motion to dismiss

REGLE ABSOLUE: Cite UNIQUEMENT les precedents fournis. N'invente AUCUN cas.

## TICKET
- Infraction: {ticket.get('infraction', '')}
- HTA Section: {ticket.get('loi', '')}
- Amende: {ticket.get('amende', '')}
- Points: {ticket.get('points_inaptitude', 0)}
- Lieu: {ticket.get('lieu', '')}
- Date: {ticket.get('date', '')}
- Appareil: {ticket.get('appareil', '')}
- Type: {ticket.get('ticket_type', 'Part I')}

## LOIS HTA APPLICABLES
{ctx_lois if ctx_lois else "Aucune section HTA specifique indexee."}

## PRECEDENTS ON (DE NOTRE BASE)
{ctx_precedents if ctx_precedents else "AUCUN precedent ON dans la base. Analyse sur principes generaux."}

## REPONDS EN JSON:
{{
    "score_contestation": 0-100,
    "confiance": "faible|moyen|eleve",
    "base_sur_precedents": true/false,
    "nb_precedents_utilises": 0,
    "loi_applicable": "HTA section et resume",
    "ticket_type": "Part I|Part III",
    "early_resolution_possible": true/false,
    "disclosure_recommandee": true/false,
    "stunt_driving": true/false,
    "strategie": "description detaillee pour ON",
    "arguments": ["arg1 specifique ON", "arg2"],
    "precedents_cites": [
        {{"citation": "EXACTEMENT comme fourni", "pertinence": "desc", "resultat": "acquitte|reduit|rejete"}}
    ],
    "recommandation": "contester|payer|negocier",
    "explication": "2-3 phrases",
    "early_resolution_note": "ce qu'on peut obtenir en negociation",
    "avertissement": "note importante"
}}"""

        system = ("Avocat ON specialise HTA/POA. Cite UNIQUEMENT les precedents fournis. "
                  "Connais le Highway Traffic Act et la procedure POA. JSON uniquement.")

        response = self.call_ai(prompt, system_prompt=system, model=QWEN3, temperature=0.1, max_tokens=3000)
        duration = time.time() - start

        if response["success"]:
            try:
                analyse = self.parse_json_response(response["text"])
                if not precedents:
                    analyse["confiance"] = "faible"
                    analyse["base_sur_precedents"] = False
                    analyse["avertissement"] = "Analyse sur principes generaux. Aucun precedent ON reel."

                self.log(f"Score ON: {analyse.get('score_contestation', '?')}% | Stunt: {analyse.get('stunt_driving', False)}", "OK")
                self.log_run("analyser_on", f"ON {ticket.get('infraction', '')}",
                             f"Score={analyse.get('score_contestation', '?')}%",
                             tokens=response["tokens"], duration=duration)
                return analyse
            except Exception as e:
                self.log(f"Erreur parsing: {e}", "FAIL")
                self.log_run("analyser_on", "", "", duration=duration, success=False, error=str(e))
                return {"raw_response": response["text"], "error": str(e)}
        else:
            self.log(f"Erreur AI: {response.get('error', '?')}", "FAIL")
            self.log_run("analyser_on", "", "", duration=duration, success=False, error=response.get("error"))
            return None
