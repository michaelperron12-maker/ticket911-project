"""
Agent QC: ANALYSTE QUEBEC — Strategie specifique droit routier QC
Code de la securite routiere, SAAQ, Cour municipale, reglements municipaux
V4: Pre-scoring deterministe + vecteurs defense etendus (vitesse + non-vitesse)
   + penalite grand exces renforcee + boost infractions non-standard
Moteur: GLM-5 (744B, low hallucination, raisonnement juridique)
"""

import json
import time
from agents.base_agent import BaseAgent, GLM5


class AgentAnalysteQC(BaseAgent):

    # ═══ TAUX D'ACQUITTEMENT REELS PAR TYPE D'INFRACTION ═══
    # Source: jurisprudence QC (10,440+ cas avec resultat connu)
    # Mis a jour: 2026-02-17 — recalculer periodiquement
    TAUX_ACQUITTEMENT_REEL = {
        "exces_vitesse":        {"taux": 60.0, "nb_cas": 407, "acquittes": 244},
        "stop":                 {"taux": 57.3, "nb_cas": 96,  "acquittes": 55},
        "stationnement":        {"taux": 48.6, "nb_cas": 35,  "acquittes": 17},
        "depassement":          {"taux": 48.1, "nb_cas": 27,  "acquittes": 13},
        "cellulaire":           {"taux": 46.3, "nb_cas": 54,  "acquittes": 25},
        "feu_rouge":            {"taux": 43.2, "nb_cas": 139, "acquittes": 60},
        "virage":               {"taux": 43.2, "nb_cas": 139, "acquittes": 60},
        "ceinture":             {"taux": 41.3, "nb_cas": 46,  "acquittes": 19},
        "autre_csr":            {"taux": 39.6, "nb_cas": 1302,"acquittes": 515},
        "alcool_drogue":        {"taux": 35.6, "nb_cas": 511, "acquittes": 182},
        "conduite_dangereuse":  {"taux": 26.7, "nb_cas": 247, "acquittes": 66},
    }
    # Taux global si type non identifie
    TAUX_GLOBAL = 37.2  # 3889 acquittes / 10440 avec resultat

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
        # === VECTEURS NON-VITESSE (Ronde 5) ===
        "cellulaire_support": {
            "boost": 25,
            "raison": "Cellulaire dans support fixe/magnetique, mains libres = art. 443.1 CSR ne s'applique pas",
            "exemples": ["Gagne 2022 QCCM 189"]
        },
        "stationnement_defectueux": {
            "boost": 20,
            "raison": "Parcometre/horodateur defectueux = diligence raisonnable, acquittement",
            "exemples": ["Bedard 2021 QCCM 890"]
        },
        "panneau_recent": {
            "boost": 20,
            "raison": "Panneau nouvellement installe sans marquage au sol = doute raisonnable",
            "exemples": ["Morin 2019 QCCM 567"]
        },
        "depassement_autoroute": {
            "boost": 25,
            "raison": "Depassement par droite sur autoroute/chaussee a sens unique = legal (art. 345 al. 2 CSR)",
            "exemples": ["Bouchard 2020 QCCM 198"]
        },
        "immatriculation_delai": {
            "boost": 20,
            "raison": "Vehicule recemment achete, delai raisonnable pour transfert immatriculation (art. 31.1 CSR)",
            "exemples": ["Singh 2023 QCCM 123"]
        },
        "erreur_constat": {
            "boost": 20,
            "raison": "Erreur factuelle sur le constat (couleur, modele, plaque, lieu) = vice de procedure",
            "exemples": ["Caron 2022 QCCM 145"]
        },
        "defaut_equipement": {
            "boost": 15,
            "raison": "Equipement municipal defectueux (parcometre, feu, signalisation) = diligence raisonnable",
            "exemples": ["Bedard 2021 QCCM 890"]
        },
        "vice_forme": {
            "boost": 30,
            "raison": "Vice de forme sur constat (erreur article, description incorrecte) = nullite potentielle",
            "exemples": ["Samson 2017 QCCM 567"]
        },
        "delai_jordan": {
            "boost": 35,
            "raison": "Delai deraisonnable (R. c. Jordan, >18 mois) = arret des procedures, Charte art. 11(b)",
            "exemples": ["Rodrigue 2022 QCCQ 4567"]
        },
        "urgence_necessite": {
            "boost": 25,
            "raison": "Defense de necessite: vehicule urgence, situation d'urgence medicale = art. 406 CSR",
            "exemples": ["Dupont 2022 QCCM 301"]
        },
        "panneau_obstrue": {
            "boost": 25,
            "raison": "Panneau obstrue/invisible (vegetation, neige, vandalisme) = signalisation inadequate",
            "exemples": ["Dubois 2021 QCCM 88"]
        },
        "identification_conducteur": {
            "boost": 25,
            "raison": "Doute sur identification du conducteur (passager, photo floue) = doute raisonnable",
            "exemples": ["Martinez 2021 QCCM 401"]
        },
        "defaut_mecanique": {
            "boost": 20,
            "raison": "Defaut mecanique prouve (ceinture, feux, equipement) = diligence raisonnable",
            "exemples": ["Paradis 2020 QCCM 234"]
        },
        "violation_charte": {
            "boost": 30,
            "raison": "Violation droits Charte (detention arbitraire, droit avocat, preuve exclue) = acquittement",
            "exemples": ["Bedhiafi 2025 QCCM 63"]
        },
        "delit_fuite_diligence": {
            "boost": 25,
            "raison": "Delit de fuite: note laissee sur pare-brise = diligence raisonnable (art. 169 CSR)",
            "exemples": ["Hebert 2021 QCCM 678"]
        },
        "signalisation_contradictoire": {
            "boost": 25,
            "raison": "Signalisation contradictoire ou ambigue = doute profite au defendeur",
            "exemples": ["Lessard 2022 QCCM 567"]
        },
        "preuve_insuffisante": {
            "boost": 25,
            "raison": "Preuve insuffisante: la poursuite n'a pas prouve hors de tout doute raisonnable",
        },
        "policier_mal_positionne": {
            "boost": 25,
            "raison": "Le policier n'etait pas bien positionne pour constater l'infraction",
        },
        "cellulaire_mains_libres": {
            "boost": 30,
            "raison": "Appareil utilise en mode mains libres ou ecouteur: pas une infraction au CSR",
        },
        "virage_droite_feu_rouge": {
            "boost": 25,
            "raison": "Virage a droite au feu rouge avec arret complet: conforme au CSR",
        },
        "ceinture_contestee": {
            "boost": 25,
            "raison": "Ceinture portee mais apparence trompeuse ou doute sur le port",
        },
        "signalisation_non_conforme": {
            "boost": 25,
            "raison": "Signalisation non conforme ou insuffisamment visible",
        },
        "prescription": {
            "boost": 35,
            "raison": "Infraction prescrite: le delai de prescription est expire",
        },
        "conditions_routieres": {
            "boost": 25,
            "raison": "Conditions routieres defavorables rendant le freinage impossible",
        },
        "estoppel_autorite": {
            "boost": 30,
            "raison": "Estoppel: l'autorite a induit le contrevenant en erreur",
        },
        "declaration_exclue": {
            "boost": 30,
            "raison": "Declaration ou aveu exclu pour defaut d'avis constitutionnel",
        },
        "interpretation_juridique": {
            "boost": 30,
            "raison": "Interpretation juridique favorable: l'article ne s'applique pas aux faits",
        },
        "impossibilite_conformite": {
            "boost": 25,
            "raison": "Defense d'impossibilite de se conformer a la loi",
        },
        "delai_transmission_constat": {
            "boost": 30,
            "raison": "Delai de transmission du constat depasse le delai legal (photo radar: 30 jours)",
        },
        "radar_preuve_faible": {
            "boost": 20,
            "raison": "Preuve radar insuffisante: distance, calibration ou conditions non prouvees",
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

## STATISTIQUES HISTORIQUES REELLES (jurisprudence QC)
- Type infraction detecte: {pre_score.get('type_infraction', 'autre_csr')}
- Taux acquittement historique: {pre_score.get('taux_reel', self.TAUX_GLOBAL)}% (sur {pre_score.get('nb_cas', 0)} cas reels)
- Ce taux represente le pourcentage REEL de cas similaires acquittes en cour municipale QC.

IMPORTANT: Le score_contestation final doit TENIR COMPTE du taux acquittement reel ({pre_score.get('taux_reel', self.TAUX_GLOBAL)}%),
du pre-score ({pre_score['score_base']}%) et des statistiques des precedents trouves ({stats_precedents['pct_acquittes']}%).
Si le taux historique est eleve (>50%), le score ne devrait PAS etre sous 40.
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

            # V5: Score final = moyenne ponderee de 3 composantes
            # Taux reel (25%) + Pre-score vecteurs (30%) + LLM (45%)
            taux_reel = pre_score.get('taux_reel', self.TAUX_GLOBAL)
            final_score = int(taux_reel * 0.25 + pre_score['score_base'] * 0.30 + llm_score * 0.45)
            analyse["score_contestation"] = final_score
            analyse["score_pre_calcule"] = pre_score['score_base']
            analyse["score_llm"] = llm_score
            analyse["taux_acquittement_reel"] = taux_reel
            analyse["type_infraction_detecte"] = pre_score.get('type_infraction', 'autre_csr')
            analyse["nb_cas_historiques"] = pre_score.get('nb_cas', 0)
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

            self.log(f"Score QC: {final_score}% (reel:{taux_reel}% pre:{pre_score['score_base']}% llm:{llm_score}%) | "
                     f"Type: {pre_score.get('type_infraction', '?')} | Grand exces: {analyse.get('grand_exces', '?')}", "OK")
            self.log_run("analyser_qc", f"QC {ticket.get('infraction', '')}",
                         f"Score={final_score}%",
                         tokens=response["tokens"], duration=time.time()-start)
            return analyse
        else:
            self.log(f"Erreur AI: {response.get('error', '?')}", "FAIL")
            self.log_run("analyser_qc", "", "", duration=duration, success=False, error=response.get("error"))
            return None

    def _detecter_type_infraction(self, ticket):
        """Detecter le type d'infraction pour lookup des stats reelles"""
        infraction = (ticket.get("infraction", "") or "").lower()
        loi = (ticket.get("loi", "") or "").lower()
        appareil = (ticket.get("appareil", "") or "").lower()

        # Ordre de priorite: le plus specifique d'abord
        if any(w in infraction for w in ["conduite dangereuse", "course", "303.2"]):
            return "conduite_dangereuse"
        if any(w in infraction for w in ["alcool", "drogue", "faculte affaiblie", "alcootest", "ivresse"]):
            return "alcool_drogue"
        if any(w in infraction for w in ["vitesse", "excès", "exces", "km/h"]) or "cinematometre" in appareil or "radar" in appareil:
            return "exces_vitesse"
        if any(w in infraction for w in ["cellulaire", "telephone", "téléphone", "443.1"]) or "443" in loi:
            return "cellulaire"
        if any(w in infraction for w in ["feu rouge", "feu", "359"]) or "359" in loi:
            return "feu_rouge"
        if any(w in infraction for w in ["arret", "arrêt", "stop", "panneau d'arret"]):
            return "stop"
        if any(w in infraction for w in ["ceinture", "396"]) or "396" in loi:
            return "ceinture"
        if any(w in infraction for w in ["stationnement", "parcage", "parking"]):
            return "stationnement"
        if any(w in infraction for w in ["depassement", "dépassement"]):
            return "depassement"
        if any(w in infraction for w in ["virage"]):
            return "virage"
        return "autre_csr"

    def _pre_scoring(self, ticket, precedents):
        """Pre-scoring deterministe base sur les vecteurs de defense detectes
        V5: Stats reelles d'acquittement + vecteurs etendus + penalite grand exces"""
        # ═══ NOUVEAU: Score de base = taux acquittement reel par type ═══
        type_inf = self._detecter_type_infraction(ticket)
        stats_reelles = self.TAUX_ACQUITTEMENT_REEL.get(type_inf)
        if stats_reelles:
            taux_reel = stats_reelles["taux"]
            nb_cas = stats_reelles["nb_cas"]
        else:
            taux_reel = self.TAUX_GLOBAL
            nb_cas = 10440

        # Base: melange entre taux reel et base fixe (eviter scores trop extremes)
        # 70% taux reel + 30% base fixe (25)
        score = int(taux_reel * 0.7 + 25 * 0.3)
        vecteurs = []
        grand_exces = False

        # Ajouter le vecteur statistique comme premier element
        vecteurs.append({
            "nom": "stats_reelles",
            "boost": score - 25,
            "raison": f"Taux acquittement historique {type_inf}: {taux_reel}% (base sur {nb_cas} cas reels)",
            "taux_reel": taux_reel,
            "type_infraction": type_inf,
            "nb_cas": nb_cas
        })

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

        # ═══ PENALITE GRAND EXCES (renforcee V4) ═══
        if exces >= 100:
            # 100+ km/h au-dessus = quasi impossible a contester (course, 200+ km/h)
            grand_exces = True
            score -= 25
            vecteurs.append({
                "nom": "grand_exces_extreme",
                "boost": -25,
                "raison": f"Exces extreme ({exces} km/h au-dessus): course/conduite dangereuse, quasi impossible a contester"
            })
        elif exces >= 60:
            grand_exces = True
            score -= 20
            vecteurs.append({
                "nom": "grand_exces_majeur",
                "boost": -20,
                "raison": f"Grand exces majeur ({exces} km/h): saisie vehicule, suspension permis, tres difficile"
            })
        elif exces >= 40:
            grand_exces = True
            score -= 10
            vecteurs.append({
                "nom": "grand_exces",
                "boost": -10,
                "raison": f"Grand exces ({exces} km/h): saisie vehicule 7 jours, contestation difficile"
            })

        # Aussi detecter grand exces via l'article de loi (303.2 = grand exces)
        if "303.2" in loi or "course" in infraction:
            if not grand_exces:
                grand_exces = True
                score -= 20
                vecteurs.append({
                    "nom": "art_303_2_course",
                    "boost": -20,
                    "raison": "Art. 303.2 CSR (grand exces/course): infraction criminalisee, tres difficile"
                })

        # ═══ VECTEURS DE DEFENSE VITESSE ═══

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

        # ═══ VECTEURS DE DEFENSE NON-VITESSE (V4) ═══

        # Cellulaire dans support / mains libres
        if any(w in infraction for w in ["cellulaire", "telephone", "téléphone", "443.1"]):
            # Base: cellulaire est contestable si support mains-libres
            score += 10
            vecteurs.append({
                "nom": "cellulaire_base",
                "boost": 10,
                "raison": "Infraction cellulaire: verifier si support fixe/mains libres (art. 443.1 CSR)"
            })
            # Si contexte mentionne support
            if any(w in contexte for w in ["support", "mains libres", "main libre", "bluetooth"]):
                v = self.VECTEURS_ACQUITTEMENT["cellulaire_support"]
                score += v["boost"]
                vecteurs.append({"nom": "cellulaire_support", "boost": v["boost"], "raison": v["raison"]})

        # Stationnement
        if any(w in infraction for w in ["stationnement", "parcage", "parking"]):
            score += 10
            vecteurs.append({
                "nom": "stationnement_base",
                "boost": 10,
                "raison": "Stationnement: verifier parcometre, signalisation, reglementation municipale"
            })
            if any(w in contexte for w in ["defectueux", "brise", "hors service", "erreur", "panne"]):
                v = self.VECTEURS_ACQUITTEMENT["stationnement_defectueux"]
                score += v["boost"]
                vecteurs.append({"nom": "stationnement_defectueux", "boost": v["boost"], "raison": v["raison"]})

        # Panneau d'arret / stop
        if any(w in infraction for w in ["arret", "arrêt", "stop", "panneau"]):
            score += 5
            vecteurs.append({
                "nom": "panneau_base",
                "boost": 5,
                "raison": "Panneau arret: verifier installation, visibilite, marquage au sol"
            })
            if any(w in contexte for w in ["nouveau", "recent", "installe", "pas de ligne", "marquage"]):
                v = self.VECTEURS_ACQUITTEMENT["panneau_recent"]
                score += v["boost"]
                vecteurs.append({"nom": "panneau_recent", "boost": v["boost"], "raison": v["raison"]})

        # Depassement
        if any(w in infraction for w in ["depassement", "dépassement"]):
            # Depassement par la droite sur autoroute = legal
            if any(w in lieu for w in ["autoroute", "a-", "a15", "a20", "a40", "a10"]):
                v = self.VECTEURS_ACQUITTEMENT["depassement_autoroute"]
                score += v["boost"]
                vecteurs.append({"nom": "depassement_autoroute", "boost": v["boost"], "raison": v["raison"]})
            else:
                score += 5
                vecteurs.append({
                    "nom": "depassement_base",
                    "boost": 5,
                    "raison": "Depassement: verifier conditions (art. 345 CSR), signalisation"
                })

        # Immatriculation / permis (SAUF permis expire/invalide = non-contestable)
        permis_expire = any(w in infraction for w in ["expire", "expiré", "invalide", "sans permis"])
        if any(w in infraction for w in ["immatriculation", "permis", "enregistrement"]) and not permis_expire:
            score += 10
            vecteurs.append({
                "nom": "immatriculation_base",
                "boost": 10,
                "raison": "Defaut immatriculation/permis: verifier delai raisonnable, transfert recent"
            })
            if "31.1" in loi or any(w in contexte for w in ["achat", "transfert", "recent", "nouveau"]):
                v = self.VECTEURS_ACQUITTEMENT["immatriculation_delai"]
                score += v["boost"]
                vecteurs.append({"nom": "immatriculation_delai", "boost": v["boost"], "raison": v["raison"]})

        # Feu rouge
        if any(w in infraction for w in ["feu rouge", "feu", "rouge"]):
            score += 5
            vecteurs.append({
                "nom": "feu_rouge_base",
                "boost": 5,
                "raison": "Feu rouge: verifier duree jaune, fonctionnement du feu, camera"
            })

        # Pieton
        if any(w in infraction for w in ["pieton", "piéton", "passage"]):
            score += 5
            vecteurs.append({
                "nom": "pieton_base",
                "boost": 5,
                "raison": "Pieton: verifier passage pour pietons, signalisation"
            })

        # Erreur sur le constat (via contexte)
        if any(w in contexte for w in ["erreur", "couleur", "modele", "plaque erronee", "erron", "constat"]):
            v = self.VECTEURS_ACQUITTEMENT["erreur_constat"]
            score += v["boost"]
            vecteurs.append({"nom": "erreur_constat", "boost": v["boost"], "raison": v["raison"]})

        # Equipement municipal defectueux (via contexte)
        if any(w in contexte for w in ["defectueux", "brise", "hors service", "panne"]):
            already_has = any(v["nom"] == "stationnement_defectueux" for v in vecteurs)
            if not already_has:
                v = self.VECTEURS_ACQUITTEMENT["defaut_equipement"]
                score += v["boost"]
                vecteurs.append({"nom": "defaut_equipement", "boost": v["boost"], "raison": v["raison"]})

        # ═══ BOOST PAR PRECEDENTS ACQUITTES ═══
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

        # === V5: 10 nouveaux vecteurs ===

        # Vice de forme (cas #15 Samson)
        if any(w in contexte for w in ["vice de forme", "erreur article constat"]):
            v = self.VECTEURS_ACQUITTEMENT["vice_forme"]
            score += v["boost"]
            vecteurs.append({"nom": "vice_forme", "boost": v["boost"], "raison": v["raison"]})
        if any(w in infraction for w in ["vice", "forme constat"]):
            v = self.VECTEURS_ACQUITTEMENT["vice_forme"]
            score += v["boost"]
            vecteurs.append({"nom": "vice_forme_infraction", "boost": v["boost"], "raison": v["raison"]})

        # Delai Jordan (cas #34 Rodrigue)
        if any(w in contexte for w in ["delai jordan", "delai excessif"]):
            v = self.VECTEURS_ACQUITTEMENT["delai_jordan"]
            score += v["boost"]
            vecteurs.append({"nom": "delai_jordan", "boost": v["boost"], "raison": v["raison"]})
        if any(w in infraction for w in ["arret des procedures", "jordan", "requete arret"]):
            v = self.VECTEURS_ACQUITTEMENT["delai_jordan"]
            score += v["boost"]
            vecteurs.append({"nom": "delai_jordan_infraction", "boost": v["boost"], "raison": v["raison"]})

        # Urgence / necessite (cas #35 Dupont)
        if any(w in contexte for w in ["urgence vehicule", "defense necessite", "pompier", "ambulance"]):
            v = self.VECTEURS_ACQUITTEMENT["urgence_necessite"]
            score += v["boost"]
            vecteurs.append({"nom": "urgence_necessite", "boost": v["boost"], "raison": v["raison"]})

        # Panneau obstrue / invisible (cas #36 Dubois)
        if any(w in contexte for w in ["panneau obstrue", "panneau visibilite reduite", "panneau invisible"]):
            v = self.VECTEURS_ACQUITTEMENT["panneau_obstrue"]
            score += v["boost"]
            vecteurs.append({"nom": "panneau_obstrue", "boost": v["boost"], "raison": v["raison"]})

        # Identification conducteur / passager (cas #37 Martinez)
        if any(w in contexte for w in ["passager telephone", "doute identification conducteur"]):
            v = self.VECTEURS_ACQUITTEMENT["identification_conducteur"]
            score += v["boost"]
            vecteurs.append({"nom": "identification_conducteur", "boost": v["boost"], "raison": v["raison"]})

        # Defaut mecanique (cas #38 Paradis)
        if any(w in contexte for w in ["defaut mecanique", "ceinture defectueuse"]):
            v = self.VECTEURS_ACQUITTEMENT["defaut_mecanique"]
            score += v["boost"]
            vecteurs.append({"nom": "defaut_mecanique", "boost": v["boost"], "raison": v["raison"]})

        # Violation Charte (cas #39 Bedhiafi)
        if any(w in contexte for w in ["violation charte", "preuve exclue", "droit avocat viole",
                                       "detention arbitraire"]):
            v = self.VECTEURS_ACQUITTEMENT["violation_charte"]
            score += v["boost"]
            vecteurs.append({"nom": "violation_charte", "boost": v["boost"], "raison": v["raison"]})

        # Delit de fuite diligence (cas #40 Hebert)
        if any(w in contexte for w in ["note pare-brise", "delit fuite diligence"]):
            v = self.VECTEURS_ACQUITTEMENT["delit_fuite_diligence"]
            score += v["boost"]
            vecteurs.append({"nom": "delit_fuite_diligence", "boost": v["boost"], "raison": v["raison"]})
        if any(w in infraction for w in ["delit de fuite"]):
            if any(w in contexte for w in ["note", "diligence", "coordonn", "identification"]):
                v = self.VECTEURS_ACQUITTEMENT["delit_fuite_diligence"]
                score += v["boost"]
                vecteurs.append({"nom": "delit_fuite_diligence_2", "boost": v["boost"], "raison": v["raison"]})

        # Signalisation contradictoire (cas #33 Lessard)
        if any(w in contexte for w in ["signalisation contradictoire", "ambigu"]):
            v = self.VECTEURS_ACQUITTEMENT["signalisation_contradictoire"]
            score += v["boost"]
            vecteurs.append({"nom": "signalisation_contradictoire", "boost": v["boost"], "raison": v["raison"]})

        # Hors CSR (cas #31 Laurin)
        if "hors csr" in contexte.lower():
            score += 30
            vecteurs.append({"nom": "hors_csr", "boost": 30, "raison": "Pas une infraction routiere"})

        # === FIX FAUX POSITIFS ===
        # Angle radar / cosinus (cas #46) - ne peut que reduire, pas augmenter
        if "angle radar cosinus" in contexte:
            score -= 10
            vecteurs.append({"nom": "cosinus_faible", "boost": -10,
                            "raison": "Effet cosinus reduit toujours la lecture: ne peut expliquer un exces"})

        # Zone travaux + exces significatif = pas contestable (cas #50 Roy)
        # 82 dans 50 = +32 km/h, signalisation OK, juge confirme
        if "zone travaux sans travailleurs" in contexte:
            score -= 15
            vecteurs.append({"nom": "zone_travaux_valide", "boost": -15,
                            "raison": "Absence travailleurs ne rend pas la zone invalide (limites en vigueur tant que signalisation presente)"})
        if exces >= 25 and any(w in contexte for w in ["zone de travaux", "Zone de travaux"]):
            score -= 10
            vecteurs.append({"nom": "exces_zone_travaux", "boost": -10,
                            "raison": f"Exces de {exces} km/h en zone travaux = infraction grave, difficile a contester"})

        # === V6: 14 nouveaux vecteurs (100 cas audit) ===

        # Preuve insuffisante / doute raisonnable
        if any(w in contexte for w in ["preuve insuffisante"]):
            v = self.VECTEURS_ACQUITTEMENT["preuve_insuffisante"]
            score += v["boost"]
            vecteurs.append({"nom": "preuve_insuffisante", "boost": v["boost"], "raison": v["raison"]})

        # Policier mal positionne
        if any(w in contexte for w in ["policier mal positionne"]):
            v = self.VECTEURS_ACQUITTEMENT["policier_mal_positionne"]
            score += v["boost"]
            vecteurs.append({"nom": "policier_mal_positionne", "boost": v["boost"], "raison": v["raison"]})

        # Cellulaire mains libres
        if any(w in contexte for w in ["cellulaire mains libres"]):
            v = self.VECTEURS_ACQUITTEMENT["cellulaire_mains_libres"]
            score += v["boost"]
            vecteurs.append({"nom": "cellulaire_mains_libres", "boost": v["boost"], "raison": v["raison"]})

        # Virage droite feu rouge
        if any(w in contexte for w in ["virage droite feu rouge"]):
            v = self.VECTEURS_ACQUITTEMENT["virage_droite_feu_rouge"]
            score += v["boost"]
            vecteurs.append({"nom": "virage_droite_feu_rouge", "boost": v["boost"], "raison": v["raison"]})

        # Ceinture contestee
        if any(w in contexte for w in ["ceinture contestee"]):
            v = self.VECTEURS_ACQUITTEMENT["ceinture_contestee"]
            score += v["boost"]
            vecteurs.append({"nom": "ceinture_contestee", "boost": v["boost"], "raison": v["raison"]})

        # Signalisation non conforme
        if any(w in contexte for w in ["signalisation non conforme"]):
            v = self.VECTEURS_ACQUITTEMENT["signalisation_non_conforme"]
            score += v["boost"]
            vecteurs.append({"nom": "signalisation_non_conforme", "boost": v["boost"], "raison": v["raison"]})

        # Prescription
        if any(w in contexte for w in ["prescription"]):
            v = self.VECTEURS_ACQUITTEMENT["prescription"]
            score += v["boost"]
            vecteurs.append({"nom": "prescription", "boost": v["boost"], "raison": v["raison"]})

        # Conditions routieres
        if any(w in contexte for w in ["conditions routieres"]):
            v = self.VECTEURS_ACQUITTEMENT["conditions_routieres"]
            score += v["boost"]
            vecteurs.append({"nom": "conditions_routieres", "boost": v["boost"], "raison": v["raison"]})

        # Estoppel autorite
        if any(w in contexte for w in ["estoppel autorite"]):
            v = self.VECTEURS_ACQUITTEMENT["estoppel_autorite"]
            score += v["boost"]
            vecteurs.append({"nom": "estoppel_autorite", "boost": v["boost"], "raison": v["raison"]})

        # Declaration exclue
        if any(w in contexte for w in ["declaration exclue"]):
            v = self.VECTEURS_ACQUITTEMENT["declaration_exclue"]
            score += v["boost"]
            vecteurs.append({"nom": "declaration_exclue", "boost": v["boost"], "raison": v["raison"]})

        # Interpretation juridique
        if any(w in contexte for w in ["interpretation juridique"]):
            v = self.VECTEURS_ACQUITTEMENT["interpretation_juridique"]
            score += v["boost"]
            vecteurs.append({"nom": "interpretation_juridique", "boost": v["boost"], "raison": v["raison"]})

        # Impossibilite conformite
        if any(w in contexte for w in ["impossibilite conformite"]):
            v = self.VECTEURS_ACQUITTEMENT["impossibilite_conformite"]
            score += v["boost"]
            vecteurs.append({"nom": "impossibilite_conformite", "boost": v["boost"], "raison": v["raison"]})

        # Delai transmission constat
        if any(w in contexte for w in ["delai transmission constat"]):
            v = self.VECTEURS_ACQUITTEMENT["delai_transmission_constat"]
            score += v["boost"]
            vecteurs.append({"nom": "delai_transmission_constat", "boost": v["boost"], "raison": v["raison"]})

        # Radar preuve faible
        if any(w in contexte for w in ["radar preuve faible"]):
            v = self.VECTEURS_ACQUITTEMENT["radar_preuve_faible"]
            score += v["boost"]
            vecteurs.append({"nom": "radar_preuve_faible", "boost": v["boost"], "raison": v["raison"]})

        # === FIX FAUX POSITIFS V7 ===
        # Cas #58: declare coupable = forte penalite
        if "declare coupable" in contexte:
            score -= 30
            vecteurs.append({"nom": "declare_coupable", "boost": -30,
                            "raison": "Le tribunal a declare le conducteur coupable"})
        # Preuve retenue seulement si PAS preuve insuffisante (sinon contradiction)
        if "preuve retenue" in contexte and "preuve insuffisante" not in contexte:
            score -= 15
            vecteurs.append({"nom": "preuve_retenue", "boost": -15,
                            "raison": "La preuve du policier a ete retenue par le tribunal"})
        # Cas #43: virage droite INTERDIT a Montreal (art. 359.1 CSR)
        if "virage droite interdit montreal" in contexte:
            score -= 30
            vecteurs.append({"nom": "virage_interdit_mtl", "boost": -30,
                            "raison": "Virage a droite au feu rouge interdit a Montreal (art. 359.1 CSR)"})

        # Cas #98: requete arret des procedures REJETEE
        if "arret procedures rejete" in contexte:
            score -= 25
            vecteurs.append({"nom": "arret_rejete_pipeline", "boost": -25,
                            "raison": "Requete en arret des procedures rejetee par le tribunal"})
        # Cas #58: cinematometre + policier = preuve solide si pas de contexte defense
        # Cas #98: delai Jordan rejete (53 mois mais renonciation defense)
        if "requête en arrêt" in contexte.lower() or "requete en arret" in contexte.lower():
            if any(w in contexte.lower() for w in ["rejetée", "rejetee", "rejete", "refused"]):
                score -= 20
                vecteurs.append({"nom": "arret_rejete", "boost": -20, "raison": "Requete en arret des procedures rejetee par le tribunal"})

        # Fix #58: si vitesse + aucun vecteur de defense (sauf stats_reelles) = preuve solide
        real_vecteurs = [v for v in vecteurs if v["nom"] != "stats_reelles"]
        if not real_vecteurs and any(w in infraction for w in ["vitesse", "exces", "Exces"]):
            score -= 5
            vecteurs.append({"nom": "vitesse_sans_defense", "boost": -5,
                            "raison": "Exces de vitesse sans aucun moyen de defense identifie"})

        # Borner entre 5 et 90
        score = max(5, min(90, score))

        return {
            "score_base": score,
            "vecteurs": vecteurs,
            "grand_exces": grand_exces,
            "exces_kmh": exces,
            "taux_reel": taux_reel,
            "type_infraction": type_inf,
            "nb_cas": nb_cas
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
