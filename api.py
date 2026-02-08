#!/usr/bin/env python3
"""
TICKET911 — API Flask
Endpoints pour l'analyse de tickets de circulation
Port: 8911
"""

import json
import time
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

import sys
sys.path.insert(0, "/var/www/ticket911")
from agents.orchestrateur import Orchestrateur
from agents.base_agent import DB_PATH

app = Flask(__name__, static_folder="web", static_url_path="")
CORS(app)

# Init orchestrateur (une seule fois)
orchestrateur = None

def get_orchestrateur():
    global orchestrateur
    if orchestrateur is None:
        orchestrateur = Orchestrateur()
    return orchestrateur


# ─── PAGE WEB ─────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("web", "index.html")


# ─── API ENDPOINTS ────────────────────────────
@app.route("/api/health")
def health():
    """Status du systeme"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM jurisprudence")
        nb_juris = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM lois")
        nb_lois = c.fetchone()[0]
        conn.close()
        return jsonify({
            "status": "ok",
            "jurisprudence": nb_juris,
            "lois": nb_lois,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/stats")
def stats():
    """Statistiques detaillees"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute("SELECT COUNT(*) FROM jurisprudence")
        total = c.fetchone()[0]

        c.execute("SELECT juridiction, COUNT(*) FROM jurisprudence GROUP BY juridiction")
        par_juridiction = {row[0] or "N/A": row[1] for row in c.fetchall()}

        c.execute("SELECT resultat, COUNT(*) FROM jurisprudence GROUP BY resultat")
        par_resultat = {row[0] or "N/A": row[1] for row in c.fetchall()}

        c.execute("SELECT COUNT(*) FROM lois")
        nb_lois = c.fetchone()[0]

        c.execute("SELECT COUNT(*) FROM analyses_completes")
        nb_analyses = c.fetchone()[0]

        conn.close()
        return jsonify({
            "jurisprudence_total": total,
            "par_juridiction": par_juridiction,
            "par_resultat": par_resultat,
            "lois_indexees": nb_lois,
            "analyses_effectuees": nb_analyses
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """Analyse complete d'un ticket — pipeline 5 agents"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON requis"}), 400

    ticket = data.get("ticket", data)
    if not ticket.get("infraction"):
        return jsonify({"error": "Champ 'infraction' requis"}), 400

    try:
        orch = get_orchestrateur()
        rapport = orch.analyser_ticket(ticket)

        return jsonify({
            "success": True,
            "score": rapport.get("score_final", 0),
            "confiance": rapport.get("confiance", 0),
            "recommandation": rapport.get("recommandation", "?"),
            "temps": rapport.get("temps_total", 0),
            "erreurs": rapport.get("nb_erreurs", 0),
            "etapes": {k: v.get("status") for k, v in rapport.get("etapes", {}).items()},
            "analyse": rapport.get("etapes", {}).get("analyste", {}).get("analyse"),
            "precedents_trouves": rapport.get("etapes", {}).get("precedents", {}).get("nb_precedents", 0),
            "lois_trouvees": rapport.get("etapes", {}).get("lois", {}).get("nb_lois", 0),
            "verification": rapport.get("etapes", {}).get("verificateur", {}).get("verification"),
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/results")
def results():
    """Historique des analyses"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""SELECT id, score_final, confiance, recommandation, temps_total, created_at
                     FROM analyses_completes ORDER BY id DESC LIMIT 20""")
        rows = c.fetchall()
        conn.close()
        return jsonify([{
            "id": r[0], "score": r[1], "confiance": r[2],
            "recommandation": r[3], "temps": r[4], "date": r[5]
        } for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("TICKET911 API — http://0.0.0.0:8912 (nginx proxy sur 8911)")
    app.run(host="0.0.0.0", port=8912, debug=False)
