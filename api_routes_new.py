
# ─── SCORE JURIDIQUE ─────────────────────────────
@app.route("/api/score", methods=["POST"])
def calculer_score():
    """Calcule le score statistique pour un ticket. Pas un avis juridique."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON requis"}), 400
    ticket = data.get("ticket", data)
    preuves = data.get("preuves", [])
    try:
        from score_juridique import ScoreJuridique
        scorer = ScoreJuridique()
        resultat = scorer.calculer(ticket, preuves)
        return jsonify({"success": True, **resultat})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/score/<dossier_uuid>")
def get_score(dossier_uuid):
    """Recupere un score deja calcule."""
    try:
        import psycopg2
        conn = psycopg2.connect(host="172.18.0.3", port=5432, dbname="tickets_qc_on", user="ticketdb_user", password="Tk911PgSecure2026")
        cur = conn.cursor()
        cur.execute("""
            SELECT score_global, f1_taux_acquittement, f2_force_preuves,
                   f3_arguments_applicables, f4_coherence_dossier,
                   f5_facteurs_contextuels, nb_jugements_similaires,
                   nb_acquittements, nb_condamnations, detail_json, created_at
            FROM scores_juridiques WHERE dossier_uuid = %s
            ORDER BY id DESC LIMIT 1
        """, (dossier_uuid,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return jsonify({"error": "Score non trouve"}), 404
        return jsonify({
            "dossier_uuid": dossier_uuid,
            "score": float(row[0]),
            "f1": float(row[1]), "f2": float(row[2]), "f3": float(row[3]),
            "f4": float(row[4]), "f5": float(row[5]),
            "nb_jugements": row[6], "acquittements": row[7], "condamnations": row[8],
            "detail": row[9], "date": str(row[10])
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── CHATBOT D ACCUEIL ──────────────────────────
@app.route("/api/chat/start", methods=["POST"])
def chat_start():
    """Demarre une conversation chatbot informative."""
    data = request.get_json() or {}
    session_id = data.get("session_id", str(uuid.uuid4())[:12])
    langue = data.get("langue", "fr")
    from chatbot_accueil import ChatbotAccueil
    bot = ChatbotAccueil()
    result = bot.demarrer_conversation(session_id, langue)
    return jsonify(result)


@app.route("/api/chat/reply", methods=["POST"])
def chat_reply():
    """Envoie une reponse au chatbot et recoit la prochaine question."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON requis"}), 400
    session_id = data.get("session_id", "")
    reponse = data.get("message", "")
    langue = data.get("langue", "fr")
    if not session_id or not reponse:
        return jsonify({"error": "session_id et message requis"}), 400
    from chatbot_accueil import ChatbotAccueil
    bot = ChatbotAccueil()
    result = bot.repondre(session_id, reponse, langue)
    return jsonify(result)


@app.route("/api/chat/history/<session_id>")
def chat_history(session_id):
    """Retourne l historique d une conversation."""
    try:
        import psycopg2
        conn = psycopg2.connect(host="172.18.0.3", port=5432, dbname="tickets_qc_on", user="ticketdb_user", password="Tk911PgSecure2026")
        cur = conn.cursor()
        cur.execute("""
            SELECT role, message, etape, created_at
            FROM chatbot_messages WHERE session_id = %s ORDER BY id ASC
        """, (session_id,))
        messages = [{"role": row[0], "message": row[1], "etape": row[2], "time": str(row[3])} for row in cur.fetchall()]
        conn.close()
        return jsonify({"session_id": session_id, "messages": messages})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/chatbot")
def chatbot_page():
    """Page chatbot d accueil AITicketInfo."""
    return send_from_directory(".", "chatbot.html")

