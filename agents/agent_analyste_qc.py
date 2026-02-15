"""
Agent QC: ANALYSTE QUEBEC — Strategie specifique droit routier QC
Code de la securite routiere, SAAQ, Cour municipale, reglements municipaux
V2: Pre-scoring deterministe + stats acquittement + boost vecteurs defense
Moteur: GLM-5 (744B, low hallucination, raisonnement juridique)
"""

import json
import time
from agents.base_agent import BaseAgent, GLM5


class AgentAnalysteQC(BaseAgent):

    # Taux d'acquittement connus par vecteur de defense (base sur jurisprudence reelle)
    VECTEURS_ACQUITTEMENT = {
        "cinematometre": {
            "boost": 25,
            "raison": "Vice technique cinematometre (calibration, numero serie) = acquittement frequent",
            "exemples": ["Bergeron 2023 QCCM 901", "Picard 2023 QCCM 89"]
        },
        "radar_photo": {
            "boost": 15,
            "raison": "Photo radar: identification vehicule/plaque contestable (art. 592 CSR)",
            "exemples": ["Fortier 2022 QCCM 234"]
        },
        "identification": {
            "boost": 15,
            "raison": "Erreur identification vehicule (couleur, modele, plaque) = doute raisonnable",
            "exemples": ["Caron 2022 QCCM 145", "Fortier 2022 QCCM 234"]
        },
        "signalisation": {
            "boost": 20,
            "raison": "Signalisation absente/deficiente (zone travaux, temporaire) = acquittement",
            "exemples": ["Gendron 2020 QCCM 312"]
        },
        "zone_travaux": {
            "boost": 15,
            "raison": "Zone travaux sans travaux actifs ou sans signalisation adequate",
            "exemples": ["Gendron 2020 QCCM 312"]
        },
        "double_appareil": {
            "boost": 25,
            "raison": "Double lecture/appareil contradictoire = doute raisonnable",
            "exemples": ["Picard 2023 QCCM 89"]
        },
        "motocyclette": {
            "boost": 10,
            "raison": "Plaque moto souvent illisible sur photo radar",
            "exemples": ["Fortier 2022 QCCM 234"]
        },
    }

    def __init__(self):
        super().__init__("Analyste_QC")

    def analyser(self, ticket, lois, precedents, contexte_texte=""):
        """
        Input: ticket QC + lois CSR + precedents QC + contexte enrichi
        Output: analyse juridique specifique au Quebec
        V2: Pre-scoring deterministe avant LLM
        """
        self.log("Analyse juridique QC (CSR/SAAQ)...", "STEP")
        start = time.time()

        # ═══ ETAPE 1: Pre-scoring deterministe ═══
        pre_score = self._pre_scoring(ticket, precedents)

        # ═══ ETAPE 2: Analyse stats des precedents ═══
        stats_precedents = self._analyser_precedents_stats(precedents)

        # ═══ ETAPE 3: Preparer contexte LLM ═══
        ctx_lois = "\n".join([
            f"- Art. {l.get('article','?')}: {l.get('titre_article', l.get('texte',''))[:200]}"
            for l in (lois or [])[:7]
        ])

        ctx_precedents = "\n".join([
            f"- [{p.get('citation','?')}] {p.get('tribunal','?')} | "
            f"{p.get('date','?')} | RESULTAT: {p.get('resultat','inconnu')}\n  {p.get('resume','')[:250]}"
            for p in (precedents or [])[:10]
        ])

        # ═══ ETAPE 4: LLM avec pre-scoring en contexte ═══
        prompt = f"""Tu es un avocat specialise en droit routier au Quebec.

REGLES SPECIFIQUES QUEBEC:
- Code de la securite routiere (CSR), L.R.Q., c. C-24.2
- Constat d'infraction: 30 jours pour plaider non coupable (art. 160)
- Cour municipale: juge seul, pas de jury
- Photo radar/cinematometre: proprietaire = presume conducteur (art. 592 CSR)
- MAIS: le proprietaire peut nommer le vrai conducteur pour eviter les points
- Zones scolaires: amende doublee (art. 329)
- Zone de construction: amende doublee (art. 329.2)
- Grand exces (40+ km/h): saisie immediate du vehicule 7 jours
- SAAQ: regime de points d'inaptitude (max 15 pour permis regulier)

REGLE ABSOLUE: Cite UNIQUEMENT les precedents fournis. N'invente AUCUN cas.

## TICKET
- Infraction: {ticket.get('infraction', '')}
- Article CSR: {ticket.get('loi', '')}
- Amende: {ticket.get('amende', '')}
- Points SAAQ: {ticket.get('points_inaptitude', 0)}
- Lieu: {ticket.get('lieu', '')}
- Date: {ticket.get('date', '')}
- Appareil: {ticket.get('appareil', '')}
- Vehicule: {ticket.get('vehicule', '')}
- Vitesse captee: {ticket.get('vitesse_captee', '')}
- Vitesse permise: {ticket.get('vitesse_permise', '')}

## LOIS CSR APPLICABLES
{ctx_lois if ctx_lois else "Aucun article CSR specifique indexe."}

## PRECEDENTS QC (DE NOTRE BASE — REELS)
{ctx_precedents if ctx_precedents else "AUCUN precedent QC."}

## STATISTIQUES DES PRECEDENTS TROUVES
- Total: {stats_precedents['total']}
- Acquittes: {stats_precedents['acquittes']} ({stats_precedents['pct_acquittes']}%)
- Coupables: {stats_precedents['coupables']} ({stats_precedents['pct_coupables']}%)
- Taux d'acquittement sur cas similaires: {stats_precedents['pct_acquittes']}%

## PRE-ANALYSE (VECTEURS DE DEFENSE DETECTES)
Score pre-calcule: {pre_score['score_base']}%
Vecteurs detectes:
{chr(10).join(f"- {v['nom']}: +{v['boost']}% — {v['raison']}" for v in pre_score['vecteurs'])}

IMPORTANT: Le score_contestation final doit TENIR COMPTE du pre-score ({pre_score['score_base']}%)
et des statistiques d'acquittement ({stats_precedents['pct_acquittes']}%).
Si le pre-score est >= 50, le score final ne devrait PAS etre en dessous de 45.
Si des vecteurs de defense forts sont detectes, le score devrait refleter ces opportunites.

## CONTEXTE ENVIRONNEMENTAL
{contexte_texte if contexte_texte else "Aucune donnee meteo/route disponible."}

## REPONDS EN JSON:
{{
    "score_contestation": {pre_score['score_base']},
    "confiance": "faible|moyen|eleve",
    "base_sur_precedents": true,
    "nb_precedents_utilises": {stats_precedents['total']},
    "loi_applicable": "article CSR et resume",
    "zone_speciale": "scolaire|construction|aucune",
    "grand_exces": {str(pre_score.get('grand_exces', False)).lower()},
    "saisie_vehicule": false,
    "vecteurs_defense": {json.dumps([v['nom'] for v in pre_score['vecteurs']], ensure_ascii=False)},
    "strategie": "description detaillee",
    "arguments": ["arg1 specifique avec reference jurisprudence", "arg2", "arg3"],
    "precedents_cites": [
        {{"citation": "EXACTEMENT comme fourni", "pertinence": "desc", "resultat": "acquitte|coupable"}}
    ],
    "recommandation": "contester|payer|negocier|attendre",
    "explication": "2-3 phrases",
    "note_saaq": "impact sur les points SAAQ",
    "avertissement": ""
}}

IMPORTANT: Ajuste le score_contestation selon ton analyse juridique, mais garde-le PROCHE du pre-score ({pre_score['score_base']}%) sauf si tu as une raison juridique forte de le modifier significativement."""

        system = ("Avocat QC specialise CSR/SAAQ. Cite UNIQUEMENT les precedents fournis. "
                  "Tiens compte du pre-score et des vecteurs de defense. JSON uniquement.")

        response = self.call_ai(prompt, system_prompt=system, model=GLM5, temperature=0.1, max_tokens=4000)
        duration = time.time() - start

        if response["success"]:
            try:
                analyse = self.parse_json_response(response["text"])
            except Exception as e:
                self.log(f"Parsing fail ({e}), retry Mixtral...", "WARN")
                from agents.base_agent import MIXTRAL_FR
                response = self.call_ai(prompt, system_prompt=system, model=MIXTRAL_FR, temperature=0.1, max_tokens=4000)
                if response["success"]:
                    try:
                        analyse = self.parse_json_response(response["text"])
                    except Exception as e2:
                        self.log(f"Erreur parsing retry: {e2}", "FAIL")
                        self.log_run("analyser_qc", "", "", duration=time.time()-start, success=False, error=str(e2))
                        return {"raw_response": response["text"], "error": str(e2)}
                else:
                    self.log(f"Erreur AI retry: {response.get('error', '?')}", "FAIL")
                    self.log_run("analyser_qc", "", "", duration=time.time()-start, success=False, error=response.get("error"))
                    return None

            # ═══ POST-TRAITEMENT: S'assurer que le score n'est pas trop bas vs pre-score ═══
            llm_score = analyse.get("score_contestation", 0)
            if isinstance(llm_score, str):
                try:
                    llm_score = int(llm_score)
                except (ValueError, TypeError):
                    llm_score = pre_score['score_base']

            # Le score final est la moyenne ponderee du pre-score et du score LLM
            # Pre-score (40%) + LLM (60%) — le LLM peut ajuster mais pas ignorer les vecteurs
            final_score = int(pre_score['score_base'] * 0.4 + llm_score * 0.6)
            analyse["score_contestation"] = final_score
            analyse["score_pre_calcule"] = pre_score['score_base']
            analyse["score_llm"] = llm_score
            analyse["vecteurs_defense"] = [v['nom'] for v in pre_score['vecteurs']]

            if not precedents:
                analyse["confiance"] = "faible"
                analyse["base_sur_precedents"] = False

            # Recommandation basee sur le score final
            if final_score >= 60:
                analyse["recommandation"] = "contester"
            elif final_score >= 40:
                analyse["recommandation"] = "contester"
            elif final_score >= 25:
                analyse["recommandation"] = "negocier"
            else:
                analyse["recommandation"] = "payer"

            self.log(f"Score QC: {final_score}% (pre:{pre_score['score_base']}% llm:{llm_score}%) | "
                     f"Grand exces: {analyse.get('grand_exces', '?')}", "OK")
            self.log_run("analyser_qc", f"QC {ticket.get('infraction', '')}",
                         f"Score={final_score}%",
                         tokens=response["tokens"], duration=time.time()-start)
            return analyse
        else:
            self.log(f"Erreur AI: {response.get('error', '?')}", "FAIL")
            self.log_run("analyser_qc", "", "", duration=duration, success=False, error=response.get("error"))
            return None

    def _pre_scoring(self, ticket, precedents):
        """Pre-scoring deterministe base sur les vecteurs de defense detectes"""
        score = 25  # Score de base pour tout ticket
        vecteurs = []
        grand_exces = False

        infraction = (ticket.get("infraction", "") or "").lower()
        appareil = (ticket.get("appareil", "") or "").lower()
        vehicule = (ticket.get("vehicule", "") or "").lower()
        lieu = (ticket.get("lieu", "") or "").lower()
        loi = (ticket.get("loi", "") or "").lower()
        contexte = (ticket.get("contexte", "") or "").lower()

        v_captee = ticket.get("vitesse_captee")
        v_permise = ticket.get("vitesse_permise")
        exces = 0
        if v_captee and v_permise:
            try:
                exces = int(v_captee) - int(v_permise)
            except (ValueError, TypeError):
                pass

        # Grand exces = malus
        if exces >= 40:
            grand_exces = True
            score -= 10  # Plus dur a contester

        # === VECTEURS DE DEFENSE ===

        # Tout ticket de vitesse a un potentiel de base (verif appareil, constat)
        if any(w in infraction for w in ["vitesse", "excès", "exces", "km/h"]):
            score += 5
            vecteurs.append({
                "nom": "vitesse_base",
                "boost": 5,
                "raison": "Tout ticket vitesse: verifier appareil, constat, signalisation"
            })

        # Cinematometre
        if "cinematometre" in appareil or "cinémomètre" in appareil:
            v = self.VECTEURS_ACQUITTEMENT["cinematometre"]
            score += v["boost"]
            vecteurs.append({"nom": "cinematometre", "boost": v["boost"], "raison": v["raison"]})

        # Radar photo
        if "radar" in appareil or "photo" in appareil:
            v = self.VECTEURS_ACQUITTEMENT["radar_photo"]
            score += v["boost"]
            vecteurs.append({"nom": "radar_photo", "boost": v["boost"], "raison": v["raison"]})

        # Motocyclette
        if "moto" in vehicule or "motocyclette" in vehicule:
            v = self.VECTEURS_ACQUITTEMENT["motocyclette"]
            score += v["boost"]
            vecteurs.append({"nom": "motocyclette", "boost": v["boost"], "raison": v["raison"]})

        # Zone travaux
        if "travaux" in lieu or "construction" in lieu or "chantier" in lieu or "travaux" in contexte:
            v = self.VECTEURS_ACQUITTEMENT["zone_travaux"]
            score += v["boost"]
            vecteurs.append({"nom": "zone_travaux", "boost": v["boost"], "raison": v["raison"]})

        # Signalisation
        if "signalisation" in contexte or "panneau" in contexte or "temporaire" in lieu:
            v = self.VECTEURS_ACQUITTEMENT["signalisation"]
            score += v["boost"]
            vecteurs.append({"nom": "signalisation", "boost": v["boost"], "raison": v["raison"]})

        # Double appareil
        if "double" in contexte or "deux" in contexte:
            v = self.VECTEURS_ACQUITTEMENT["double_appareil"]
            score += v["boost"]
            vecteurs.append({"nom": "double_appareil", "boost": v["boost"], "raison": v["raison"]})

        # === BOOST PAR PRECEDENTS ACQUITTES ===
        if precedents:
            nb_acquittes = sum(1 for p in precedents
                             if (p.get("resultat", "") or "").lower() in ("acquitte", "accueilli", "annule"))
            nb_total = len([p for p in precedents if (p.get("resultat", "") or "").lower() != "inconnu"])
            if nb_total > 0:
                pct_acquittes = nb_acquittes * 100 // nb_total
                if pct_acquittes >= 50:
                    boost = min(15, pct_acquittes // 5)
                    score += boost
                    vecteurs.append({
                        "nom": "precedents_favorables",
                        "boost": boost,
                        "raison": f"{pct_acquittes}% des precedents similaires sont des acquittements"
                    })

        # Borner entre 10 et 90
        score = max(10, min(90, score))

        return {
            "score_base": score,
            "vecteurs": vecteurs,
            "grand_exces": grand_exces,
            "exces_kmh": exces
        }

    def _analyser_precedents_stats(self, precedents):
        """Calculer les statistiques des precedents trouves"""
        if not precedents:
            return {"total": 0, "acquittes": 0, "coupables": 0, "pct_acquittes": 0, "pct_coupables": 0}

        acquittes = sum(1 for p in precedents
                       if (p.get("resultat", "") or "").lower() in ("acquitte", "accueilli", "annule"))
        coupables = sum(1 for p in precedents
                       if (p.get("resultat", "") or "").lower() in ("coupable", "condamne"))
        total = len(precedents)
        total_avec_resultat = acquittes + coupables

        pct_a = round(acquittes * 100 / total_avec_resultat) if total_avec_resultat > 0 else 0
        pct_c = round(coupables * 100 / total_avec_resultat) if total_avec_resultat > 0 else 0

        return {
            "total": total,
            "acquittes": acquittes,
            "coupables": coupables,
            "pct_acquittes": pct_a,
            "pct_coupables": pct_c
        }
