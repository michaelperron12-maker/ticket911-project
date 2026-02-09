"""
Agent Phase 4: RAPPORT AVOCAT — Dossier technique complet pour l'avocat
Jargon juridique, citations, references legales completes
"""

import time
import json
from agents.base_agent import BaseAgent


class AgentRapportAvocat(BaseAgent):

    def __init__(self):
        super().__init__("Rapport_Avocat")

    def generer(self, ticket, analyse, lois, precedents, procedure, points_calc, validation, cross_verif):
        """
        Input: TOUTES les donnees de tous les agents
        Output: dossier technique complet pour l'avocat
        """
        self.log("Generation du rapport avocat...", "STEP")
        start = time.time()

        score = analyse.get("score_contestation", 0) if isinstance(analyse, dict) else 0
        confiance = cross_verif.get("fiabilite", "?") if cross_verif else "?"

        # Construire contexte complet
        ctx_lois = "\n".join([
            f"  - Art. {l.get('article','?')} ({l.get('juridiction','?')}): {l.get('texte','')[:300]}"
            for l in (lois or [])[:8]
        ])

        ctx_precedents = "\n".join([
            f"  - [{p.get('citation','?')}] Score:{p.get('score',0)}% | {p.get('tribunal','?')} | "
            f"{p.get('date','?')} | {p.get('resultat','?')}\n    {p.get('resume','')[:200]}"
            for p in (precedents or [])[:10]
        ])

        ctx_validation = "\n".join([
            f"  - [{v.get('test','?')}] {'PASS' if v.get('valide') else 'FAIL'}: {v.get('detail','')}"
            for v in (validation.get("validations", []) if validation else [])
        ])

        prompt = f"""Genere un dossier technique COMPLET pour un avocat en droit routier.
Utilise le jargon juridique. Cite les articles de loi et la jurisprudence avec precision.

## DOSSIER
Infraction: {ticket.get('infraction', '?')}
Juridiction: {ticket.get('juridiction', '?')}
Loi: {ticket.get('loi', '?')}
Amende: {ticket.get('amende', '?')}
Points: {ticket.get('points_inaptitude', 0)}
Date: {ticket.get('date', '?')}
Lieu: {ticket.get('lieu', '?')}
Appareil: {ticket.get('appareil', '?')}

## LOIS APPLICABLES
{ctx_lois if ctx_lois else "Aucune loi specifique indexee."}

## JURISPRUDENCE
{ctx_precedents if ctx_precedents else "Aucun precedent dans la base."}

## VALIDATION DONNEES
{ctx_validation if ctx_validation else "Non effectuee."}

## ANALYSE AI
Score: {score}% | Confiance verification: {confiance}

## REPONDS EN JSON:
{{
    "numero_dossier": "T911-XXXX",
    "resume_technique": "resume en jargon juridique",
    "fondement_legal": "articles et lois applicables",
    "jurisprudence_pertinente": "citations cles et leur pertinence",
    "moyens_de_defense": ["moyen 1 avec reference", "moyen 2"],
    "faiblesses_dossier": ["faiblesse 1", "faiblesse 2"],
    "strategie_recommandee": "plan detaille",
    "procedure_a_suivre": "etapes pour l'avocat",
    "documents_a_preparer": ["doc1", "doc2"],
    "estimation_honoraires": "categorie",
    "note_confidentielle": "observations internes"
}}"""

        response = self.call_ai(prompt,
                                system_prompt="Redige pour un avocat. Jargon juridique, citations precises. JSON uniquement.",
                                temperature=0.1, max_tokens=3000)
        duration = time.time() - start

        if response["success"]:
            try:
                rapport = self.parse_json_response(response["text"])
                self.log(f"Rapport avocat genere — {len(rapport.get('moyens_de_defense', []))} moyens", "OK")
                self.log_run("generer", f"Score={score}%",
                             f"Moyens={len(rapport.get('moyens_de_defense', []))}",
                             tokens=response["tokens"], duration=duration)
                return rapport
            except Exception as e:
                self.log(f"Erreur parsing: {e}", "FAIL")
                self.log_run("generer", "", "", duration=duration, success=False, error=str(e))
        else:
            self.log(f"Erreur AI: {response.get('error', '?')}", "FAIL")
            self.log_run("generer", "", "", duration=duration, success=False, error=response.get("error"))

        return {"resume_technique": "Rapport non genere — erreur AI", "moyens_de_defense": []}
