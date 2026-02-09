"""
Agent Phase 4: NOTIFICATION — SMS + Email automatiques
Stubs pour Twilio (SMS) et SendGrid (Email) — cles API requises
"""

import time
import os
from agents.base_agent import BaseAgent

TWILIO_SID = os.environ.get("TWILIO_SID", "")
TWILIO_TOKEN = os.environ.get("TWILIO_TOKEN", "")
TWILIO_FROM = os.environ.get("TWILIO_FROM", "")
SENDGRID_KEY = os.environ.get("SENDGRID_KEY", "")


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
            results["sms"] = {"sent": False, "status": "Twilio non configure (cle API manquante)"}
            self.log("SMS: Twilio non configure", "WARN")
        else:
            results["sms"] = {"sent": False, "status": "Pas de numero de telephone"}

        # Email via SendGrid
        if email and SENDGRID_KEY:
            results["email"] = self._envoyer_email(email, dossier_id, resume, verdict)
        elif email:
            results["email"] = {"sent": False, "status": "SendGrid non configure (cle API manquante)"}
            self.log("Email: SendGrid non configure", "WARN")
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

    def _envoyer_email(self, email, dossier_id, resume, verdict):
        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail

            sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_KEY)
            message = Mail(
                from_email="noreply@ticket911.ca",
                to_emails=email,
                subject=f"[Ticket911] Votre analyse #{dossier_id} est prete",
                html_content=f"""
                <h2>Votre analyse Ticket911 est prete</h2>
                <p><strong>Dossier:</strong> #{dossier_id}</p>
                <p><strong>Resume:</strong> {resume}</p>
                <p><strong>Verdict:</strong> {verdict}</p>
                <p>Connectez-vous a votre portail pour voir le rapport complet.</p>
                <p>— Ticket911 par SeoAI</p>
                """
            )
            response = sg.send(message)
            self.log(f"Email envoye: {response.status_code}", "OK")
            return {"sent": True, "status": "Envoye", "code": response.status_code}
        except ImportError:
            return {"sent": False, "status": "Module sendgrid non installe"}
        except Exception as e:
            self.log(f"Erreur email: {e}", "FAIL")
            return {"sent": False, "status": f"Erreur: {str(e)[:100]}"}
