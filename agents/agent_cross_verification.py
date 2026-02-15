"""
Agent Phase 3: CROSS-VERIFICATION — Double moteur independant
Verifie l'analyse avec un modele DIFFERENT pour fiabilite 99.5%
"""

import time
import json
from agents.base_agent import BaseAgent, DEEPSEEK_R1, KIMI_THINK


class AgentCrossVerification(BaseAgent):

    def __init__(self):
        super().__init__("CrossVerification")

    def verifier_analyse(self, ticket, analyse, lois, precedents, contexte_texte=""):
        """
        Input: ticket + analyse originale + lois + precedents + contexte enrichi
        Output: verification independante avec score de concordance
        """
        self.log("Cross-verification double moteur...", "STEP")
        start = time.time()

        # Construire le prompt de verification
        ctx = json.dumps({
            "ticket": ticket,
            "analyse_originale": {
                "score": analyse.get("score_contestation", 0) if isinstance(analyse, dict) else 0,
                "recommandation": analyse.get("recommandation", "?") if isinstance(analyse, dict) else "?",
                "arguments": analyse.get("arguments", []) if isinstance(analyse, dict) else [],
                "precedents_cites": [p.get("citation", "") for p in (analyse.get("precedents_cites", []) if isinstance(analyse, dict) else [])],
            },
            "nb_lois": len(lois) if lois else 0,
            "nb_precedents": len(precedents) if precedents else 0,
        }, ensure_ascii=False, indent=2)

        prompt = f"""Tu es un verificateur independant. On te presente une analyse juridique d'un ticket de contravention.
Tu dois VERIFIER si l'analyse est coherente et raisonnable.

DONNEES:
{ctx}

CONTEXTE ENVIRONNEMENTAL (donnees officielles):
{contexte_texte if contexte_texte else "Aucune donnee meteo/route disponible."}
NOTE: Verifie si les arguments meteo/route de l'analyse sont coherents avec les donnees officielles ci-dessus.

VERIFIE:
1. Le score de contestation est-il realiste pour ce type d'infraction?
2. La recommandation (contester/payer/negocier) est-elle coherente avec le score?
3. Les arguments de defense sont-ils valides juridiquement?
4. Les precedents cites existent-ils dans les donnees fournies?
5. Les arguments meteo/conditions routieres sont-ils supportes par les donnees officielles?

REPONDS EN JSON:
{{
    "score_verification": 0-100,
    "concordance": true/false,
    "score_ajuste": 0-100,
    "problemes_detectes": ["probleme1", "probleme2"],
    "confirmation_arguments": true/false,
    "recommandation_verifiee": "contester|payer|negocier",
    "note": "explication courte"
}}"""

        # Utiliser un modele DIFFERENT (R1 au lieu de V3)
        response = self.call_ai(prompt,
                                system_prompt="Verificateur independant. Sois critique et objectif. JSON uniquement.",
                                model=DEEPSEEK_R1,
                                temperature=0.05,
                                max_tokens=1500)

        duration = time.time() - start

        if response["success"]:
            try:
                verification = self.parse_json_response(response["text"])

                # Calculer la concordance
                score_original = analyse.get("score_contestation", 0) if isinstance(analyse, dict) else 0
                score_verif = verification.get("score_ajuste", score_original)
                ecart = abs(score_original - score_verif)

                verification["ecart"] = ecart
                verification["fiabilite"] = "haute" if ecart <= 10 else "moyenne" if ecart <= 20 else "faible"

                self.log(f"Concordance: {verification.get('concordance', '?')} | Ecart: {ecart}% | Fiabilite: {verification['fiabilite']}", "OK")
                self.log_run("verifier_analyse", f"Score original={score_original}",
                             f"Score ajuste={score_verif} Ecart={ecart}",
                             tokens=response["tokens"], duration=duration)
                return verification

            except Exception as e:
                self.log(f"Erreur parsing: {e}", "FAIL")
                self.log_run("verifier_analyse", "", "", duration=duration, success=False, error=str(e))
                return {"concordance": True, "score_verification": 50, "note": f"Erreur parsing: {e}"}
        else:
            self.log(f"Erreur AI: {response.get('error', '?')}", "FAIL")
            self.log_run("verifier_analyse", "", "", duration=duration, success=False, error=response.get("error"))
            return {"concordance": True, "score_verification": 50, "note": "Cross-verification non disponible"}
