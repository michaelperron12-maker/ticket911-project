"""
Base Agent — Classe parente pour tous les agents Ticket911
Stack multi-moteurs Fireworks AI — 12 modeles optimises par role
"""

import os
import json
import time
import sqlite3
import re
import base64
from datetime import datetime
from openai import OpenAI

# ═══════════════════════════════════════════════════════════
# FIREWORKS AI — STACK 12 MODELES
# ═══════════════════════════════════════════════════════════
FIREWORKS_API_KEY = os.environ.get("FIREWORKS_API_KEY", "fw_CbsGnsaL5NSi4wgasWhjtQ")

# --- Vision (seul modele multimodal) ---
QWEN_VL = "accounts/fireworks/models/qwen3-vl-235b-a22b-instruct"

# --- Raisonnement profond ---
QWEN3 = "accounts/fireworks/models/qwen3-235b-a22b"           # #1 knowledge/classification
DEEPSEEK_V3 = "accounts/fireworks/models/deepseek-v3p2"       # #2 raisonnement general
COGITO = "accounts/fireworks/models/cogito-671b-v2-p1"         # #3 raisonnement profond 671B

# --- Thinking / Verification independante ---
DEEPSEEK_R1 = "accounts/fireworks/models/deepseek-r1-0528"    # Chain-of-thought verification
KIMI_THINK = "accounts/fireworks/models/kimi-k2-thinking"      # Thinking mode audit

# --- Francais (Quebec) ---
MIXTRAL_FR = "accounts/fireworks/models/mixtral-8x22b-instruct"  # Mistral (France), fort en FR

# --- Anglais / Multilingue (Ontario, NY) ---
GLM4 = "accounts/fireworks/models/glm-4p7"                    # Zhipu, fort multilingue
KIMI_K2 = "accounts/fireworks/models/kimi-k2p5"               # Moonshot, agentic

# --- Rapide / Leger ---
GPT_OSS_SMALL = "accounts/fireworks/models/gpt-oss-20b"       # 20B, ultra-rapide
GPT_OSS_LARGE = "accounts/fireworks/models/gpt-oss-120b"      # 120B, general purpose
MINIMAX = "accounts/fireworks/models/minimax-m2p1"             # MiniMax, rapide

# --- Legacy / Fallback ---
DEEPSEEK_MODEL = DEEPSEEK_V3  # Compatibilite avec l'ancien code

DB_PATH = "/var/www/ticket911/db/ticket911.db"
DATA_DIR = "/var/www/ticket911/data"
LOG_DIR = "/var/www/ticket911/logs"


class BaseAgent:
    """Classe de base pour tous les agents Ticket911 — stack multi-moteurs"""

    def __init__(self, name):
        self.name = name
        self.db_path = DB_PATH
        self.client = OpenAI(
            api_key=FIREWORKS_API_KEY,
            base_url="https://api.fireworks.ai/inference/v1"
        )
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS agent_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT,
            action TEXT,
            input_summary TEXT,
            output_summary TEXT,
            tokens_used INTEGER,
            duration_seconds REAL,
            success INTEGER,
            error TEXT,
            created_at TEXT
        )""")
        conn.commit()
        conn.close()

    def log_run(self, action, input_summary, output_summary, tokens=0, duration=0, success=True, error=None):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""INSERT INTO agent_runs
            (agent_name, action, input_summary, output_summary, tokens_used, duration_seconds, success, error, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (self.name, action, str(input_summary)[:500], str(output_summary)[:500],
             tokens, round(duration, 2), 1 if success else 0, error, datetime.now().isoformat()))
        conn.commit()
        conn.close()

    def call_ai(self, prompt, system_prompt="", model=None, temperature=0.1, max_tokens=2000):
        """Appel AI via Fireworks — multi-moteurs"""
        model = model or DEEPSEEK_V3
        start = time.time()
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            text = response.choices[0].message.content
            tokens = response.usage.total_tokens if response.usage else 0
            duration = time.time() - start

            return {"text": text, "tokens": tokens, "duration": duration, "success": True, "model": model}
        except Exception as e:
            duration = time.time() - start
            # Fallback automatique sur DeepSeek V3 si le modele primaire echoue
            if model != DEEPSEEK_V3:
                self.log(f"Fallback {model.split('/')[-1]} → DeepSeek V3", "WARN")
                return self.call_ai(prompt, system_prompt, model=DEEPSEEK_V3, temperature=temperature, max_tokens=max_tokens)
            return {"text": "", "tokens": 0, "duration": duration, "success": False, "error": str(e)}

    def call_ai_vision(self, prompt, image_path=None, image_base64=None, system_prompt="", model=None, temperature=0.1, max_tokens=2000):
        """Appel AI Vision via Qwen3-VL — analyse d'images"""
        model = model or QWEN_VL
        start = time.time()
        try:
            # Encoder l'image si chemin fourni
            if image_path and not image_base64:
                with open(image_path, "rb") as f:
                    image_base64 = base64.b64encode(f.read()).decode("utf-8")

            if not image_base64:
                return self.call_ai(prompt, system_prompt, model=DEEPSEEK_V3, temperature=temperature, max_tokens=max_tokens)

            # Detecter le type MIME
            ext = (image_path or "image.jpg").rsplit(".", 1)[-1].lower()
            mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "gif": "gif"}.get(ext, "jpeg")

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{image_base64}"}}
                ]
            })

            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            text = response.choices[0].message.content
            tokens = response.usage.total_tokens if response.usage else 0
            duration = time.time() - start

            return {"text": text, "tokens": tokens, "duration": duration, "success": True, "model": model}
        except Exception as e:
            duration = time.time() - start
            self.log(f"Vision fail, fallback texte: {e}", "WARN")
            return self.call_ai(prompt, system_prompt, model=DEEPSEEK_V3, temperature=temperature, max_tokens=max_tokens)

    def parse_json_response(self, text):
        """Parse JSON depuis une reponse AI (gere les blocs markdown)"""
        cleaned = text.strip()
        # Retirer blocs markdown
        md_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", cleaned)
        if md_match:
            cleaned = md_match.group(1).strip()
        # Extraire le JSON
        json_match = re.search(r"\{[\s\S]*\}", cleaned)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(cleaned)

    def get_db(self):
        return sqlite3.connect(self.db_path)

    def log(self, msg, level="INFO"):
        symbols = {"INFO": "[i]", "OK": "[+]", "FAIL": "[X]", "WARN": "[!]", "STEP": ">>>"}
        print(f"  {symbols.get(level, '')} [{self.name}] {msg}")
