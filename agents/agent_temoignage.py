"""
Agent Gold Standard: ANALYSE TEMOIGNAGE — NLP extraction
Analyse le temoignage ecrit du client + temoins
Extrait faits, contradictions, elements de defense
"""

import time
import json
from agents.base_agent import BaseAgent, GLM5


class AgentTemoignage(BaseAgent):

    def __init__(self):
        super().__init__("Temoignage")

    def analyser_temoignage(self, temoignage_client, temoins=None, ticket=None):
        """
        Input: texte du client, liste de temoins (optionnel), ticket
        Output: extraction des faits + impact sur la defense
        """
        self.log("Analyse du temoignage...", "STEP")
        start = time.time()

        if not temoignage_client and not temoins:
            self.log("Aucun temoignage fourni", "WARN")
            return {"status": "SKIP", "note": "Aucun temoignage"}

        # Construire le contexte temoins
        ctx_temoins = ""
        if temoins:
            for i, t in enumerate(temoins, 1):
                nom = t.get("nom", f"Temoin {i}")
                texte = t.get("temoignage", t.get("texte", ""))
                relation = t.get("relation", "inconnu")
                ctx_temoins += f"\n  TEMOIN {i}: {nom} (relation: {relation})\n  \"{texte}\"\n"

        infraction = ticket.get("infraction", "?") if ticket else "?"
        lieu = ticket.get("lieu", "?") if ticket else "?"
        date = ticket.get("date", "?") if ticket else "?"

        prompt = f"""Analyse le temoignage d'un conducteur conteste une contravention.

CONTEXTE DU TICKET:
- Infraction: {infraction}
- Lieu: {lieu}
- Date: {date}

TEMOIGNAGE DU CLIENT:
\"{temoignage_client or 'Non fourni'}\"

{f'TEMOIGNAGES ADDITIONNELS:{ctx_temoins}' if ctx_temoins else ''}

ANALYSE ET EXTRAIS:
1. Les FAITS cles mentionnes (ce qui est arrive selon le client)
2. Les CONTRADICTIONS potentielles avec le constat d'infraction
3. Les ELEMENTS DE DEFENSE que le client mentionne (sans le savoir)
4. La CREDIBILITE du temoignage (coherent, detaille, specifique)
5. Les FAIBLESSES du temoignage (vague, emotif, contradictoire)
6. Si les temoins CORROBORENT le recit du client

REPONDS EN JSON:
{{
    "faits_cles": ["fait 1", "fait 2", "fait 3"],
    "contradictions_constat": ["contradiction 1"],
    "elements_defense": ["element 1", "element 2"],
    "credibilite": 0-100,
    "niveau_detail": "vague|moyen|detaille",
    "ton": "factuel|emotif|mixte",
    "faiblesses": ["faiblesse 1"],
    "temoins_corroborent": true/false/null,
    "resume_juridique": "resume utile pour l'avocat",
    "arguments_extraits": ["argument juridique 1", "argument 2"],
    "note": "observation importante"
}}"""

        response = self.call_ai(prompt,
                                system_prompt="Analyse juridique de temoignage. Extrais les faits et arguments de defense. Objectif et factuel. JSON uniquement.",
                                model=GLM5, temperature=0.1, max_tokens=2000)

        duration = time.time() - start

        if response["success"]:
            try:
                analyse = self.parse_json_response(response["text"])
                analyse["temoignage_fourni"] = bool(temoignage_client)
                analyse["nb_temoins"] = len(temoins) if temoins else 0

                # Calculer impact
                analyse["impact_defense"] = self._calculer_impact(analyse)

                self.log(f"Credibilite: {analyse.get('credibilite', '?')}% | "
                         f"{len(analyse.get('elements_defense', []))} elements defense | "
                         f"Impact: +{analyse['impact_defense']['score_bonus']}%", "OK")
                self.log_run("analyser_temoignage",
                             f"Client={bool(temoignage_client)} Temoins={len(temoins or [])}",
                             f"Credibilite={analyse.get('credibilite', '?')}%",
                             tokens=response["tokens"], duration=duration)
                return analyse
            except Exception as e:
                self.log(f"Erreur parsing: {e}", "FAIL")
                self.log_run("analyser_temoignage", "", "", duration=duration, success=False, error=str(e))
        else:
            self.log(f"Erreur AI: {response.get('error', '?')}", "FAIL")
            self.log_run("analyser_temoignage", "", "", duration=duration, success=False, error=response.get("error"))

        # Fallback
        return {
            "temoignage_fourni": bool(temoignage_client),
            "nb_temoins": len(temoins) if temoins else 0,
            "faits_cles": [],
            "elements_defense": ["Temoignage du client fourni"],
            "credibilite": 50,
            "impact_defense": {"score_bonus": 5, "note": "Temoignage non analyse par AI"}
        }

    def _calculer_impact(self, analyse):
        """Calcule le bonus au score de contestation"""
        score_bonus = 0
        raisons = []

        credibilite = analyse.get("credibilite", 50)
        elements = analyse.get("elements_defense", [])
        contradictions = analyse.get("contradictions_constat", [])
        temoins = analyse.get("temoins_corroborent", None)
        detail = analyse.get("niveau_detail", "moyen")

        # Credibilite haute
        if credibilite >= 80:
            score_bonus += 10
            raisons.append("Temoignage tres credible")
        elif credibilite >= 60:
            score_bonus += 5

        # Elements de defense trouves
        score_bonus += min(15, len(elements) * 5)
        if elements:
            raisons.append(f"{len(elements)} elements de defense identifies")

        # Contradictions avec le constat
        score_bonus += min(15, len(contradictions) * 7)
        if contradictions:
            raisons.append(f"{len(contradictions)} contradiction(s) avec le constat")

        # Temoins qui corroborent
        if temoins is True:
            score_bonus += 10
            raisons.append("Temoins corroborent le recit")

        # Niveau de detail
        if detail == "detaille":
            score_bonus += 5
            raisons.append("Temoignage detaille et specifique")

        score_bonus = min(35, score_bonus)  # Cap a +35%

        return {
            "score_bonus": score_bonus,
            "raisons": raisons,
            "note": f"+{score_bonus}% de bonus au score grace au temoignage"
        }
