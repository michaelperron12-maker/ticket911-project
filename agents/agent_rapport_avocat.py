"""
Agent Phase 4: RAPPORT AVOCAT — Dossier technique complet pour l'avocat
Jargon juridique, citations, references legales completes
"""

import time
import json
from agents.base_agent import BaseAgent, SAMBA_LLAMA70B


class AgentRapportAvocat(BaseAgent):

    def __init__(self):
        super().__init__("Rapport_Avocat")

    def generer(self, ticket, analyse, lois, precedents, procedure, points_calc, validation, cross_verif, contexte_enrichi=None):
        """
        Input: TOUTES les donnees de tous les agents + contexte enrichi
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

        # Construire section preuves contextuelles
        ctx_preuves = ""
        if contexte_enrichi:
            w = contexte_enrichi.get("weather")
            if w:
                parts = []
                if w.get("temperature_c") is not None:
                    parts.append(f"Temperature: {w['temperature_c']}°C")
                if w.get("precipitation_mm"):
                    parts.append(f"Precipitation: {w['precipitation_mm']}mm")
                if w.get("snow_cm"):
                    parts.append(f"Neige: {w['snow_cm']}cm")
                if w.get("wind_speed_kmh"):
                    parts.append(f"Vent: {w['wind_speed_kmh']}km/h")
                if w.get("station"):
                    parts.append(f"Station: {w['station']}")
                if parts:
                    ctx_preuves += "  Meteo (Env Canada): " + " | ".join(parts) + "\n"

            roads = contexte_enrichi.get("road_conditions", [])
            if roads:
                for r in roads[:5]:
                    ctx_preuves += f"  Route: {r.get('road', '?')} — {r.get('type', '?')} | {r.get('description', '')[:150]}\n"

            speeds = contexte_enrichi.get("speed_limits", [])
            if speeds:
                limits = [f"{s.get('road', '?')}: {s.get('limit_kmh', '?')} km/h" for s in speeds[:5]]
                ctx_preuves += "  Limites OSM: " + " | ".join(limits) + "\n"

            notes = points_calc.get("notes_contexte", []) if points_calc else []
            for n in notes:
                ctx_preuves += f"  Note: {n}\n"

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

## PREUVES CONTEXTUELLES (sources officielles)
{ctx_preuves if ctx_preuves else "Aucune donnee contextuelle disponible."}
Sources: Environnement Canada (meteo), 511 QC/ON (routes), OpenStreetMap (limites vitesse)

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
    "preuves_contextuelles": "resume des preuves meteo/route/vitesse si pertinent",
    "moyens_de_defense": ["moyen 1 avec reference", "moyen 2"],
    "faiblesses_dossier": ["faiblesse 1", "faiblesse 2"],
    "strategie_recommandee": "plan detaille",
    "procedure_a_suivre": "etapes pour l'avocat",
    "documents_a_preparer": ["doc1", "doc2"],
    "estimation_honoraires": "categorie",
    "note_confidentielle": "observations internes"
}}"""

        # SambaNova Llama 70B — rapide, gratuit, no thinking
        jur = ticket.get("juridiction", "QC")
        model = SAMBA_LLAMA70B
        lang = "Francais" if jur == "QC" else "English"

        response = self.call_ai(prompt,
                                system_prompt=f"Redige pour un avocat. Jargon juridique, citations precises. {lang}. JSON uniquement.",
                                model=model, temperature=0.1, max_tokens=3000)
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
