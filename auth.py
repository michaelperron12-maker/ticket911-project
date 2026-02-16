#!/usr/bin/env python3
"""
auth.py — Authentification Ticket911
JWT + bcrypt, PostgreSQL users table
"""

import os
import functools
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta

try:
    import jwt
except ImportError:
    import subprocess
    subprocess.check_call(["pip3", "install", "PyJWT"])
    import jwt

try:
    import bcrypt
except ImportError:
    import subprocess
    subprocess.check_call(["pip3", "install", "bcrypt"])
    import bcrypt

from flask import request, jsonify

JWT_SECRET = os.environ.get("JWT_SECRET", "Tk911JwtSecret2026!ChangeThis")
JWT_EXPIRY_HOURS = 24

PG_CONFIG = {
    'host': os.environ.get('TICKETS_DB_HOST', '172.18.0.3'),
    'port': int(os.environ.get('TICKETS_DB_PORT', 5432)),
    'dbname': os.environ.get('TICKETS_DB_NAME', 'tickets_qc_on'),
    'user': os.environ.get('TICKETS_DB_USER', 'ticketdb_user'),
    'password': os.environ.get('TICKETS_DB_PASS', 'Tk911PgSecure2026'),
}


def get_conn():
    return psycopg2.connect(**PG_CONFIG)


def init_auth_tables():
    """Cree les tables users et user_analyses si elles n'existent pas"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            nom VARCHAR(100),
            prenom VARCHAR(100),
            telephone VARCHAR(20),
            role VARCHAR(20) DEFAULT 'client',
            plan VARCHAR(20) DEFAULT 'gratuit',
            stripe_customer_id VARCHAR(100),
            email_verified BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            last_login TIMESTAMP
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_analyses (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            dossier_uuid VARCHAR(20),
            titre TEXT,
            score_global NUMERIC(4,1),
            recommandation VARCHAR(50),
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    conn.commit()
    cur.close()
    conn.close()


def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def check_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))


def create_token(user_id, email, role="client"):
    payload = {
        "user_id": user_id,
        "email": email,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def decode_token(token):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_current_user():
    """Extrait l'utilisateur du JWT dans le header Authorization"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:]
    payload = decode_token(token)
    if not payload:
        return None
    return payload


def require_auth(f):
    """Decorateur pour proteger les routes"""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"error": "Non authentifie"}), 401
        request.user = user
        return f(*args, **kwargs)
    return decorated


def require_admin(f):
    """Decorateur pour routes admin seulement"""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user or user.get("role") != "admin":
            return jsonify({"error": "Acces refuse"}), 403
        request.user = user
        return f(*args, **kwargs)
    return decorated


# ═══════════════════════════════════════════════════════
# ENDPOINTS — a enregistrer dans api.py
# ═══════════════════════════════════════════════════════

def register_auth_routes(app):
    """Enregistre les routes auth dans l'app Flask"""

    @app.route("/api/auth/register", methods=["POST"])
    def auth_register():
        data = request.get_json()
        if not data:
            return jsonify({"error": "Donnees manquantes"}), 400

        email = (data.get("email") or "").strip().lower()
        password = data.get("password", "")
        nom = data.get("nom", "")
        prenom = data.get("prenom", "")
        telephone = data.get("telephone", "")

        if not email or "@" not in email:
            return jsonify({"error": "Email invalide"}), 400
        if len(password) < 6:
            return jsonify({"error": "Mot de passe trop court (min 6 caracteres)"}), 400

        conn = get_conn()
        cur = conn.cursor()

        # Verifier si email existe deja
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({"error": "Cet email est deja utilise"}), 409

        # Creer l'utilisateur
        pw_hash = hash_password(password)
        cur.execute("""
            INSERT INTO users (email, password_hash, nom, prenom, telephone)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        """, (email, pw_hash, nom, prenom, telephone))
        user_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        token = create_token(user_id, email)
        return jsonify({
            "token": token,
            "user": {"id": user_id, "email": email, "nom": nom, "prenom": prenom, "role": "client", "plan": "gratuit"}
        }), 201

    @app.route("/api/auth/login", methods=["POST"])
    def auth_login():
        data = request.get_json()
        if not data:
            return jsonify({"error": "Donnees manquantes"}), 400

        email = (data.get("email") or "").strip().lower()
        password = data.get("password", "")

        if not email or not password:
            return jsonify({"error": "Email et mot de passe requis"}), 400

        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cur.fetchone()

        if not user or not check_password(password, user["password_hash"]):
            cur.close()
            conn.close()
            return jsonify({"error": "Email ou mot de passe incorrect"}), 401

        # Mettre a jour last_login
        cur.execute("UPDATE users SET last_login = NOW() WHERE id = %s", (user["id"],))
        conn.commit()
        cur.close()
        conn.close()

        token = create_token(user["id"], user["email"], user["role"])
        return jsonify({
            "token": token,
            "user": {
                "id": user["id"],
                "email": user["email"],
                "nom": user["nom"],
                "prenom": user["prenom"],
                "role": user["role"],
                "plan": user["plan"],
            }
        })

    @app.route("/api/auth/me")
    @require_auth
    def auth_me():
        user_data = request.user
        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT id, email, nom, prenom, telephone, role, plan,
                   stripe_customer_id, email_verified, created_at, last_login
            FROM users WHERE id = %s
        """, (user_data["user_id"],))
        user = cur.fetchone()

        if not user:
            cur.close()
            conn.close()
            return jsonify({"error": "Utilisateur non trouve"}), 404

        # Recuperer les analyses
        cur.execute("""
            SELECT dossier_uuid, titre, score_global, recommandation, created_at
            FROM user_analyses WHERE user_id = %s
            ORDER BY created_at DESC LIMIT 20
        """, (user["id"],))
        analyses = cur.fetchall()

        cur.close()
        conn.close()

        return jsonify({
            "user": {
                "id": user["id"],
                "email": user["email"],
                "nom": user["nom"],
                "prenom": user["prenom"],
                "telephone": user["telephone"],
                "role": user["role"],
                "plan": user["plan"],
                "email_verified": user["email_verified"],
                "created_at": user["created_at"].isoformat() if user["created_at"] else None,
                "last_login": user["last_login"].isoformat() if user["last_login"] else None,
            },
            "analyses": [
                {
                    "dossier_uuid": a["dossier_uuid"],
                    "titre": a["titre"],
                    "score": float(a["score_global"]) if a["score_global"] else None,
                    "recommandation": a["recommandation"],
                    "date": a["created_at"].isoformat() if a["created_at"] else None,
                }
                for a in analyses
            ]
        })

    @app.route("/api/auth/me", methods=["PUT"])
    @require_auth
    def auth_update_profile():
        data = request.get_json()
        if not data:
            return jsonify({"error": "Donnees manquantes"}), 400

        user_data = request.user
        conn = get_conn()
        cur = conn.cursor()

        updates = []
        values = []
        for field in ["nom", "prenom", "telephone"]:
            if field in data:
                updates.append(f"{field} = %s")
                values.append(data[field])

        if not updates:
            cur.close()
            conn.close()
            return jsonify({"error": "Aucun champ a modifier"}), 400

        values.append(user_data["user_id"])
        cur.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = %s", values)
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"message": "Profil mis a jour"})

    @app.route("/api/auth/change-password", methods=["POST"])
    @require_auth
    def auth_change_password():
        data = request.get_json()
        old_pw = data.get("old_password", "")
        new_pw = data.get("new_password", "")

        if len(new_pw) < 6:
            return jsonify({"error": "Nouveau mot de passe trop court"}), 400

        user_data = request.user
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE id = %s", (user_data["user_id"],))
        row = cur.fetchone()

        if not row or not check_password(old_pw, row[0]):
            cur.close()
            conn.close()
            return jsonify({"error": "Ancien mot de passe incorrect"}), 401

        new_hash = hash_password(new_pw)
        cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (new_hash, user_data["user_id"]))
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"message": "Mot de passe change"})
