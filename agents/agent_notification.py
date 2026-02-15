"""
Agent Phase 4: NOTIFICATION — Email automatique
OVH SMTP (production) ou localhost SMTP (test)
"""

import time
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from agents.base_agent import BaseAgent

TWILIO_SID = os.environ.get("TWILIO_SID", "")
TWILIO_TOKEN = os.environ.get("TWILIO_TOKEN", "")
TWILIO_FROM = os.environ.get("TWILIO_FROM", "")
SENDGRID_KEY = os.environ.get("SENDGRID_KEY", "")

# SMTP OVH (production)
SMTP_HOST = os.environ.get("SMTP_HOST", "ssl0.ovh.net")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "alert@seoparai.com")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "alert@seoparai.com")

# Localhost SMTP (fallback test — fonctionne sans auth sur OVH VPS)
LOCAL_SMTP = os.environ.get("LOCAL_SMTP", "localhost")
LOCAL_SMTP_PORT = int(os.environ.get("LOCAL_SMTP_PORT", "25"))


class AgentNotification(BaseAgent):

    def __init__(self):
        super().__init__("Notification")

    def notifier(self, dossier_id, client_info, rapport_client):
        """
        Input: ID dossier, info client (email/tel), rapport client
        Output: statut des notifications envoyees
        """
        self.log("Envoi des notifications...", "STEP")
        start = time.time()

        results = {
            "dossier_id": dossier_id,
            "sms": {"sent": False, "status": ""},
            "email": {"sent": False, "status": ""},
        }

        email = client_info.get("email", "")
        phone = client_info.get("phone", "")
        resume = rapport_client.get("resume", "") if rapport_client else ""
        verdict = rapport_client.get("verdict", "") if rapport_client else ""

        # SMS via Twilio
        if phone and TWILIO_SID:
            results["sms"] = self._envoyer_sms(phone, dossier_id, verdict)
        elif phone:
            results["sms"] = {"sent": False, "status": "Twilio non configure"}
            self.log("SMS: Twilio non configure", "WARN")
        else:
            results["sms"] = {"sent": False, "status": "Pas de numero"}

        # Email: SendGrid (prod) -> OVH SMTP (prod) -> localhost SMTP (test)
        if email and SENDGRID_KEY:
            results["email"] = self._envoyer_email_sendgrid(email, dossier_id, resume, verdict, rapport_client)
        elif email and SMTP_PASS:
            results["email"] = self._envoyer_email_smtp(email, dossier_id, resume, verdict, rapport_client)
        elif email:
            results["email"] = self._envoyer_email_local(email, dossier_id, resume, verdict, rapport_client)
        else:
            results["email"] = {"sent": False, "status": "Pas d'adresse email"}

        duration = time.time() - start
        self.log(f"SMS: {results['sms']['status']} | Email: {results['email']['status']}", "OK")
        self.log_run("notifier", f"Dossier {dossier_id}",
                     f"SMS={results['sms']['sent']} Email={results['email']['sent']}", duration=duration)
        return results

    def _envoyer_sms(self, phone, dossier_id, message):
        try:
            from twilio.rest import Client
            client = Client(TWILIO_SID, TWILIO_TOKEN)
            sms = client.messages.create(
                body=f"[FightMyTicket] Dossier #{dossier_id}: {message[:140]}",
                from_=TWILIO_FROM,
                to=phone
            )
            self.log(f"SMS envoye: {sms.sid}", "OK")
            return {"sent": True, "status": "Envoye", "sid": sms.sid}
        except ImportError:
            return {"sent": False, "status": "Module twilio non installe"}
        except Exception as e:
            self.log(f"Erreur SMS: {e}", "FAIL")
            return {"sent": False, "status": f"Erreur: {str(e)[:100]}"}

    def _envoyer_email_sendgrid(self, email, dossier_id, resume, verdict, rapport_client=None):
        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail

            sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_KEY)
            message = Mail(
                from_email="noreply@fightmyticket.ca",
                to_emails=email,
                subject=f"[FightMyTicket] Votre analyse #{dossier_id} est prete",
                html_content=self._build_email_html(dossier_id, resume, verdict, rapport_client)
            )
            response = sg.send(message)
            self.log(f"Email SendGrid envoye: {response.status_code}", "OK")
            return {"sent": True, "status": "Envoye (SendGrid)", "code": response.status_code}
        except ImportError:
            return {"sent": False, "status": "Module sendgrid non installe"}
        except Exception as e:
            self.log(f"Erreur SendGrid: {e}", "FAIL")
            return {"sent": False, "status": f"Erreur: {str(e)[:100]}"}

    def _envoyer_email_smtp(self, email, dossier_id, resume, verdict, rapport_client=None):
        """SMTP OVH — necessite SMTP_PASS"""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[FightMyTicket] Votre analyse #{dossier_id} est prete"
            msg["From"] = SMTP_FROM or SMTP_USER
            msg["To"] = email

            html = self._build_email_html(dossier_id, resume, verdict, rapport_client)
            msg.attach(MIMEText(html, "html", "utf-8"))

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.ehlo()
                if SMTP_PORT == 587:
                    server.starttls()
                    server.ehlo()
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(SMTP_FROM or SMTP_USER, email, msg.as_string())

            self.log(f"Email SMTP OVH envoye a {email}", "OK")
            return {"sent": True, "status": f"Envoye (SMTP {SMTP_HOST})"}
        except Exception as e:
            self.log(f"Erreur SMTP: {e}", "FAIL")
            return {"sent": False, "status": f"Erreur SMTP: {str(e)[:100]}"}

    def _envoyer_email_local(self, email, dossier_id, resume, verdict, rapport_client=None):
        """Localhost SMTP — fonctionne sur OVH VPS sans auth"""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[FightMyTicket] Votre analyse #{dossier_id} est prete"
            msg["From"] = "FightMyTicket <noreply@seoparai.com>"
            msg["To"] = email
            msg["Reply-To"] = "info@seoparai.com"

            html = self._build_email_html(dossier_id, resume, verdict, rapport_client)
            msg.attach(MIMEText(html, "html", "utf-8"))

            with smtplib.SMTP(LOCAL_SMTP, LOCAL_SMTP_PORT, timeout=10) as server:
                server.ehlo("seoparai.com")
                server.sendmail("noreply@seoparai.com", email, msg.as_string())

            self.log(f"Email local envoye a {email}", "OK")
            return {"sent": True, "status": "Envoye (localhost SMTP)"}
        except Exception as e:
            self.log(f"Erreur local SMTP: {e}", "FAIL")
            return {"sent": False, "status": f"Erreur: {str(e)[:100]}"}

    def _build_email_html(self, dossier_id, resume, verdict, rapport_client=None):
        rc = rapport_client or {}
        score = rc.get("score", "")
        economie = rc.get("economie", "")
        attention = rc.get("attention", "")
        etapes = rc.get("prochaines_etapes", [])

        etapes_html = ""
        for e in etapes:
            etapes_html += f'<li style="margin-bottom:8px;">{e}</li>'

        score_html = ""
        if score:
            score_html = f"""
            <div style="text-align:center;margin:20px 0;">
                <div style="display:inline-block;background:#1e3a5f;color:white;
                            border-radius:50%;width:80px;height:80px;line-height:80px;
                            font-size:24px;font-weight:bold;">{score}%</div>
                <p style="color:#666;font-size:12px;margin:5px 0;">Score de contestation</p>
            </div>"""

        attention_html = ""
        if attention:
            attention_html = f"""
            <div style="background:#fff3e0;border-left:4px solid #f39c12;padding:12px;
                        margin:15px 0;border-radius:4px;">
                <strong style="color:#e67e22;">Attention:</strong> {attention}
            </div>"""

        return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f0f2f5;">
<div style="font-family:'Helvetica Neue',Arial,sans-serif;max-width:600px;margin:0 auto;background:white;">

    <div style="background:linear-gradient(135deg,#1e3a5f 0%,#2c5282 100%);color:white;
                padding:30px;text-align:center;">
        <h1 style="margin:0;font-size:28px;letter-spacing:2px;">FIGHTMYTICKET</h1>
        <p style="margin:8px 0 0;font-size:14px;opacity:0.9;">Analyse par intelligence artificielle</p>
        <p style="margin:4px 0 0;font-size:12px;opacity:0.7;">Dossier #{dossier_id}</p>
    </div>

    {score_html}

    <div style="padding:0 25px;">
        <div style="background:#f8f9fa;border-radius:8px;padding:18px;margin:15px 0;
                    border-left:4px solid #e63946;">
            <h3 style="color:#1e3a5f;margin:0 0 10px;font-size:16px;">Resume de votre dossier</h3>
            <p style="color:#333;line-height:1.6;margin:0;">{resume}</p>
        </div>

        <div style="background:#e8f5e9;border-radius:8px;padding:18px;margin:15px 0;
                    border-left:4px solid #27ae60;">
            <h3 style="color:#1b5e20;margin:0 0 10px;font-size:16px;">Notre recommandation</h3>
            <p style="color:#333;font-weight:bold;margin:0;">{verdict}</p>
        </div>

        {attention_html}

        {"<div style='margin:20px 0;'><h3 style=color:#1e3a5f;font-size:16px;>Prochaines etapes</h3><ol style=padding-left:20px;color:#333;line-height:1.8;>" + etapes_html + "</ol></div>" if etapes_html else ""}

        {f"<p style='color:#27ae60;font-weight:bold;font-size:16px;text-align:center;'>{economie}</p>" if economie else ""}

        <div style="text-align:center;margin:25px 0;">
            <a href="https://www.seoparai.com/scanticket/api/rapport/{dossier_id}"
               style="background:#e63946;color:white;padding:14px 35px;text-decoration:none;
                      border-radius:6px;font-weight:bold;font-size:15px;display:inline-block;">
                Telecharger le rapport PDF
            </a>
        </div>
    </div>

    <div style="background:#f8f9fa;padding:20px;text-align:center;border-top:1px solid #eee;">
        <p style="color:#999;font-size:11px;margin:0;">
            FightMyTicket par SeoAI | Analyse par 26 agents IA specialises<br>
            Ce courriel a ete genere automatiquement.<br>
            Ce rapport ne constitue pas un avis juridique.
        </p>
    </div>

</div>
</body>
</html>"""
