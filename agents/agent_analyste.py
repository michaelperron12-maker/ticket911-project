"""
Agent 4: ANALYSTE — DeepSeek R1 analyse UNIQUEMENT avec les vrais cas
temperature=0.1, cite SEULEMENT les precedents fournis
"""

import json
import time
from agents.base_agent import BaseAgent, DEEPSEEK_MODEL


class AgentAnalyste(BaseAgent):

    def __init__(self):
        super().__init__("Analyste")

    def analyser(self, ticket, lois, precedents):
        """
        Input: ticket + lois + precedents REELS (de Agent 3)
        Output: analyse complete avec score
        """
        self.log("Analyse juridique en cours...", "STEP")
        start = time.time()

        # Construire le contexte avec les VRAIS precedents
        ctx_lois = ""
        if lois:
            ctx_lois = "\n".join([
                f"- Art. {l.get('article','?')} ({l.get('juridiction','?')}): {l.get('texte','')[:200]}"
                for l in lois[:5]
            ])

        ctx_precedents = ""
        if precedents:
            ctx_precedents = "\n".join([
                f"- [{p.get('citation','?')}] (Score: {p.get('score',0)}%) "
                f"Tribunal: {p.get('tribunal','?')} | Date: {p.get('date','?')} | "
                f"Resultat: {p.get('resultat','?')}\n  Resume: {p.get('resume','')[:200]}"
                for p in precedents[:10]
            ])

        prompt = f"""Tu es un avocat specialise en droit routier au Quebec/Ontario.

REGLE ABSOLUE: Tu ne peux citer QUE les precedents fournis ci-dessous.
N'invente AUCUN cas. Si un cas n'est pas dans la liste, ne le cite pas.
Si aucun precedent n'est fourni, dis-le honnêtement.

## TICKET
- Infraction: {ticket.get('infraction', '')}
- Juridiction: {ticket.get('juridiction', '')}
- Loi: {ticket.get('loi', '')}
- Amende: {ticket.get('amende', '')}
- Points: {ticket.get('points_inaptitude', 0)}
- Lieu: {ticket.get('lieu', '')}
- Date: {ticket.get('date', '')}
- Appareil: {ticket.get('appareil', '')}

## LOIS APPLICABLES (VERIFIEES)
{ctx_lois if ctx_lois else "Aucune loi specifique trouvee dans la base locale."}

## PRECEDENTS REELS (DE NOTRE BASE DE DONNEES)
{ctx_precedents if ctx_precedents else "AUCUN precedent trouve dans notre base. Analyse basee sur les principes generaux uniquement."}

## REPONDS EN JSON:
{{
    "score_contestation": 0-100,
    "confiance": "faible|moyen|eleve",
    "base_sur_precedents": true/false,
    "nb_precedents_utilises": 0,
    "loi_applicable": "article et resume",
    "strategie": "description",
    "arguments": ["arg1", "arg2", "arg3"],
    "precedents_cites": [
        {{"citation": "EXACTEMENT comme fourni", "pertinence": "desc", "resultat": "acquitte|reduit|rejete"}}
    ],
    "recommandation": "contester|payer|negocier",
    "explication": "2-3 phrases",
    "avertissement": "message si peu de precedents trouves"
}}"""

        system = ("Tu es un avocat specialise. REGLE: cite UNIQUEMENT les cas de la section PRECEDENTS REELS. "
                  "N'invente aucune citation. Reponds en JSON valide uniquement.")

        response = self.call_ai(prompt, system_prompt=system, temperature=0.1, max_tokens=3000)
        duration = time.time() - start

        if response["success"]:
            try:
                analyse = self.parse_json_response(response["text"])

                # Si aucun precedent dans la base, ajuster le score de confiance
                if not precedents:
                    analyse["confiance"] = "faible"
                    analyse["base_sur_precedents"] = False
                    analyse["avertissement"] = "Analyse basee sur les connaissances generales uniquement. Aucun precedent reel de notre base."

                self.log(f"Score: {analyse.get('score_contestation', '?')}%", "OK")
                self.log(f"Recommandation: {analyse.get('recommandation', '?')}", "OK")
                self.log(f"Confiance: {analyse.get('confiance', '?')}", "OK")
                self.log(f"Base sur precedents: {analyse.get('base_sur_precedents', False)}", "OK")

                self.log_run("analyser", f"{ticket.get('infraction','')} ({ticket.get('juridiction','')})",
                             f"Score={analyse.get('score_contestation','?')}% Reco={analyse.get('recommandation','?')}",
                             tokens=response["tokens"], duration=duration)
                return analyse

            except Exception as e:
                self.log(f"Erreur parsing JSON: {e}", "FAIL")
                self.log(f"Reponse brute: {response['text'][:300]}", "WARN")
                self.log_run("analyser", str(ticket)[:200], "", duration=duration, success=False, error=str(e))
                return {"raw_response": response["text"], "error": str(e)}
        else:
            self.log(f"Erreur AI: {response.get('error', '?')}", "FAIL")
            self.log_run("analyser", str(ticket)[:200], "", duration=duration, success=False, error=response.get("error"))
            return None
