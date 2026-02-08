"""
ORCHESTRATEUR — Master agent qui coordonne les 5 agents
Pipeline: Lecteur -> Lois -> Precedents -> Analyste -> Verificateur
"""

import json
import time
import sqlite3
from datetime import datetime
from agents.base_agent import BaseAgent, DB_PATH
from agents.agent_lecteur import AgentLecteur
from agents.agent_lois import AgentLois
from agents.agent_precedents import AgentPrecedents
from agents.agent_analyste import AgentAnalyste
from agents.agent_verificateur import AgentVerificateur


class Orchestrateur(BaseAgent):

    def __init__(self):
        super().__init__("Orchestrateur")
        self.lecteur = AgentLecteur()
        self.lois = AgentLois()
        self.precedents = AgentPrecedents()
        self.analyste = AgentAnalyste()
        self.verificateur = AgentVerificateur()
        self._init_results_table()

    def _init_results_table(self):
        conn = self.get_db()
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS analyses_completes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_json TEXT,
            lois_json TEXT,
            precedents_json TEXT,
            analyse_json TEXT,
            verification_json TEXT,
            score_final INTEGER,
            confiance INTEGER,
            recommandation TEXT,
            temps_total REAL,
            created_at TEXT
        )""")
        conn.commit()
        conn.close()

    def analyser_ticket(self, ticket_input):
        """
        Pipeline complet: ticket -> 5 agents -> rapport verifie
        """
        print("\n" + "="*60)
        print("  TICKET911 — ANALYSE MULTI-AGENT")
        print("="*60)
        total_start = time.time()

        rapport = {
            "etapes": {},
            "erreurs": []
        }

        # ─── Agent 1: LECTEUR ─────────────────────
        print(f"\n--- Agent 1: LECTEUR ---")
        try:
            ticket = self.lecteur.parse_ticket(ticket_input)
            if ticket:
                rapport["etapes"]["lecteur"] = {"status": "OK", "ticket": ticket}
                print(f"  Ticket: {ticket.get('infraction', '?')}")
            else:
                rapport["etapes"]["lecteur"] = {"status": "FAIL"}
                rapport["erreurs"].append("Agent Lecteur: echec du parsing")
                ticket = ticket_input if isinstance(ticket_input, dict) else {}
        except Exception as e:
            rapport["etapes"]["lecteur"] = {"status": "FAIL", "error": str(e)}
            rapport["erreurs"].append(f"Agent Lecteur: {e}")
            ticket = ticket_input if isinstance(ticket_input, dict) else {}

        # ─── Agent 2: LOIS ─────────────────────────
        print(f"\n--- Agent 2: CHERCHEUR DE LOIS ---")
        try:
            lois_trouvees = self.lois.chercher_loi(ticket)
            rapport["etapes"]["lois"] = {"status": "OK", "nb_lois": len(lois_trouvees), "lois": lois_trouvees}
        except Exception as e:
            lois_trouvees = []
            rapport["etapes"]["lois"] = {"status": "FAIL", "error": str(e)}
            rapport["erreurs"].append(f"Agent Lois: {e}")

        # ─── Agent 3: PRECEDENTS ───────────────────
        print(f"\n--- Agent 3: CHERCHEUR DE PRECEDENTS ---")
        try:
            precedents_trouves = self.precedents.chercher_precedents(ticket, lois_trouvees)
            rapport["etapes"]["precedents"] = {
                "status": "OK",
                "nb_precedents": len(precedents_trouves),
                "precedents": precedents_trouves
            }
        except Exception as e:
            precedents_trouves = []
            rapport["etapes"]["precedents"] = {"status": "FAIL", "error": str(e)}
            rapport["erreurs"].append(f"Agent Precedents: {e}")

        # ─── Agent 4: ANALYSTE ─────────────────────
        print(f"\n--- Agent 4: ANALYSTE ---")
        try:
            analyse = self.analyste.analyser(ticket, lois_trouvees, precedents_trouves)
            rapport["etapes"]["analyste"] = {"status": "OK", "analyse": analyse}
        except Exception as e:
            analyse = None
            rapport["etapes"]["analyste"] = {"status": "FAIL", "error": str(e)}
            rapport["erreurs"].append(f"Agent Analyste: {e}")

        # ─── Agent 5: VERIFICATEUR ─────────────────
        print(f"\n--- Agent 5: VERIFICATEUR ---")
        try:
            verification = self.verificateur.verifier(analyse, precedents_trouves)
            rapport["etapes"]["verificateur"] = {"status": "OK", "verification": verification}
        except Exception as e:
            verification = {"confiance_globale": 0}
            rapport["etapes"]["verificateur"] = {"status": "FAIL", "error": str(e)}
            rapport["erreurs"].append(f"Agent Verificateur: {e}")

        # ─── RAPPORT FINAL ─────────────────────────
        total_time = time.time() - total_start
        score_final = analyse.get("score_contestation", 0) if analyse and isinstance(analyse, dict) else 0
        confiance = verification.get("confiance_globale", 0)
        recommandation = analyse.get("recommandation", "?") if analyse and isinstance(analyse, dict) else "?"

        rapport["score_final"] = score_final
        rapport["confiance"] = confiance
        rapport["recommandation"] = recommandation
        rapport["temps_total"] = round(total_time, 2)
        rapport["nb_erreurs"] = len(rapport["erreurs"])

        # Sauver en SQLite
        try:
            conn = self.get_db()
            c = conn.cursor()
            c.execute("""INSERT INTO analyses_completes
                (ticket_json, lois_json, precedents_json, analyse_json, verification_json,
                 score_final, confiance, recommandation, temps_total, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (json.dumps(ticket, ensure_ascii=False),
                 json.dumps(lois_trouvees, ensure_ascii=False, default=str),
                 json.dumps(precedents_trouves, ensure_ascii=False, default=str),
                 json.dumps(analyse, ensure_ascii=False, default=str),
                 json.dumps(verification, ensure_ascii=False, default=str),
                 score_final, confiance, recommandation,
                 round(total_time, 2), datetime.now().isoformat()))
            conn.commit()
            conn.close()
        except Exception as e:
            rapport["erreurs"].append(f"SQLite save: {e}")

        # Afficher le rapport
        self._afficher_rapport(rapport, ticket, analyse, verification)

        return rapport

    def _afficher_rapport(self, rapport, ticket, analyse, verification):
        print(f"""
+===========================================================+
|           TICKET911 — RAPPORT D'ANALYSE                   |
|           {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                          |
+===========================================================+
|  Ticket: {str(ticket.get('infraction', '?'))[:47]:<47} |
|  Juridiction: {str(ticket.get('juridiction', '?')):<42}|
+-----------------------------------------------------------+""")

        for nom, etape in rapport["etapes"].items():
            status = "PASS" if etape.get("status") == "OK" else "FAIL"
            print(f"|  [{status}] Agent {nom:<40}       |")

        score = rapport.get("score_final", 0)
        confiance = rapport.get("confiance", 0)
        reco = rapport.get("recommandation", "?")

        print(f"""+-----------------------------------------------------------+
|  Score contestation: {score}%                                |
|  Confiance: {confiance}%                                         |
|  Recommandation: {reco:<39} |
|  Temps total: {rapport.get('temps_total', 0):.1f}s                                   |
+-----------------------------------------------------------+""")

        # Details analyse
        if analyse and isinstance(analyse, dict):
            args = analyse.get("arguments", [])
            if args:
                print("\n  ARGUMENTS DE DEFENSE:")
                for i, arg in enumerate(args, 1):
                    print(f"    {i}. {arg}")

            precedents = analyse.get("precedents_cites", [])
            if precedents:
                print("\n  PRECEDENTS CITES:")
                for p in precedents:
                    print(f"    - {p.get('citation', '?')} -> {p.get('resultat', '?')}")

            explication = analyse.get("explication", "")
            if explication:
                print(f"\n  EXPLICATION: {explication}")

        # Verification
        if verification:
            avert = verification.get("avertissement")
            if avert:
                print(f"\n  *** {avert}")

        if rapport.get("erreurs"):
            print(f"\n  ERREURS ({len(rapport['erreurs'])}):")
            for err in rapport["erreurs"]:
                print(f"    - {err}")

        print()
