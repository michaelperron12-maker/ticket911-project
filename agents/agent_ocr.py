"""
Agent Phase 1: OCR MASTER — Photo de contravention → champs extraits
Moteur: OCR.space (gratuit) → DeepSeek V3 (parsing structuré)
Fallback: Qwen3-VL vision si disponible
"""

import os
import json
import time
import base64
from agents.base_agent import BaseAgent, QWEN_VL


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

        # Methode 1: OCR.space (gratuit, toujours disponible)
        if image_path or image_base64:
            result = self._ocr_space(image_path, image_base64)

        # Methode 2: AI vision fallback (Qwen VL si disponible)
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

    def _ocr_space(self, image_path, image_base64):
        """OCR via OCR.space API gratuite → texte brut → AI parsing"""
        try:
            import requests

            self.log("OCR.space: extraction du texte...", "STEP")

            # Preparer l'image en base64
            if image_path and os.path.exists(image_path):
                with open(image_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode()
            elif image_base64:
                img_b64 = image_base64
            else:
                return None

            # Detecter l'extension
            ext = "jpg"
            if image_path:
                ext = image_path.rsplit(".", 1)[-1].lower() if "." in image_path else "jpg"
            mime = "image/png" if ext == "png" else "image/jpeg"
            if ext == "pdf":
                mime = "application/pdf"

            # Appel OCR.space (cle gratuite: helloworld)
            resp = requests.post("https://api.ocr.space/parse/image",
                data={
                    "apikey": "helloworld",
                    "base64Image": f"data:{mime};base64,{img_b64}",
                    "language": "fre",
                    "isOverlayRequired": False,
                    "OCREngine": 2,
                    "scale": True,
                    "isTable": True,
                },
                timeout=30
            )

            if resp.status_code != 200:
                self.log(f"OCR.space erreur HTTP {resp.status_code}", "FAIL")
                return None

            data = resp.json()
            if not data.get("ParsedResults"):
                self.log(f"OCR.space: aucun resultat — {data.get('ErrorMessage', '?')}", "FAIL")
                return None

            raw_text = data["ParsedResults"][0].get("ParsedText", "")
            if not raw_text or len(raw_text.strip()) < 20:
                self.log("OCR.space: texte trop court ou vide", "WARN")
                return None

            self.log(f"OCR.space: {len(raw_text)} caracteres extraits", "OK")

            # Parser le texte brut avec DeepSeek V3
            result = self._parse_raw_text(raw_text)
            return result

        except Exception as e:
            self.log(f"Erreur OCR.space: {e}", "FAIL")
            return None

    def _parse_raw_text(self, raw_text):
        """Utilise DeepSeek V3 pour structurer le texte OCR brut en JSON"""
        self.log("AI parsing du texte OCR...", "STEP")

        prompt = f"""Texte OCR d une contravention routiere. Extrais les infos en JSON.

REGLES JURIDICTION:
- Si le texte est en francais ou mentionne Montreal, Quebec, Anjou, Laval, Longueuil, SAAQ, CSR, cour municipale, district judiciaire, arrondissement, ou toute ville du Quebec → juridiction = "QC"
- Si le texte mentionne Ontario, HTA, Highway Traffic, Provincial Offences → juridiction = "ON"
- Si le texte mentionne New York, VTL, DMV, TVB → juridiction = "NY"
- En cas de doute, un ticket en francais = "QC"

TEXTE OCR:
{raw_text[:2500]}

JSON: {{"infraction":"","juridiction":"QC ou ON ou NY","loi":"","amende":"","points_inaptitude":0,"lieu":"","date":"YYYY-MM-DD","appareil":"","vitesse_captee":0,"vitesse_permise":0,"numero_constat":"","agent":"","poste_police":"","plaque":"","vehicule":"","signalisation":""}}"""

        response = self.call_ai(prompt,
                                system_prompt="JSON uniquement. Pas de texte explicatif. N invente rien.",
                                temperature=0.05, max_tokens=3000)

        if response["success"]:
            try:
                result = self.parse_json_response(response["text"])
                # Garder le texte brut pour reference
                result["texte_brut_ocr"] = raw_text[:500]
                filled = len([v for v in result.values() if v and v != 0])
                self.log(f"AI parsing reussi — {filled} champs remplis", "OK")
                return result
            except Exception as e:
                self.log(f"AI parsing erreur: {e}", "FAIL")
                return None
        else:
            self.log(f"AI parsing erreur: {response.get('error', '?')}", "FAIL")
            return None

    def _ocr_ai_vision(self, image_path, image_base64):
        """Vision AI fallback: Qwen3-VL lit directement la photo du ticket"""
        self.log("Vision AI fallback: Qwen3-VL analyse la photo...", "STEP")

        prompt = """Lis cette photo de contravention/ticket routier.
Extrais TOUS les champs visibles sur le document.
N'invente RIEN — seulement ce qui est visible.

Reponds UNIQUEMENT en JSON:
{
    "infraction": "type d'infraction",
    "juridiction": "Quebec|Ontario|New York",
    "loi": "article de loi",
    "amende": "montant",
    "points_inaptitude": 0,
    "lieu": "lieu de l'infraction",
    "date": "YYYY-MM-DD",
    "appareil": "type d'appareil de mesure si visible",
    "vitesse_captee": 0,
    "vitesse_permise": 0,
    "numero_constat": "numero du constat",
    "agent": "nom/matricule de l'agent",
    "poste_police": "poste de police",
    "plaque": "numero de plaque",
    "vehicule": "marque/modele si visible"
}"""

        response = self.call_ai_vision(prompt,
                                       image_path=image_path,
                                       image_base64=image_base64,
                                       system_prompt="OCR expert. Lis le ticket et extrais toutes les donnees. N'invente rien. JSON uniquement.",
                                       temperature=0.05, max_tokens=1500)

        if response["success"]:
            try:
                result = self.parse_json_response(response["text"])
                filled = len([v for v in result.values() if v and v != 0])
                self.log(f"Vision OCR reussi — {filled} champs extraits", "OK")
                return result
            except Exception as e:
                self.log(f"Vision OCR parsing error: {e}", "FAIL")
                return None
        else:
            self.log(f"Vision OCR indisponible: {response.get('error', '?')}", "WARN")
            return None

    def _empty_ticket(self):
        return {
            "infraction": "", "juridiction": "", "loi": "", "amende": "",
            "points_inaptitude": 0, "lieu": "", "date": "", "appareil": "",
            "vitesse_captee": 0, "vitesse_permise": 0, "numero_constat": "",
            "agent": "", "poste_police": ""
        }
