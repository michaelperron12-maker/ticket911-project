#!/usr/bin/env python3
"""
TICKET911 — API Flask v2
Pipeline 26 agents / 4 phases / upload fichiers / PDF rapport
Port: 8912 (nginx proxy sur 8911)
"""

import json
import time
import os
import uuid
import sqlite3
import hashlib
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, send_file, abort
from flask_cors import CORS
from werkzeug.utils import secure_filename

import sys
sys.path.insert(0, "/var/www/ticket911")
from agents.orchestrateur import Orchestrateur
from agents.base_agent import DB_PATH, DATA_DIR

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
    return send_from_directory("web", "index.html")


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


# ─── ANALYSE COMPLETE (26 agents) ─────────────
@app.route("/api/analyze", methods=["POST"])
def analyze():
    """Analyse complete — pipeline 26 agents / 4 phases"""
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

    if not ticket.get("infraction"):
        return jsonify({"error": "Champ 'infraction' requis"}), 400

    try:
        orch = get_orchestrateur()
        rapport = orch.analyser_ticket(
            ticket, image_path=image_path, client_info=client_info,
            evidence_photos=evidence_photos if evidence_photos else None,
            temoignage=temoignage if temoignage else None,
            temoins=temoins if temoins else None)

        dossier_uuid = rapport.get("dossier_uuid", "")

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
            "analyse": rapport.get("phases", {}).get("analyse", {}).get("analyste", {}).get("analyse") if isinstance(rapport.get("phases", {}).get("analyse", {}).get("analyste"), dict) else None,
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
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""SELECT ticket_json, analyse_json, rapport_client_json,
                            rapport_avocat_json, procedure_json, points_json,
                            lois_json, precedents_json, cross_verification_json,
                            supervision_json, score_final, confiance, recommandation,
                            juridiction, temps_total, created_at
                     FROM analyses_completes WHERE dossier_uuid = ?""", (dossier_uuid,))
        row = c.fetchone()
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
                             download_name=f"Ticket911-{dossier_uuid}.pdf")
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
        pdf_path = os.path.join(RAPPORT_DIR, f"Ticket911-{data['dossier_uuid']}.pdf")
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
    @page {{ size: A4; margin: 2cm; }}
    body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color: #1e3a5f; font-size: 11pt; line-height: 1.5; }}
    h1 {{ color: #1e3a5f; font-size: 22pt; border-bottom: 3px solid #e63946; padding-bottom: 8px; }}
    h2 {{ color: #1e3a5f; font-size: 14pt; border-bottom: 2px solid #d4a843; padding-bottom: 4px; margin-top: 20px; }}
    h3 {{ color: #e63946; font-size: 12pt; }}
    .header {{ text-align: center; margin-bottom: 30px; }}
    .header img {{ max-width: 200px; }}
    .score-box {{ background: {score_color}; color: white; padding: 15px 25px; border-radius: 10px;
                   display: inline-block; font-size: 24pt; font-weight: bold; }}
    .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 15px 0; }}
    .info-item {{ background: #f8f9fa; padding: 8px 12px; border-radius: 5px; }}
    .info-label {{ font-weight: bold; color: #666; font-size: 9pt; text-transform: uppercase; }}
    table {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 10pt; }}
    th {{ background: #1e3a5f; color: white; padding: 8px; text-align: left; }}
    td {{ padding: 6px 8px; border-bottom: 1px solid #eee; }}
    tr:nth-child(even) {{ background: #f8f9fa; }}
    .reco-box {{ background: #e8f5e9; border-left: 4px solid #27ae60; padding: 12px; margin: 15px 0; }}
    .warn-box {{ background: #fff3e0; border-left: 4px solid #f39c12; padding: 12px; margin: 15px 0; }}
    .page-break {{ page-break-before: always; }}
    .footer {{ text-align: center; color: #999; font-size: 8pt; margin-top: 30px;
               border-top: 1px solid #ddd; padding-top: 8px; }}
    ul {{ padding-left: 20px; }}
    li {{ margin-bottom: 5px; }}
    .eco-total {{ font-size: 18pt; color: #27ae60; font-weight: bold; }}
</style>
</head>
<body>

<!-- PAGE 1: Couverture -->
<div class="header">
    <h1>TICKET911</h1>
    <p style="font-size: 14pt; color: #666;">Rapport d'analyse juridique par intelligence artificielle</p>
    <p style="font-size: 11pt;">Dossier <strong>#{uuid_str}</strong> | {date_str} | {juridiction}</p>
    <div style="margin: 20px 0;">
        <div class="score-box">{score}%</div>
        <p style="font-size: 10pt; color: #666;">Score de contestation</p>
    </div>
</div>

<div class="info-grid">
    <div class="info-item"><span class="info-label">Infraction</span><br>{ticket.get('infraction', '?')}</div>
    <div class="info-item"><span class="info-label">Juridiction</span><br>{juridiction}</div>
    <div class="info-item"><span class="info-label">Amende</span><br>{ticket.get('amende', '?')}</div>
    <div class="info-item"><span class="info-label">Points</span><br>{ticket.get('points_inaptitude', 0)}</div>
    <div class="info-item"><span class="info-label">Lieu</span><br>{ticket.get('lieu', '?')}</div>
    <div class="info-item"><span class="info-label">Date</span><br>{ticket.get('date', '?')}</div>
    <div class="info-item"><span class="info-label">Recommandation</span><br><strong>{reco.upper()}</strong></div>
    <div class="info-item"><span class="info-label">Confiance</span><br>{confiance}%</div>
</div>

<div class="reco-box">
    <h3>Verdict</h3>
    <p>{rapport_client.get('verdict', reco)}</p>
</div>

<!-- PAGE 2: Resume client -->
<div class="page-break"></div>
<h1>Resume pour le client</h1>
<p>{rapport_client.get('resume', 'Analyse en cours...')}</p>

<h2>Prochaines etapes</h2>
<ol>{etapes_client_html}</ol>

{f'<div class="warn-box"><strong>Attention:</strong> {rapport_client.get("attention", "")}</div>' if rapport_client.get("attention") else ""}

<h2>Economie potentielle</h2>
<p class="eco-total">${eco.get('total', 0):,}</p>
<div class="info-grid">
    <div class="info-item"><span class="info-label">Amende</span><br>${eco.get('amende', 0)}</div>
    <div class="info-item"><span class="info-label">Assurance (3 ans)</span><br>${eco.get('assurance_3ans', eco.get('cout_supplementaire_3ans', 0)):,}</div>
</div>

<!-- PAGE 3: Arguments de defense -->
<div class="page-break"></div>
<h1>Arguments de defense</h1>
<ol>{args_html}</ol>

<h2>Strategie recommandee</h2>
<p>{analyse.get('strategie', analyse.get('explication', ''))}</p>

<!-- PAGE 4: Lois applicables -->
<div class="page-break"></div>
<h1>Lois applicables</h1>
<table>
    <tr><th>Article</th><th>Juridiction</th><th>Texte</th></tr>
    {lois_html}
</table>

<!-- PAGE 5: Jurisprudence -->
<div class="page-break"></div>
<h1>Jurisprudence pertinente</h1>
<p>{len(precedents)} decisions analysees</p>
<table>
    <tr><th>Citation</th><th>Tribunal</th><th>Date</th><th>Resultat</th><th>Pertinence</th></tr>
    {prec_html}
</table>

<!-- PAGE 6: Procedure -->
<div class="page-break"></div>
<h1>Procedure judiciaire</h1>
<div class="info-grid">
    <div class="info-item"><span class="info-label">Tribunal</span><br>{procedure.get('tribunal', '?') if procedure else '?'}</div>
    <div class="info-item"><span class="info-label">Jours restants</span><br>{procedure.get('jours_restants', '?') if procedure else '?'}</div>
</div>
<h2>Etapes</h2>
<ol>{etapes_html}</ol>

<!-- PAGE 7: Points et assurance -->
<div class="page-break"></div>
<h1>Impact points et assurance</h1>
<div class="info-grid">
    <div class="info-item"><span class="info-label">Points</span><br>{points.get('points_demerite', points.get('points_dmv', '?')) if points else '?'}</div>
    <div class="info-item"><span class="info-label">Augmentation assurance</span><br>{points.get('impact_assurance', {}).get('note', '?') if points else '?'}</div>
</div>

<!-- PAGE 8: Rapport technique avocat -->
<div class="page-break"></div>
<h1>Rapport technique (avocat)</h1>
<p><em>{rapport_avocat.get('resume_technique', '')}</em></p>

<h2>Moyens de defense</h2>
<ol>{moyens_html}</ol>

<h2>Faiblesses du dossier</h2>
<ul>{faiblesses_html}</ul>

<h2>Fondement legal</h2>
<p>{rapport_avocat.get('fondement_legal', '')}</p>

<!-- PAGE 9: Certification -->
<div class="page-break"></div>
<h1>Certification du rapport</h1>
<div class="info-grid">
    <div class="info-item"><span class="info-label">Dossier</span><br>#{uuid_str}</div>
    <div class="info-item"><span class="info-label">Date</span><br>{date_str}</div>
    <div class="info-item"><span class="info-label">Score qualite</span><br>{supervision.get('score_qualite', '?')}%</div>
    <div class="info-item"><span class="info-label">Decision</span><br>{supervision.get('decision', '?')}</div>
    <div class="info-item"><span class="info-label">Agents verifies</span><br>{supervision.get('agents_verifies', '?')}</div>
    <div class="info-item"><span class="info-label">Cross-verification</span><br>{cross_verif.get('fiabilite', '?')}</div>
</div>

<div style="margin-top: 40px; text-align: center;">
    <p><strong>Ce rapport a ete genere automatiquement par le systeme Ticket911</strong></p>
    <p>Analyse par 26 agents IA specialises | {len(lois)} articles de loi | {len(precedents)} precedents</p>
    <p style="font-size: 9pt; color: #999;">Ce rapport ne constitue pas un avis juridique. Consultez un avocat pour des conseils personnalises.</p>
</div>

<div class="footer">
    <p>Ticket911 par SeoAI | ticket911.ca | {datetime.now().year}</p>
</div>

</body>
</html>"""


# ─── API ENDPOINTS EXISTANTS ──────────────────
@app.route("/api/health")
def health():
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
            "version": "2.0",
            "agents": 26,
            "jurisprudence": nb_juris,
            "lois": nb_lois,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/stats")
def stats():
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
            "analyses_effectuees": nb_analyses,
            "version": "2.0 (26 agents)"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/results")
def results():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""SELECT id, dossier_uuid, score_final, confiance, recommandation,
                            juridiction, temps_total, created_at
                     FROM analyses_completes ORDER BY id DESC LIMIT 20""")
        rows = c.fetchall()
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
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""SELECT ticket_json, analyse_json, rapport_client_json,
                            rapport_avocat_json, procedure_json, points_json,
                            lois_json, precedents_json, cross_verification_json,
                            supervision_json, score_final, confiance, recommandation,
                            juridiction, temps_total, created_at
                     FROM analyses_completes WHERE dossier_uuid = ?""", (dossier_uuid,))
        row = c.fetchone()
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


if __name__ == "__main__":
    print("TICKET911 API v2 — 26 agents — http://0.0.0.0:8912")
    app.run(host="0.0.0.0", port=8912, debug=False)
