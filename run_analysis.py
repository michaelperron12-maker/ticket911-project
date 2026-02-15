#!/usr/bin/env python3
"""
RUN ANALYSIS — Test complet du pipeline multi-agent
Usage: python3 run_analysis.py
"""

import sys
import os

# Ajouter le dossier parent au path
sys.path.insert(0, "/var/www/aiticketinfo")

from agents.orchestrateur import Orchestrateur


# Scenarios de test
SCENARIOS = [
    {
        "nom": "Exces de vitesse 95/70 — Quebec (radar fixe)",
        "ticket": {
            "infraction": "Exces de vitesse — 95 km/h dans une zone de 70 km/h",
            "juridiction": "Quebec",
            "loi": "Code de la securite routiere, art. 299",
            "amende": "175$ + 30$ frais",
            "points_inaptitude": 2,
            "lieu": "Boulevard Henri-Bourassa, Montreal",
            "date": "2026-01-15",
            "appareil": "Radar fixe",
            "vitesse_captee": 95,
            "vitesse_permise": 70
        }
    },
    {
        "nom": "Feu rouge — Quebec",
        "ticket": {
            "infraction": "Ne pas avoir respecte un feu rouge",
            "juridiction": "Quebec",
            "loi": "Code de la securite routiere, art. 328",
            "amende": "150$ + 30$ frais",
            "points_inaptitude": 3,
            "lieu": "Intersection Sherbrooke/St-Denis, Montreal",
            "date": "2026-01-20",
            "appareil": "Camera feu rouge"
        }
    },
    {
        "nom": "Speeding 130/100 — Ontario",
        "ticket": {
            "infraction": "Speeding — 130 km/h in a 100 km/h zone",
            "juridiction": "Ontario",
            "loi": "Highway Traffic Act, s.128",
            "amende": "$260",
            "points_inaptitude": 3,
            "lieu": "Highway 401, Toronto",
            "date": "2026-01-22",
            "appareil": "Radar gun"
        }
    }
]


def main():
    print("""
+===========================================================+
|       TICKET911 — TEST MULTI-AGENT COMPLET                |
|       Pipeline: Lecteur -> Lois -> Precedents ->          |
|                 Analyste -> Verificateur                   |
+===========================================================+
""")

    orchestrateur = Orchestrateur()

    # Par defaut, tester le premier scenario
    scenario_idx = 0
    if len(sys.argv) > 1:
        try:
            scenario_idx = int(sys.argv[1]) - 1
        except ValueError:
            # Chercher par nom
            for i, s in enumerate(SCENARIOS):
                if sys.argv[1].lower() in s["nom"].lower():
                    scenario_idx = i
                    break

    if scenario_idx < 0 or scenario_idx >= len(SCENARIOS):
        print(f"Scenarios disponibles:")
        for i, s in enumerate(SCENARIOS, 1):
            print(f"  {i}. {s['nom']}")
        print(f"\nUsage: python3 run_analysis.py [1-{len(SCENARIOS)}]")
        return

    scenario = SCENARIOS[scenario_idx]
    print(f"  Scenario: {scenario['nom']}\n")

    rapport = orchestrateur.analyser_ticket(scenario["ticket"])

    # Resume
    print(f"""
+===========================================================+
|  RESUME FINAL                                             |
|  Score: {rapport.get('score_final', 0)}% | Confiance: {rapport.get('confiance', 0)}% | Reco: {rapport.get('recommandation', '?'):<12} |
|  Temps: {rapport.get('temps_total', 0):.1f}s | Erreurs: {rapport.get('nb_erreurs', 0)}                            |
+===========================================================+
""")


if __name__ == "__main__":
    main()
