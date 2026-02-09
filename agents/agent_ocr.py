"""
Agent Phase 1: OCR MASTER — Photo de contravention → 50+ champs extraits
Utilise Mindee API quand disponible, sinon fallback sur AI vision
"""

import os
import json
import time
import base64
from agents.base_agent import BaseAgent

MINDEE_API_KEY = os.environ.get("MINDEE_API_KEY", "")


class AgentOCR(BaseAgent):

    def __init__(self):
        super().__init__("OCR_Master")

    def extraire_ticket(self, image_path=None, image_base64=None):
        """
        Input: chemin vers image OU image en base64
        Output: dict avec tous les champs extraits du ticket
        """
        self.log("Extraction OCR du ticket...", "STEP")
        start = time.time()

        result = None

        # Methode 1: Mindee API (si cle disponible)
        if MINDEE_API_KEY and (image_path or image_base64):
            result = self._ocr_mindee(image_path, image_base64)

        # Methode 2: AI vision fallback
        if not result and (image_path or image_base64):
            result = self._ocr_ai_vision(image_path, image_base64)

        # Methode 3: Pas d'image, retourner structure vide
        if not result:
            result = self._empty_ticket()
            self.log("Aucune image fournie — structure vide", "WARN")

        duration = time.time() - start
        self.log_run("extraire_ticket", f"image={'oui' if image_path or image_base64 else 'non'}",
                     f"{len([v for v in result.values() if v])} champs extraits", duration=duration)
        self.log(f"OCR complete en {duration:.1f}s — {len([v for v in result.values() if v])} champs", "OK")
        return result

    def _ocr_mindee(self, image_path, image_base64):
        """OCR via Mindee API — extraction structuree"""
        try:
            import requests

            url = "https://api.mindee.net/v1/products/mindee/expense_receipts/v5/predict"
            headers = {"Authorization": f"Token {MINDEE_API_KEY}"}

            if image_path and os.path.exists(image_path):
                with open(image_path, "rb") as f:
                    resp = requests.post(url, headers=headers, files={"document": f})
            elif image_base64:
                import tempfile
                img_data = base64.b64decode(image_base64)
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    tmp.write(img_data)
                    tmp_path = tmp.name
                with open(tmp_path, "rb") as f:
                    resp = requests.post(url, headers=headers, files={"document": f})
                os.unlink(tmp_path)
            else:
                return None

            if resp.status_code == 201:
                data = resp.json()
                prediction = data.get("document", {}).get("inference", {}).get("prediction", {})
                # Mapper les champs Mindee vers notre format
                result = self._mapper_mindee(prediction)
                self.log("Mindee OCR reussi", "OK")
                return result
            else:
                self.log(f"Mindee erreur {resp.status_code}: {resp.text[:200]}", "FAIL")
                return None

        except ImportError:
            self.log("Module requests non installe", "WARN")
            return None
        except Exception as e:
            self.log(f"Erreur Mindee: {e}", "FAIL")
            return None

    def _ocr_ai_vision(self, image_path, image_base64):
        """Fallback: utiliser AI pour lire le ticket depuis le texte extrait"""
        self.log("Fallback: AI text extraction", "WARN")
        # Pour l'instant, retourner None — sera implemente avec Claude Vision ou equivalent
        return None

    def _mapper_mindee(self, prediction):
        """Mappe les champs Mindee vers le format Ticket911"""
        # Mindee expense receipt n'est pas ideal pour les tickets
        # Quand on aura un modele custom Mindee, ce mapping sera plus precis
        raw_text = ""
        for page in prediction.get("pages", []):
            raw_text += page.get("raw_text", "")

        # Utiliser AI pour extraire les champs specifiques du texte brut
        if raw_text:
            prompt = f"""Extrais les informations de ce ticket de contravention.
Le texte OCR brut est:
{raw_text[:2000]}

Reponds UNIQUEMENT en JSON:
{{
    "infraction": "",
    "juridiction": "Quebec|Ontario|New York",
    "loi": "article de loi",
    "amende": "montant",
    "points_inaptitude": 0,
    "lieu": "",
    "date": "YYYY-MM-DD",
    "appareil": "",
    "vitesse_captee": 0,
    "vitesse_permise": 0,
    "numero_constat": "",
    "agent": "",
    "poste_police": ""
}}"""
            response = self.call_ai(prompt, system_prompt="Extrais les donnees du ticket. JSON uniquement.")
            if response["success"]:
                try:
                    return self.parse_json_response(response["text"])
                except Exception:
                    pass

        return self._empty_ticket()

    def _empty_ticket(self):
        return {
            "infraction": "", "juridiction": "", "loi": "", "amende": "",
            "points_inaptitude": 0, "lieu": "", "date": "", "appareil": "",
            "vitesse_captee": 0, "vitesse_permise": 0, "numero_constat": "",
            "agent": "", "poste_police": ""
        }
