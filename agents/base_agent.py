"""
Base Agent — Classe parente pour tous les agents Ticket911
Pattern identique a /projet web/seo-ai/agents/agents_system.py
"""

import os
import json
import time
import sqlite3
import re
from datetime import datetime
from openai import OpenAI

# Config
FIREWORKS_API_KEY = "fw_CbsGnsaL5NSi4wgasWhjtQ"
DEEPSEEK_MODEL = "accounts/fireworks/models/deepseek-v3p2"
DEEPSEEK_R1 = "accounts/fireworks/models/deepseek-r1"
DB_PATH = "/var/www/ticket911/db/ticket911.db"
DATA_DIR = "/var/www/ticket911/data"
LOG_DIR = "/var/www/ticket911/logs"


class BaseAgent:
    """Classe de base pour tous les agents Ticket911"""

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
        """Appel DeepSeek via Fireworks — temperature basse pour factuel"""
        model = model or DEEPSEEK_MODEL
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

            return {"text": text, "tokens": tokens, "duration": duration, "success": True}
        except Exception as e:
            duration = time.time() - start
            return {"text": "", "tokens": 0, "duration": duration, "success": False, "error": str(e)}

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
