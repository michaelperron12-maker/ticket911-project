"""
AITicketInfo — Chatbot d'accueil v2
Flow: Nom → Photo ticket (OCR) → Confirmation → Questions dynamiques → Preuves → Email
AUCUN conseil juridique — information et statistiques seulement.
Sources: CanLII, SOQUIJ, LegisQuebec, SAAQ
LLM: Fireworks API (DeepSeek V3)
"""

import os
import re
import json
import uuid as uuid_mod
import psycopg2
import psycopg2.extras
from openai import OpenAI

PG_CONFIG = {
    "host": "172.18.0.3",
    "port": 5432,
    "dbname": "tickets_qc_on",
    "user": "ticketdb_user",
    "password": "Tk911PgSecure2026"
}

FIREWORKS_API_KEY = os.environ.get("FIREWORKS_API_KEY", "")
LLM_MODEL = "accounts/fireworks/models/glm-5"


# ─── SYSTEM PROMPT ─────────────────────────────────────────────────────
SYSTEM_PROMPT = """Tu es l'assistant de collecte d'information du site AITicketInfo.

=== REGLES ABSOLUES (JAMAIS enfreindre) ===
1. Tu n'es PAS un avocat. Tu ne donnes JAMAIS de conseil juridique.
2. Tu ne dis JAMAIS "vous devriez contester", "vous avez des chances", "je vous recommande".
3. Tu ne predis JAMAIS le resultat d'un dossier.
4. Tu ne donnes JAMAIS ton opinion sur les chances de succes.
5. Tu ne suggeres JAMAIS de strategie de defense.
6. Si le client demande un conseil → reponds: "Je ne suis pas en mesure de donner des conseils juridiques. Consultez un avocat membre du Barreau (barreau.qc.ca ou lso.ca)."

=== TON ROLE ===
Tu es un assistant de COLLECTE D'INFORMATION. Le client a deja scanne son ticket et les informations ont ete extraites par OCR. Tu dois maintenant poser des questions supplementaires sur les informations manquantes.

=== CE QUE TU PEUX FAIRE ===
- Poser des questions pour completer les informations manquantes du ticket
- Reformuler les reponses du client pour confirmer
- Citer des SOURCES OFFICIELLES: CanLII, SOQUIJ, LegisQuebec, SAAQ
- Indiquer les ARTICLES DE LOI applicables de maniere factuelle
- Donner des STATISTIQUES factuelles
- Informer sur les DELAIS legaux

=== CE QUE TU NE PEUX PAS FAIRE ===
- Donner un avis juridique ou une opinion
- Recommander de contester ou non
- Predire un resultat ou evaluer la force d'un dossier

=== FORMAT ===
Sois concis (2-3 phrases max). Naturel et conversationnel.
Reponds dans la MEME LANGUE que le client (francais ou anglais).

REGLE CRITIQUE: Tu dois UNIQUEMENT ecrire le message destine au client.
NE JAMAIS ecrire tes pensees, ton analyse ou ton raisonnement.
NE JAMAIS commencer par "Okay", "Let me", "The user", "I need to", etc.
Commence DIRECTEMENT par la question ou le message au client.

=== ETAT DU DOSSIER ===
{etat_dossier}

=== PROCHAINE INFORMATION A COLLECTER ===
{prochaine_info}
"""


# ─── PHASES DU CHATBOT ────────────────────────────────────────────────
# Phase 0: Accueil + demander nom
# Phase 1: Demander photo du ticket
# Phase 2: OCR en cours (gere cote frontend)
# Phase 3: Confirmation des details extraits
# Phase 4+: Questions dynamiques basees sur ce qui manque
# Derniere: Email + fin

CHAMPS_OCR = [
    "infraction", "juridiction", "date", "amende", "lieu",
    "loi", "vitesse_captee", "vitesse_permise", "appareil",
    "numero_constat", "agent", "nom_conducteur", "permis", "plaque"
]

QUESTIONS_SUPPLEMENTAIRES = [
    {
        "champ": "circonstances",
        "label_fr": "Que s'est-il passe exactement?",
        "label_en": "What exactly happened?",
        "description_fr": "Decrivez les circonstances de l'infraction (ex: trafic, meteo, visibilite)",
        "description_en": "Describe the circumstances (traffic, weather, visibility)",
        "type": "texte_long",
        "toujours": True,
    },
    {
        "champ": "vitesse_details",
        "label_fr": "Details de la vitesse",
        "label_en": "Speed details",
        "description_fr": "Quelle etait votre vitesse reelle selon vous? La limite affichee etait-elle visible?",
        "description_en": "What was your actual speed? Was the speed limit sign visible?",
        "type": "texte",
        "condition": lambda d: any(w in (d.get("infraction", "") + d.get("loi", "")).lower() for w in ["vitesse", "speed", "299", "328", "excess"]),
    },
    {
        "champ": "appareil_details",
        "label_fr": "Type d'appareil de mesure",
        "label_en": "Measurement device type",
        "description_fr": "Savez-vous quel type d'appareil a ete utilise? (radar, cinematometre, lidar, photo radar)",
        "description_en": "Do you know what device was used? (radar, lidar, photo radar)",
        "type": "texte",
        "condition": lambda d: not d.get("appareil") or d.get("appareil") in ("?", "0", ""),
    },
    {
        "champ": "signalisation",
        "label_fr": "Signalisation sur les lieux",
        "label_en": "Signage at the location",
        "description_fr": "La signalisation etait-elle clairement visible? Y avait-il un panneau de limite de vitesse?",
        "description_en": "Was signage clearly visible? Was there a speed limit sign?",
        "type": "texte",
        "condition": lambda d: any(w in (d.get("infraction", "") + d.get("loi", "")).lower() for w in ["vitesse", "speed", "feu", "red", "stop", "arret"]),
    },
    {
        "champ": "anomalies",
        "label_fr": "Anomalies sur le ticket",
        "label_en": "Ticket anomalies",
        "description_fr": "Y a-t-il des erreurs visibles sur le constat? (nom, plaque, date, adresse, numero d'article)",
        "description_en": "Are there visible errors on the ticket? (name, plate, date, address)",
        "type": "texte",
        "toujours": True,
    },
    {
        "champ": "preuves",
        "label_fr": "Preuves disponibles",
        "label_en": "Available evidence",
        "description_fr": "Avez-vous des preuves supplementaires?",
        "description_en": "Do you have additional evidence?",
        "type": "multi_choix",
        "options_fr": ["Photo de la signalisation", "Temoins", "Certificat de calibration", "Autre document", "Aucune preuve supplementaire"],
        "options_en": ["Signage photo", "Witnesses", "Calibration certificate", "Other document", "No additional evidence"],
        "upload_photo": True,
        "toujours": True,
    },
    {
        "champ": "temoins",
        "label_fr": "Temoins",
        "label_en": "Witnesses",
        "description_fr": "Combien de temoins? Nom(s) si possible.",
        "description_en": "How many witnesses? Name(s) if possible.",
        "type": "texte",
        "optionnel": True,
        "condition": lambda d: "Temoins" in d.get("preuves", []) or "Witnesses" in d.get("preuves", []),
    },
    {
        "champ": "email",
        "label_fr": "Courriel pour le rapport",
        "label_en": "Email for report",
        "description_fr": "A quelle adresse courriel voulez-vous recevoir le rapport statistique?",
        "description_en": "What email address should we send the statistical report to?",
        "type": "email",
        "toujours": True,
    },
]


class ChatbotAccueil:
    """
    Chatbot v2 — Flow intelligent:
    Nom → Photo → OCR → Confirmation → Questions dynamiques → Fin
    """

    def __init__(self):
        self.conn = None
        self.llm = OpenAI(
            api_key=FIREWORKS_API_KEY,
            base_url="https://api.fireworks.ai/inference/v1"
        )

    def get_db(self):
        if self.conn is None or self.conn.closed:
            self.conn = psycopg2.connect(**PG_CONFIG)
        return self.conn

    # ─── DEMARRAGE ────────────────────────────────────

    def demarrer_conversation(self, session_id, langue="fr"):
        try:
            conn = self.get_db()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO chatbot_conversations (session_id, etape_courante, donnees_collectees)
                VALUES (%s, 0, '{}')
                ON CONFLICT DO NOTHING
            """, (session_id,))
            conn.commit()
        except Exception as e:
            print(f"Erreur demarrage chatbot: {e}")
            if self.conn:
                self.conn.rollback()

        if langue == "fr":
            msg = ("Bonjour! Je suis l'assistant AITicketInfo.\n\n"
                   "Pour commencer, quel est votre nom?")
        else:
            msg = ("Hello! I'm the AITicketInfo assistant.\n\n"
                   "To start, what is your name?")

        self._sauvegarder_message(session_id, "bot", msg, 0)

        return {
            "message": msg,
            "etape": 0,
            "total_etapes": 6,
            "phase": "nom",
            "type": "texte",
            "options": [],
            "champ": "nom",
            "session_id": session_id
        }

    # ─── REPONDRE ─────────────────────────────────────

    def repondre(self, session_id, reponse_user, langue="fr"):
        session = self._charger_session(session_id)
        if not session:
            return self.demarrer_conversation(session_id, langue)

        etape_num = session["etape_courante"]
        donnees = session["donnees_collectees"] or {}

        self._sauvegarder_message(session_id, "user", reponse_user, etape_num)

        # ─── PHASE 0: NOM ───
        if etape_num == 0:
            donnees["nom"] = reponse_user.strip()
            self._maj_session(session_id, 1, donnees)

            nom = donnees["nom"].split()[0] if donnees["nom"] else ""
            if langue == "fr":
                msg = (f"Merci {nom}! Maintenant, prenez votre ticket en photo ou "
                       f"choisissez une image de votre galerie.\n\n"
                       f"Notre IA va extraire automatiquement toutes les informations du constat.")
            else:
                msg = (f"Thanks {nom}! Now, take a photo of your ticket or "
                       f"choose an image from your gallery.\n\n"
                       f"Our AI will automatically extract all information from the ticket.")

            self._sauvegarder_message(session_id, "bot", msg, 1)

            return {
                "message": msg,
                "etape": 1,
                "total_etapes": 6,
                "phase": "photo",
                "type": "photo_ticket",
                "options": [],
                "champ": "ticket_photo",
                "session_id": session_id
            }

        # ─── PHASE 1: PHOTO SCANNEE (donnees OCR recues) ───
        if etape_num == 1:
            # Les donnees OCR arrivent en JSON depuis le frontend
            try:
                ocr_data = json.loads(reponse_user)
            except (json.JSONDecodeError, TypeError):
                ocr_data = {}

            if ocr_data:
                donnees["ticket_ocr"] = ocr_data
                # Copier les champs OCR dans donnees
                for champ in CHAMPS_OCR:
                    val = ocr_data.get(champ, "")
                    if val and val not in ("?", "0", "", "N/A"):
                        donnees[champ] = str(val)

            self._maj_session(session_id, 2, donnees)

            # Generer le resume de confirmation
            msg = self._generer_confirmation(donnees, langue)
            self._sauvegarder_message(session_id, "bot", msg, 2)

            return {
                "message": msg,
                "etape": 2,
                "total_etapes": 6,
                "phase": "confirmation",
                "type": "choix",
                "options": ["Oui, c'est correct", "Non, corriger"] if langue == "fr" else ["Yes, correct", "No, fix it"],
                "champ": "confirmation",
                "session_id": session_id
            }

        # ─── PHASE 2: CONFIRMATION ───
        if etape_num == 2:
            reponse_lower = reponse_user.lower()
            if any(w in reponse_lower for w in ["non", "no", "corriger", "fix", "erreur", "faux", "wrong"]):
                if langue == "fr":
                    msg = "D'accord, quelles informations sont incorrectes? Dites-moi ce qu'il faut corriger."
                else:
                    msg = "OK, what information is incorrect? Tell me what needs to be fixed."
                self._sauvegarder_message(session_id, "bot", msg, 2)
                # Rester a etape 2 pour correction
                return {
                    "message": msg,
                    "etape": 2,
                    "total_etapes": 6,
                    "phase": "correction",
                    "type": "texte_long",
                    "options": [],
                    "champ": "correction",
                    "session_id": session_id
                }
            elif etape_num == 2 and donnees.get("_en_correction"):
                # Appliquer la correction via LLM
                donnees = self._appliquer_correction(donnees, reponse_user)
                del donnees["_en_correction"]
                self._maj_session(session_id, 3, donnees)
            else:
                # Confirme — passer aux questions supplementaires
                self._maj_session(session_id, 3, donnees)

            # Determiner les questions supplementaires
            questions = self._determiner_questions(donnees)
            donnees["_questions_queue"] = [q["champ"] for q in questions]
            self._maj_session(session_id, 3, donnees)

            if not questions:
                return self._terminer(session_id, donnees, langue)

            return self._poser_question_suivante(session_id, donnees, questions[0], 3, langue)

        # ─── PHASE 2 BIS: CORRECTION ───
        if etape_num == 2 and donnees.get("phase") == "correction":
            donnees = self._appliquer_correction(donnees, reponse_user)
            msg = self._generer_confirmation(donnees, langue)
            self._sauvegarder_message(session_id, "bot", msg, 2)
            return {
                "message": msg,
                "etape": 2,
                "total_etapes": 6,
                "phase": "confirmation",
                "type": "choix",
                "options": ["Oui, c'est correct", "Non, corriger"] if langue == "fr" else ["Yes, correct", "No, fix it"],
                "champ": "confirmation",
                "session_id": session_id
            }

        # ─── PHASE 3+: QUESTIONS DYNAMIQUES ───
        if etape_num >= 3:
            # Sauvegarder la reponse
            queue = donnees.get("_questions_queue", [])
            if queue:
                champ_courant = queue[0]
                if champ_courant == "preuves":
                    donnees[champ_courant] = [p.strip() for p in reponse_user.split(",") if p.strip()]
                else:
                    donnees[champ_courant] = reponse_user
                queue.pop(0)
                donnees["_questions_queue"] = queue

            # Filtrer les questions restantes (certaines dependent des reponses precedentes)
            questions_restantes = self._determiner_questions_restantes(donnees, queue)
            donnees["_questions_queue"] = [q["champ"] for q in questions_restantes]

            etape_suivante = etape_num + 1
            self._maj_session(session_id, etape_suivante, donnees)

            if not questions_restantes:
                return self._terminer(session_id, donnees, langue)

            return self._poser_question_suivante(session_id, donnees, questions_restantes[0], etape_suivante, langue)

        # Fallback
        return self.demarrer_conversation(session_id, langue)

    # ─── HELPERS ──────────────────────────────────────

    def _generer_confirmation(self, donnees, langue):
        """Genere un message de confirmation avec les details OCR."""
        champs_display = {
            "infraction": ("Infraction", "Violation"),
            "juridiction": ("Province", "Province"),
            "date": ("Date", "Date"),
            "amende": ("Amende", "Fine"),
            "lieu": ("Lieu", "Location"),
            "loi": ("Article de loi", "Law article"),
            "vitesse_captee": ("Vitesse captee", "Recorded speed"),
            "vitesse_permise": ("Vitesse permise", "Speed limit"),
            "appareil": ("Appareil", "Device"),
            "numero_constat": ("No. constat", "Ticket no."),
            "agent": ("Agent", "Officer"),
        }

        nom = donnees.get("nom", "")
        idx = 0 if langue == "fr" else 1
        lines = []
        for champ, labels in champs_display.items():
            val = donnees.get(champ, "")
            if val and val not in ("?", "0", "", "N/A"):
                lines.append(f"  {labels[idx]}: {val}")

        if langue == "fr":
            header = f"{nom}, voici les informations extraites de votre ticket:\n"
            footer = "\n\nEst-ce que ces informations sont correctes?"
        else:
            header = f"{nom}, here are the details extracted from your ticket:\n"
            footer = "\n\nAre these details correct?"

        if not lines:
            if langue == "fr":
                return f"{nom}, le scan n'a pas reussi a extraire les informations. Pouvez-vous saisir les details manuellement?"
            else:
                return f"{nom}, the scan couldn't extract the information. Can you enter the details manually?"

        return header + "\n".join(lines) + footer

    def _determiner_questions(self, donnees):
        """Determine quelles questions supplementaires poser basees sur les donnees OCR."""
        questions = []
        for q in QUESTIONS_SUPPLEMENTAIRES:
            if q.get("toujours"):
                questions.append(q)
            elif "condition" in q:
                try:
                    if q["condition"](donnees):
                        questions.append(q)
                except Exception:
                    pass
        return questions

    def _determiner_questions_restantes(self, donnees, queue_champs):
        """Filtre les questions restantes en fonction des reponses deja donnees."""
        questions = []
        for q in QUESTIONS_SUPPLEMENTAIRES:
            if q["champ"] in queue_champs:
                # Re-evaluer les conditions
                if q.get("toujours"):
                    questions.append(q)
                elif "condition" in q:
                    try:
                        if q["condition"](donnees):
                            questions.append(q)
                    except Exception:
                        pass
        return questions

    def _poser_question_suivante(self, session_id, donnees, question, etape, langue):
        """Pose la prochaine question supplementaire."""
        idx = "fr" if langue == "fr" else "en"

        # Utiliser le LLM pour formuler la question naturellement
        etat = self._formater_etat(donnees)
        label = question.get(f"label_{idx}", question["label_fr"])
        description = question.get(f"description_{idx}", question.get("description_fr", ""))
        prochaine = f"{label} — {description}"

        historique = self._charger_historique(session_id)
        msg = self._appel_llm(historique, etat, prochaine, langue)
        msg = self._nettoyer_message(msg)

        # Fallback
        if not msg or len(msg) < 10:
            msg = description

        self._sauvegarder_message(session_id, "bot", msg, etape)

        # Calculer progression
        total_q = len(self._determiner_questions(donnees))
        queue = donnees.get("_questions_queue", [])
        done = total_q - len(queue)
        # +3 pour les phases nom/photo/confirmation
        progress_etape = 3 + done
        progress_total = 3 + total_q

        result = {
            "message": msg,
            "etape": progress_etape,
            "total_etapes": progress_total,
            "phase": "questions",
            "type": question["type"],
            "options": question.get(f"options_{idx}", []),
            "champ": question["champ"],
            "optionnel": question.get("optionnel", False),
            "upload_photo": question.get("upload_photo", False),
            "session_id": session_id
        }
        return result

    def _terminer(self, session_id, donnees, langue):
        """Finalise la conversation."""
        historique = self._charger_historique(session_id)
        msg_fin = self._generer_fin_llm(donnees, historique, langue)
        etape_fin = 3 + len(self._determiner_questions(donnees))
        self._sauvegarder_message(session_id, "bot", msg_fin, etape_fin)
        self._finaliser_session(session_id, donnees)

        return {
            "message": msg_fin,
            "etape": etape_fin,
            "total_etapes": etape_fin,
            "phase": "fin",
            "type": "fin",
            "options": [],
            "champ": None,
            "termine": True,
            "donnees_collectees": {k: v for k, v in donnees.items() if not k.startswith("_")},
            "dossier_uuid": donnees.get("dossier_uuid", ""),
            "session_id": session_id
        }

    def _appliquer_correction(self, donnees, correction_text):
        """Applique les corrections du client aux donnees."""
        # Mapping simple: chercher des patterns dans le texte de correction
        text = correction_text.lower()
        # Si le client donne une correction specifique, on la stocke
        donnees["corrections_client"] = correction_text

        # Patterns de correction
        patterns = {
            "vitesse": ["vitesse", "speed", "km/h", "km"],
            "amende": ["amende", "fine", "montant", "$", "dollar"],
            "date": ["date", "jour", "day"],
            "lieu": ["lieu", "location", "rue", "street", "autoroute", "highway"],
            "infraction": ["infraction", "violation", "charge"],
        }
        for champ, mots in patterns.items():
            if any(m in text for m in mots):
                # Extraire la valeur apres le mot cle
                donnees[f"{champ}_corrige"] = correction_text
        return donnees

    def _formater_etat(self, donnees):
        """Formate l'etat du dossier pour le system prompt."""
        if not donnees:
            return "Aucune information collectee."

        lignes = []
        labels = {
            "nom": "Nom du client",
            "infraction": "Infraction",
            "juridiction": "Province",
            "date": "Date",
            "amende": "Amende",
            "lieu": "Lieu",
            "loi": "Article de loi",
            "vitesse_captee": "Vitesse captee",
            "vitesse_permise": "Vitesse permise",
            "appareil": "Appareil de mesure",
            "numero_constat": "Numero de constat",
            "agent": "Agent",
            "circonstances": "Circonstances",
            "signalisation": "Signalisation",
            "anomalies": "Anomalies",
            "preuves": "Preuves",
            "temoins": "Temoins",
            "email": "Courriel",
        }
        for champ, label in labels.items():
            valeur = donnees.get(champ)
            if valeur:
                if isinstance(valeur, list):
                    valeur = ", ".join(valeur)
                if str(valeur) not in ("?", "0", "", "N/A"):
                    lignes.append(f"- {label}: {valeur}")

        return "\n".join(lignes) if lignes else "Aucune information collectee."

    # ─── LLM ──────────────────────────────────────────

    def _appel_llm(self, historique, etat_dossier, prochaine_info, langue):
        system = SYSTEM_PROMPT.format(
            etat_dossier=etat_dossier,
            prochaine_info=prochaine_info
        )

        messages = [{"role": "system", "content": system}]

        for msg in historique[-16:]:
            role = "assistant" if msg["role"] == "bot" else "user"
            messages.append({"role": role, "content": msg["message"]})

        if not historique:
            lang_instruction = "Reponds en francais." if langue == "fr" else "Respond in English."
            messages.append({"role": "user", "content": f"[Debut de conversation] {lang_instruction}"})

        try:
            resp = self.llm.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                temperature=0.3,
                max_tokens=300
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"Erreur LLM chatbot: {e}")
            return ""

    def _generer_fin_llm(self, donnees, historique, langue):
        resume = self._formater_etat(donnees)
        nom = donnees.get("nom", "")

        prompt_fin = f"""Le client {nom} a termine le questionnaire. Voici toutes les informations:

{resume}

Genere un message de fin qui:
1. Remercie le client par son prenom
2. Resume les informations en liste courte
3. Informe que le rapport statistique sera genere et envoye par courriel
4. Rappelle que ce n'est PAS un avis juridique
5. Indique de consulter un avocat du Barreau (barreau.qc.ca ou lso.ca)

{"Reponds en francais. Sois concis." if langue == "fr" else "Respond in English. Be concise."}"""

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT.format(etat_dossier=resume, prochaine_info="TERMINE — generer le resume final")},
            {"role": "user", "content": prompt_fin}
        ]

        try:
            resp = self.llm.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                temperature=0.3,
                max_tokens=500
            )
            msg = resp.choices[0].message.content.strip()
            msg = self._nettoyer_message(msg)
            if msg and len(msg) > 20:
                return msg
        except Exception as e:
            print(f"Erreur LLM fin: {e}")

        return self._message_fin_statique(donnees, langue)

    def _nettoyer_message(self, msg):
        """Enleve les tags et le raisonnement interne du LLM."""
        msg = re.sub(r'\[CHAMP:[^\]]*\]', '', msg)

        # Strategie: detecter les blocs de "pensee" en anglais/interne
        # et ne garder que les parties qui s'adressent au client
        lines = msg.split('\n')
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                cleaned.append(line)
                continue

            lower = stripped.lower()

            # Detecter raisonnement interne (anglais ou meta-reflexion)
            is_thinking = False

            # Phrases anglaises de reflexion
            en_thinking = [
                "okay,", "okay ", "ok,", "ok ", "let me", "let's",
                "i need", "i should", "i will", "i'll", "i can see",
                "the user", "the client", "they're", "they are",
                "he ", "she ", "this is", "that's", "it's a",
                "it seems", "based on", "looking at", "now,", "now ",
                "first,", "first ", "next,", "next ", "so,", "so the",
                "need to", "the ticket", "the information",
                "the extracted", "according to", "i recall",
                "come to mind", "i should", "highlight the",
                "keep it conc", "ensure the response",
                "but wait", "wait,", "also,", "also ",
                "however,", "moreover,", "furthermore,",
                "in this case", "in quebec", "in ontario",
                "the assistant", "my response", "my answer",
                "note that", "note:",
            ]
            if any(lower.startswith(p) for p in en_thinking):
                is_thinking = True

            # Phrases francaises de meta-reflexion
            fr_lower = lower.replace('\u00e9', 'e').replace('\u00e8', 'e').replace('\u00ea', 'e').replace('\u00e0', 'a')
            fr_thinking = [
                "nous avons deja", "nous devons", "nous allons",
                "l'utilisateur a", "je dois", "je vais", "je peux",
                "je note", "prochaine information", "prochaine etape",
                "le client a", "le dossier", "les informations extraites",
                "l'etat actuel", "dans le format", "le format dit",
            ]
            if any(fr_lower.startswith(p) for p in fr_thinking):
                is_thinking = True

            if not is_thinking:
                cleaned.append(line)

        msg = '\n'.join(cleaned).strip()

        # Si tout a ete filtre, chercher la meilleure phrase utile
        if len(msg) < 10 and lines:
            # Prendre les phrases avec "?" (questions) ou commencant par ** (markdown)
            for line in lines:
                s = line.strip()
                if s and ('?' in s or s.startswith('**') or s.startswith('- ')) and len(s) > 15:
                    if not any(s.lower().startswith(p) for p in en_thinking):
                        cleaned.append(s)
            msg = '\n'.join(cleaned).strip()

        return msg

    def _message_fin_statique(self, donnees, langue):
        nom = donnees.get("nom", "Client")
        infraction = donnees.get("infraction", "?")
        province = donnees.get("juridiction", donnees.get("province", "?"))
        date = donnees.get("date", "?")
        amende = donnees.get("amende", "?")
        lieu = donnees.get("lieu", "?")
        email = donnees.get("email", "?")

        if langue == "fr":
            return (
                f"Merci {nom}! Voici le resume de votre dossier:\n\n"
                f"- Infraction: {infraction}\n- Province: {province}\n- Date: {date}\n"
                f"- Amende: {amende}\n- Lieu: {lieu}\n\n"
                f"Votre rapport statistique sera envoye a {email}.\n\n"
                f"RAPPEL: Ce rapport contient des STATISTIQUES (CanLII, SOQUIJ). "
                f"Ce n'est PAS un avis juridique. AITicketInfo n'est PAS un cabinet d'avocats. "
                f"Consultez un avocat du Barreau (barreau.qc.ca)."
            )
        else:
            return (
                f"Thank you {nom}! Here is your file summary:\n\n"
                f"- Violation: {infraction}\n- Province: {province}\n- Date: {date}\n"
                f"- Fine: {amende}\n- Location: {lieu}\n\n"
                f"Your statistical report will be sent to {email}.\n\n"
                f"REMINDER: This report contains STATISTICS (CanLII). "
                f"This is NOT legal advice. AITicketInfo is NOT a law firm. "
                f"Consult a lawyer (lso.ca)."
            )

    # ─── HISTORIQUE ────────────────────────────────────

    def _charger_historique(self, session_id):
        try:
            conn = self.get_db()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("""
                SELECT role, message, etape FROM chatbot_messages
                WHERE session_id = %s ORDER BY id ASC
            """, (session_id,))
            return [dict(r) for r in cur.fetchall()]
        except Exception:
            return []

    # ─── DB HELPERS ────────────────────────────────────

    def _charger_session(self, session_id):
        try:
            conn = self.get_db()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT session_id, etape_courante, donnees_collectees, statut FROM chatbot_conversations WHERE session_id = %s", (session_id,))
            row = cur.fetchone()
            return dict(row) if row else None
        except Exception:
            return None

    def _maj_session(self, session_id, etape, donnees):
        try:
            conn = self.get_db()
            cur = conn.cursor()
            cur.execute("UPDATE chatbot_conversations SET etape_courante = %s, donnees_collectees = %s, updated_at = NOW() WHERE session_id = %s",
                        (etape, json.dumps(donnees, default=str), session_id))
            conn.commit()
        except Exception as e:
            print(f"Erreur maj session: {e}")
            if self.conn:
                self.conn.rollback()

    def _sauvegarder_message(self, session_id, role, message, etape):
        try:
            conn = self.get_db()
            cur = conn.cursor()
            cur.execute("INSERT INTO chatbot_messages (session_id, role, message, etape) VALUES (%s, %s, %s, %s)",
                        (session_id, role, message, etape))
            conn.commit()
        except Exception as e:
            print(f"Erreur sauvegarde message: {e}")
            if self.conn:
                self.conn.rollback()

    def _finaliser_session(self, session_id, donnees):
        dossier_uuid = str(uuid_mod.uuid4())[:8].upper()
        donnees["dossier_uuid"] = dossier_uuid
        try:
            conn = self.get_db()
            cur = conn.cursor()
            province = donnees.get("juridiction", donnees.get("province", "QC"))
            if "quebec" in str(province).lower() or province == "QC":
                province = "QC"
            elif "ontario" in str(province).lower() or province == "ON":
                province = "ON"
            cur.execute("""
                UPDATE chatbot_conversations SET statut = 'termine', dossier_uuid = %s,
                    donnees_collectees = %s, province = %s, updated_at = NOW()
                WHERE session_id = %s
            """, (dossier_uuid, json.dumps(donnees, default=str), province, session_id))
            conn.commit()
        except Exception as e:
            print(f"Erreur finalisation: {e}")
            if self.conn:
                self.conn.rollback()
