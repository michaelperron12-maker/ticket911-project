#!/usr/bin/env python3
"""
TEST PIPELINE 26 AGENTS — Ticket911
Lance une analyse complete avec un ticket QC de test
Envoie le resultat par email

Usage:
  SMTP_PASS=xxx python3 test_pipeline.py              # avec email alert@seoparai.com
  python3 test_pipeline.py                             # sans email (analyse seulement)
"""

import sys
import json
import os
import time

sys.path.insert(0, "/var/www/ticket911")

# ─── TICKET DE TEST (Quebec — exces de vitesse) ─────
TICKET_TEST_QC = {
    "infraction": "Excès de vitesse",
    "juridiction": "QC",
    "loi": "Art. 299 CSR",
    "amende": "368$",
    "points_inaptitude": 3,
    "lieu": "Autoroute 15, Laval",
    "date": "2026-02-01",
    "appareil": "Cinémomètre laser",
    "vitesse_captee": 138,
    "vitesse_permise": 100,
}

CLIENT_TEST = {
    "email": "michaelperron12@gmail.com",
    "phone": "",
    "nom": "Michael Perron (TEST)",
}


def main():
    print("=" * 60)
    print("  TICKET911 — TEST PIPELINE 26 AGENTS")
    print("=" * 60)
    print(f"\n  Ticket: {TICKET_TEST_QC['infraction']}")
    print(f"  Juridiction: {TICKET_TEST_QC['juridiction']}")
    print(f"  Vitesse: {TICKET_TEST_QC['vitesse_captee']} / {TICKET_TEST_QC['vitesse_permise']} km/h")
    print(f"  Client email: {CLIENT_TEST['email']}")
    print()

    start = time.time()

    # Importer l'orchestrateur
    from agents.orchestrateur import Orchestrateur
    print("[+] Orchestrateur charge\n")

    orch = Orchestrateur()

    # Lancer l'analyse complete
    rapport = orch.analyser_ticket(
        ticket_input=TICKET_TEST_QC,
        image_path=None,
        client_info=CLIENT_TEST
    )

    total = time.time() - start

    # ─── RESULTATS ────────────────────────────────
    print("\n" + "=" * 60)
    print("  RESULTATS DU TEST")
    print("=" * 60)

    print(f"\n  Dossier UUID: {rapport.get('dossier_uuid', '?')}")
    print(f"  Score: {rapport.get('score_final', 0)}%")
    print(f"  Confiance: {rapport.get('confiance', 0)}%")
    print(f"  Recommandation: {rapport.get('recommandation', '?')}")
    print(f"  Juridiction: {rapport.get('juridiction', '?')}")
    print(f"  Temps total: {total:.1f}s")
    print(f"  Erreurs: {rapport.get('nb_erreurs', 0)}")

    # Phases
    print("\n  PHASES:")
    for phase_name, phase_data in rapport.get("phases", {}).items():
        if isinstance(phase_data, dict):
            agents_ok = sum(1 for d in phase_data.values()
                           if isinstance(d, dict) and d.get("status") == "OK")
            agents_total = len(phase_data)
            print(f"    {phase_name}: {agents_ok}/{agents_total} agents OK")

    # Rapport client
    rc = rapport.get("phases", {}).get("livraison", {}).get("rapport_client", {})
    if rc and isinstance(rc, dict):
        print(f"\n  RAPPORT CLIENT:")
        print(f"    Resume: {rc.get('resume', '?')[:200]}")
        print(f"    Verdict: {rc.get('verdict', '?')}")
        etapes = rc.get("prochaines_etapes", [])
        if etapes:
            print(f"    Etapes:")
            for e in etapes[:3]:
                print(f"      - {e}")

    # Supervision
    sup = rapport.get("phases", {}).get("livraison", {}).get("supervision", {})
    if sup and isinstance(sup, dict):
        print(f"\n  SUPERVISION:")
        print(f"    Qualite: {sup.get('score_qualite', '?')}%")
        print(f"    Decision: {sup.get('decision', '?')}")
        print(f"    Agents verifies: {sup.get('agents_verifies', '?')}")

    # Notification
    notif = rapport.get("phases", {}).get("livraison", {}).get("notification", {})
    if notif and isinstance(notif, dict):
        print(f"\n  NOTIFICATION:")
        print(f"    Email: {notif.get('email', notif.get('status', '?'))}")
        print(f"    SMS: {notif.get('sms', '?')}")

    # Erreurs
    if rapport.get("erreurs"):
        print(f"\n  ERREURS ({len(rapport['erreurs'])}):")
        for err in rapport["erreurs"]:
            print(f"    [X] {err}")

    # Sauver le rapport JSON complet
    rapport_path = f"/var/www/ticket911/data/test-{rapport.get('dossier_uuid', 'test')}.json"
    try:
        os.makedirs(os.path.dirname(rapport_path), exist_ok=True)
        with open(rapport_path, "w", encoding="utf-8") as f:
            json.dump(rapport, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n  Rapport JSON sauve: {rapport_path}")
    except Exception as e:
        print(f"\n  Erreur sauvegarde: {e}")

    print(f"\n  Total: {total:.1f}s")
    print("=" * 60)

    return rapport


if __name__ == "__main__":
    main()
