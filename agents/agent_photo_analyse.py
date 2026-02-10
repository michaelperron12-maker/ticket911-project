"""
Agent Gold Standard: ANALYSE PHOTOS — AI Vision reelle
Moteur: Qwen3-VL-235B (vision multimodale)
Detecte panneaux, signalisation, conditions route, position radar
"""

import time
import os
import json
import base64
from agents.base_agent import BaseAgent, QWEN_VL


class AgentPhotoAnalyse(BaseAgent):

    def __init__(self):
        super().__init__("Photo_Analyse")

    def analyser_photos(self, photo_paths, ticket):
        """
        Input: liste de chemins vers les photos + ticket
        Output: analyse de chaque photo + impact sur la defense
        """
        self.log(f"Analyse de {len(photo_paths)} photo(s)...", "STEP")
        start = time.time()

        resultats = []
        for path in photo_paths:
            if not os.path.exists(path):
                self.log(f"Photo non trouvee: {path}", "WARN")
                continue

            ext = path.rsplit(".", 1)[-1].lower()
            if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
                self.log(f"Format non supporte: {ext}", "WARN")
                continue

            analyse = self._analyser_une_photo(path, ticket)
            if analyse:
                resultats.append(analyse)

        # Score d'impact global des preuves photo
        impact = self._calculer_impact(resultats, ticket)

        result = {
            "nb_photos": len(photo_paths),
            "nb_analysees": len(resultats),
            "analyses": resultats,
            "impact_defense": impact,
        }

        duration = time.time() - start
        self.log(f"{len(resultats)} photos analysees | Impact: {impact.get('score_bonus', 0)}%", "OK")
        self.log_run("analyser_photos", f"{len(photo_paths)} photos",
                     f"Impact={impact.get('score_bonus', 0)}%", duration=duration)
        return result

    def _analyser_une_photo(self, path, ticket):
        """Analyse une seule photo via AI"""
        infraction = ticket.get("infraction", "")
        juridiction = ticket.get("juridiction", "QC")
        lieu = ticket.get("lieu", "")

        # Determiner le type de photo par le nom du fichier
        filename = os.path.basename(path).lower()
        photo_type = "lieu"
        if "ticket" in filename:
            photo_type = "ticket"
        elif "radar" in filename or "camera" in filename:
            photo_type = "radar"
        elif "dashcam" in filename or "video" in filename:
            photo_type = "dashcam_frame"
        elif "panneau" in filename or "sign" in filename:
            photo_type = "signalisation"
        elif "maps" in filename or "google" in filename:
            photo_type = "google_maps"

        # Encoder l'image en base64 pour l'AI
        try:
            with open(path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
            file_size = os.path.getsize(path)
        except Exception as e:
            self.log(f"Erreur lecture {path}: {e}", "FAIL")
            return None

        # Si l'image est trop grosse pour l'API (>5 Mo), on fait une analyse textuelle
        if file_size > 5 * 1024 * 1024:
            return self._analyse_textuelle(path, photo_type, ticket)

        prompt = f"""Analyse cette photo dans le contexte d'une contravention routiere.

CONTEXTE:
- Infraction: {infraction}
- Juridiction: {juridiction}
- Lieu: {lieu}
- Type de photo: {photo_type}

CHERCHE ET IDENTIFIE:
1. SIGNALISATION: panneaux visibles? Limite de vitesse affichee? Panneau cache/obstrue par vegetation?
2. CONDITIONS: meteo (soleil, pluie, neige), eclairage (jour, nuit), visibilite
3. ROUTE: etat de la chaussee, marquage au sol, nombre de voies, intersections
4. RADAR/CAMERA: si visible — position, angle, distance, signaletique d'avertissement
5. ELEMENTS DE DEFENSE: tout element qui pourrait aider la defense du conducteur

REPONDS EN JSON:
{{
    "type_photo": "{photo_type}",
    "description": "description de ce qu'on voit",
    "elements_detectes": {{
        "panneaux": ["liste des panneaux visibles"],
        "limite_vitesse_affichee": null ou nombre,
        "panneau_visible": true/false,
        "panneau_obstrue": true/false,
        "conditions_meteo": "description",
        "eclairage": "jour/nuit/crepuscule",
        "etat_route": "description",
        "radar_visible": true/false,
        "signalisation_radar": true/false
    }},
    "elements_defense": ["element 1 favorable", "element 2"],
    "elements_defavorables": ["element 1 negatif"],
    "pertinence": 0-100,
    "note": "observation importante"
}}"""

        response = self.call_ai_vision(prompt,
                                       image_path=path,
                                       system_prompt="Analyse photo expert en droit routier. Identifie tous les elements pertinents pour une defense. JSON uniquement.",
                                       temperature=0.1, max_tokens=1500)

        if response["success"]:
            try:
                analyse = self.parse_json_response(response["text"])
                analyse["fichier"] = os.path.basename(path)
                analyse["taille"] = file_size
                self.log(f"  Photo '{os.path.basename(path)}': {len(analyse.get('elements_defense', []))} elements defense", "OK")
                return analyse
            except Exception as e:
                self.log(f"Erreur parsing photo: {e}", "FAIL")
                return self._analyse_textuelle(path, photo_type, ticket)
        else:
            self.log(f"Erreur AI photo: {response.get('error', '?')}", "FAIL")
            return self._analyse_textuelle(path, photo_type, ticket)

    def _analyse_textuelle(self, path, photo_type, ticket):
        """Fallback: analyse basee sur le type de photo sans vision AI"""
        filename = os.path.basename(path)
        return {
            "type_photo": photo_type,
            "fichier": filename,
            "taille": os.path.getsize(path),
            "description": f"Photo de type '{photo_type}' soumise par le client",
            "elements_detectes": {},
            "elements_defense": [f"Photo '{photo_type}' fournie comme preuve"],
            "elements_defavorables": [],
            "pertinence": 30,
            "note": "Analyse vision non disponible — photo incluse dans le dossier comme preuve"
        }

    def _calculer_impact(self, analyses, ticket):
        """Calcule l'impact global des photos sur la defense"""
        if not analyses:
            return {"score_bonus": 0, "note": "Aucune photo analysee"}

        score_bonus = 0
        raisons = []

        for a in analyses:
            elements = a.get("elements_detectes", {})
            defense = a.get("elements_defense", [])

            # Panneau obstrue = gros bonus
            if elements.get("panneau_obstrue"):
                score_bonus += 20
                raisons.append("Panneau de signalisation obstrue/cache detecte")

            # Panneau absent
            if elements.get("panneau_visible") is False:
                score_bonus += 15
                raisons.append("Panneau de limite non visible sur la photo")

            # Mauvaises conditions
            meteo = (elements.get("conditions_meteo", "") or "").lower()
            if any(w in meteo for w in ["pluie", "neige", "brouillard", "rain", "snow"]):
                score_bonus += 5
                raisons.append(f"Conditions meteo: {meteo}")

            # Radar mal positionne
            if elements.get("radar_visible") and not elements.get("signalisation_radar"):
                score_bonus += 10
                raisons.append("Radar visible mais pas de signalisation d'avertissement")

            # Chaque element de defense
            score_bonus += len(defense) * 3

        score_bonus = min(40, score_bonus)  # Cap a +40%

        return {
            "score_bonus": score_bonus,
            "nb_elements_defense": sum(len(a.get("elements_defense", [])) for a in analyses),
            "raisons": raisons,
            "note": f"+{score_bonus}% de bonus au score de contestation grace aux preuves photo"
        }
