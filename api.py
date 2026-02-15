#!/usr/bin/env python3
"""
FightMyTicket — API Flask v2
Pipeline 27 agents / 4 phases / upload fichiers / PDF rapport
Port: 8912 (nginx proxy sur 8911)
"""

import json
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
            "rapport_client": rapport.get("phases", {}).get("livraison", {}).get("rapport_client"),
            "procedure": rapport.get("phases", {}).get("analyse", {}).get("procedure"),
            "points": rapport.get("phases", {}).get("analyse", {}).get("points"),
            "supervision": rapport.get("phases", {}).get("livraison", {}).get("supervision"),
            "precedents_trouves": rapport.get("phases", {}).get("analyse", {}).get("precedents", {}).get("nb", 0) if isinstance(rapport.get("phases", {}).get("analyse", {}).get("precedents"), dict) else 0,
            "lois_trouvees": rapport.get("phases", {}).get("analyse", {}).get("lois", {}).get("nb", 0) if isinstance(rapport.get("phases", {}).get("analyse", {}).get("lois"), dict) else 0,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
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
        return jsonify({"status": "error", "error": str(e)}), 500


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
            return jsonify({"error": "Dossier non trouve"}), 404

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

        return jsonify({
            "success": result.get("email", {}).get("sent", False),
            "status": result.get("email", {}).get("status", "?"),
            "dossier_uuid": dossier_uuid,
            "email": email
        })
    except Exception as e:
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

        conn.close()

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
        if nb_no_embed > 100:
            alertes.append({"level": "warning", "msg": f"{nb_no_embed} dossiers sans embedding ({embed_pct}% complete)"})
        if nb_juris_total < 500:
            alertes.append({"level": "warning", "msg": f"Jurisprudence faible: {nb_juris_total} dossiers"})
        remaining = canlii_quota.get("remaining", 5000)
        if isinstance(remaining, int) and remaining <= 0:
            alertes.append({"level": "warning", "msg": "Quota CanLII epuise pour aujourd'hui"})
        if isinstance(remaining, int) and remaining <= 500 and remaining > 0:
            alertes.append({"level": "info", "msg": f"Quota CanLII bas: {remaining} restant"})
        if analyses_stats["total"] == 0:
            alertes.append({"level": "info", "msg": "Aucune analyse effectuee encore"})
        if nb_embedded == nb_juris_total and nb_juris_total > 0:
            alertes.append({"level": "info", "msg": f"Embeddings 100% complets ({nb_embedded} dossiers)"})

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
            "cron": {
                "import": "0 1 * * * — Import CanLII 4800 req",
                "embeddings": "30 1 * * * — Populate embeddings nouveaux"
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


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



if __name__ == "__main__":
    print("FightMyTicket API v2 — 27 agents — http://0.0.0.0:8912")
    app.run(host="0.0.0.0", port=8912, debug=False)
