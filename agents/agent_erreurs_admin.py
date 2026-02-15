"""
Agent Phase 1: ERREURS ADMINISTRATIVES + ANALYSE STATISTIQUE SOCIALE
Analyse profonde du constat pour erreurs administratives (Art. 146 CPP, R-25)
+ Cross-reference statistique: profil agent, profil lieu, detection blitz/speed trap
Source: qc_constats_infraction (356K+ constats), lois_articles, jurisprudence
Zero IA requise (100% deterministe — requetes SQL + logique)
"""

import re
import time
from datetime import datetime
from agents.base_agent import BaseAgent


# ═══════════════════════════════════════════════════════════
# CHAMPS OBLIGATOIRES PAR JURIDICTION
# ═══════════════════════════════════════════════════════════

CHAMPS_OBLIGATOIRES_QC = {
    "numero_constat":  {"label": "Numero du constat",        "severite": "critique", "ref": "Art. 146 CPP / R-25"},
    "agent":           {"label": "Nom/matricule de l'agent", "severite": "critique", "ref": "Art. 146 CPP"},
    "date":            {"label": "Date de l'infraction",     "severite": "critique", "ref": "Art. 146 CPP"},
    "lieu":            {"label": "Lieu de l'infraction",     "severite": "critique", "ref": "Art. 146 CPP"},
    "loi":             {"label": "Article de loi cite",      "severite": "critique", "ref": "Art. 146 CPP"},
    "infraction":      {"label": "Nature de l'infraction",   "severite": "critique", "ref": "Art. 146 CPP"},
    "amende":          {"label": "Montant de l'amende",      "severite": "majeure",  "ref": "Art. 160 CSR"},
    "plaque":          {"label": "Numero de plaque",         "severite": "majeure",  "ref": "R-25 Reglement"},
    "nom_conducteur":  {"label": "Nom du contrevenant",      "severite": "majeure",  "ref": "Art. 146 CPP"},
    "permis":          {"label": "Numero de permis",         "severite": "mineure",  "ref": "R-25 Reglement"},
    "vehicule":        {"label": "Description du vehicule",  "severite": "mineure",  "ref": "R-25 Reglement"},
    "poste_police":    {"label": "Poste emetteur",           "severite": "mineure",  "ref": "Art. 146 CPP"},
}

CHAMPS_OBLIGATOIRES_ON = {
    "numero_constat":  {"label": "Offence number",           "severite": "critique", "ref": "POA s.3"},
    "agent":           {"label": "Officer name/badge",       "severite": "critique", "ref": "POA s.3"},
    "date":            {"label": "Date of offence",          "severite": "critique", "ref": "POA s.3"},
    "lieu":            {"label": "Location of offence",      "severite": "critique", "ref": "POA s.3"},
    "loi":             {"label": "HTA section cited",        "severite": "critique", "ref": "POA s.3"},
    "infraction":      {"label": "Offence description",      "severite": "critique", "ref": "POA s.3"},
    "amende":          {"label": "Set fine amount",          "severite": "majeure",  "ref": "POA s.12"},
    "plaque":          {"label": "Plate number",             "severite": "majeure",  "ref": "POA s.3"},
    "nom_conducteur":  {"label": "Defendant name",           "severite": "majeure",  "ref": "POA s.3"},
}

# Appareils de mesure certifies au Quebec (liste non exhaustive)
APPAREILS_CERTIFIES = [
    "stalker", "lidar", "laser", "photo radar", "cinematometre",
    "radar", "multanova", "genesis", "traffipax", "redflex",
    "gatsometer", "poliscan", "vitronic", "jenoptik", "kustom",
    "decatur", "applied concepts", "mph", "lti", "ultralyte",
]

# Seuils statistiques
SEUIL_BLITZ_MEME_JOUR_LIEU = 10       # >10 tickets meme lieu meme jour = blitz
SEUIL_AGENT_ABUSIF_PAR_JOUR = 8       # >8 tickets/jour actif = volume anormal
SEUIL_AGENT_MEME_JOUR = 10            # >10 tickets en une journee = speed trap
SEUIL_LIEU_TOP_PERCENT = 5000         # >5000 tickets = top lieux


class AgentErreursAdmin(BaseAgent):
    """
    Analyse profonde des erreurs administratives + statistiques sociales.
    Partie A: Champs manquants, transcription, incoherences logiques
    Partie B: Profil agent, profil lieu, detection blitz/speed trap
    """

    def __init__(self):
        super().__init__("ErreursAdmin")

    def analyser_erreurs(self, ticket, classification, ocr_data=None, client_data=None):
        """
        Analyse complete: erreurs admin + stats sociales.
        Input: ticket dict, classification dict, raw OCR data, client-provided data
        Output: structured dict with errors, stats, defense text
        """
        self.log("Analyse erreurs administratives + statistiques...", "STEP")
        start = time.time()

        juridiction = (ticket.get("juridiction") or classification.get("juridiction", "QC")).upper()[:2]
        erreurs = []
        questions_client = []

        # ═══ PARTIE A: ERREURS ADMINISTRATIVES ═══

        # A1: Champs obligatoires manquants
        erreurs_champs = self._verifier_champs_obligatoires(ticket, ocr_data, juridiction)
        erreurs.extend(erreurs_champs)

        # A2: Erreurs de transcription
        erreurs_transcription = self._verifier_transcription(ticket, ocr_data, client_data, juridiction)
        erreurs.extend(erreurs_transcription)

        # A3: Incoherences logiques
        erreurs_incoherences = self._verifier_incoherences(ticket, classification, juridiction)
        erreurs.extend(erreurs_incoherences)

        # A4: Verification contre la DB (article existe, amende dans bareme)
        erreurs_db = self._verifier_contre_db(ticket, juridiction)
        erreurs.extend(erreurs_db)

        # Questions pour le client (champs non verifiables par OCR)
        questions_client = self._generer_questions_client(ticket, erreurs, juridiction)

        # Score admin
        nb_critiques = sum(1 for e in erreurs if e["severite"] == "critique")
        nb_majeures = sum(1 for e in erreurs if e["severite"] == "majeure")
        nb_mineures = sum(1 for e in erreurs if e["severite"] == "mineure")
        # Score: -20 par critique, -10 par majeure, -3 par mineure
        score_admin = max(0, 100 - (nb_critiques * 20) - (nb_majeures * 10) - (nb_mineures * 3))

        # ═══ PARTIE B: ANALYSE STATISTIQUE SOCIALE ═══

        analyse_stats = {}
        if juridiction in ("QC", ""):
            analyse_stats = self._analyse_statistique_sociale(ticket)

        # ═══ RESUME ═══

        contestable_count = sum(1 for e in erreurs if e.get("contestable"))
        resume = self._generer_resume(erreurs, analyse_stats, contestable_count, juridiction)

        result = {
            "erreurs_admin": {
                "nb_erreurs": len(erreurs),
                "nb_critiques": nb_critiques,
                "nb_majeures": nb_majeures,
                "nb_mineures": nb_mineures,
                "erreurs": erreurs,
                "score_validite_admin": score_admin,
            },
            "analyse_statistique": analyse_stats,
            "questions_client": questions_client,
            "nb_contestable": contestable_count,
            "resume": resume,
            "juridiction": juridiction,
        }

        duration = time.time() - start
        self.log(f"Analyse: {len(erreurs)} erreurs ({nb_critiques}C/{nb_majeures}M/{nb_mineures}m) | "
                 f"Score admin: {score_admin}% | Stats: {'OK' if analyse_stats else 'N/A'}", "OK")
        self.log_run("analyser_erreurs",
                     f"{ticket.get('infraction', '')[:60]} | {juridiction}",
                     f"Erreurs={len(erreurs)} Score={score_admin}% Contestable={contestable_count}",
                     duration=duration)
        return result

    # ═══════════════════════════════════════════════════════════
    # PARTIE A: ERREURS ADMINISTRATIVES
    # ═══════════════════════════════════════════════════════════

    def _verifier_champs_obligatoires(self, ticket, ocr_data, juridiction):
        """A1: Verifier que tous les champs obligatoires sont presents."""
        erreurs = []
        champs = CHAMPS_OBLIGATOIRES_QC if juridiction == "QC" else CHAMPS_OBLIGATOIRES_ON

        raw_text = ""
        if ocr_data and isinstance(ocr_data, dict):
            raw_text = (ocr_data.get("texte_brut_ocr") or "").lower()

        for champ, info in champs.items():
            val = ticket.get(champ, "")
            # Valeurs considerees comme vides
            if not val or str(val).strip() in ("", "0", "?", "N/A", "None", "null"):
                # Verifier si le champ est peut-etre dans le texte brut OCR
                present_dans_ocr = False
                if raw_text:
                    # Mots-cles associes a chaque champ
                    keywords = {
                        "numero_constat": ["constat", "no.", "numero", "dossier"],
                        "agent": ["agent", "matricule", "badge", "#", "sergent", "constable"],
                        "date": ["date", "le "],
                        "lieu": ["lieu", "adresse", "intersection", "autoroute", "rue"],
                        "loi": ["art.", "article", "csr", "hta", "vtl", "code"],
                        "infraction": ["infraction", "offense", "violation"],
                        "amende": ["amende", "fine", "$", "montant"],
                        "plaque": ["plaque", "plate", "immatriculation"],
                        "nom_conducteur": ["nom", "prenom", "name", "defendant"],
                        "permis": ["permis", "license", "permit"],
                        "vehicule": ["vehicule", "vehicle", "marque", "modele"],
                        "poste_police": ["poste", "district", "division", "station"],
                    }
                    for kw in keywords.get(champ, []):
                        if kw in raw_text:
                            present_dans_ocr = True
                            break

                if present_dans_ocr:
                    # Le champ est dans le texte brut mais pas extrait = erreur OCR, pas du constat
                    erreurs.append({
                        "type": "extraction_ocr",
                        "champ": champ,
                        "severite": "mineure",
                        "article_reference": info["ref"],
                        "description": f"{info['label']} present dans le texte OCR mais non extrait par le parseur",
                        "impact": "Verifier manuellement sur le constat original",
                        "contestable": False,
                    })
                else:
                    erreurs.append({
                        "type": "champ_manquant",
                        "champ": champ,
                        "severite": info["severite"],
                        "article_reference": info["ref"],
                        "description": f"{info['label']} absent du constat",
                        "impact": "Motif de contestation potentiel — champ obligatoire manquant"
                              if info["severite"] in ("critique", "majeure")
                              else "Information manquante",
                        "contestable": info["severite"] in ("critique", "majeure"),
                    })

        return erreurs

    def _verifier_transcription(self, ticket, ocr_data, client_data, juridiction):
        """A2: Comparer les donnees OCR vs client pour detecter erreurs de transcription."""
        erreurs = []

        # Comparaison OCR vs donnees client
        if client_data and isinstance(client_data, dict):
            # Nom du conducteur
            nom_ticket = (ticket.get("nom_conducteur") or "").strip().lower()
            nom_client = (client_data.get("nom") or "").strip().lower()
            if nom_ticket and nom_client and nom_ticket != nom_client:
                similarity = self._fuzzy_similarity(nom_ticket, nom_client)
                if similarity < 0.85:
                    erreurs.append({
                        "type": "transcription",
                        "champ": "nom_conducteur",
                        "severite": "majeure",
                        "article_reference": "Art. 146 CPP" if juridiction == "QC" else "POA s.3",
                        "description": f"Nom sur constat '{ticket.get('nom_conducteur')}' "
                                       f"ne correspond pas au nom du client '{client_data.get('nom')}' "
                                       f"(similarite: {int(similarity*100)}%)",
                        "impact": "Erreur de nom = motif de contestation — le constat doit identifier correctement le contrevenant",
                        "contestable": True,
                    })

            # Plaque
            plaque_ticket = (ticket.get("plaque") or "").strip().upper().replace(" ", "")
            plaque_client = (client_data.get("plaque") or "").strip().upper().replace(" ", "")
            if plaque_ticket and plaque_client and plaque_ticket != plaque_client:
                erreurs.append({
                    "type": "transcription",
                    "champ": "plaque",
                    "severite": "critique",
                    "article_reference": "R-25 Reglement" if juridiction == "QC" else "POA s.3",
                    "description": f"Plaque sur constat '{ticket.get('plaque')}' "
                                   f"ne correspond pas a la plaque reelle '{client_data.get('plaque')}'",
                    "impact": "Erreur de plaque = motif de contestation fort — mauvais vehicule identifie",
                    "contestable": True,
                })

        # Validation format numero de constat
        numero = ticket.get("numero_constat", "")
        if numero:
            erreur_format = self._verifier_format_constat(numero, juridiction)
            if erreur_format:
                erreurs.append(erreur_format)

        return erreurs

    def _verifier_incoherences(self, ticket, classification, juridiction):
        """A3: Detecter les incoherences logiques dans le constat."""
        erreurs = []
        infraction = (ticket.get("infraction") or "").lower()
        loi = (ticket.get("loi") or "").lower()
        appareil = (ticket.get("appareil") or "").lower()
        vitesse_captee = int(ticket.get("vitesse_captee") or 0)
        vitesse_permise = int(ticket.get("vitesse_permise") or 0)
        exces = vitesse_captee - vitesse_permise if vitesse_captee and vitesse_permise else 0

        if juridiction == "QC":
            # 1. Photo radar + points = IMPOSSIBLE (Art. 592 CSR)
            is_photo_radar = any(w in appareil for w in ["photo", "radar fixe", "radar photo"])
            points = int(ticket.get("points_inaptitude") or 0)
            if is_photo_radar and points > 0:
                erreurs.append({
                    "type": "incoherence",
                    "champ": "points_inaptitude",
                    "severite": "critique",
                    "article_reference": "Art. 592 CSR",
                    "description": f"Photo radar avec {points} points d'inaptitude — "
                                   "Art. 592 CSR: les infractions par photo radar sont imputees "
                                   "au proprietaire, pas au conducteur, donc aucun point",
                    "impact": "Erreur grave — contestation garantie si points attribues pour photo radar",
                    "contestable": True,
                })

            # 2. Grand exces (>=40 km/h) sans mention saisie vehicule
            if exces >= 40:
                ocr_text = (ticket.get("texte_brut_ocr") or "").lower()
                if "saisie" not in ocr_text and "confiscation" not in ocr_text:
                    erreurs.append({
                        "type": "incoherence",
                        "champ": "grand_exces",
                        "severite": "majeure",
                        "article_reference": "Art. 209.2.1 CSR",
                        "description": f"Exces de {exces} km/h (>=40) — devrait mentionner "
                                       "la saisie du vehicule (7 jours)",
                        "impact": "Omission potentielle de la procedure de saisie",
                        "contestable": False,
                    })

            # 3. Zone scolaire hors heures
            if "scolaire" in infraction or "school" in infraction or "329" in loi:
                date_str = ticket.get("date", "")
                if date_str:
                    try:
                        dt = datetime.strptime(date_str, "%Y-%m-%d")
                        # Ete (juillet-aout) = pas d'ecole
                        if dt.month in (7, 8):
                            erreurs.append({
                                "type": "incoherence",
                                "champ": "zone_scolaire",
                                "severite": "majeure",
                                "article_reference": "Art. 329 CSR",
                                "description": f"Infraction en zone scolaire le {date_str} "
                                               "(mois de juillet/aout — pas de periode scolaire)",
                                "impact": "Zone scolaire non applicable hors periode scolaire — motif de contestation",
                                "contestable": True,
                            })
                    except ValueError:
                        pass

            # 4. Appareil de mesure non certifie
            if appareil and any(w in infraction for w in ["vitesse", "speed", "exces"]):
                is_known = any(cert in appareil for cert in APPAREILS_CERTIFIES)
                if not is_known and len(appareil) > 3:
                    erreurs.append({
                        "type": "incoherence",
                        "champ": "appareil",
                        "severite": "mineure",
                        "article_reference": "Reglement sur les cinematometres",
                        "description": f"Appareil '{ticket.get('appareil')}' — "
                                       "non reconnu dans la liste des appareils certifies",
                        "impact": "Verifier le certificat de calibration de l'appareil",
                        "contestable": False,
                    })

        elif juridiction == "ON":
            # Ontario: stunt driving threshold
            if exces >= 40 and vitesse_permise <= 80:
                ocr_text = (ticket.get("texte_brut_ocr") or "").lower()
                if "stunt" not in ocr_text and "racing" not in ocr_text:
                    erreurs.append({
                        "type": "incoherence",
                        "champ": "stunt_driving",
                        "severite": "majeure",
                        "article_reference": "HTA s.172",
                        "description": f"Exces de {exces} km/h dans zone {vitesse_permise} km/h — "
                                       "pourrait constituer 'stunt driving' (HTA s.172)",
                        "impact": "Charge potentiellement sous-evaluee ou correctement evaluee",
                        "contestable": False,
                    })

        return erreurs

    def _verifier_contre_db(self, ticket, juridiction):
        """A4: Verifier les donnees du ticket contre la base de donnees."""
        erreurs = []
        try:
            conn = self.get_db()
            cur = conn.cursor()

            # Extraire le numero d'article
            loi_str = ticket.get("loi", "")
            art_match = re.search(r"(?:art\.?\s*)?(\d+(?:\.\d+)*)", loi_str)
            article = art_match.group(1) if art_match else ""

            if article:
                province = "QC" if juridiction == "QC" else ("ON" if juridiction == "ON" else "")
                if province:
                    cur.execute(
                        "SELECT id, article, titre_article, texte_complet FROM lois_articles "
                        "WHERE province = %s AND article = %s LIMIT 1",
                        (province, article)
                    )
                    row = cur.fetchone()
                    if not row:
                        # Essayer avec des variantes (299 vs 299.1)
                        cur.execute(
                            "SELECT id, article, titre_article FROM lois_articles "
                            "WHERE province = %s AND article LIKE %s LIMIT 3",
                            (province, f"{article}%")
                        )
                        variants = cur.fetchall()
                        if not variants:
                            erreurs.append({
                                "type": "db_mismatch",
                                "champ": "loi",
                                "severite": "majeure",
                                "article_reference": loi_str,
                                "description": f"Article '{article}' non trouve dans la base de lois "
                                               f"({province}) — article possiblement inexistant ou mal cite",
                                "impact": "Article de loi invalide = motif de contestation fort",
                                "contestable": True,
                            })
                        else:
                            suggested = [v[1] for v in variants]
                            erreurs.append({
                                "type": "db_mismatch",
                                "champ": "loi",
                                "severite": "mineure",
                                "article_reference": loi_str,
                                "description": f"Article '{article}' exact non trouve — "
                                               f"articles proches: {', '.join(suggested)}",
                                "impact": "Verifier l'article exact sur le constat original",
                                "contestable": False,
                            })

            conn.close()
        except Exception as e:
            self.log(f"Erreur verification DB: {e}", "WARN")

        return erreurs

    # ═══════════════════════════════════════════════════════════
    # PARTIE B: ANALYSE STATISTIQUE SOCIALE
    # ═══════════════════════════════════════════════════════════

    def _analyse_statistique_sociale(self, ticket):
        """Analyse les patterns statistiques: profil agent, lieu, blitz."""
        stats = {
            "agent": {},
            "lieu": {},
            "blitz": {},
            "article_lieu": {},
            "defense_statistique": "",
        }

        date_ticket = ticket.get("date", "")
        lieu = ticket.get("lieu", "")
        loi_str = ticket.get("loi", "")
        agent_info = ticket.get("agent", "")

        # Extraire le code municipal du lieu (approximation)
        code_muni = self._trouver_code_municipal(lieu)
        art_match = re.search(r"(\d+(?:\.\d+)*)", loi_str)
        article = art_match.group(1) if art_match else ""

        try:
            conn = self.get_db()
            cur = conn.cursor()

            # ─── B1: Profil agent ce jour-la ───
            if date_ticket and code_muni:
                # Tickets au meme endroit le meme jour (proxy pour le meme agent)
                cur.execute("""
                    SELECT COUNT(*) FROM qc_constats_infraction
                    WHERE raw_data->>'COD_MUNI_LIEU' = %s
                      AND raw_data->>'DAT_INFRA_COMMI' = %s
                """, (code_muni, date_ticket))
                tickets_meme_jour_lieu = cur.fetchone()[0]

                # Si on a un ID agent dans les donnees
                # L'agent du ticket OCR est un nom, les DB ont IDENT_INTRT (anonymise)
                # On utilise lieu+date comme proxy
                stats["agent"] = {
                    "tickets_meme_jour_meme_lieu": tickets_meme_jour_lieu,
                    "alerte": "",
                }
                if tickets_meme_jour_lieu >= SEUIL_AGENT_MEME_JOUR:
                    stats["agent"]["alerte"] = (
                        f"Volume anormal: {tickets_meme_jour_lieu} tickets au meme endroit "
                        f"le {date_ticket} — pattern de piege a vitesse (speed trap)"
                    )

            # ─── B2: Profil global du lieu ───
            if code_muni:
                cur.execute("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(DISTINCT raw_data->>'IDENT_INTRT') as nb_agents,
                        COUNT(DISTINCT raw_data->>'DAT_INFRA_COMMI') as nb_jours,
                        MIN(raw_data->>'DAT_INFRA_COMMI') as premier,
                        MAX(raw_data->>'DAT_INFRA_COMMI') as dernier
                    FROM qc_constats_infraction
                    WHERE raw_data->>'COD_MUNI_LIEU' = %s
                """, (code_muni,))
                row = cur.fetchone()
                if row and row[0]:
                    total = row[0]
                    nb_agents = row[1]
                    nb_jours = row[2]
                    ratio = round(total / max(nb_jours, 1), 1)

                    # Percentile du lieu
                    cur.execute("""
                        SELECT COUNT(DISTINCT raw_data->>'COD_MUNI_LIEU')
                        FROM qc_constats_infraction
                    """)
                    total_lieux = cur.fetchone()[0] or 1

                    cur.execute("""
                        SELECT COUNT(*) FROM (
                            SELECT raw_data->>'COD_MUNI_LIEU' as lieu, COUNT(*) as nb
                            FROM qc_constats_infraction
                            GROUP BY raw_data->>'COD_MUNI_LIEU'
                            HAVING COUNT(*) > %s
                        ) sub
                    """, (total,))
                    lieux_au_dessus = cur.fetchone()[0]
                    percentile = round((1 - lieux_au_dessus / max(total_lieux, 1)) * 100, 1)

                    alerte_lieu = ""
                    if total >= SEUIL_LIEU_TOP_PERCENT:
                        alerte_lieu = (
                            f"Zone a haute frequence — {total} tickets, top {round(100 - percentile, 1)}% "
                            f"des lieux les plus verbalises au Quebec"
                        )

                    stats["lieu"] = {
                        "code_municipal": code_muni,
                        "total_tickets": total,
                        "nb_agents_distincts": nb_agents,
                        "nb_jours_actifs": nb_jours,
                        "ratio_tickets_par_jour": ratio,
                        "percentile": percentile,
                        "premier_constat": row[3] or "",
                        "dernier_constat": row[4] or "",
                        "alerte": alerte_lieu,
                    }

            # ─── B3: Detection blitz (meme jour, meme lieu) ───
            if date_ticket and code_muni:
                cur.execute("""
                    SELECT COUNT(*),
                           COUNT(DISTINCT raw_data->>'IDENT_INTRT') as nb_agents
                    FROM qc_constats_infraction
                    WHERE raw_data->>'COD_MUNI_LIEU' = %s
                      AND raw_data->>'DAT_INFRA_COMMI' = %s
                """, (code_muni, date_ticket))
                blitz_row = cur.fetchone()
                nb_tickets_blitz = blitz_row[0] if blitz_row else 0
                nb_agents_blitz = blitz_row[1] if blitz_row else 0

                is_blitz = nb_tickets_blitz >= SEUIL_BLITZ_MEME_JOUR_LIEU
                stats["blitz"] = {
                    "meme_jour_meme_lieu": nb_tickets_blitz,
                    "nb_agents_impliques": nb_agents_blitz,
                    "detecte": is_blitz,
                    "alerte": (
                        f"Operation blitz detectee — {nb_tickets_blitz} tickets au meme endroit "
                        f"le {date_ticket} par {nb_agents_blitz} agent(s)"
                    ) if is_blitz else "",
                }

            # ─── B4: Article + lieu croise ───
            if article and code_muni:
                cur.execute("""
                    SELECT COUNT(*) FROM qc_constats_infraction
                    WHERE raw_data->>'COD_MUNI_LIEU' = %s
                      AND raw_data->>'NO_ARTCL_L_R' = %s
                """, (code_muni, article))
                nb_article_lieu = cur.fetchone()[0]

                total_lieu = stats.get("lieu", {}).get("total_tickets", 1)
                pct_article = round(nb_article_lieu / max(total_lieu, 1) * 100, 1)

                stats["article_lieu"] = {
                    "article": article,
                    "nb_constats_article_ce_lieu": nb_article_lieu,
                    "pct_du_total_lieu": pct_article,
                    "alerte": (
                        f"Art. {article} represente {pct_article}% des tickets a cet endroit "
                        f"({nb_article_lieu}/{total_lieu})"
                    ) if pct_article > 30 else "",
                }

            # ─── B5: Top jours au meme lieu (pires journees) ───
            if code_muni:
                cur.execute("""
                    SELECT raw_data->>'DAT_INFRA_COMMI' as date,
                           COUNT(*) as nb
                    FROM qc_constats_infraction
                    WHERE raw_data->>'COD_MUNI_LIEU' = %s
                    GROUP BY raw_data->>'DAT_INFRA_COMMI'
                    ORDER BY nb DESC
                    LIMIT 5
                """, (code_muni,))
                top_jours = [{"date": r[0], "nb_tickets": r[1]} for r in cur.fetchall()]
                stats["top_jours_lieu"] = top_jours

            conn.close()
        except Exception as e:
            self.log(f"Erreur analyse statistique: {e}", "WARN")
            stats["erreur"] = str(e)

        # ─── Generer texte de defense statistique ───
        stats["defense_statistique"] = self._generer_defense_statistique(stats, ticket)

        return stats

    def _trouver_code_municipal(self, lieu):
        """Trouver le code municipal approximatif a partir du lieu du ticket."""
        if not lieu:
            return ""
        try:
            conn = self.get_db()
            cur = conn.cursor()

            # Chercher par correspondance dans les constats existants
            lieu_parts = [p.strip() for p in lieu.replace(",", " ").split() if len(p.strip()) > 3]
            for part in lieu_parts:
                cur.execute("""
                    SELECT raw_data->>'COD_MUNI_LIEU' as code, COUNT(*) as nb
                    FROM qc_constats_infraction
                    WHERE raw_data->>'COD_MUNI_LIEU' IS NOT NULL
                    GROUP BY raw_data->>'COD_MUNI_LIEU'
                    HAVING COUNT(*) > 10
                    ORDER BY nb DESC
                    LIMIT 1
                """)
                # Approche: mapper les noms de villes aux codes
                # Montreal = 66023, Laval = 65005, Quebec = 23027, Longueuil = 58033
                # Terrebonne = 64008, Gatineau = 81017, Sherbrooke = 43027

            conn.close()
        except Exception:
            pass

        # Mapping direct villes → codes municipaux (donnees connues)
        CODES_MUNICIPAUX = {
            "montreal": "66023", "montréal": "66023", "mtl": "66023",
            "laval": "65005",
            "quebec": "23027", "québec": "23027",
            "longueuil": "58033",
            "gatineau": "81017",
            "sherbrooke": "43027",
            "trois-rivieres": "37067", "trois-rivières": "37067",
            "levis": "25213", "lévis": "25213",
            "terrebonne": "64008",
            "saguenay": "94068",
            "repentigny": "60013",
            "brossard": "58007",
            "drummondville": "49058",
            "saint-jean-sur-richelieu": "56083",
            "blainville": "73005",
            "saint-jerome": "74047", "saint-jérôme": "74047",
            "chateauguay": "67010", "châteauguay": "67010",
            "rimouski": "09058",
            "granby": "47017",
            "saint-hyacinthe": "54048",
            "victoriaville": "39062",
            "alma": "93042",
            "boisbriand": "73015",
            "mirabel": "74005",
            "mascouche": "64050",
            "vaudreuil-dorion": "71100",
        }

        lieu_lower = lieu.lower()
        for ville, code in CODES_MUNICIPAUX.items():
            if ville in lieu_lower:
                return code

        return ""

    # ═══════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════

    def _fuzzy_similarity(self, s1, s2):
        """Calcul de similarite simple (caracteres communs / max longueur)."""
        if not s1 or not s2:
            return 0.0
        s1, s2 = s1.lower().strip(), s2.lower().strip()
        if s1 == s2:
            return 1.0
        # Levenshtein simplifie
        longer = max(len(s1), len(s2))
        common = sum(1 for a, b in zip(s1, s2) if a == b)
        return common / longer

    def _verifier_format_constat(self, numero, juridiction):
        """Verifier le format du numero de constat."""
        if juridiction == "QC":
            # Format QC typique: lettres + chiffres, 10-20 chars
            if len(numero) < 5:
                return {
                    "type": "transcription",
                    "champ": "numero_constat",
                    "severite": "mineure",
                    "article_reference": "R-25",
                    "description": f"Numero de constat '{numero}' anormalement court ({len(numero)} chars)",
                    "impact": "Verifier le numero complet sur le constat original",
                    "contestable": False,
                }
        return None

    def _generer_questions_client(self, ticket, erreurs, juridiction):
        """Generer les questions a poser au client pour les champs non verifiables par OCR."""
        questions = []

        # Questions toujours pertinentes
        questions.append("Le constat porte-t-il la signature de l'agent?")
        questions.append("Votre nom est-il correctement ecrit sur le constat?")
        questions.append("Le numero de plaque correspond-il a votre vehicule?")

        if juridiction == "QC":
            questions.append("Le code municipal ou district judiciaire est-il indique?")
            questions.append("La cour municipale et le delai de contestation sont-ils mentionnes?")

        # Questions specifiques aux erreurs trouvees
        champs_manquants = [e["champ"] for e in erreurs if e["type"] == "champ_manquant"]
        if "agent" in champs_manquants:
            questions.append("Le nom ou le matricule de l'agent est-il visible sur le constat?")
        if "lieu" in champs_manquants:
            questions.append("Le lieu exact de l'infraction est-il indique sur le constat?")

        return questions

    def _generer_defense_statistique(self, stats, ticket):
        """Generer un texte de defense base sur les statistiques."""
        parts = []

        # Blitz detecte
        blitz = stats.get("blitz", {})
        if blitz.get("detecte"):
            parts.append(
                f"Une operation de blitz policier a ete detectee: {blitz['meme_jour_meme_lieu']} "
                f"contraventions ont ete emises au meme endroit le {ticket.get('date', 'meme jour')}, "
                f"impliquant {blitz.get('nb_agents_impliques', '?')} agent(s). "
                f"Ce volume anormalement eleve peut etre presente comme un element de defense — "
                f"un contexte de 'piege a vitesse' (speed trap) ou la signalisation etait "
                f"potentiellement inadequate."
            )

        # Lieu a haute frequence
        lieu = stats.get("lieu", {})
        if lieu.get("alerte"):
            parts.append(
                f"Le lieu de l'infraction est une zone a haute frequence de contraventions: "
                f"{lieu.get('total_tickets', 0)} tickets emis historiquement, "
                f"ce qui le place dans le top {round(100 - lieu.get('percentile', 50), 1)}% "
                f"des endroits les plus verbalises au Quebec. "
                f"Cette statistique peut suggerer une signalisation inadequate ou "
                f"un piege systematique."
            )

        # Article concentre a cet endroit
        article_lieu = stats.get("article_lieu", {})
        if article_lieu.get("alerte"):
            parts.append(
                f"L'article {article_lieu.get('article')} represente "
                f"{article_lieu.get('pct_du_total_lieu')}% des contraventions a cet endroit "
                f"({article_lieu.get('nb_constats_article_ce_lieu')} sur "
                f"{lieu.get('total_tickets', '?')}). "
                f"Cette concentration inhabituelle d'un meme type d'infraction renforce "
                f"l'hypothese d'un probleme de signalisation."
            )

        if not parts:
            return "Aucun pattern statistique significatif detecte pour ce lieu et cette date."

        return " ".join(parts)

    def _generer_resume(self, erreurs, stats, contestable_count, juridiction):
        """Generer un resume global."""
        parts = []

        if erreurs:
            nb_critiques = sum(1 for e in erreurs if e["severite"] == "critique")
            nb_majeures = sum(1 for e in erreurs if e["severite"] == "majeure")
            parts.append(
                f"{len(erreurs)} erreur(s) administrative(s) detectee(s) "
                f"({nb_critiques} critique(s), {nb_majeures} majeure(s))"
            )
            if contestable_count:
                parts.append(f"dont {contestable_count} motif(s) de contestation potentiel(s)")
        else:
            parts.append("Aucune erreur administrative majeure detectee sur le constat")

        defense = stats.get("defense_statistique", "")
        if defense and "Aucun pattern" not in defense:
            parts.append("Analyse statistique: patterns significatifs detectes (voir details)")

        return ". ".join(parts) + "."
