#!/usr/bin/env python3
"""Test branchement pgvector dans agents precedents QC et ON"""
import sys
import time
sys.path.insert(0, "/var/www/aiticketinfo")

print("=" * 60)
print("TEST BRANCHEMENT pgvector → agents precedents")
print("=" * 60)

# --- Test QC ---
print("\n--- AGENT PRECEDENTS QC ---")
from agents.agent_precedents_qc import AgentPrecedentsQC
agent_qc = AgentPrecedentsQC()

start = time.time()
results_sem = agent_qc._recherche_semantique_qc("exces de vitesse radar photo", 5)
t_sem = time.time() - start
print(f"\nSemantique pgvector QC: {len(results_sem)} resultats ({t_sem:.2f}s)")
for r in results_sem:
    score = r.get("score", 0)
    cit = r.get("citation", "?")[:60]
    trib = r.get("tribunal", "?")
    res = r.get("resultat", "?")
    src = r.get("source", "?")
    print(f"  [{score:.1f}%] {cit} | {trib} | {res} | {src}")

print("\n--- RECHERCHE COMPLETE QC ---")
ticket_qc = {
    "infraction": "Exces de vitesse - 30 km/h au-dessus de la limite",
    "juridiction": "QC",
    "lieu": "Montreal"
}
start = time.time()
top_qc = agent_qc.chercher_precedents(ticket_qc, [], n_results=10)
t_full = time.time() - start
print(f"Resultats complets: {len(top_qc)} ({t_full:.2f}s)")
for r in top_qc[:5]:
    score = r.get("score", 0)
    cit = r.get("citation", "?")[:60]
    src = r.get("source", "?")
    res = r.get("resultat", "?")
    print(f"  [{score}] {cit} | {src} | {res}")

# --- Test ON ---
print("\n\n--- AGENT PRECEDENTS ON ---")
from agents.agent_precedents_on import AgentPrecedentsON
agent_on = AgentPrecedentsON()

start = time.time()
results_on = agent_on._recherche_semantique_on("speeding 30 over school zone", 5)
t_sem_on = time.time() - start
print(f"\nSemantique pgvector ON: {len(results_on)} resultats ({t_sem_on:.2f}s)")
for r in results_on:
    score = r.get("score", 0)
    cit = r.get("citation", "?")[:60]
    trib = r.get("tribunal", "?")
    res = r.get("resultat", "?")
    src = r.get("source", "?")
    print(f"  [{score:.1f}%] {cit} | {trib} | {res} | {src}")

print("\n--- RECHERCHE COMPLETE ON ---")
ticket_on = {
    "infraction": "Speeding - 30 km/h over limit",
    "juridiction": "ON",
    "lieu": "Toronto"
}
start = time.time()
top_on = agent_on.chercher_precedents(ticket_on, [], n_results=10)
t_full_on = time.time() - start
print(f"Resultats complets: {len(top_on)} ({t_full_on:.2f}s)")
for r in top_on[:5]:
    score = r.get("score", 0)
    cit = r.get("citation", "?")[:60]
    src = r.get("source", "?")
    res = r.get("resultat", "?")
    print(f"  [{score}] {cit} | {src} | {res}")

print("\n" + "=" * 60)
print("TEST TERMINE")
print("=" * 60)
