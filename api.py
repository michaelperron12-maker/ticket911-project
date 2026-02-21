#!/usr/bin/env python3
"""
FightMyTicket — API Flask v2
Pipeline 27 agents / 4 phases / upload fichiers / PDF rapport
Port: 8912 (nginx proxy sur 8911)
"""

import json
import subprocess
import time
import os
import uuid
import hashlib
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, send_file, abort, make_response
from flask_cors import CORS
from werkzeug.utils import secure_filename
import psycopg2

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agents.orchestrateur import Orchestrateur
from agents.base_agent import PG_CONFIG, DATA_DIR

app = Flask(__name__, static_folder="web", static_url_path="")
CORS(app)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB max

# Dossiers
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
RAPPORT_DIR = os.path.join(DATA_DIR, "rapports")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RAPPORT_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "pdf", "heic"}

# Init orchestrateur (une seule fois)
orchestrateur = None


def get_orchestrateur():
    global orchestrateur
    if orchestrateur is None:
        orchestrateur = Orchestrateur()
    return orchestrateur


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_client_folder(dossier_uuid):
    """Cree un dossier client unique pour stockage"""
    folder = os.path.join(UPLOAD_DIR, dossier_uuid)
    os.makedirs(folder, exist_ok=True)
    return folder


# ─── PAGE WEB ─────────────────────────────────

# Auth module
try:
    from auth import register_auth_routes, init_auth_tables
    _auth_available = True
except ImportError:
    _auth_available = False

@app.route("/")
def index():
    resp = make_response(send_from_directory(".", "scanner.html"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


# ─── UPLOAD FICHIERS ──────────────────────────
@app.route("/api/upload", methods=["POST"])
def upload_files():
    """Upload ticket photo + preuves — stocke dans dossier UUID"""
    dossier_uuid = request.form.get("dossier_uuid", str(uuid.uuid4())[:8].upper())
    folder = get_client_folder(dossier_uuid)

    uploaded = []
    errors = []

    for key in request.files:
        file = request.files[key]
        if file and file.filename:
            if allowed_file(file.filename):
                safe_name = secure_filename(file.filename)
                # Prefixer avec type (ticket, preuve, dashcam)
                file_type = key.replace("[]", "")  # ticket_photo, evidence_1, dashcam, etc.
                final_name = f"{file_type}_{safe_name}"
                filepath = os.path.join(folder, final_name)
                file.save(filepath)
                uploaded.append({
                    "name": final_name,
                    "type": file_type,
                    "size": os.path.getsize(filepath),
                    "path": filepath
                })
            else:
                errors.append(f"{file.filename}: type non supporte")

    return jsonify({
        "success": True,
        "dossier_uuid": dossier_uuid,
        "uploaded": len(uploaded),
        "files": uploaded,
        "errors": errors
    })


# ─── ANALYSE COMPLETE (27 agents) ─────────────

def _save_user_analysis(dossier_uuid, titre, score, recommandation, auth_header):
    """Sauvegarde l'analyse dans user_analyses si l'utilisateur est connecte"""
    if not auth_header or not auth_header.startswith("Bearer ") or not _auth_available:
        return
    try:
        from auth import decode_token
        token = auth_header[7:]
        payload = decode_token(token)
        if not payload:
            return
        user_id = payload.get("user_id")
        if not user_id:
            return
        conn2 = psycopg2.connect(**PG_CONFIG)
        cur2 = conn2.cursor()
        cur2.execute("""
            INSERT INTO user_analyses (user_id, dossier_uuid, titre, score_global, recommandation)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, dossier_uuid, titre, score, recommandation))
        conn2.commit()
        cur2.close()
        conn2.close()
        print(f"[AUTH] Analyse {dossier_uuid} sauvegardee pour user {user_id}")
    except Exception as e:
        print(f"[AUTH] Erreur save analyse: {e}")


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """Analyse complete — pipeline 27 agents / 4 phases"""
    content_type = request.content_type or ""

    # Support multipart (avec fichiers) ou JSON
    if "multipart" in content_type:
        ticket_json = request.form.get("ticket", "{}")
        try:
            ticket = json.loads(ticket_json)
        except json.JSONDecodeError:
            ticket = {}

        client_info_json = request.form.get("client_info", "{}")
        try:
            client_info = json.loads(client_info_json)
        except json.JSONDecodeError:
            client_info = {}

        # Upload des fichiers
        dossier_uuid = str(uuid.uuid4())[:8].upper()
        folder = get_client_folder(dossier_uuid)
        image_path = None
        evidence_photos = []

        for key in request.files:
            file = request.files[key]
            if file and file.filename and allowed_file(file.filename):
                safe_name = secure_filename(file.filename)
                filepath = os.path.join(folder, f"{key}_{safe_name}")
                file.save(filepath)
                if key in ("ticket_photo", "ticket"):
                    image_path = filepath
                elif key.startswith("evidence") or key.startswith("photo") or key.startswith("preuve"):
                    evidence_photos.append(filepath)

        # Temoignage et temoins (depuis form data)
        temoignage = request.form.get("temoignage", "")
        temoins_json = request.form.get("temoins", "[]")
        try:
            temoins = json.loads(temoins_json)
        except json.JSONDecodeError:
            temoins = []
    else:
        data = request.get_json()
        if not data:
            return jsonify({"error": "JSON ou multipart requis"}), 400
        ticket = data.get("ticket", data)
        client_info = data.get("client_info", {})
        image_path = None
        evidence_photos = []
        temoignage = data.get("temoignage", "")
        temoins = data.get("temoins", [])

    if not ticket.get("infraction") and not image_path:
        return jsonify({"error": "Photo du ticket ou champ 'infraction' requis"}), 400

    try:
        orch = get_orchestrateur()
        rapport = orch.analyser_ticket(
            ticket, image_path=image_path, client_info=client_info,
            evidence_photos=evidence_photos if evidence_photos else None,
            temoignage=temoignage if temoignage else None,
            temoins=temoins if temoins else None)

        dossier_uuid = rapport.get("dossier_uuid", "")

        # Extraire l'analyse complete depuis le rapport sauvegardé en DB
        analyse_data = None
        try:
            conn = psycopg2.connect(**PG_CONFIG)
            cur = conn.cursor()
            cur.execute("SELECT analyse_json FROM analyses_completes WHERE dossier_uuid = %s",
                      (dossier_uuid,))
            row = cur.fetchone()
            if row and row[0]:
                analyse_data = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            conn.close()
        except Exception:
            pass

        # Sauvegarder dans user_analyses si connecte
        _save_user_analysis(
            dossier_uuid,
            ticket.get("infraction", ticket.get("titre", "Analyse")),
            rapport.get("score_final", 0),
            rapport.get("recommandation", "?"),
            request.headers.get("Authorization", "")
        )

        return jsonify({
            "success": True,
            "dossier_uuid": dossier_uuid,
            "score": rapport.get("score_final", 0),
            "confiance": rapport.get("confiance", 0),
            "recommandation": rapport.get("recommandation", "?"),
            "juridiction": rapport.get("juridiction", "?"),
            "temps": rapport.get("temps_total", 0),
            "erreurs": rapport.get("nb_erreurs", 0),
            "phases": {
                phase: {
                    agent: (d.get("status", "OK") if isinstance(d, dict) and "status" in d else "OK")
                    for agent, d in agents.items()
                } if isinstance(agents, dict) else {}
                for phase, agents in rapport.get("phases", {}).items()
            },
            "analyse": analyse_data,
            "rapport_client": (rapport.get("phases", {}).get("livraison") or {}).get("rapport_client"),
            "procedure": (rapport.get("phases", {}).get("analyse") or {}).get("procedure"),
            "points": (rapport.get("phases", {}).get("analyse") or {}).get("points"),
            "supervision": (rapport.get("phases", {}).get("livraison") or {}).get("supervision"),
            "precedents_trouves": ((rapport.get("phases", {}).get("analyse") or {}).get("precedents") or {}).get("nb", 0) if isinstance((rapport.get("phases", {}).get("analyse") or {}).get("precedents"), dict) else 0,
            "lois_trouvees": ((rapport.get("phases", {}).get("analyse") or {}).get("lois") or {}).get("nb", 0) if isinstance((rapport.get("phases", {}).get("analyse") or {}).get("lois"), dict) else 0,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return jsonify({"success": False, "error": str(e)}), 500


# ─── RAPPORT PDF ───────────────────────────────
@app.route("/api/rapport/<dossier_uuid>")
def get_rapport_pdf(dossier_uuid):
    """Genere et retourne le rapport PDF 9 pages"""
    # Chercher l'analyse en DB
    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur = conn.cursor()
        cur.execute("""SELECT ticket_json, analyse_json, rapport_client_json,
                            rapport_avocat_json, procedure_json, points_json,
                            lois_json, precedents_json, cross_verification_json,
                            supervision_json, score_final, confiance, recommandation,
                            juridiction, temps_total, created_at
                     FROM analyses_completes WHERE dossier_uuid = %s""", (dossier_uuid,))
        row = cur.fetchone()
        conn.close()

        if not row:
            conn.close()
            return jsonify({"error": f"Dossier {dossier_uuid} non trouve"}), 404

        # Parse les JSONs
        data = {
            "ticket": json.loads(row[0] or "{}"),
            "analyse": json.loads(row[1] or "{}"),
            "rapport_client": json.loads(row[2] or "{}"),
            "rapport_avocat": json.loads(row[3] or "{}"),
            "procedure": json.loads(row[4] or "{}"),
            "points": json.loads(row[5] or "{}"),
            "lois": json.loads(row[6] or "[]"),
            "precedents": json.loads(row[7] or "[]"),
            "cross_verification": json.loads(row[8] or "{}"),
            "supervision": json.loads(row[9] or "{}"),
            "score_final": row[10],
            "confiance": row[11],
            "recommandation": row[12],
            "juridiction": row[13],
            "temps_total": row[14],
            "created_at": row[15],
            "dossier_uuid": dossier_uuid,
        }

        # Generer le PDF
        pdf_path = _generer_pdf(data)
        if pdf_path and os.path.exists(pdf_path):
            return send_file(pdf_path, mimetype="application/pdf",
                             as_attachment=True,
                             download_name=f"FightMyTicket-{dossier_uuid}.pdf")
        else:
            # Fallback: retourner le HTML
            html = _generer_html_rapport(data)
            return html, 200, {"Content-Type": "text/html; charset=utf-8"}

    except Exception as e:
        conn.close()

        return jsonify({"error": str(e)}), 500


def _generer_pdf(data):
    """Genere le PDF via WeasyPrint"""
    try:
        from weasyprint import HTML
        html_content = _generer_html_rapport(data)
        pdf_path = os.path.join(RAPPORT_DIR, f"FightMyTicket-{data['dossier_uuid']}.pdf")
        HTML(string=html_content).write_pdf(pdf_path)
        return pdf_path
    except ImportError:
        return None
    except Exception:
        return None


def _generer_html_rapport(data):
    """Genere le rapport HTML 9 pages"""
    ticket = data.get("ticket", {})
    analyse = data.get("analyse", {})
    rapport_client = data.get("rapport_client", {})
    rapport_avocat = data.get("rapport_avocat", {})
    procedure = data.get("procedure", {})
    points = data.get("points", {})
    lois = data.get("lois", [])
    precedents = data.get("precedents", [])
    cross_verif = data.get("cross_verification", {})
    supervision = data.get("supervision", {})
    uuid_str = data.get("dossier_uuid", "?")
    score = data.get("score_final", 0)
    confiance = data.get("confiance", 0)
    reco = data.get("recommandation", "?")
    juridiction = data.get("juridiction", "?")
    date_str = data.get("created_at", datetime.now().isoformat())[:10]

    # Couleur score
    if score >= 70:
        score_color = "#27ae60"
    elif score >= 40:
        score_color = "#f39c12"
    else:
        score_color = "#e74c3c"

    # Arguments
    args_html = ""
    arguments = analyse.get("arguments", [])
    for i, arg in enumerate(arguments, 1):
        args_html += f"<li>{arg}</li>"

    # Precedents
    prec_html = ""
    for p in precedents[:8]:
        prec_html += f"""<tr>
            <td>{p.get('citation', '?')[:60]}</td>
            <td>{p.get('tribunal', '?')}</td>
            <td>{p.get('date', '?')}</td>
            <td>{p.get('resultat', '?')}</td>
            <td>{p.get('score', 0)}%</td>
        </tr>"""

    # Lois
    lois_html = ""
    for l in lois[:6]:
        lois_html += f"""<tr>
            <td>{l.get('article', '?')}</td>
            <td>{l.get('juridiction', '?')}</td>
            <td>{l.get('texte', '')[:200]}</td>
        </tr>"""

    # Etapes procedure
    etapes_html = ""
    for etape in (procedure.get("etapes", []) if procedure else []):
        etapes_html += f"<li>{etape}</li>"

    # Moyens de defense (avocat)
    moyens_html = ""
    for m in rapport_avocat.get("moyens_de_defense", []):
        moyens_html += f"<li>{m}</li>"

    # Faiblesses
    faiblesses_html = ""
    for f in rapport_avocat.get("faiblesses_dossier", []):
        faiblesses_html += f"<li>{f}</li>"

    # Economie
    eco = points.get("economie_si_acquitte", {}) if points else {}

    # Prochaines etapes client
    etapes_client_html = ""
    for e in rapport_client.get("prochaines_etapes", []):
        etapes_client_html += f"<li>{e}</li>"

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<style>
    @page {{ size: A4; margin: 1.5cm 1.5cm 1.2cm 1.5cm; }}
    body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color: #1e3a5f; font-size: 9.5pt; line-height: 1.4; }}
    h1 {{ color: #1e3a5f; font-size: 16pt; border-bottom: 2px solid #2563eb; padding-bottom: 4px; margin: 14px 0 8px; }}
    h2 {{ color: #1e3a5f; font-size: 12pt; border-bottom: 1px solid #d4a843; padding-bottom: 3px; margin: 12px 0 6px; }}
    h3 {{ color: #2563eb; font-size: 10pt; margin: 8px 0 4px; }}
    .header {{ text-align: center; margin-bottom: 12px; padding-bottom: 10px; border-bottom: 2px solid #2563eb; }}
    .score-box {{ background: {score_color}; color: white; padding: 10px 20px; border-radius: 8px;
                   display: inline-block; font-size: 20pt; font-weight: bold; }}
    .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin: 8px 0; }}
    .info-grid-4 {{ display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 6px; margin: 8px 0; }}
    .info-item {{ background: #f8f9fa; padding: 5px 8px; border-radius: 4px; font-size: 8.5pt; }}
    .info-label {{ font-weight: bold; color: #666; font-size: 7.5pt; text-transform: uppercase; }}
    table {{ width: 100%; border-collapse: collapse; margin: 6px 0; font-size: 8.5pt; }}
    th {{ background: #1e3a5f; color: white; padding: 5px 6px; text-align: left; font-size: 8pt; }}
    td {{ padding: 4px 6px; border-bottom: 1px solid #eee; }}
    tr:nth-child(even) {{ background: #f8f9fa; }}
    .reco-box {{ background: #e8f5e9; border-left: 3px solid #27ae60; padding: 8px 10px; margin: 8px 0; }}
    .warn-box {{ background: #fff3e0; border-left: 3px solid #f39c12; padding: 8px 10px; margin: 8px 0; }}
    .section {{ page-break-inside: avoid; }}
    .page-break {{ page-break-before: always; }}
    .footer {{ text-align: center; color: #999; font-size: 7pt; margin-top: 15px;
               border-top: 1px solid #ddd; padding-top: 5px; }}
    ul, ol {{ padding-left: 18px; margin: 4px 0; }}
    li {{ margin-bottom: 3px; }}
    .eco-total {{ font-size: 14pt; color: #27ae60; font-weight: bold; }}
    .disclaimer {{ font-size: 7.5pt; color: #999; text-align: center; margin-top: 10px; }}
</style>
</head>
<body>

<!-- COUVERTURE + RESUME -->
<div class="header">
    <h1 style="border:none;font-size:20pt;margin:0;">FIGHTMYTICKET</h1>
    <p style="font-size: 10pt; color: #666; margin: 2px 0;">Rapport d'analyse juridique par intelligence artificielle</p>
    <p style="font-size: 9pt; margin: 2px 0;">Dossier <strong>#{uuid_str}</strong> | {date_str} | {juridiction}</p>
    <div style="margin: 10px 0 5px;">
        <div class="score-box">{score}%</div>
        <span style="font-size: 9pt; color: #666; margin-left: 10px;">Score de contestation</span>
    </div>
</div>

<div class="info-grid-4">
    <div class="info-item"><span class="info-label">Infraction</span><br>{ticket.get('infraction', '?')}</div>
    <div class="info-item"><span class="info-label">Amende</span><br>{ticket.get('amende', '?')}</div>
    <div class="info-item"><span class="info-label">Points</span><br>{ticket.get('points_inaptitude', 0)}</div>
    <div class="info-item"><span class="info-label">Juridiction</span><br>{juridiction}</div>
    <div class="info-item"><span class="info-label">Lieu</span><br>{ticket.get('lieu', '?')}</div>
    <div class="info-item"><span class="info-label">Date</span><br>{ticket.get('date', '?')}</div>
    <div class="info-item"><span class="info-label">Recommandation</span><br><strong>{reco.upper()}</strong></div>
    <div class="info-item"><span class="info-label">Confiance</span><br>{confiance}%</div>
</div>

<div class="reco-box">
    <h3 style="margin:0 0 3px;">Verdict</h3>
    <p style="margin:0;">{rapport_client.get('verdict', reco)}</p>
</div>

<div class="section">
    <h2>Resume</h2>
    <p>{rapport_client.get('resume', 'Analyse en cours...')}</p>
</div>

<div class="section">
    <h2>Prochaines etapes</h2>
    <ol>{etapes_client_html}</ol>
</div>

{f'<div class="warn-box"><strong>Attention:</strong> {rapport_client.get("attention", "")}</div>' if rapport_client.get("attention") else ""}

<div class="info-grid">
    <div class="info-item"><span class="info-label">Economie potentielle</span><br><span class="eco-total">${eco.get('total', 0):,}</span></div>
    <div class="info-item"><span class="info-label">Amende: ${eco.get('amende', 0)}</span><br>Assurance (3 ans): ${eco.get('assurance_3ans', eco.get('cout_supplementaire_3ans', 0)):,}</div>
</div>

<!-- PAGE 2: Defense + Lois + Jurisprudence -->
<div class="page-break"></div>

<div class="section">
    <h1>Arguments de defense</h1>
    <ol>{args_html}</ol>
</div>

<div class="section">
    <h2>Strategie recommandee</h2>
    <p>{analyse.get('strategie', analyse.get('explication', ''))}</p>
</div>

<div class="section">
    <h2>Lois applicables</h2>
    <table>
        <tr><th>Article</th><th>Juridiction</th><th>Texte</th></tr>
        {lois_html}
    </table>
</div>

<div class="section">
    <h2>Jurisprudence pertinente ({len(precedents)} decisions)</h2>
    <table>
        <tr><th>Citation</th><th>Tribunal</th><th>Date</th><th>Resultat</th><th>%</th></tr>
        {prec_html}
    </table>
</div>

<!-- PAGE 3: Procedure + Points + Rapport avocat -->
<div class="page-break"></div>

<div class="section">
    <h1>Procedure judiciaire</h1>
    <div class="info-grid">
        <div class="info-item"><span class="info-label">Tribunal</span><br>{procedure.get('tribunal', '?') if procedure else '?'}</div>
        <div class="info-item"><span class="info-label">Jours restants</span><br>{procedure.get('jours_restants', '?') if procedure else '?'}</div>
    </div>
    <h3>Etapes</h3>
    <ol>{etapes_html}</ol>
</div>

<div class="section">
    <h2>Impact points et assurance</h2>
    <div class="info-grid">
        <div class="info-item"><span class="info-label">Points</span><br>{points.get('points_demerite', points.get('points_dmv', '?')) if points else '?'}</div>
        <div class="info-item"><span class="info-label">Augmentation assurance</span><br>{points.get('impact_assurance', {{}}).get('note', '?') if points else '?'}</div>
    </div>
</div>

<div class="section">
    <h2>Rapport technique (avocat)</h2>
    <p><em>{rapport_avocat.get('resume_technique', '')}</em></p>

    <h3>Moyens de defense</h3>
    <ol>{moyens_html}</ol>

    <h3>Faiblesses du dossier</h3>
    <ul>{faiblesses_html}</ul>

    <h3>Fondement legal</h3>
    <p>{rapport_avocat.get('fondement_legal', '')}</p>
</div>

<!-- Certification -->
<div style="margin-top: 15px; padding-top: 10px; border-top: 2px solid #2563eb;">
    <h2 style="border:none;">Certification</h2>
    <div class="info-grid-4">
        <div class="info-item"><span class="info-label">Dossier</span><br>#{uuid_str}</div>
        <div class="info-item"><span class="info-label">Qualite</span><br>{supervision.get('score_qualite', '?')}%</div>
        <div class="info-item"><span class="info-label">Decision</span><br>{supervision.get('decision', '?')}</div>
        <div class="info-item"><span class="info-label">Agents</span><br>{supervision.get('agents_verifies', '?')}</div>
    </div>
</div>

<div class="disclaimer">
    <p><strong>Ce rapport a ete genere automatiquement par FightMyTicket</strong><br>
    Analyse par 27 agents IA specialises | {len(lois)} articles de loi | {len(precedents)} precedents<br>
    Ce rapport ne constitue pas un avis juridique. Consultez un avocat pour des conseils personnalises.</p>
</div>

<div class="footer">
    <p>FightMyTicket par SeoAI | fightmyticket.ca | {datetime.now().year}</p>
</div>

</body>
</html>"""


# ─── API ENDPOINTS EXISTANTS ──────────────────
@app.route("/api/health")
def health():
    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM jurisprudence")
        nb_juris = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM lois_articles")
        nb_lois = cur.fetchone()[0]
        conn.close()

        return jsonify({
            "status": "ok",
            "version": "2.0-pg",
            "agents": 27,
            "jurisprudence": nb_juris,
            "lois": nb_lois,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/status")
def status():
    return health()

@app.route("/api/stats")
def stats():
    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM jurisprudence")
        total = cur.fetchone()[0]
        cur.execute("SELECT province, COUNT(*) FROM jurisprudence GROUP BY province")
        par_juridiction = {row[0] or "N/A": row[1] for row in cur.fetchall()}
        cur.execute("SELECT resultat, COUNT(*) FROM jurisprudence GROUP BY resultat")
        par_resultat = {row[0] or "N/A": row[1] for row in cur.fetchall()}
        cur.execute("SELECT COUNT(*) FROM lois_articles")
        nb_lois = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM analyses_completes")
        nb_analyses = cur.fetchone()[0]
        conn.close()

        return jsonify({
            "jurisprudence_total": total,
            "par_juridiction": par_juridiction,
            "par_resultat": par_resultat,
            "lois_indexees": nb_lois,
            "analyses_effectuees": nb_analyses,
            "version": "2.0 (27 agents)"
        })
    except Exception as e:
        conn.close()

        return jsonify({"error": str(e)}), 500


@app.route("/api/results")
def results():
    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur = conn.cursor()
        cur.execute("""SELECT id, dossier_uuid, score_final, confiance, recommandation,
                            juridiction, temps_total, created_at
                     FROM analyses_completes ORDER BY id DESC LIMIT 20""")
        rows = cur.fetchall()
        conn.close()
        return jsonify([{
            "id": r[0], "dossier_uuid": r[1], "score": r[2], "confiance": r[3],
            "recommandation": r[4], "juridiction": r[5], "temps": r[6], "date": r[7]
        } for r in rows])
    except Exception as e:
        conn.close()

        return jsonify({"error": str(e)}), 500


@app.route("/api/dossier/<dossier_uuid>")
def get_dossier(dossier_uuid):
    """Retourne les donnees completes d'un dossier"""
    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur = conn.cursor()
        cur.execute("""SELECT ticket_json, analyse_json, rapport_client_json,
                            rapport_avocat_json, procedure_json, points_json,
                            lois_json, precedents_json, cross_verification_json,
                            supervision_json, score_final, confiance, recommandation,
                            juridiction, temps_total, created_at
                     FROM analyses_completes WHERE dossier_uuid = %s""", (dossier_uuid,))
        row = cur.fetchone()
        conn.close()

        if not row:
            conn.close()
            return jsonify({"error": f"Dossier {dossier_uuid} non trouve"}), 404
        return jsonify({"error": "Dossier non trouve"}), 404

        conn.close()

        return jsonify({
            "dossier_uuid": dossier_uuid,
            "ticket": json.loads(row[0] or "{}"),
            "analyse": json.loads(row[1] or "{}"),
            "rapport_client": json.loads(row[2] or "{}"),
            "rapport_avocat": json.loads(row[3] or "{}"),
            "procedure": json.loads(row[4] or "{}"),
            "points": json.loads(row[5] or "{}"),
            "lois": json.loads(row[6] or "[]"),
            "precedents": json.loads(row[7] or "[]"),
            "cross_verification": json.loads(row[8] or "{}"),
            "supervision": json.loads(row[9] or "{}"),
            "score_final": row[10],
            "confiance": row[11],
            "recommandation": row[12],
            "juridiction": row[13],
            "temps_total": row[14],
            "created_at": row[15]
        })
    except Exception as e:
        conn.close()

        return jsonify({"error": str(e)}), 500


# ─── ENVOI EMAIL RAPPORT ──────────────────────
@app.route("/api/send-report", methods=["POST"])
def send_report():
    """Envoie le rapport par email a un destinataire"""
    data = request.get_json()
    if not data:

        return jsonify({"error": "JSON requis"}), 400

    email = data.get("email", "")
    dossier_uuid = data.get("dossier_uuid", "")

    if not email or not dossier_uuid:

        return jsonify({"error": "email et dossier_uuid requis"}), 400

    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur = conn.cursor()
        cur.execute("""SELECT rapport_client_json, score_final, recommandation
                     FROM analyses_completes WHERE dossier_uuid = %s""", (dossier_uuid,))
        row = cur.fetchone()
        conn.close()

        if not row:
            conn.close()
            return jsonify({"error": f"Dossier {dossier_uuid} non trouve"}), 404
        return jsonify({"error": f"Dossier {dossier_uuid} non trouve"}), 404

        rapport_client = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
        rapport_client["score"] = row[1]

        from agents.agent_notification import AgentNotification
        notif = AgentNotification()
        result = notif.notifier(
            dossier_uuid,
            {"email": email},
            rapport_client
        )

        conn.close()

        return jsonify({
            "success": result.get("email", {}).get("sent", False),
            "status": result.get("email", {}).get("status", "?"),
            "dossier_uuid": dossier_uuid,
            "email": email
        })
    except Exception as e:
        conn.close()

        return jsonify({"error": str(e)}), 500


# ─── DEMO (test sans ticket reel) ────────────
@app.route("/api/demo", methods=["POST"])
def demo_analyze():
    """Retourne un resultat simule pour tester le frontend"""
    import random
    score = random.randint(62, 88)
    confiance = random.randint(75, 95)
    uuid_demo = f"DEMO{random.randint(1000,9999)}"
    return jsonify({
        "success": True,
        "dossier_uuid": uuid_demo,
        "score": score,
        "score_final": score,
        "confiance": confiance,
        "recommandation": "contester" if score >= 65 else "negocier",
        "juridiction": "QC",
        "temps": 45.2,
        "temps_total": 45.2,
        "nb_erreurs": 0,
        "phases": {
            "intake": {"lecteur": "OK", "ocr": "OK", "classificateur": "OK", "validateur": "OK", "routing": "OK"},
            "analyse": {"lois": "OK", "precedents": "OK", "analyste": "OK", "procedure": "OK", "points": "OK",
                        "temoignage": "OK", "photo": "OK", "lois_qc": "OK", "precedents_qc": "OK",
                        "analyste_qc": "OK", "procedure_qc": "OK", "lois_on": "SKIP", "precedents_on": "SKIP",
                        "analyste_on": "SKIP", "procedure_on": "SKIP"},
            "audit": {"verificateur": "OK", "cross_verification": "OK"},
            "livraison": {"rapport_client": "OK", "rapport_avocat": "OK", "notification": "OK", "supervision": "OK"}
        },
        "arguments": [
            "L'appareil de mesure (cinematometre laser) doit etre calibre quotidiennement selon le Manuel du fabricant — verifier le registre de calibration",
            "L'agent n'a pas precise dans son rapport la distance de captation — une mesure a plus de 300m est contestable (R. c. Beaulieu, 2019)",
            "La signalisation de la zone de vitesse reduite doit etre conforme aux normes MTQ — verifier la presence du panneau a l'entree de la zone",
            "Le delai entre la captation et l'interception est un facteur: un delai trop long empeche l'identification formelle du vehicule",
            "La marge d'erreur de +/- 2 km/h de l'appareil peut etre invoquee si l'exces est marginal"
        ],
        "supervision": {"score_qualite": 92, "decision": "APPROUVE", "agents_verifies": 26},
        "rapport_client": {
            "resume": "Votre contravention pour exces de vitesse presente plusieurs elements contestables. L'analyse de 27 agents IA specialises identifie 5 arguments de defense solides bases sur la jurisprudence quebecoise et les normes de calibration des appareils de mesure. Nous recommandons de contester cette infraction.",
            "verdict": "CONTESTER — Bonnes chances de reussite",
            "prochaines_etapes": [
                "Enregistrer votre plaidoyer de non-culpabilite au greffe de la cour municipale dans les 30 jours",
                "Demander la divulgation de la preuve (rapport d'infraction, registre de calibration, formation de l'agent)",
                "Preparer votre defense avec les arguments identifies ci-dessus",
                "Si possible, consulter un avocat specialise en droit routier pour maximiser vos chances"
            ]
        },
        "precedents_trouves": 8,
        "lois_trouvees": 4,
        "timestamp": datetime.now().isoformat()
    })


# ─── MONITORING / ADMIN DASHBOARD ─────────────


# ═══════════════════════════════════════════════════════════
# MONITOR HELPERS — Services, Data Quality, RAG, Agents
# ═══════════════════════════════════════════════════════════



def _monitor_cron():
    """Lit le vrai crontab du système."""
    crons = []
    try:
        # Crontab de l'utilisateur ubuntu
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=3)
        if r.returncode == 0:
            for line in r.stdout.strip().split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Parser le cron: 5 champs schedule + commande
                parts = line.split(None, 5)
                if len(parts) >= 6:
                    schedule = " ".join(parts[:5])
                    cmd = parts[5]
                    # Extraire un nom lisible
                    name = cmd.split("/")[-1].split(".")[0] if "/" in cmd else cmd[:40]
                    # Détecter le type
                    if "aiticketinfo" in cmd or "ticket" in cmd.lower():
                        category = "ticket911"
                    elif "seo" in cmd.lower():
                        category = "seo"
                    elif "facturation" in cmd.lower():
                        category = "facturation"
                    else:
                        category = "system"
                    crons.append({
                        "schedule": schedule,
                        "command": cmd[:100],
                        "name": name[:30],
                        "category": category,
                        "raw": line[:120]
                    })
    except Exception as e:
        crons.append({"name": "Erreur", "error": str(e)})

    # Aussi lire /etc/cron.d/ pour les crons système
    try:
        import glob
        for cron_file in glob.glob("/etc/cron.d/*"):
            fname = os.path.basename(cron_file)
            if fname.startswith(".") or fname in ("e2scrub_all",):
                continue
            try:
                with open(cron_file) as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or line.startswith("SHELL") or line.startswith("PATH") or line.startswith("MAILTO"):
                            continue
                        parts = line.split(None, 6)
                        if len(parts) >= 7:
                            schedule = " ".join(parts[:5])
                            user = parts[5]
                            cmd = parts[6]
                            crons.append({
                                "schedule": schedule,
                                "command": cmd[:100],
                                "name": f"{fname}/{cmd.split('/')[-1].split('.')[0]}"[:30],
                                "category": "system",
                                "user": user,
                                "raw": line[:120]
                            })
            except Exception:
                pass
    except Exception:
        pass

    # Systemd timers
    try:
        r = subprocess.run(["systemctl", "list-timers", "--no-pager", "--plain"],
                          capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            for line in r.stdout.strip().split("\n")[1:]:  # Skip header
                parts = line.split()
                if len(parts) >= 5:
                    timer_name = parts[-1] if parts[-1].endswith(".timer") else None
                    if timer_name:
                        next_run = " ".join(parts[:3])
                        crons.append({
                            "schedule": next_run[:25],
                            "name": timer_name.replace(".timer", ""),
                            "category": "systemd",
                            "command": timer_name
                        })
    except Exception:
        pass

    return {
        "total": len(crons),
        "jobs": crons,
        "ticket911": [c for c in crons if c.get("category") == "ticket911"],
        "seo": [c for c in crons if c.get("category") == "seo"],
        "system": [c for c in crons if c.get("category") in ("system", "systemd")],
    }


def _monitor_saaq(cur):
    """Données SAAQ réelles depuis lois_articles + qc_constats_infraction."""
    saaq = {"articles": [], "bareme_vitesse": [], "top_infractions": []}
    try:
        # Articles principaux avec points (QC)
        cur.execute("""
            SELECT article, titre_article, categorie,
                   amende_min, amende_max,
                   points_inaptitude_min, points_inaptitude_max
            FROM lois_articles
            WHERE province = 'QC'
              AND points_inaptitude_min IS NOT NULL
              AND points_inaptitude_min > 0
            ORDER BY points_inaptitude_max DESC, article
            LIMIT 15
        """)
        for row in cur.fetchall():
            saaq["articles"].append({
                "article": row[0],
                "titre": (row[1] or "")[:50],
                "categorie": row[2],
                "amende_min": float(row[3]) if row[3] else None,
                "amende_max": float(row[4]) if row[4] else None,
                "points_min": row[5],
                "points_max": row[6]
            })

        # Barème vitesse réel (depuis constats)
        cur.execute("""
            SELECT
                CASE
                    WHEN (vitesse_constatee - vitesse_permise) BETWEEN 1 AND 20 THEN '1-20'
                    WHEN (vitesse_constatee - vitesse_permise) BETWEEN 21 AND 30 THEN '21-30'
                    WHEN (vitesse_constatee - vitesse_permise) BETWEEN 31 AND 45 THEN '31-45'
                    WHEN (vitesse_constatee - vitesse_permise) BETWEEN 46 AND 50 THEN '46-50'
                    WHEN (vitesse_constatee - vitesse_permise) > 50 THEN '50+'
                END as tranche,
                COUNT(*) as nb,
                MIN(vitesse_constatee - vitesse_permise) as exces_min,
                MAX(vitesse_constatee - vitesse_permise) as exces_max
            FROM qc_constats_infraction
            WHERE vitesse_constatee IS NOT NULL AND vitesse_permise IS NOT NULL
              AND vitesse_constatee > vitesse_permise
            GROUP BY tranche
            ORDER BY MIN(vitesse_constatee - vitesse_permise)
        """)
        for row in cur.fetchall():
            if row[0]:
                saaq["bareme_vitesse"].append({
                    "tranche": row[0] + " km/h",
                    "nb_constats": row[1],
                    "exces_min": row[2],
                    "exces_max": row[3]
                })

        # Top infractions par nombre de constats
        cur.execute("""
            SELECT ci.article, la.titre_article, COUNT(*) as nb,
                   la.points_inaptitude_min, la.points_inaptitude_max,
                   la.amende_min, la.amende_max
            FROM qc_constats_infraction ci
            LEFT JOIN lois_articles la ON ci.article = la.article AND la.province = 'QC'
            WHERE ci.article IS NOT NULL AND ci.article != ''
            GROUP BY ci.article, la.titre_article, la.points_inaptitude_min,
                     la.points_inaptitude_max, la.amende_min, la.amende_max
            ORDER BY nb DESC
            LIMIT 10
        """)
        for row in cur.fetchall():
            saaq["top_infractions"].append({
                "article": row[0],
                "titre": (row[1] or "")[:40],
                "nb_constats": row[2],
                "points_min": row[3],
                "points_max": row[4],
                "amende_min": float(row[5]) if row[5] else None,
                "amende_max": float(row[6]) if row[6] else None
            })

        # Stats globales constats
        cur.execute("SELECT COUNT(*) FROM qc_constats_infraction")
        saaq["total_constats"] = cur.fetchone()[0]

        cur.execute("SELECT COUNT(DISTINCT article) FROM qc_constats_infraction WHERE article IS NOT NULL")
        saaq["nb_articles_distincts"] = cur.fetchone()[0]

    except Exception as e:
        saaq["error"] = str(e)
    return saaq

def _monitor_sources(cur):
    """Stats par source de donnees"""
    sources = {}
    try:
        cur.execute("""
            SELECT COALESCE(source, 'canlii') as src, COUNT(*)
            FROM jurisprudence GROUP BY src ORDER BY COUNT(*) DESC
        """)
        for row in cur.fetchall():
            sources[row[0]] = row[1]
    except Exception as e:
        sources["error"] = str(e)
    return sources


def _monitor_background_agents(cur):
    """Stats des agents autonomes 24/7 (cron + services + AI)"""
    agents = []

    # 1. Classifier AI (classify_inconnu) — état du fichier state
    import json as _json
    state_file = "/var/www/aiticketinfo/db/classify_inconnu_state.json"
    try:
        with open(state_file) as _f:
            state = _json.load(_f)
        agents.append({
            "name": "AI Classifier (Mixtral)",
            "type": "ai",
            "status": state.get("status", "running"),
            "detail": f"Classifies: {state.get('classified', 0)}, Non-det: {state.get('still_inconnu', 0)}",
            "last_run": state.get("last_run", state.get("last_update", "")),
            "icon": "brain",
        })
    except FileNotFoundError:
        agents.append({
            "name": "AI Classifier (Mixtral)",
            "type": "ai",
            "status": "idle",
            "detail": "En attente",
            "last_run": "",
            "icon": "brain",
        })
    except Exception:
        pass

    # 2. Import CanLII (cron 1h00 AM)
    import_log = "/var/www/aiticketinfo/logs/canlii_import.log"
    try:
        with open(import_log) as _f:
            lines = _f.readlines()
            last_lines = [l.strip() for l in lines[-5:] if l.strip()]
        last_ts = ""
        for l in reversed(last_lines):
            m = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})', l)
            if m:
                last_ts = m.group(1)
                break
        agents.append({
            "name": "Import CanLII",
            "type": "cron",
            "status": "active",
            "detail": "Cron 1h00 AM — 4800 dossiers/nuit",
            "last_run": last_ts,
            "icon": "download",
        })
    except Exception:
        agents.append({
            "name": "Import CanLII",
            "type": "cron",
            "status": "active",
            "detail": "Cron 1h00 AM",
            "last_run": "",
            "icon": "download",
        })

    # 3. Embeddings Populator (cron 1h30 AM)
    embed_log = "/var/www/aiticketinfo/logs/embeddings.log"
    try:
        with open(embed_log) as _f:
            lines = _f.readlines()
            last_lines = [l.strip() for l in lines[-5:] if l.strip()]
        last_ts = ""
        for l in reversed(last_lines):
            m = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})', l)
            if m:
                last_ts = m.group(1)
                break
        agents.append({
            "name": "Embedding Generator",
            "type": "cron",
            "status": "active",
            "detail": "Cron 1h30 AM — qwen3-8b 4096d",
            "last_run": last_ts,
            "icon": "vector",
        })
    except Exception:
        agents.append({
            "name": "Embedding Generator",
            "type": "cron",
            "status": "active",
            "detail": "Cron 1h30 AM",
            "last_run": "",
            "icon": "vector",
        })

    # 4. Data Repair (cron 1h45 AM)
    repair_log = "/var/www/aiticketinfo/logs/data_repair.log"
    try:
        with open(repair_log) as _f:
            lines = _f.readlines()
            last_lines = [l.strip() for l in lines[-5:] if l.strip()]
        last_ts = ""
        for l in reversed(last_lines):
            m = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})', l)
            if m:
                last_ts = m.group(1)
                break
        agents.append({
            "name": "Data Repair",
            "type": "cron",
            "status": "active",
            "detail": "Cron 1h45 AM — auto-correcteur DB",
            "last_run": last_ts,
            "icon": "wrench",
        })
    except Exception:
        agents.append({
            "name": "Data Repair",
            "type": "cron",
            "status": "active",
            "detail": "Cron 1h45 AM",
            "last_run": "",
            "icon": "wrench",
        })

    # 5. Classifier 24/7 (systemd service)
    try:
        import subprocess
        r = subprocess.run(["systemctl", "is-active", "aiticketinfo-classifier"], capture_output=True, text=True, timeout=3)
        st = r.stdout.strip()
        agents.append({
            "name": "Classifier 24/7",
            "type": "service",
            "status": st if st in ("active", "inactive") else "unknown",
            "detail": "Keyword classifier — boucle 60s",
            "last_run": "",
            "icon": "tag",
        })
    except Exception:
        pass

    # 6. RAG Hybrid Search (intégré API)
    try:
        cur.execute("SELECT COUNT(*) FROM jurisprudence WHERE embedding IS NOT NULL")
        n_embed = cur.fetchone()[0]
        agents.append({
            "name": "RAG Hybrid Search",
            "type": "integrated",
            "status": "active",
            "detail": f"40% keyword + 60% semantic — {n_embed:,} vecteurs",
            "last_run": "",
            "icon": "search",
        })
    except Exception:
        pass

    # 7. Import A2AJ
    agents.append({
        "name": "Import A2AJ (York U.)",
        "type": "manual",
        "status": "active",
        "detail": "Source complementaire — 438 cas importes",
        "last_run": "",
        "icon": "database",
    })

    # 8. Pipeline 26 agents (stats)
    try:
        cur.execute("SELECT COUNT(DISTINCT agent_name) FROM agent_runs")
        n_agents = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM agent_runs")
        n_runs = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM agent_runs WHERE success = true")
        n_success = cur.fetchone()[0]
        pct = round(n_success / n_runs * 100, 1) if n_runs > 0 else 0
        agents.append({
            "name": f"Pipeline Analyse ({n_agents} agents)",
            "type": "pipeline",
            "status": "active",
            "detail": f"{n_runs} runs — {pct}% succes",
            "last_run": "",
            "icon": "pipeline",
        })
    except Exception:
        pass

    return agents

def _monitor_services():
    """Check systemd services status"""
    svcs = [
        ("aiticketinfo", "Ticket911 API (27 agents)"),
        ("aiticketinfo-classifier", "Classifier 24/7"),
        ("chatbot", "Chatbot Ticket911"),
        ("nginx", "Nginx Proxy"),
    ]
    results = []
    for svc, desc in svcs:
        try:
            r = subprocess.run(["systemctl", "is-active", f"{svc}.service"],
                              capture_output=True, text=True, timeout=3)
            status = r.stdout.strip()
            r2 = subprocess.run(["systemctl", "show", f"{svc}.service", "--property=ActiveEnterTimestamp"],
                               capture_output=True, text=True, timeout=3)
            since = r2.stdout.strip().replace("ActiveEnterTimestamp=", "")
            results.append({"name": svc, "desc": desc, "status": status, "since": since})
        except Exception:
            results.append({"name": svc, "desc": desc, "status": "unknown", "since": ""})
    # Docker PostgreSQL
    try:
        r = subprocess.run(["docker", "ps", "--filter", "name=seo-agent-postgres", "--format", "{{.Status}}"],
                          capture_output=True, text=True, timeout=5)
        pg_st = "running" if "Up" in r.stdout else "stopped"
        results.append({"name": "postgresql", "desc": "PostgreSQL (Docker)", "status": pg_st, "since": r.stdout.strip()[:50]})
    except Exception:
        results.append({"name": "postgresql", "desc": "PostgreSQL (Docker)", "status": "unknown", "since": ""})
    return results


def _monitor_data_quality(cur, total_juris):
    """Data quality audit"""
    fields = {}
    for col in ["database_id", "resume", "titre", "resultat", "embedding", "date_decision"]:
        try:
            if col == "embedding":
                cur.execute(f"SELECT count(*) FROM jurisprudence WHERE {col} IS NULL")
            else:
                cur.execute(f"SELECT count(*) FROM jurisprudence WHERE {col} IS NULL OR {col}::text = \'\'")
            nc = cur.fetchone()[0]
            pct = round((1 - nc / total_juris) * 100, 1) if total_juris > 0 else 0
            fields[col] = {"null": nc, "pct": pct}
        except Exception:
            cur.connection.rollback()
            fields[col] = {"null": -1, "pct": 0}
    ws = {"database_id": 3, "resume": 2, "titre": 2, "resultat": 3, "embedding": 2, "date_decision": 1}
    tw = sum(ws.values())
    score = round(sum(fields.get(c, {}).get("pct", 0) * w for c, w in ws.items()) / tw, 1)
    repair = {}
    try:
        sf = "/var/www/aiticketinfo/db/data_repair_state.json"
        if os.path.exists(sf):
            with open(sf) as f:
                repair = json.load(f)
    except Exception:
        pass
    return {"fields": fields, "score": score, "last_repair": repair}


def _monitor_agents_stats(cur):
    """Agent pipeline stats"""
    try:
        cur.execute("""
            SELECT agent_name, COUNT(*), AVG(duration_seconds),
                   SUM(CASE WHEN success = true THEN 1 ELSE 0 END),
                   SUM(CASE WHEN success = false THEN 1 ELSE 0 END)
            FROM agent_runs GROUP BY agent_name ORDER BY COUNT(*) DESC LIMIT 15
        """)
        agents = []
        for r in cur.fetchall():
            t = r[1]
            agents.append({
                "name": r[0], "runs": t,
                "avg_time": round(float(r[2] or 0), 1),
                "success": r[3] or 0, "fail": r[4] or 0,
                "success_pct": round((r[3] or 0) / t * 100, 1) if t > 0 else 0
            })
        cur.execute("SELECT COUNT(*), AVG(duration_seconds) FROM agent_runs")
        tot = cur.fetchone()
        return {"agents": agents, "total_runs": tot[0] or 0, "avg_duration": round(float(tot[1] or 0), 1)}
    except Exception as e:
        return {"error": str(e)}


def _monitor_rag_metrics(cur):
    """RAG system metrics"""
    m = {}
    try:
        cur.execute("SELECT indexname FROM pg_indexes WHERE tablename='jurisprudence' AND indexdef LIKE '%%hnsw%%'")
        hnsw = cur.fetchall()
        m["hnsw_index"] = len(hnsw) > 0
        m["hnsw_name"] = hnsw[0][0] if hnsw else None
        m["vector_note"] = "4096d > pgvector 2000d limit" if not m["hnsw_index"] else "indexed"
        cur.execute("SELECT COUNT(*) FROM pg_indexes WHERE tablename='jurisprudence' AND indexdef LIKE '%%gin%%'")
        m["gin_indexes"] = cur.fetchone()[0]
        cur.execute("""SELECT AVG(duration_seconds), COUNT(*) FROM agent_runs
                      WHERE agent_name LIKE '%%Precedents%%' AND created_at > now() - interval '7 days'""")
        r = cur.fetchone()
        m["avg_search_time"] = round(float(r[0] or 0), 1)
        m["searches_7d"] = r[1] or 0
        m["model"] = "fireworks/qwen3-embedding-8b"
        m["dims"] = 4096
        m["store"] = "pgvector"
    except Exception as e:
        m["error"] = str(e)
    return m




def _monitor_system():
    """Info systeme: CPU, RAM, disque, uptime"""
    info = {}
    try:
        import shutil
        # Disk
        total, used, free = shutil.disk_usage("/")
        info["disk_total_gb"] = round(total / (1024**3), 1)
        info["disk_used_gb"] = round(used / (1024**3), 1)
        info["disk_free_gb"] = round(free / (1024**3), 1)
        info["disk_pct"] = round(used / total * 100, 1)
    except Exception:
        info["disk_pct"] = 0

    try:
        # RAM
        with open("/proc/meminfo") as f:
            mem = {}
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    mem[parts[0].rstrip(":")] = int(parts[1])
            total_kb = mem.get("MemTotal", 0)
            avail_kb = mem.get("MemAvailable", mem.get("MemFree", 0))
            used_kb = total_kb - avail_kb
            info["ram_total_gb"] = round(total_kb / (1024**2), 1)
            info["ram_used_gb"] = round(used_kb / (1024**2), 1)
            info["ram_free_gb"] = round(avail_kb / (1024**2), 1)
            info["ram_pct"] = round(used_kb / total_kb * 100, 1) if total_kb > 0 else 0
    except Exception:
        info["ram_pct"] = 0

    try:
        # CPU load
        with open("/proc/loadavg") as f:
            parts = f.read().split()
            info["cpu_load_1m"] = float(parts[0])
            info["cpu_load_5m"] = float(parts[1])
            info["cpu_load_15m"] = float(parts[2])
        # CPU count
        info["cpu_cores"] = os.cpu_count() or 1
        info["cpu_pct"] = round(info["cpu_load_1m"] / info["cpu_cores"] * 100, 1)
    except Exception:
        info["cpu_pct"] = 0

    try:
        # Uptime
        with open("/proc/uptime") as f:
            uptime_secs = float(f.read().split()[0])
            days = int(uptime_secs // 86400)
            hours = int((uptime_secs % 86400) // 3600)
            info["uptime"] = f"{days}j {hours}h"
            info["uptime_seconds"] = int(uptime_secs)
    except Exception:
        info["uptime"] = "?"

    return info


def _monitor_robots():
    """Robots/processus deployes en temps reel"""
    robots = []

    # Processus Python actifs liés au projet
    robot_patterns = [
        ("classify_qccm", "Classificateur QCCM (5 modeles)"),
        ("classify_inconnus", "Classificateur inconnus"),
        ("benchmark", "Benchmark A vs B"),
        ("test_analyze", "Test analyse"),
        ("embedding_service", "Service embeddings"),
        ("canlii_import", "Import CanLII"),
        ("auto_repair", "Auto-reparation DB"),
        ("dual_runner", "Comparateur dual A/B"),
        ("api.py", "API Ticket911"),
    ]

    try:
        import subprocess
        r = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
        lines = r.stdout.split("\n")

        for pattern, desc in robot_patterns:
            matching = [l for l in lines if pattern in l and "grep" not in l]
            if matching:
                for line in matching:
                    parts = line.split()
                    pid = parts[1] if len(parts) > 1 else "?"
                    cpu = parts[2] if len(parts) > 2 else "0"
                    mem = parts[3] if len(parts) > 3 else "0"
                    # Extract runtime from ps
                    started = parts[8] if len(parts) > 8 else "?"
                    robots.append({
                        "name": desc,
                        "pattern": pattern,
                        "pid": pid,
                        "cpu": cpu,
                        "mem": mem,
                        "started": started,
                        "status": "running"
                    })
    except Exception as e:
        robots.append({"name": "Erreur", "status": "error", "error": str(e)})

    # Cron jobs planifies
    try:
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=3)
        crons = [l.strip() for l in r.stdout.split("\n") if l.strip() and not l.startswith("#")]
        for c in crons:
            robots.append({"name": "Cron", "pattern": c[:60], "status": "scheduled"})
    except Exception:
        pass

    return robots


def _monitor_audit(cur):
    """Stats audit: classification, qualite, progression"""
    audit = {}
    try:
        # Classification progress
        cur.execute("""
            SELECT resultat, COUNT(*) FROM jurisprudence
            WHERE est_ticket_related = true
            GROUP BY resultat ORDER BY COUNT(*) DESC
        """)
        audit["par_resultat"] = {row[0] or "NULL": row[1] for row in cur.fetchall()}

        cur.execute("SELECT COUNT(*) FROM jurisprudence WHERE resultat = 'inconnu' AND est_ticket_related = true")
        audit["inconnus_restants"] = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM jurisprudence WHERE est_ticket_related = false")
        audit["hors_sujet_total"] = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM jurisprudence")
        audit["total_jurisprudence"] = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM jurisprudence WHERE est_ticket_related = true")
        audit["ticket_related"] = cur.fetchone()[0]

        # Classification par tribunal
        cur.execute("""
            SELECT database_id, resultat, COUNT(*)
            FROM jurisprudence
            WHERE est_ticket_related = true AND resultat != 'inconnu'
            GROUP BY database_id, resultat ORDER BY database_id, COUNT(*) DESC
        """)
        par_tribunal = {}
        for db_id, res, cnt in cur.fetchall():
            db = db_id or "NULL"
            if db not in par_tribunal:
                par_tribunal[db] = {}
            par_tribunal[db][res] = cnt
        audit["classification_par_tribunal"] = par_tribunal

        # Derniere classification
        try:
            log_path = "/tmp/classify_qccm_500.log"
            if os.path.exists(log_path):
                with open(log_path) as f:
                    lines = f.readlines()
                    last = [l.strip() for l in lines[-5:] if l.strip()]
                    audit["derniere_classification"] = "\n".join(last)
                    # Extract progress
                    for l in reversed(lines):
                        if "/" in l and "[" in l:
                            import re
                            m = re.search(r"\[(\d+)/(\d+)\]", l)
                            if m:
                                audit["classify_progress"] = f"{m.group(1)}/{m.group(2)}"
                                break
            else:
                audit["derniere_classification"] = "Aucun log"
        except Exception:
            audit["derniere_classification"] = "Erreur lecture log"

    except Exception as e:
        audit["error"] = str(e)

    return audit



@app.route("/api/monitor")
def monitor():
    """Endpoint monitoring complet v2 — DB, embeddings, quota, pipeline, alertes"""
    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur = conn.cursor()

        # Toutes les 16 tables avec descriptions
        ALL_TABLES = [
            ('qc_constats_infraction', 'Vrais tickets QC'),
            ('speed_limits', 'Limites de vitesse QC+ON'),
            ('jurisprudence', 'Decisions de cour'),
            ('qc_radar_photo_stats', 'Stats radars photo QC'),
            ('lois_articles', 'Articles de loi QC/ON'),
            ('road_conditions', 'Conditions routieres'),
            ('on_set_fines', 'Bareme amendes ON'),
            ('jurisprudence_citations', 'Citations jurisprudence'),
            ('jurisprudence_legislation', 'Liens juris-lois'),
            ('qc_radar_photo_lieux', 'Emplacements radars'),
            ('agent_runs', 'Logs agent'),
            ('on_traffic_offences', 'Stats infractions ON'),
            ('ref_jurisprudence_cle', 'References cles'),
            ('analyses_completes', 'Analyses'),
            ('data_source_log', 'Log sources donnees'),
            ('mtl_escouade_mobilite', 'Escouade mobilite MTL'),
        ]

        tables_stats = {}
        tables_desc = {}
        for table, desc in ALL_TABLES:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                tables_stats[table] = cur.fetchone()[0]
                tables_desc[table] = desc
            except Exception:
                conn.rollback()
                tables_stats[table] = -1
                tables_desc[table] = desc

        # Jurisprudence breakdown
        cur.execute("SELECT database_id, COUNT(*) FROM jurisprudence GROUP BY database_id ORDER BY COUNT(*) DESC")
        par_tribunal = {row[0] or "N/A": row[1] for row in cur.fetchall()}

        cur.execute("SELECT resultat, COUNT(*) FROM jurisprudence GROUP BY resultat ORDER BY COUNT(*) DESC")
        par_resultat = {row[0] or "inconnu": row[1] for row in cur.fetchall()}

        cur.execute("SELECT province, COUNT(*) FROM jurisprudence GROUP BY province ORDER BY COUNT(*) DESC")
        par_province = {row[0] or "N/A": row[1] for row in cur.fetchall()}

        # Embeddings stats
        cur.execute("SELECT COUNT(*) FROM jurisprudence WHERE embedding IS NOT NULL")
        nb_embedded = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM jurisprudence WHERE embedding IS NULL")
        nb_no_embed = cur.fetchone()[0]
        nb_juris_total = tables_stats.get('jurisprudence', 0)
        embed_pct = round(nb_embedded / nb_juris_total * 100, 1) if nb_juris_total > 0 else 0

        # Recent imports (par jour)
        cur.execute("""SELECT date_trunc('day', imported_at)::date as jour, COUNT(*)
                      FROM jurisprudence
                      WHERE imported_at > now() - interval '7 days'
                      GROUP BY jour ORDER BY jour DESC""")
        imports_par_jour = {str(row[0]): row[1] for row in cur.fetchall()}

        # Analyses stats
        cur.execute("""SELECT COUNT(*), AVG(score_final), AVG(confiance), AVG(temps_total)
                      FROM analyses_completes""")
        a_row = cur.fetchone()
        analyses_stats = {
            "total": a_row[0] or 0,
            "score_moyen": round(float(a_row[1] or 0), 1),
            "confiance_moyenne": round(float(a_row[2] or 0), 1),
            "temps_moyen": round(float(a_row[3] or 0), 1)
        }

        cur.execute("""SELECT recommandation, COUNT(*)
                      FROM analyses_completes GROUP BY recommandation""")
        analyses_par_reco = {row[0] or "?": row[1] for row in cur.fetchall()}


        # CanLII quota
        canlii_quota = {"remaining": "unknown", "used_today": 0, "daily_max": 4800}
        try:
            usage_file = "/var/www/aiticketinfo/logs/canlii_usage.json"
            if os.path.exists(usage_file):
                with open(usage_file) as f:
                    usage = json.load(f)
                import datetime as dt2
                today_yday = dt2.datetime.now().timetuple().tm_yday
                if usage.get("day") == today_yday:
                    used = usage.get("count", 0)
                else:
                    used = 0
                canlii_quota = {
                    "used_today": used,
                    "remaining": 4800 - used,
                    "daily_max": 4800,
                    "last_update": usage.get("last_update", "?")
                }
        except Exception:
            pass

        # Last import log
        last_import = "Aucun log"
        try:
            log_path = "/var/www/aiticketinfo/logs/canlii_import.log"
            if os.path.exists(log_path):
                with open(log_path) as f:
                    lines = f.readlines()
                    last_lines = [l.strip() for l in lines[-20:] if l.strip()]
                    last_import = "\n".join(last_lines)
        except Exception:
            pass

        # Last embeddings log
        last_embed_log = "Pas encore execute"
        try:
            elog_path = "/var/www/aiticketinfo/logs/embeddings.log"
            if os.path.exists(elog_path):
                with open(elog_path) as f:
                    elines = f.readlines()
                    last_elines = [l.strip() for l in elines[-10:] if l.strip()]
                    last_embed_log = "\n".join(last_elines)
        except Exception:
            pass

        # Alertes
        alertes = []
        anomalies = []

        # --- Embeddings ---
        if nb_no_embed > 100:
            alertes.append({"level": "warning", "msg": f"{nb_no_embed} dossiers sans embedding ({embed_pct}% complete)"})
        elif nb_embedded == nb_juris_total and nb_juris_total > 0:
            alertes.append({"level": "info", "msg": f"Embeddings 100% complets ({nb_embedded} dossiers)"})

        # --- Jurisprudence ---
        if nb_juris_total < 500:
            alertes.append({"level": "warning", "msg": f"Jurisprudence faible: {nb_juris_total} dossiers"})

        # --- CanLII quota ---
        remaining = canlii_quota.get("remaining", 5000)
        if isinstance(remaining, int) and remaining <= 0:
            alertes.append({"level": "warning", "msg": "Quota CanLII epuise pour aujourd'hui"})
        elif isinstance(remaining, int) and remaining <= 500 and remaining > 0:
            alertes.append({"level": "info", "msg": f"Quota CanLII bas: {remaining} restant"})

        # --- Analyses ---
        if analyses_stats["total"] == 0:
            alertes.append({"level": "info", "msg": "Aucune analyse effectuee encore"})

        # --- ANOMALIES: Agents en echec ---
        try:
            cur.execute("""
                SELECT agent_name, COUNT(*) as total,
                       SUM(CASE WHEN success = false THEN 1 ELSE 0 END) as fails
                FROM agent_runs GROUP BY agent_name HAVING COUNT(*) >= 10
            """)
            for row in cur.fetchall():
                agent_name, total, fails = row[0], row[1], row[2] or 0
                fail_pct = round(fails / total * 100, 1) if total > 0 else 0
                if fail_pct >= 30:
                    anomalies.append({"level": "critical", "category": "agent",
                        "msg": f"Agent {agent_name}: {fail_pct}% echecs ({fails}/{total} runs)"})
                elif fail_pct >= 10:
                    anomalies.append({"level": "warning", "category": "agent",
                        "msg": f"Agent {agent_name}: {fail_pct}% echecs ({fails}/{total} runs)"})
        except Exception:
            cur.connection.rollback()

        # --- ANOMALIES: Qualite donnees ---
        for col, label, seuil in [("resume", "Resume", 80), ("resultat", "Resultat", 85),
                                   ("titre", "Titre", 95), ("date_decision", "Date", 90)]:
            try:
                cur.execute(f"SELECT count(*) FROM jurisprudence WHERE {col} IS NULL OR {col}::text = ''")
                nc = cur.fetchone()[0]
                pct_filled = round((1 - nc / nb_juris_total) * 100, 1) if nb_juris_total > 0 else 0
                if pct_filled < seuil:
                    anomalies.append({"level": "warning", "category": "data_quality",
                        "msg": f"{label}: {pct_filled}% rempli ({nc} vides sur {nb_juris_total})"})
            except Exception:
                cur.connection.rollback()

        # --- ANOMALIES: Systeme (swap, disque) ---
        try:
            with open("/proc/meminfo") as f:
                mem = {}
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        mem[parts[0].rstrip(":")] = int(parts[1])
            swap_total = mem.get("SwapTotal", 0)
            swap_free = mem.get("SwapFree", 0)
            if swap_total > 0:
                swap_pct = round((swap_total - swap_free) / swap_total * 100, 1)
                if swap_pct >= 70:
                    anomalies.append({"level": "warning", "category": "system",
                        "msg": f"Swap utilise a {swap_pct}% ({round((swap_total - swap_free) / 1024 / 1024, 1)} Go / {round(swap_total / 1024 / 1024, 1)} Go)"})
        except Exception:
            pass

        try:
            import shutil
            total_d, used_d, _ = shutil.disk_usage("/")
            disk_pct = round(used_d / total_d * 100, 1)
            if disk_pct >= 80:
                anomalies.append({"level": "critical", "category": "system",
                    "msg": f"Disque a {disk_pct}% ({round(used_d / (1024**3), 1)} / {round(total_d / (1024**3), 1)} Go)"})
            elif disk_pct >= 70:
                anomalies.append({"level": "warning", "category": "system",
                    "msg": f"Disque a {disk_pct}% ({round(used_d / (1024**3), 1)} / {round(total_d / (1024**3), 1)} Go)"})
        except Exception:
            pass

        # --- ANOMALIES: Aucun utilisateur reel ---
        try:
            cur.execute("SELECT count(*) FROM tickets_scannes_meta")
            nb_scans = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM user_analyses")
            nb_user_analyses = cur.fetchone()[0]
            if nb_scans == 0 and nb_user_analyses == 0:
                anomalies.append({"level": "info", "category": "usage",
                    "msg": "0 ticket scanne par utilisateur — aucune utilisation reelle"})
        except Exception:
            cur.connection.rollback()

        # --- ANOMALIES: Indexes doublons ---
        try:
            cur.execute("""SELECT indexname FROM pg_indexes
                          WHERE tablename='jurisprudence'
                          AND (indexname LIKE 'idx_juris_tsv%%' OR indexname LIKE 'idx_jurisprudence_tsv%%')
                          ORDER BY indexname""")
            idx_names = [r[0] for r in cur.fetchall()]
            tsv_fr_count = sum(1 for n in idx_names if 'tsv_fr' in n)
            tsv_en_count = sum(1 for n in idx_names if 'tsv_en' in n)
            if tsv_fr_count > 1:
                anomalies.append({"level": "info", "category": "db",
                    "msg": f"Index tsv_fr en doublon ({tsv_fr_count} indexes)"})
            if tsv_en_count > 1:
                anomalies.append({"level": "info", "category": "db",
                    "msg": f"Index tsv_en en doublon ({tsv_en_count} indexes)"})
        except Exception:
            cur.connection.rollback()

        # conn.close() moved after helper calls below

        services_data = _monitor_services()
        dq_data = _monitor_data_quality(cur, nb_juris_total)
        agents_data = _monitor_agents_stats(cur)
        sources_data = _monitor_sources(cur)
        bg_agents_data = _monitor_background_agents(cur)
        rag_data = _monitor_rag_metrics(cur)
        system_data = _monitor_system()
        robots_data = _monitor_robots()
        audit_data = _monitor_audit(cur)
        saaq_data = _monitor_saaq(cur)

        conn.close()

        return jsonify({
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "db": {
                "tables": tables_stats,
                "tables_desc": tables_desc,
                "total_rows": sum(v for v in tables_stats.values() if v > 0),
                "jurisprudence": {
                    "par_tribunal": par_tribunal,
                    "par_resultat": par_resultat,
                    "par_province": par_province,
                    "imports_par_jour": imports_par_jour
                }
            },
            "embeddings": {
                "total": nb_juris_total,
                "embedded": nb_embedded,
                "missing": nb_no_embed,
                "pct": embed_pct,
                "model": "fireworks/qwen3-embedding-8b",
                "dims": 4096,
                "store": "pgvector"
            },
            "analyses": {
                "stats": analyses_stats,
                "par_recommandation": analyses_par_reco
            },
            "canlii": canlii_quota,
            "last_import_log": last_import[-800:] if isinstance(last_import, str) else last_import,
            "last_embed_log": last_embed_log[-500:] if isinstance(last_embed_log, str) else last_embed_log,
            "alertes": alertes,
            "anomalies": anomalies,
            "cron": _monitor_cron(),
            "services": services_data,
            "sources": sources_data,
            "background_agents": bg_agents_data,
            "data_quality": dq_data,
            "agents_stats": agents_data,
            "rag_metrics": rag_data,
            "system": system_data,
            "robots": robots_data,
            "audit": audit_data,
            "saaq": saaq_data
        })
    except Exception as e:
        conn.close()

        return jsonify({"status": "error", "error": str(e)}), 500




@app.route("/api/test-search")
def test_search():
    """Test de recherche RAG — ping jurisprudence depuis le dashboard."""
    import time
    import re as re_mod
    query = request.args.get("q", "").strip()
    mode = request.args.get("mode", "text")  # text, vector, article, all
    limit = min(int(request.args.get("limit", "10")), 50)

    if not query or len(query) < 2:
        return jsonify({"error": "Parametre q requis (min 2 chars)"}), 400

    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur = conn.cursor()
        t0 = time.time()
        results = []

        if mode in ("text", "all"):
            # Recherche plein texte tsvector
            clean = re_mod.sub(r"[^\w\s]", " ", query.lower())
            mots = [w for w in clean.split() if len(w) > 2 and w.isalpha()][:6]
            if not mots:
                mots = ["infraction"]
            tsquery = " | ".join(mots)

            cur.execute("""
                SELECT id, canlii_id, citation, titre, tribunal, database_id,
                       date_decision, resultat, LEFT(resume, 200) as resume,
                       ts_rank(tsv_fr, to_tsquery('french_unaccent', %s)) AS score,
                       'tsvector' AS methode
                FROM jurisprudence
                WHERE est_ticket_related = true
                  AND tsv_fr @@ to_tsquery('french_unaccent', %s)
                ORDER BY score DESC
                LIMIT %s
            """, (tsquery, tsquery, limit))

            for row in cur.fetchall():
                results.append({
                    "id": row[0], "canlii_id": row[1], "citation": row[2],
                    "titre": row[3], "tribunal": row[4], "database_id": row[5],
                    "date": str(row[6]) if row[6] else None, "resultat": row[7],
                    "resume": row[8], "score": round(float(row[9]), 4),
                    "methode": row[10]
                })

        if mode in ("vector", "all"):
            # Recherche vectorielle pgvector
            try:
                from openai import OpenAI as OAI
                import os
                fw_client = OAI(
                    api_key=os.environ.get("FIREWORKS_API_KEY", ""),
                    base_url="https://api.fireworks.ai/inference/v1"
                )
                resp = fw_client.embeddings.create(
                    model="fireworks/qwen3-embedding-8b",
                    input=[query[:2000]]
                )
                emb = resp.data[0].embedding
                emb_str = "[" + ",".join(str(x) for x in emb) + "]"

                cur.execute("""
                    SELECT id, canlii_id, citation, titre, tribunal, database_id,
                           date_decision, resultat, LEFT(resume, 200) as resume,
                           1 - (embedding <=> %s::vector) AS score,
                           'pgvector' AS methode
                    FROM jurisprudence
                    WHERE est_ticket_related = true AND embedding IS NOT NULL
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                """, (emb_str, emb_str, limit))

                seen_ids = {r["id"] for r in results}
                for row in cur.fetchall():
                    if row[0] not in seen_ids:
                        results.append({
                            "id": row[0], "canlii_id": row[1], "citation": row[2],
                            "titre": row[3], "tribunal": row[4], "database_id": row[5],
                            "date": str(row[6]) if row[6] else None, "resultat": row[7],
                            "resume": row[8], "score": round(float(row[9]), 4),
                            "methode": row[10]
                        })
            except Exception as e:
                results.append({"methode": "pgvector", "error": str(e)[:100]})

        if mode in ("article", "all"):
            # Recherche par article CSR
            cur.execute("""
                SELECT id, canlii_id, citation, titre, tribunal, database_id,
                       date_decision, resultat, LEFT(resume, 200) as resume,
                       0.9 AS score, 'article' AS methode
                FROM jurisprudence
                WHERE est_ticket_related = true
                  AND EXISTS (SELECT 1 FROM unnest(lois_pertinentes) lp WHERE lp ILIKE %s)
                ORDER BY date_decision DESC
                LIMIT %s
            """, (f"%{query}%", limit))

            seen_ids = {r["id"] for r in results if isinstance(r, dict) and "id" in r}
            for row in cur.fetchall():
                if row[0] not in seen_ids:
                    results.append({
                        "id": row[0], "canlii_id": row[1], "citation": row[2],
                        "titre": row[3], "tribunal": row[4], "database_id": row[5],
                        "date": str(row[6]) if row[6] else None, "resultat": row[7],
                        "resume": row[8], "score": round(float(row[9]), 4),
                        "methode": row[10]
                    })

        # Aussi chercher dans lois_articles
        loi_result = None
        try:
            cur.execute("""
                SELECT article, titre_article, LEFT(texte_complet, 300),
                       amende_min, amende_max, points_inaptitude_min, points_inaptitude_max
                FROM lois_articles WHERE article = %s LIMIT 1
            """, (query,))
            row = cur.fetchone()
            if row:
                loi_result = {
                    "article": row[0], "titre": row[1], "texte": row[2],
                    "amende_min": str(row[3]) if row[3] else None,
                    "amende_max": str(row[4]) if row[4] else None,
                    "points_min": row[5], "points_max": row[6]
                }
        except Exception:
            pass

        elapsed = time.time() - t0
        conn.close()

        # Trier par score
        valid_results = [r for r in results if "score" in r]
        valid_results.sort(key=lambda x: x.get("score", 0), reverse=True)

        return jsonify({
            "query": query,
            "mode": mode,
            "count": len(valid_results),
            "time_ms": round(elapsed * 1000),
            "results": valid_results[:limit],
            "loi": loi_result,
            "stats": {
                "tsvector": len([r for r in valid_results if r.get("methode") == "tsvector"]),
                "pgvector": len([r for r in valid_results if r.get("methode") == "pgvector"]),
                "article": len([r for r in valid_results if r.get("methode") == "article"]),
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route("/api/jurisprudence/<int:juris_id>")
def get_jurisprudence_detail(juris_id):
    """Detail complet d'une decision de jurisprudence."""
    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur = conn.cursor()

        cur.execute("""
            SELECT id, canlii_id, database_id, province, titre, citation,
                   numero_dossier, date_decision, url_canlii, tribunal, langue,
                   mots_cles, lois_pertinentes, resume, texte_complet,
                   resultat, est_ticket_related, source, imported_at
            FROM jurisprudence WHERE id = %s
        """, (juris_id,))
        row = cur.fetchone()

        if not row:
            conn.close()
            return jsonify({"error": "Dossier non trouve"}), 404

        # Chercher les articles de loi pertinents
        lois_details = []
        if row[12]:  # lois_pertinentes
            for loi in row[12][:10]:
                cur.execute("""
                    SELECT article, titre_article, LEFT(texte_complet, 500),
                           amende_min, amende_max, points_inaptitude_min, points_inaptitude_max,
                           categorie
                    FROM lois_articles WHERE article = %s LIMIT 1
                """, (loi,))
                lrow = cur.fetchone()
                if lrow:
                    lois_details.append({
                        "article": lrow[0], "titre": lrow[1], "texte": lrow[2],
                        "amende_min": str(lrow[3]) if lrow[3] else None,
                        "amende_max": str(lrow[4]) if lrow[4] else None,
                        "points_min": lrow[5], "points_max": lrow[6],
                        "categorie": lrow[7]
                    })

        # Stats: combien de cas similaires (meme article)
        stats_similaires = {}
        if row[12]:
            for loi in row[12][:3]:
                cur.execute("""
                    SELECT resultat, COUNT(*) FROM jurisprudence
                    WHERE est_ticket_related = true
                      AND EXISTS (SELECT 1 FROM unnest(lois_pertinentes) lp WHERE lp = %s)
                    GROUP BY resultat
                """, (loi,))
                stats_similaires[loi] = {r[0]: r[1] for r in cur.fetchall() if r[0]}

        conn.close()

        texte = row[14] or ""

        return jsonify({
            "id": row[0],
            "canlii_id": row[1],
            "database_id": row[2],
            "province": row[3],
            "titre": row[4],
            "citation": row[5],
            "numero_dossier": row[6],
            "date_decision": str(row[7]) if row[7] else None,
            "url_canlii": row[8],
            "tribunal": row[9],
            "langue": row[10],
            "mots_cles": row[11],
            "lois_pertinentes": row[12],
            "resume": row[13],
            "texte_complet": texte[:15000],
            "texte_length": len(texte),
            "resultat": row[15],
            "est_ticket_related": row[16],
            "source": row[17],
            "imported_at": str(row[18]) if row[18] else None,
            "lois_details": lois_details,
            "stats_similaires": stats_similaires
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin")
def admin_dashboard():
    """Dashboard admin — monitoring visuel"""
    return send_from_directory(".", "admin.html")



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
            conn.close()
            return jsonify({"error": f"Dossier {dossier_uuid} non trouve"}), 404
        return jsonify({"error": "Score non trouve"}), 404
        conn.close()

        return jsonify({
            "dossier_uuid": dossier_uuid,
            "score": float(row[0]),
            "f1": float(row[1]), "f2": float(row[2]), "f3": float(row[3]),
            "f4": float(row[4]), "f5": float(row[5]),
            "nb_jugements": row[6], "acquittements": row[7], "condamnations": row[8],
            "detail": row[9], "date": str(row[10])
        })
    except Exception as e:
        conn.close()

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
        conn.close()

        return jsonify({"session_id": session_id, "messages": messages})
    except Exception as e:
        conn.close()

        return jsonify({"error": str(e)}), 500




@app.route("/api/chat/scan", methods=["POST"])
def chat_scan():
    """OCR leger — scan photo ticket et retourne les champs extraits (sans pipeline 27 agents)."""
    import time
    start = time.time()
    
    if "ticket_photo" not in request.files:

        return jsonify({"error": "Aucune image. Envoyez ticket_photo."}), 400
    
    file = request.files["ticket_photo"]
    if not file or not file.filename:

        return jsonify({"error": "Fichier vide"}), 400
    
    # Sauvegarder temporairement
    import tempfile
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    tmp = tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False, dir="/tmp")
    file.save(tmp.name)
    tmp.close()
    
    try:
        from agents.agent_ocr import AgentOCR
        ocr = AgentOCR()
        ticket = ocr.extraire_ticket(image_path=tmp.name)
        
        duration = round(time.time() - start, 1)
        
        if not ticket or not any(v for k, v in ticket.items() if k != "texte_brut_ocr" and v):
            return jsonify({
                "success": False,
                "error": "OCR n a pas reussi a extraire les informations. Essayez avec une meilleure photo.",
                "temps": duration
            })

        return jsonify({
            "success": True,
            "ticket": ticket,
            "temps": duration,
            "methode": "OCR.space + DeepSeek V3"
        })
    except Exception as e:

        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        import os
        try:
            os.unlink(tmp.name)
        except:
            pass



@app.route("/api/chat/evidence", methods=["POST"])
def chat_evidence():
    """Upload photos de preuves avec extraction EXIF/GPS."""
    import time
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
    start = time.time()

    session_id = request.form.get("session_id", "")
    if not session_id:

        return jsonify({"error": "session_id requis"}), 400

    files = request.files.getlist("evidence_photos")
    if not files:

        return jsonify({"error": "Aucune photo envoyee"}), 400

    folder = os.path.join(UPLOAD_DIR, f"chat_{session_id}")
    os.makedirs(folder, exist_ok=True)

    results = []
    for i, file in enumerate(files):
        if not file or not file.filename:
            continue
        if not allowed_file(file.filename):
            results.append({"name": file.filename, "error": "Format non supporte"})
            continue

        safe_name = secure_filename(file.filename)
        final_name = f"preuve_{i+1}_{safe_name}"
        filepath = os.path.join(folder, final_name)
        file.save(filepath)

        exif_data = _extract_exif_gps(filepath)

        results.append({
            "name": final_name,
            "original": file.filename,
            "size": os.path.getsize(filepath),
            "exif": exif_data,
            "path": filepath
        })

    duration = round(time.time() - start, 1)
    return jsonify({
        "success": True,
        "session_id": session_id,
        "uploaded": len([r for r in results if "error" not in r]),
        "photos": results,
        "temps": duration
    })


def _extract_exif_gps(filepath):
    """Extrait les donnees EXIF et GPS d une photo."""
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
    data = {}
    try:
        img = Image.open(filepath)
        exif_raw = img._getexif()
        if not exif_raw:
            return {"info": "Pas de donnees EXIF"}

        for tag_id, value in exif_raw.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag == "GPSInfo":
                gps = {}
                for gps_tag_id, gps_value in value.items():
                    gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                    gps[gps_tag] = gps_value
                lat = _gps_to_decimal(gps.get("GPSLatitude"), gps.get("GPSLatitudeRef"))
                lon = _gps_to_decimal(gps.get("GPSLongitude"), gps.get("GPSLongitudeRef"))
                if lat and lon:
                    data["gps_lat"] = round(lat, 6)
                    data["gps_lon"] = round(lon, 6)
                    data["gps_google_maps"] = f"https://maps.google.com/?q={lat},{lon}"
                if gps.get("GPSAltitude"):
                    try:
                        alt = float(gps["GPSAltitude"])
                        data["gps_altitude"] = round(alt, 1)
                    except (TypeError, ValueError):
                        pass
            elif tag == "DateTimeOriginal":
                data["date_photo"] = str(value)
            elif tag == "DateTime":
                if "date_photo" not in data:
                    data["date_photo"] = str(value)
            elif tag == "Make":
                data["appareil_marque"] = str(value)
            elif tag == "Model":
                data["appareil_modele"] = str(value)
            elif tag == "ImageWidth":
                data["largeur"] = value
            elif tag == "ImageLength":
                data["hauteur"] = value

        if "largeur" not in data:
            data["largeur"] = img.width
            data["hauteur"] = img.height

    except Exception as e:
        data["erreur_exif"] = str(e)
    return data


def _gps_to_decimal(coords, ref):
    """Convertit coordonnees GPS EXIF en decimal."""
    if not coords or not ref:
        return None
    try:
        d = float(coords[0])
        m = float(coords[1])
        s = float(coords[2])
        decimal = d + m / 60.0 + s / 3600.0
        if ref in ("S", "W"):
            decimal = -decimal
        return decimal
    except (TypeError, ValueError, IndexError):
        return None


@app.route("/chatbot")
def chatbot_page():
    """Page chatbot d accueil AITicketInfo."""
    return send_from_directory(".", "chatbot.html")



# ─── PAGES HTML STATIQUES ────────────────
@app.route("/recensement")
def recensement_page():
    return send_from_directory(".", "recensement.html")

@app.route("/presentation")
def presentation_page():
    return send_from_directory(".", "presentation-aiticketinfo.html")

@app.route("/resume-apis")
def resume_apis_page():
    return send_from_directory(".", "resume-apis-agents-aiticketinfo.html")

@app.route("/plan-execution")
def plan_execution_page():
    return send_from_directory(".", "plan-execution-interne-aiticketinfo.html")

@app.route("/email-pitch")
def email_pitch_page():
    return send_from_directory(".", "email-pitch-aiticketinfo.html")


# ─── RECENSEMENT DES STATS (anomalies pre-calculees) ───
@app.route("/api/recensement")
def api_recensement():
    """Dashboard des anomalies statistiques detectees."""
    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur = conn.cursor()

        # Stats globales
        cur.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN severity = 'high' THEN 1 ELSE 0 END),
                SUM(CASE WHEN severity = 'medium' THEN 1 ELSE 0 END),
                SUM(CASE WHEN severity = 'low' THEN 1 ELSE 0 END)
            FROM recensement_stats WHERE is_active = TRUE
        """)
        row = cur.fetchone()
        total, high, medium, low = row[0] or 0, row[1] or 0, row[2] or 0, row[3] or 0

        # Dernier run
        cur.execute("""
            SELECT batch_id, completed_at, anomalies_computed, duration_seconds
            FROM recensement_runs WHERE status = 'completed'
            ORDER BY completed_at DESC LIMIT 1
        """)
        last_run = cur.fetchone()

        # Top zones (lieux avec le plus d'anomalies high) + nom municipalite
        cur.execute("""
            SELECT r.region, COUNT(*) AS nb,
                SUM(CASE WHEN r.severity = 'high' THEN 1 ELSE 0 END) AS nb_high,
                m.nom_municipalite, m.mrc, m.region_admin, m.population
            FROM recensement_stats r
            LEFT JOIN municipalites_qc m ON m.code_geo = r.region
            WHERE r.is_active = TRUE AND r.region IS NOT NULL
            GROUP BY r.region, m.nom_municipalite, m.mrc, m.region_admin, m.population
            ORDER BY nb_high DESC, nb DESC
            LIMIT 10
        """)
        top_zones = [{
            "region": r[0], "total": r[1], "high": r[2],
            "nom_municipalite": r[3], "mrc": r[4],
            "region_admin": r[5], "population": r[6]
        } for r in cur.fetchall()]

        # Top articles (acquittement ou surrepresentes)
        cur.execute("""
            SELECT article, anomaly_type, observed_value, expected_value, z_score, severity
            FROM recensement_stats
            WHERE is_active = TRUE AND article IS NOT NULL
            ORDER BY CASE severity WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, z_score DESC
            LIMIT 10
        """)
        top_articles = [{
            "article": r[0], "type": r[1],
            "observed": float(r[2]) if r[2] else None,
            "expected": float(r[3]) if r[3] else None,
            "z_score": float(r[4]) if r[4] else None,
            "severity": r[5]
        } for r in cur.fetchall()]

        # Anomalies recentes (les plus severes) + nom municipalite
        cur.execute("""
            SELECT r.anomaly_type, r.region, r.article, r.deviation_pct, r.z_score,
                   r.severity, r.defense_text_fr, r.sample_size,
                   m.nom_municipalite
            FROM recensement_stats r
            LEFT JOIN municipalites_qc m ON m.code_geo = r.region
            WHERE r.is_active = TRUE
            ORDER BY CASE r.severity WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                     r.z_score DESC
            LIMIT 100
        """)
        recent = [{
            "type": r[0], "region": r[1], "article": r[2],
            "deviation_pct": float(r[3]) if r[3] else None,
            "z_score": float(r[4]) if r[4] else None,
            "severity": r[5], "defense_text": r[6], "sample_size": r[7],
            "nom_municipalite": r[8]
        } for r in cur.fetchall()]

        # Distribution par type
        cur.execute("""
            SELECT anomaly_type, COUNT(*) FROM recensement_stats
            WHERE is_active = TRUE GROUP BY anomaly_type ORDER BY COUNT(*) DESC
        """)
        by_type = {r[0]: r[1] for r in cur.fetchall()}

        conn.close()

        return jsonify({
            "total_anomalies": total,
            "high": high, "medium": medium, "low": low,
            "last_computed": last_run[1].isoformat() if last_run and last_run[1] else None,
            "last_batch": str(last_run[0])[:8] if last_run else None,
            "last_duration_s": last_run[3] if last_run else None,
            "by_type": by_type,
            "top_zones": top_zones,
            "top_articles": top_articles,
            "recent_anomalies": recent,
            "anomalies": recent,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/recensement/match")
def api_recensement_match():
    """Match un ticket specifique contre les anomalies."""
    region = request.args.get("municipality") or request.args.get("region") or request.args.get("lieu")
    article = request.args.get("article")

    if not region and not article:
        return jsonify({"error": "Parametre 'municipality' ou 'article' requis"}), 400

    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur = conn.cursor()

        conditions = ["is_active = TRUE"]
        params = []

        if region:
            conditions.append("(region = %s OR region IS NULL)")
            params.append(region)
        if article:
            conditions.append("(article = %s OR article IS NULL)")
            params.append(article)

        where = " AND ".join(conditions)
        cur.execute(f"""
            SELECT anomaly_type, region, article, deviation_pct, z_score,
                   severity, confidence_level, defense_text_fr, legal_reference, sample_size
            FROM recensement_stats
            WHERE {where}
            ORDER BY CASE severity WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                     z_score DESC
            LIMIT 20
        """, params)

        anomalies = [{
            "type": r[0], "region": r[1], "article": r[2],
            "deviation_pct": float(r[3]) if r[3] else None,
            "z_score": float(r[4]) if r[4] else None,
            "severity": r[5], "confidence": r[6],
            "defense_text": r[7], "legal_reference": r[8], "sample_size": r[9]
        } for r in cur.fetchall()]

        nb_high = sum(1 for a in anomalies if a["severity"] == "high")
        defense_texts = [a["defense_text"] for a in anomalies if a["severity"] in ("high", "medium")]

        conn.close()

        return jsonify({
            "anomalies": anomalies,
            "nb_anomalies": len(anomalies),
            "nb_high": nb_high,
            "defense_texts": defense_texts[:10],
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/recensement/details")
def api_recensement_details():
    """Toutes les anomalies avec details enrichis + stats croisees constats."""
    severity_filter = request.args.get("severity")
    type_filter = request.args.get("type")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))
    offset = (page - 1) * per_page

    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur = conn.cursor()

        conditions = ["r.is_active = TRUE"]
        params = []
        if severity_filter:
            conditions.append("r.severity = %s")
            params.append(severity_filter)
        if type_filter:
            conditions.append("r.anomaly_type = %s")
            params.append(type_filter)

        where = " AND ".join(conditions)

        # Count total
        cur.execute(f"SELECT COUNT(*) FROM recensement_stats r WHERE {where}", params)
        total_count = cur.fetchone()[0]

        # Anomalies avec details + nom municipalite
        cur.execute(f"""
            SELECT r.id, r.anomaly_type, r.region, r.article,
                   r.observed_value, r.expected_value, r.deviation_pct, r.z_score,
                   r.severity, r.confidence_level, r.defense_text_fr, r.legal_reference,
                   r.computation_details, r.sample_size, r.period_start, r.period_end,
                   r.created_at,
                   m.nom_municipalite, m.mrc, m.region_admin, m.population
            FROM recensement_stats r
            LEFT JOIN municipalites_qc m ON m.code_geo = r.region
            WHERE {where}
            ORDER BY
                CASE r.severity WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                r.z_score DESC
            LIMIT %s OFFSET %s
        """, params + [per_page, offset])

        anomalies = []
        for row in cur.fetchall():
            a = {
                "id": row[0], "type": row[1], "region": row[2], "article": row[3],
                "observed": float(row[4]) if row[4] else None,
                "expected": float(row[5]) if row[5] else None,
                "deviation_pct": float(row[6]) if row[6] else None,
                "z_score": float(row[7]) if row[7] else None,
                "severity": row[8], "confidence": row[9],
                "defense_text": row[10], "legal_ref": row[11],
                "details": row[12], "sample_size": row[13],
                "period_start": row[14].isoformat() if row[14] else None,
                "period_end": row[15].isoformat() if row[15] else None,
                "created": row[16].isoformat() if row[16] else None,
                "nom_municipalite": row[17], "mrc": row[18],
                "region_admin": row[19], "population": row[20],
                "constats_info": None,
            }

            # Enrichir avec donnees constats si region disponible
            if a["region"]:
                cur.execute("""
                    SELECT
                        COUNT(*) AS total,
                        MIN(date_infraction) AS first_date,
                        MAX(date_infraction) AS last_date,
                        COUNT(DISTINCT article) AS nb_articles,
                        MODE() WITHIN GROUP (ORDER BY description_infraction) AS top_desc,
                        MODE() WITHIN GROUP (ORDER BY loi) AS top_loi,
                        MODE() WITHIN GROUP (ORDER BY type_intervention) AS top_interv,
                        AVG(montant_amende) AS avg_amende,
                        AVG(points_inaptitude) AS avg_points,
                        SUM(CASE WHEN vitesse_constatee IS NOT NULL THEN 1 ELSE 0 END) AS nb_vitesse
                    FROM qc_constats_infraction
                    WHERE lieu_infraction = %s
                """, (a["region"],))
                ci = cur.fetchone()
                if ci and ci[0] > 0:
                    a["constats_info"] = {
                        "total_constats": ci[0],
                        "premiere_date": ci[1].isoformat() if ci[1] else None,
                        "derniere_date": ci[2].isoformat() if ci[2] else None,
                        "nb_articles_distincts": ci[3],
                        "description_freq": ci[4],
                        "loi_freq": ci[5],
                        "type_intervention_freq": ci[6],
                        "amende_moyenne": round(float(ci[7]), 2) if ci[7] else None,
                        "points_moyens": round(float(ci[8]), 1) if ci[8] else None,
                        "nb_avec_vitesse": ci[9],
                    }

            anomalies.append(a)

        # Stats DB globales
        cur.execute("SELECT COUNT(*) FROM qc_constats_infraction")
        total_constats = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM jurisprudence WHERE est_ticket_related = TRUE")
        total_juris = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM qc_radar_photo_lieux WHERE actif = TRUE")
        total_radars = cur.fetchone()[0]

        conn.close()

        return jsonify({
            "anomalies": anomalies,
            "total": total_count,
            "page": page, "per_page": per_page,
            "total_pages": (total_count + per_page - 1) // per_page,
            "db_stats": {
                "total_constats": total_constats,
                "total_jurisprudence": total_juris,
                "total_radars_actifs": total_radars,
            }
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ══════════════════════════════════════════════════════════════
#  BLITZ — Événements de blitz policiers détectés
# ══════════════════════════════════════════════════════════════
@app.route("/api/blitz")
def api_blitz():
    """Retourne les blitz quotidiens détectés (anomaly_type = blitz_daily)."""
    municipality = request.args.get("municipality")
    severity = request.args.get("severity")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))
    offset = (page - 1) * per_page

    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur = conn.cursor()

        conditions = ["r.is_active = TRUE", "r.anomaly_type = 'blitz_daily'"]
        params = []
        if municipality:
            conditions.append("(r.region = %s OR m.nom_municipalite ILIKE %s)")
            params.extend([municipality, f"%{municipality}%"])
        if severity:
            conditions.append("r.severity = %s")
            params.append(severity)

        where = " AND ".join(conditions)

        # Count
        cur.execute(f"""
            SELECT COUNT(*) FROM recensement_stats r
            LEFT JOIN municipalites_qc m ON m.code_geo = r.region
            WHERE {where}
        """, params)
        total = cur.fetchone()[0]

        # Stats
        cur.execute(f"""
            SELECT
                COUNT(*) FILTER (WHERE r.severity = 'high') AS high,
                COUNT(*) FILTER (WHERE r.severity = 'medium') AS medium,
                COUNT(*) FILTER (WHERE r.severity = 'low') AS low,
                AVG(r.observed_value) AS avg_constats,
                MAX(r.observed_value) AS max_constats,
                AVG(r.z_score) AS avg_z
            FROM recensement_stats r
            LEFT JOIN municipalites_qc m ON m.code_geo = r.region
            WHERE {where}
        """, params)
        stats = cur.fetchone()

        # Blitz events
        cur.execute(f"""
            SELECT r.id, r.region, r.observed_value, r.expected_value,
                   r.deviation_pct, r.z_score, r.severity, r.defense_text_fr,
                   r.computation_details, r.sample_size, r.created_at,
                   m.nom_municipalite, m.mrc, m.region_admin
            FROM recensement_stats r
            LEFT JOIN municipalites_qc m ON m.code_geo = r.region
            WHERE {where}
            ORDER BY r.observed_value DESC
            LIMIT %s OFFSET %s
        """, params + [per_page, offset])

        events = []
        for row in cur.fetchall():
            details = row[8] if row[8] else {}
            events.append({
                "id": row[0], "lieu": row[1],
                "nb_constats": float(row[2]) if row[2] else 0,
                "avg_daily": float(row[3]) if row[3] else 0,
                "deviation_pct": float(row[4]) if row[4] else 0,
                "z_score": float(row[5]) if row[5] else 0,
                "severity": row[6],
                "defense_text": row[7],
                "date": details.get("date"),
                "jour": details.get("jour"),
                "nom_municipalite": row[11] or details.get("nom_municipalite", row[1]),
                "mrc": row[12], "region_admin": row[13],
                "ratio": details.get("ratio", 0),
                "blitz_type": details.get("blitz_type", "standard"),
                "consecutive_days": details.get("consecutive_days", 1),
                "blitz_group_id": details.get("blitz_group_id"),
            })

        conn.close()
        return jsonify({
            "total": total,
            "stats": {
                "high": stats[0] or 0, "medium": stats[1] or 0, "low": stats[2] or 0,
                "avg_constats": round(float(stats[3]), 1) if stats[3] else 0,
                "max_constats": float(stats[4]) if stats[4] else 0,
                "avg_z_score": round(float(stats[5]), 1) if stats[5] else 0,
            },
            "blitz_events": events,
            "page": page, "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page if total > 0 else 0,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ══════════════════════════════════════════════════════════════
#  DAY PATTERNS — Distribution jour de semaine par municipalité
# ══════════════════════════════════════════════════════════════
@app.route("/api/day-patterns")
def api_day_patterns():
    """Retourne les patterns jour de semaine anormaux (anomaly_type = pattern_jour_semaine)."""
    municipality = request.args.get("municipality")
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))
    offset = (page - 1) * per_page

    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur = conn.cursor()

        conditions = ["r.is_active = TRUE", "r.anomaly_type = 'pattern_jour_semaine'"]
        params = []
        if municipality:
            conditions.append("(r.region = %s OR m.nom_municipalite ILIKE %s)")
            params.extend([municipality, f"%{municipality}%"])

        where = " AND ".join(conditions)

        cur.execute(f"""
            SELECT COUNT(*) FROM recensement_stats r
            LEFT JOIN municipalites_qc m ON m.code_geo = r.region
            WHERE {where}
        """, params)
        total = cur.fetchone()[0]

        cur.execute(f"""
            SELECT r.id, r.region, r.observed_value, r.expected_value,
                   r.deviation_pct, r.z_score, r.severity, r.defense_text_fr,
                   r.computation_details, r.sample_size, r.created_at,
                   m.nom_municipalite, m.region_admin
            FROM recensement_stats r
            LEFT JOIN municipalites_qc m ON m.code_geo = r.region
            WHERE {where}
            ORDER BY ABS(r.z_score) DESC
            LIMIT %s OFFSET %s
        """, params + [per_page, offset])

        patterns = []
        for row in cur.fetchall():
            details = row[8] if row[8] else {}
            patterns.append({
                "id": row[0], "lieu": row[1],
                "nom_municipalite": row[11] or row[1],
                "region_admin": row[12],
                "jour_pic": details.get("jour_pic"),
                "pattern_type": details.get("pattern_type"),
                "pct_jour_pic": float(row[2]) if row[2] else 0,
                "pct_attendu": float(row[3]) if row[3] else 14.29,
                "z_score": float(row[5]) if row[5] else 0,
                "severity": row[6],
                "defense_text": row[7],
                "total_constats": row[9],
                "distribution": details.get("distribution", {}),
            })

        # Global day-of-week distribution (province-wide)
        cur.execute("""
            SELECT EXTRACT(DOW FROM date_infraction)::int AS dow, COUNT(*) AS nb
            FROM qc_constats_infraction
            WHERE date_infraction IS NOT NULL
            GROUP BY dow ORDER BY dow
        """)
        global_dow = {}
        jours = {0: 'Dimanche', 1: 'Lundi', 2: 'Mardi', 3: 'Mercredi',
                 4: 'Jeudi', 5: 'Vendredi', 6: 'Samedi'}
        total_global = 0
        for dow, nb in cur.fetchall():
            global_dow[jours[dow]] = nb
            total_global += nb

        conn.close()
        return jsonify({
            "total": total,
            "patterns": patterns,
            "global_distribution": {k: {"nb": v, "pct": round(v / total_global * 100, 2)} for k, v in global_dow.items()} if total_global > 0 else {},
            "page": page, "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page if total > 0 else 0,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ══════════════════════════════════════════════════════════════
#  OCR STATS — Statistiques des tickets scannés (matricules, rues, etc.)
# ══════════════════════════════════════════════════════════════
@app.route("/api/ocr-stats")
def api_ocr_stats():
    """Retourne les stats agrégées des tickets scannés par les clients (matricule, rue, etc.)."""
    try:
        conn = psycopg2.connect(**PG_CONFIG)
        cur = conn.cursor()

        # Check if table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'tickets_scannes_meta'
            )
        """)
        if not cur.fetchone()[0]:
            conn.close()
            return jsonify({
                "total_scans": 0,
                "message": "Table tickets_scannes_meta pas encore créée. Exécuter la migration.",
                "top_matricules": [], "top_rues": [], "top_corps": [],
            })

        cur.execute("SELECT COUNT(*) FROM tickets_scannes_meta")
        total = cur.fetchone()[0]

        if total == 0:
            conn.close()
            return jsonify({
                "total_scans": 0,
                "message": "Aucun ticket scanné encore. Les données s'accumulent au fil des scans clients.",
                "top_matricules": [], "top_rues": [], "top_corps": [],
            })

        # Top matricules
        cur.execute("""
            SELECT matricule_policier, corps_policier, COUNT(*) AS nb
            FROM tickets_scannes_meta
            WHERE matricule_policier IS NOT NULL AND matricule_policier != ''
            GROUP BY matricule_policier, corps_policier
            ORDER BY nb DESC LIMIT 20
        """)
        top_mat = [{"matricule": r[0], "corps": r[1], "nb_tickets": r[2]} for r in cur.fetchall()]

        # Top rues
        cur.execute("""
            SELECT rue_exacte, ville, COUNT(*) AS nb
            FROM tickets_scannes_meta
            WHERE rue_exacte IS NOT NULL AND rue_exacte != ''
            GROUP BY rue_exacte, ville
            ORDER BY nb DESC LIMIT 20
        """)
        top_rues = [{"rue": r[0], "ville": r[1], "nb_tickets": r[2]} for r in cur.fetchall()]

        # Top corps policiers
        cur.execute("""
            SELECT corps_policier, COUNT(*) AS nb
            FROM tickets_scannes_meta
            WHERE corps_policier IS NOT NULL AND corps_policier != ''
            GROUP BY corps_policier
            ORDER BY nb DESC LIMIT 10
        """)
        top_corps = [{"corps": r[0], "nb_tickets": r[1]} for r in cur.fetchall()]

        conn.close()
        return jsonify({
            "total_scans": total,
            "top_matricules": top_mat,
            "top_rues": top_rues,
            "top_corps": top_corps,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Init auth tables + routes
if _auth_available:
    try:
        init_auth_tables()
        register_auth_routes(app)
        print("[AUTH] Routes auth enregistrees")
    except Exception as e:
        print(f"[AUTH] Erreur init: {e}")


# ═══════════════════════════════════════════════════════
# PAGES — Login / Register / Dashboard Client
# ═══════════════════════════════════════════════════════

@app.route("/login")
def page_login():
    return send_file("templates/login.html")

@app.route("/register")
def page_register():
    return send_file("templates/register.html")

@app.route("/dashboard")
def page_dashboard():
    return send_file("templates/dashboard_client.html")



# ================================================================
# HYBRID SEARCH RRF — Reciprocal Rank Fusion (FTS + pgvector)
# ================================================================

@app.route("/api/hybrid-search")
def api_hybrid_search_rrf():
    """
    Recherche hybride RRF: combine FTS tsvector + pgvector semantic.
    Params: q (required), limit (default 20, max 50), province (QC/ON), ticket_only (default true)
    Retourne resultats fusionnes avec score RRF + stats de provenance.
    """
    query = request.args.get("q", "").strip()
    limit = min(int(request.args.get("limit", "20")), 50)
    province = request.args.get("province", None)
    ticket_only = request.args.get("ticket_only", "true").lower() != "false"

    if not query or len(query) < 2:
        return jsonify({"error": "Parametre q requis (min 2 chars)"}), 400

    try:
        from embedding_service import embedding_service as es
        result = es.hybrid_search_rrf(
            query=query,
            top_k=limit,
            province=province,
            ticket_only=ticket_only
        )

        return jsonify({
            "query": query,
            "province": province,
            "ticket_only": ticket_only,
            "count": result["stats"]["total"],
            "time_ms": result["stats"]["time_ms"],
            "fusion": "RRF (k=60)",
            "stats": result["stats"],
            "results": result["results"],
        })
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()[-500:]}), 500


if __name__ == "__main__":
    print("FightMyTicket API v2 — 27 agents — http://0.0.0.0:8912")
    app.run(host="0.0.0.0", port=8912, debug=False)
