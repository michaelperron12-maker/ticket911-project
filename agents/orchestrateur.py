"""
ORCHESTRATEUR v2 — Pipeline 26 agents / 4 phases / ~1.2M tokens
Phase 1: Intake (~50K tokens) — OCR, Classificateur, Validateur, Routing
Phase 2: Analyse juridique (~650K tokens) — Lois, Precedents, Analyste, Verificateur, Procedure, Points
Phase 3: Audit qualite (~150K tokens) — Cross-verification double moteur
Phase 4: Livraison (~350K tokens) — Rapport Client, Rapport Avocat, Notification, Superviseur
"""

import json
import time
import uuid
import sqlite3
from datetime import datetime
from agents.base_agent import BaseAgent, DB_PATH

# Phase 1: Intake
from agents.agent_ocr import AgentOCR
from agents.agent_classificateur import AgentClassificateur
from agents.agent_validateur import AgentValidateur
from agents.agent_routing import AgentRouting

# Phase 2: Analyse — Lecteur (partage)
from agents.agent_lecteur import AgentLecteur

# Phase 2: Agents QC specifiques
from agents.agent_lois_qc import AgentLoisQC
from agents.agent_precedents_qc import AgentPrecedentsQC
from agents.agent_analyste_qc import AgentAnalysteQC
from agents.agent_procedure_qc import AgentProcedureQC
from agents.agent_points_qc import AgentPointsQC
from agents.agent_verificateur_qc import AgentVerificateurQC

# Phase 2: Agents ON specifiques
from agents.agent_lois_on import AgentLoisON
from agents.agent_precedents_on import AgentPrecedentsON
from agents.agent_analyste_on import AgentAnalysteON
from agents.agent_procedure_on import AgentProcedureON
from agents.agent_points_on import AgentPointsON
from agents.agent_verificateur_on import AgentVerificateurON

# Phase 2: Agents NY specifiques
from agents.agent_lois_ny import AgentLoisNY
from agents.agent_precedents_ny import AgentPrecedentsNY
from agents.agent_analyste_ny import AgentAnalysteNY
from agents.agent_procedure_ny import AgentProcedureNY
from agents.agent_points_ny import AgentPointsNY
from agents.agent_verificateur_ny import AgentVerificateurNY

# Phase 3: Audit
from agents.agent_cross_verification import AgentCrossVerification

# Phase 4: Livraison
from agents.agent_rapport_client import AgentRapportClient
from agents.agent_rapport_avocat import AgentRapportAvocat
from agents.agent_notification import AgentNotification
from agents.agent_superviseur import AgentSuperviseur


class Orchestrateur(BaseAgent):

    def __init__(self):
        super().__init__("Orchestrateur")
        self._init_results_table()

        # Phase 1: Intake (partages)
        self.ocr = AgentOCR()
        self.classificateur = AgentClassificateur()
        self.validateur = AgentValidateur()
        self.routing = AgentRouting()

        # Phase 2: QC
        self.lecteur = AgentLecteur()
        self.lois_qc = AgentLoisQC()
        self.precedents_qc = AgentPrecedentsQC()
        self.analyste_qc = AgentAnalysteQC()
        self.verificateur_qc = AgentVerificateurQC()
        self.procedure_qc = AgentProcedureQC()
        self.points_qc = AgentPointsQC()

        # Phase 2: ON
        self.lois_on = AgentLoisON()
        self.precedents_on = AgentPrecedentsON()
        self.analyste_on = AgentAnalysteON()
        self.verificateur_on = AgentVerificateurON()
        self.procedure_on = AgentProcedureON()
        self.points_on = AgentPointsON()

        # Phase 2: NY
        self.lois_ny = AgentLoisNY()
        self.precedents_ny = AgentPrecedentsNY()
        self.analyste_ny = AgentAnalysteNY()
        self.procedure_ny = AgentProcedureNY()
        self.points_ny = AgentPointsNY()
        self.verificateur_ny = AgentVerificateurNY()

        # Phase 3: Audit
        self.cross_verif = AgentCrossVerification()

        # Phase 4: Livraison
        self.rapport_client = AgentRapportClient()
        self.rapport_avocat = AgentRapportAvocat()
        self.notification = AgentNotification()
        self.superviseur = AgentSuperviseur()

    def _init_results_table(self):
        conn = self.get_db()
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS analyses_completes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dossier_uuid TEXT,
            ticket_json TEXT,
            lois_json TEXT,
            precedents_json TEXT,
            analyse_json TEXT,
            verification_json TEXT,
            cross_verification_json TEXT,
            rapport_client_json TEXT,
            rapport_avocat_json TEXT,
            procedure_json TEXT,
            points_json TEXT,
            supervision_json TEXT,
            score_final INTEGER,
            confiance INTEGER,
            recommandation TEXT,
            juridiction TEXT,
            temps_total REAL,
            tokens_total INTEGER,
            created_at TEXT
        )""")
        conn.commit()
        conn.close()

    def analyser_ticket(self, ticket_input, image_path=None, client_info=None):
        """
        Pipeline complet 26 agents / 4 phases
        Input: ticket_input (dict ou texte), image optionnelle, info client
        Output: rapport complet avec UUID
        """
        dossier_uuid = str(uuid.uuid4())[:8].upper()
        print("\n" + "=" * 60)
        print(f"  TICKET911 — ANALYSE 26 AGENTS | Dossier #{dossier_uuid}")
        print("=" * 60)
        total_start = time.time()
        total_tokens = 0

        rapport = {
            "dossier_uuid": dossier_uuid,
            "phases": {
                "intake": {},
                "analyse": {},
                "audit": {},
                "livraison": {}
            },
            "erreurs": []
        }

        # ═══════════════════════════════════════════════════════
        # PHASE 1: INTAKE (~50K tokens)
        # ═══════════════════════════════════════════════════════
        print(f"\n{'─'*50}")
        print("  PHASE 1: INTAKE")
        print(f"{'─'*50}")

        # Agent OCR (si image fournie)
        if image_path:
            try:
                ocr_result = self.ocr.extraire_ticket(image_path)
                rapport["phases"]["intake"]["ocr"] = {"status": "OK", "data": ocr_result}
                if ocr_result and isinstance(ocr_result, dict) and ocr_result.get("infraction"):
                    ticket_input = ocr_result
            except Exception as e:
                rapport["phases"]["intake"]["ocr"] = {"status": "FAIL", "error": str(e)}
                rapport["erreurs"].append(f"OCR: {e}")
        else:
            rapport["phases"]["intake"]["ocr"] = {"status": "SKIP", "note": "Pas d'image"}

        # Agent Lecteur (parse le ticket)
        try:
            ticket = self.lecteur.parse_ticket(ticket_input)
            if not ticket:
                ticket = ticket_input if isinstance(ticket_input, dict) else {}
            rapport["phases"]["intake"]["lecteur"] = {"status": "OK"}
        except Exception as e:
            ticket = ticket_input if isinstance(ticket_input, dict) else {}
            rapport["phases"]["intake"]["lecteur"] = {"status": "FAIL", "error": str(e)}
            rapport["erreurs"].append(f"Lecteur: {e}")

        # Agent Classificateur
        try:
            classification = self.classificateur.classifier(ticket)
            rapport["phases"]["intake"]["classificateur"] = {"status": "OK", "data": classification}
            # Enrichir le ticket avec la classification
            if classification:
                ticket["type_infraction"] = classification.get("type_infraction", "")
                ticket["gravite"] = classification.get("gravite", "")
                if not ticket.get("juridiction") and classification.get("juridiction"):
                    ticket["juridiction"] = classification["juridiction"]
        except Exception as e:
            classification = {}
            rapport["phases"]["intake"]["classificateur"] = {"status": "FAIL", "error": str(e)}
            rapport["erreurs"].append(f"Classificateur: {e}")

        # Agent Validateur
        try:
            validation_ticket = self.validateur.valider(ticket)
            rapport["phases"]["intake"]["validateur"] = {"status": "OK", "data": validation_ticket}
        except Exception as e:
            validation_ticket = {}
            rapport["phases"]["intake"]["validateur"] = {"status": "FAIL", "error": str(e)}
            rapport["erreurs"].append(f"Validateur: {e}")

        # Agent Routing
        try:
            route = self.routing.router(ticket)
            rapport["phases"]["intake"]["routing"] = {"status": "OK", "data": route}
        except Exception as e:
            route = {"team": "team_qc"}  # Default QC
            rapport["phases"]["intake"]["routing"] = {"status": "FAIL", "error": str(e)}
            rapport["erreurs"].append(f"Routing: {e}")

        juridiction = ticket.get("juridiction", "QC")
        team = route.get("team", "team_qc")
        print(f"\n  >>> Juridiction: {juridiction} | Team: {team}")

        # ═══════════════════════════════════════════════════════
        # PHASE 2: ANALYSE JURIDIQUE (~650K tokens)
        # ═══════════════════════════════════════════════════════
        print(f"\n{'─'*50}")
        print(f"  PHASE 2: ANALYSE JURIDIQUE ({juridiction})")
        print(f"{'─'*50}")

        lois_trouvees = []
        precedents_trouves = []
        analyse = None
        verification = {}
        procedure_result = {}
        points_result = {}

        # Selectionner les agents selon la juridiction
        if team == "team_ny":
            ag_lois = self.lois_ny
            ag_prec = self.precedents_ny
            ag_anal = self.analyste_ny
            ag_verif = self.verificateur_ny
            ag_proc = self.procedure_ny
            ag_pts = self.points_ny
            tag = "NY"
        elif team == "team_on":
            ag_lois = self.lois_on
            ag_prec = self.precedents_on
            ag_anal = self.analyste_on
            ag_verif = self.verificateur_on
            ag_proc = self.procedure_on
            ag_pts = self.points_on
            tag = "ON"
        else:
            ag_lois = self.lois_qc
            ag_prec = self.precedents_qc
            ag_anal = self.analyste_qc
            ag_verif = self.verificateur_qc
            ag_proc = self.procedure_qc
            ag_pts = self.points_qc
            tag = "QC"

        # ── Pipeline juridiction-specifique ──
        try:
            lois_trouvees = ag_lois.chercher_loi(ticket)
            rapport["phases"]["analyse"]["lois"] = {"status": "OK", "nb": len(lois_trouvees)}
        except Exception as e:
            rapport["phases"]["analyse"]["lois"] = {"status": "FAIL", "error": str(e)}
            rapport["erreurs"].append(f"Lois {tag}: {e}")

        try:
            precedents_trouves = ag_prec.chercher_precedents(ticket, lois_trouvees)
            rapport["phases"]["analyse"]["precedents"] = {"status": "OK", "nb": len(precedents_trouves)}
        except Exception as e:
            rapport["phases"]["analyse"]["precedents"] = {"status": "FAIL", "error": str(e)}
            rapport["erreurs"].append(f"Precedents {tag}: {e}")

        try:
            analyse = ag_anal.analyser(ticket, lois_trouvees, precedents_trouves)
            rapport["phases"]["analyse"]["analyste"] = {"status": "OK"}
        except Exception as e:
            rapport["phases"]["analyse"]["analyste"] = {"status": "FAIL", "error": str(e)}
            rapport["erreurs"].append(f"Analyste {tag}: {e}")

        try:
            verification = ag_verif.verifier(analyse, precedents_trouves, ticket)
            rapport["phases"]["analyse"]["verificateur"] = {"status": "OK"}
        except Exception as e:
            verification = {"confiance_globale": 0}
            rapport["phases"]["analyse"]["verificateur"] = {"status": "FAIL", "error": str(e)}
            rapport["erreurs"].append(f"Verificateur {tag}: {e}")

        try:
            procedure_result = ag_proc.determiner_procedure(ticket)
            rapport["phases"]["analyse"]["procedure"] = {"status": "OK"}
        except Exception as e:
            rapport["phases"]["analyse"]["procedure"] = {"status": "FAIL", "error": str(e)}
            rapport["erreurs"].append(f"Procedure {tag}: {e}")

        try:
            points_result = ag_pts.calculer(ticket, analyse)
            rapport["phases"]["analyse"]["points"] = {"status": "OK"}
        except Exception as e:
            rapport["phases"]["analyse"]["points"] = {"status": "FAIL", "error": str(e)}
            rapport["erreurs"].append(f"Points {tag}: {e}")

        # ═══════════════════════════════════════════════════════
        # PHASE 3: AUDIT QUALITE (~150K tokens)
        # ═══════════════════════════════════════════════════════
        print(f"\n{'─'*50}")
        print("  PHASE 3: AUDIT QUALITE (Cross-verification)")
        print(f"{'─'*50}")

        cross_verif_result = {}
        try:
            cross_verif_result = self.cross_verif.verifier_analyse(
                ticket, analyse or {}, lois_trouvees, precedents_trouves)
            rapport["phases"]["audit"]["cross_verification"] = cross_verif_result
        except Exception as e:
            rapport["phases"]["audit"]["cross_verification"] = {}
            rapport["erreurs"].append(f"CrossVerification: {e}")

        # ═══════════════════════════════════════════════════════
        # PHASE 4: LIVRAISON (~350K tokens)
        # ═══════════════════════════════════════════════════════
        print(f"\n{'─'*50}")
        print("  PHASE 4: LIVRAISON")
        print(f"{'─'*50}")

        # Rapport Client
        rapport_client_data = {}
        try:
            rapport_client_data = self.rapport_client.generer(
                ticket, analyse or {}, procedure_result, points_result, cross_verif_result)
            rapport["phases"]["livraison"]["rapport_client"] = rapport_client_data
        except Exception as e:
            rapport["phases"]["livraison"]["rapport_client"] = {}
            rapport["erreurs"].append(f"Rapport Client: {e}")

        # Rapport Avocat
        rapport_avocat_data = {}
        try:
            rapport_avocat_data = self.rapport_avocat.generer(
                ticket, analyse or {}, lois_trouvees, precedents_trouves,
                procedure_result, points_result, validation_ticket, cross_verif_result)
            rapport["phases"]["livraison"]["rapport_avocat"] = rapport_avocat_data
        except Exception as e:
            rapport["phases"]["livraison"]["rapport_avocat"] = {}
            rapport["erreurs"].append(f"Rapport Avocat: {e}")

        # Notification (si info client disponible)
        notif_result = {}
        if client_info and (client_info.get("email") or client_info.get("phone")):
            try:
                notif_result = self.notification.notifier(dossier_uuid, client_info, rapport_client_data)
                rapport["phases"]["livraison"]["notification"] = notif_result
            except Exception as e:
                rapport["phases"]["livraison"]["notification"] = {}
                rapport["erreurs"].append(f"Notification: {e}")
        else:
            rapport["phases"]["livraison"]["notification"] = {"status": "SKIP", "note": "Pas d'info client"}

        # Superviseur — validation finale
        supervision = {}
        try:
            supervision = self.superviseur.superviser(rapport)
            rapport["phases"]["livraison"]["supervision"] = supervision
        except Exception as e:
            rapport["phases"]["livraison"]["supervision"] = {}
            rapport["erreurs"].append(f"Superviseur: {e}")

        # ═══════════════════════════════════════════════════════
        # RAPPORT FINAL
        # ═══════════════════════════════════════════════════════
        total_time = time.time() - total_start
        score_final = analyse.get("score_contestation", 0) if analyse and isinstance(analyse, dict) else 0
        confiance = verification.get("confiance_globale", 0)
        recommandation = analyse.get("recommandation", "?") if analyse and isinstance(analyse, dict) else "?"

        rapport["score_final"] = score_final
        rapport["confiance"] = confiance
        rapport["recommandation"] = recommandation
        rapport["juridiction"] = juridiction
        rapport["temps_total"] = round(total_time, 2)
        rapport["nb_erreurs"] = len(rapport["erreurs"])
        rapport["supervision"] = supervision

        # Sauver en SQLite
        try:
            conn = self.get_db()
            c = conn.cursor()
            c.execute("""INSERT INTO analyses_completes
                (dossier_uuid, ticket_json, lois_json, precedents_json, analyse_json,
                 verification_json, cross_verification_json, rapport_client_json,
                 rapport_avocat_json, procedure_json, points_json, supervision_json,
                 score_final, confiance, recommandation, juridiction, temps_total,
                 tokens_total, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (dossier_uuid,
                 json.dumps(ticket, ensure_ascii=False, default=str),
                 json.dumps(lois_trouvees, ensure_ascii=False, default=str),
                 json.dumps(precedents_trouves, ensure_ascii=False, default=str),
                 json.dumps(analyse, ensure_ascii=False, default=str),
                 json.dumps(verification, ensure_ascii=False, default=str),
                 json.dumps(cross_verif_result, ensure_ascii=False, default=str),
                 json.dumps(rapport_client_data, ensure_ascii=False, default=str),
                 json.dumps(rapport_avocat_data, ensure_ascii=False, default=str),
                 json.dumps(procedure_result, ensure_ascii=False, default=str),
                 json.dumps(points_result, ensure_ascii=False, default=str),
                 json.dumps(supervision, ensure_ascii=False, default=str),
                 score_final, confiance, recommandation, juridiction,
                 round(total_time, 2), total_tokens, datetime.now().isoformat()))
            conn.commit()
            conn.close()
        except Exception as e:
            rapport["erreurs"].append(f"SQLite save: {e}")

        self._afficher_rapport(rapport, ticket, analyse, verification, supervision)
        return rapport

    def _afficher_rapport(self, rapport, ticket, analyse, verification, supervision):
        score = rapport.get("score_final", 0)
        confiance = rapport.get("confiance", 0)
        reco = rapport.get("recommandation", "?")
        uuid_str = rapport.get("dossier_uuid", "?")
        juridiction = rapport.get("juridiction", "?")
        qualite = supervision.get("score_qualite", "?") if supervision else "?"

        print(f"""
+===========================================================+
|           TICKET911 — RAPPORT 26 AGENTS                   |
|           Dossier #{uuid_str}                              |
|           {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                          |
+===========================================================+
|  Ticket: {str(ticket.get('infraction', '?'))[:47]:<47} |
|  Juridiction: {str(juridiction):<42}|
+-----------------------------------------------------------+""")

        # Phases
        for phase_name, phase_data in rapport.get("phases", {}).items():
            print(f"|  --- {phase_name.upper()} ---")
            if isinstance(phase_data, dict):
                for agent, data in phase_data.items():
                    if isinstance(data, dict):
                        status = data.get("status", "OK")
                        if status in ("OK", "SKIP"):
                            symbol = "PASS" if status == "OK" else "SKIP"
                        else:
                            symbol = "FAIL"
                    else:
                        symbol = "OK"
                    print(f"|  [{symbol}] {agent:<44}       |")

        print(f"""+-----------------------------------------------------------+
|  Score contestation: {score}%
|  Confiance: {confiance}%
|  Recommandation: {reco}
|  Qualite supervision: {qualite}%
|  Temps total: {rapport.get('temps_total', 0):.1f}s
+-----------------------------------------------------------+""")

        if analyse and isinstance(analyse, dict):
            args = analyse.get("arguments", [])
            if args:
                print("\n  ARGUMENTS DE DEFENSE:")
                for i, arg in enumerate(args, 1):
                    print(f"    {i}. {arg}")

        if rapport.get("erreurs"):
            print(f"\n  ERREURS ({len(rapport['erreurs'])}):")
            for err in rapport["erreurs"]:
                print(f"    - {err}")

        print()
