"""
Agent QC: ANALYSTE QUEBEC — Strategie specifique droit routier QC
Code de la securite routiere, SAAQ, Cour municipale, reglements municipaux
Moteur: DeepSeek V3p2 (raisonnement juridique FR)
"""

import json
import time
from agents.base_agent import BaseAgent, DEEPSEEK_V3


class AgentAnalysteQC(BaseAgent):

    def __init__(self):
        super().__init__("Analyste_QC")

    def analyser(self, ticket, lois, precedents):
        """
        Input: ticket QC + lois CSR + precedents QC
        Output: analyse juridique specifique au Quebec
        """
        self.log("Analyse juridique QC (CSR/SAAQ)...", "STEP")
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

        prompt = f"""Tu es un avocat specialise en droit routier au Quebec.

REGLES SPECIFIQUES QUEBEC:
- Code de la securite routiere (CSR), L.R.Q., c. C-24.2
- Constat d'infraction: 30 jours pour plaider non coupable (art. 160)
- Cour municipale: juge seul, pas de jury
- Photo radar/cinémomètre: proprietaire du vehicule = presume conducteur (art. 592)
- MAIS: le proprietaire peut nommer le vrai conducteur pour eviter les points
- Zones scolaires: amende doublee (art. 329)
- Zone de construction: amende doublee (art. 329.2)
- Celullaire: 5 points + amende $300-$600 (premiere offense)
- Grand exces (40+ km/h): saisie immediate du vehicule 7 jours
- SAAQ: regime de points d'inaptitude (max 15 pour permis regulier)
- Permis probatoire: max 4 points avant suspension

REGLE ABSOLUE: Cite UNIQUEMENT les precedents fournis. N'invente AUCUN cas.

## TICKET
- Infraction: {ticket.get('infraction', '')}
- Article CSR: {ticket.get('loi', '')}
- Amende: {ticket.get('amende', '')}
- Points SAAQ: {ticket.get('points_inaptitude', 0)}
- Lieu: {ticket.get('lieu', '')}
- Date: {ticket.get('date', '')}
- Appareil: {ticket.get('appareil', '')}
- Vitesse captee: {ticket.get('vitesse_captee', '')}
- Vitesse permise: {ticket.get('vitesse_permise', '')}

## LOIS CSR APPLICABLES
{ctx_lois if ctx_lois else "Aucun article CSR specifique indexe."}

## PRECEDENTS QC (DE NOTRE BASE)
{ctx_precedents if ctx_precedents else "AUCUN precedent QC dans la base. Analyse sur principes generaux."}

## REPONDS EN JSON:
{{
    "score_contestation": 0-100,
    "confiance": "faible|moyen|eleve",
    "base_sur_precedents": true/false,
    "nb_precedents_utilises": 0,
    "loi_applicable": "article CSR et resume",
    "zone_speciale": "scolaire|construction|aucune",
    "amende_doublee": true/false,
    "grand_exces": true/false,
    "saisie_vehicule": true/false,
    "strategie": "description detaillee pour QC",
    "arguments": ["arg1 specifique QC", "arg2"],
    "precedents_cites": [
        {{"citation": "EXACTEMENT comme fourni", "pertinence": "desc", "resultat": "acquitte|reduit|rejete"}}
    ],
    "recommandation": "contester|payer|negocier",
    "explication": "2-3 phrases",
    "note_saaq": "impact sur les points SAAQ",
    "avertissement": "note importante"
}}"""

        system = ("Avocat QC specialise CSR/SAAQ. Cite UNIQUEMENT les precedents fournis. "
                  "Connais le Code de la securite routiere par coeur. JSON uniquement.")

        response = self.call_ai(prompt, system_prompt=system, model=DEEPSEEK_V3, temperature=0.1, max_tokens=3000)
        duration = time.time() - start

        if response["success"]:
            try:
                analyse = self.parse_json_response(response["text"])
                if not precedents:
                    analyse["confiance"] = "faible"
                    analyse["base_sur_precedents"] = False
                    analyse["avertissement"] = "Analyse sur principes generaux. Aucun precedent QC reel dans la base."

                self.log(f"Score QC: {analyse.get('score_contestation', '?')}% | Grand exces: {analyse.get('grand_exces', '?')}", "OK")
                self.log_run("analyser_qc", f"QC {ticket.get('infraction', '')}",
                             f"Score={analyse.get('score_contestation', '?')}%",
                             tokens=response["tokens"], duration=duration)
                return analyse
            except Exception as e:
                self.log(f"Erreur parsing: {e}", "FAIL")
                self.log_run("analyser_qc", "", "", duration=duration, success=False, error=str(e))
                return {"raw_response": response["text"], "error": str(e)}
        else:
            self.log(f"Erreur AI: {response.get('error', '?')}", "FAIL")
            self.log_run("analyser_qc", "", "", duration=duration, success=False, error=response.get("error"))
            return None
