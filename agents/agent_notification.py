"""
Agent Phase 4: NOTIFICATION — SMS + Email automatiques
SendGrid (production) ou SMTP fallback (test)
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

# SMTP fallback (test sans SendGrid)
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "")


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

        # Email: SendGrid (prod) -> SMTP fallback (test)
        if email and SENDGRID_KEY:
            results["email"] = self._envoyer_email_sendgrid(email, dossier_id, resume, verdict)
        elif email and SMTP_USER:
            results["email"] = self._envoyer_email_smtp(email, dossier_id, resume, verdict)
        elif email:
            results["email"] = {"sent": False, "status": "Aucun service email configure (SENDGRID_KEY ou SMTP_USER)"}
            self.log("Email: aucun service configure", "WARN")
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
                body=f"[Ticket911] Dossier #{dossier_id}: {message[:140]}",
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

    def _envoyer_email_sendgrid(self, email, dossier_id, resume, verdict):
        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail

            sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_KEY)
            message = Mail(
                from_email="noreply@ticket911.ca",
                to_emails=email,
                subject=f"[Ticket911] Votre analyse #{dossier_id} est prete",
                html_content=self._build_email_html(dossier_id, resume, verdict)
            )
            response = sg.send(message)
            self.log(f"Email SendGrid envoye: {response.status_code}", "OK")
            return {"sent": True, "status": "Envoye (SendGrid)", "code": response.status_code}
        except ImportError:
            return {"sent": False, "status": "Module sendgrid non installe"}
        except Exception as e:
            self.log(f"Erreur SendGrid: {e}", "FAIL")
            return {"sent": False, "status": f"Erreur: {str(e)[:100]}"}

    def _envoyer_email_smtp(self, email, dossier_id, resume, verdict):
        """Fallback SMTP — fonctionne avec Gmail, OVH, ou n'importe quel serveur SMTP"""
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[Ticket911] Votre analyse #{dossier_id} est prete"
            msg["From"] = SMTP_FROM or SMTP_USER
            msg["To"] = email

            html = self._build_email_html(dossier_id, resume, verdict)
            msg.attach(MIMEText(html, "html", "utf-8"))

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.ehlo()
                if SMTP_PORT == 587:
                    server.starttls()
                    server.ehlo()
                server.login(SMTP_USER, SMTP_PASS)
                server.sendmail(SMTP_FROM or SMTP_USER, email, msg.as_string())

            self.log(f"Email SMTP envoye a {email}", "OK")
            return {"sent": True, "status": f"Envoye (SMTP {SMTP_HOST})"}
        except Exception as e:
            self.log(f"Erreur SMTP: {e}", "FAIL")
            return {"sent": False, "status": f"Erreur SMTP: {str(e)[:100]}"}

    def _build_email_html(self, dossier_id, resume, verdict):
        return f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #1e3a5f; color: white; padding: 20px; text-align: center;">
                <h1 style="margin: 0;">TICKET911</h1>
                <p style="margin: 5px 0 0;">Votre analyse est prete</p>
            </div>
            <div style="padding: 20px; background: #f8f9fa;">
                <p><strong>Dossier:</strong> #{dossier_id}</p>
                <div style="background: white; border-radius: 8px; padding: 15px; margin: 15px 0;
                            border-left: 4px solid #e63946;">
                    <h3 style="color: #1e3a5f; margin-top: 0;">Resume</h3>
                    <p>{resume}</p>
                </div>
                <div style="background: white; border-radius: 8px; padding: 15px; margin: 15px 0;
                            border-left: 4px solid #27ae60;">
                    <h3 style="color: #1e3a5f; margin-top: 0;">Verdict</h3>
                    <p><strong>{verdict}</strong></p>
                </div>
                <p style="text-align: center; margin-top: 20px;">
                    <a href="https://seoparai.com/scanticket"
                       style="background: #e63946; color: white; padding: 12px 30px;
                              text-decoration: none; border-radius: 5px; font-weight: bold;">
                        Voir le rapport complet
                    </a>
                </p>
            </div>
            <div style="text-align: center; padding: 15px; color: #999; font-size: 12px;">
                <p>Ticket911 par SeoAI | ticket911.ca</p>
                <p>Ce courriel a ete genere automatiquement par notre systeme d'analyse IA.</p>
            </div>
        </div>"""
