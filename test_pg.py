#!/usr/bin/env python3
"""Test PostgreSQL integration for AITicketInfo agents"""
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 50)
print("TEST AGENTS AITICKETINFO - POSTGRESQL")
print("=" * 50)

# Test 1: Agent Lois QC
print("\n--- Test Agent Lois QC ---")
from agents.agent_lois_qc import AgentLoisQC
lois_qc = AgentLoisQC()
ticket_qc = {"infraction": "Exces de vitesse 95 km/h dans une zone de 70 km/h", "juridiction": "QC"}
res = lois_qc.chercher_loi(ticket_qc)
print(f"Lois QC trouvees: {len(res)}")
for r in res[:3]:
    print(f"  - art. {r.get('article','?')} : {str(r.get('texte','?'))[:80]}")

# Test 2: Agent Precedents QC
print("\n--- Test Agent Precedents QC ---")
from agents.agent_precedents_qc import AgentPrecedentsQC
prec_qc = AgentPrecedentsQC()
prec = prec_qc.chercher_precedents(ticket_qc, res)
print(f"Precedents QC trouves: {len(prec)}")
for p in prec[:3]:
    print(f"  - {p.get('citation','?')} ({p.get('tribunal','?')}) score={p.get('score',0)}")

# Test 3: Agent Lois ON
print("\n--- Test Agent Lois ON ---")
from agents.agent_lois_on import AgentLoisON
lois_on = AgentLoisON()
ticket_on = {"infraction": "Speeding 130 km/h in a 100 km/h zone", "juridiction": "ON"}
res_on = lois_on.chercher_loi(ticket_on)
print(f"Lois ON trouvees: {len(res_on)}")
for r in res_on[:3]:
    print(f"  - art. {r.get('article','?')} : {str(r.get('texte','?'))[:80]}")

# Test 4: Agent Precedents ON
print("\n--- Test Agent Precedents ON ---")
from agents.agent_precedents_on import AgentPrecedentsON
prec_on = AgentPrecedentsON()
prec_on_res = prec_on.chercher_precedents(ticket_on, res_on)
print(f"Precedents ON trouves: {len(prec_on_res)}")
for p in prec_on_res[:3]:
    print(f"  - {p.get('citation','?')} ({p.get('tribunal','?')}) score={p.get('score',0)}")

# Test 5: Agent log_run (PostgreSQL)
print("\n--- Test log_run PostgreSQL ---")
from agents.base_agent import BaseAgent
agent = BaseAgent("test_pg")
agent.log_run("test_connection", "test input", "test output", tokens=0, duration=0.1)
conn = agent.get_db()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM agent_runs WHERE agent_name = 'test_pg'")
print(f"Agent runs logged: {cur.fetchone()[0]}")
conn.close()

print("\n" + "=" * 50)
print("TOUS LES TESTS TERMINES")
print("=" * 50)
