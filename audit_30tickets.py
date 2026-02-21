#!/usr/bin/env python3
"""Audit 30 tickets réels via l'API AITicketInfo en production."""
import requests, json, time, sys

API = "https://seoparai.com/scanticket/api/analyze"

TICKETS = [
    # --- EXCÈS DE VITESSE (8 variations) ---
    {"infraction":"Excès de vitesse de 15 km/h en zone 50","lieu":"Rue Saint-Denis, Montréal","date":"2026-02-10","province":"QC","nom":"Anne-Marie Fortin"},
    {"infraction":"Excès de vitesse de 25 km/h sur autoroute","lieu":"Autoroute 40, Repentigny","date":"2025-11-20","province":"QC","nom":"Hugo Lemieux"},
    {"infraction":"Excès de vitesse de 35 km/h en zone 90","lieu":"Route 117, Mont-Tremblant","date":"2026-01-05","province":"QC","nom":"Caroline Dufresne"},
    {"infraction":"Excès de vitesse de 50 km/h (grand excès)","lieu":"Autoroute 15 Nord, Mirabel","date":"2025-08-15","province":"QC","nom":"Maxime Girard"},
    {"infraction":"Excès de vitesse de 20 km/h zone scolaire","lieu":"Rue du Collège, Sherbrooke","date":"2025-09-12","province":"QC","nom":"Nathalie Poirier"},
    {"infraction":"Excès de vitesse de 45 km/h zone de construction","lieu":"Autoroute 30, Châteauguay","date":"2026-01-28","province":"QC","nom":"Éric Bouchard"},
    {"infraction":"Excès de vitesse de 10 km/h en zone 30","lieu":"Rue commerciale, Magog","date":"2026-02-05","province":"QC","nom":"Julie Ouellet"},
    {"infraction":"Excès de vitesse radar photo 22 km/h","lieu":"Autoroute 13, Laval","date":"2025-10-30","province":"QC","nom":"Patrick Cloutier"},
    # --- FEU ROUGE / STOP (4) ---
    {"infraction":"Feu rouge non respecté","lieu":"Boulevard Taschereau et Lapinière, Brossard","date":"2026-01-15","province":"QC","nom":"Sylvie Nadeau"},
    {"infraction":"Feu rouge grillé - caméra","lieu":"Boulevard Henri-Bourassa, Québec","date":"2025-12-22","province":"QC","nom":"Martin Blais"},
    {"infraction":"Arrêt obligatoire non respecté","lieu":"Rang Saint-Joseph, Berthierville","date":"2026-02-01","province":"QC","nom":"Josée Martel"},
    {"infraction":"Virage à droite au feu rouge interdit","lieu":"Boulevard des Sources, Dorval","date":"2025-11-10","province":"QC","nom":"Stéphane Richer"},
    # --- CELLULAIRE (2) ---
    {"infraction":"Utilisation du téléphone cellulaire au volant","lieu":"Boulevard de la Concorde, Laval","date":"2026-02-08","province":"QC","nom":"Valérie Caron"},
    {"infraction":"Textos au volant","lieu":"Rue Wellington, Gatineau","date":"2025-12-05","province":"QC","nom":"Dominic Lachance"},
    # --- CEINTURE (2) ---
    {"infraction":"Défaut de porter la ceinture de sécurité","lieu":"Avenue du Parc, Montréal","date":"2026-01-20","province":"QC","nom":"Mélanie Trépanier"},
    {"infraction":"Passager sans ceinture de sécurité","lieu":"Boulevard Laurier, Québec","date":"2025-10-15","province":"QC","nom":"François Hamel"},
    # --- ALCOOL / DROGUE (2) ---
    {"infraction":"Conduite avec facultés affaiblies - alcool","lieu":"Rue Principale, Granby","date":"2025-09-28","province":"QC","nom":"Benoit Larose"},
    {"infraction":"Refus de fournir un échantillon d'haleine","lieu":"Boulevard Saint-Martin, Laval","date":"2025-11-30","province":"QC","nom":"Sébastien Plante"},
    # --- PERMIS / IMMATRICULATION (3) ---
    {"infraction":"Conduite avec permis suspendu","lieu":"Route 132, Sorel-Tracy","date":"2026-01-12","province":"QC","nom":"Alain Fréchette"},
    {"infraction":"Conduite sans permis valide","lieu":"Rue King Ouest, Sherbrooke","date":"2025-12-18","province":"QC","nom":"Nancy Grenier"},
    {"infraction":"Défaut d'immatriculation","lieu":"Boulevard Shevchenko, LaSalle","date":"2026-02-03","province":"QC","nom":"Roberto Sanchez"},
    # --- SIGNALISATION / CONDUITE (5) ---
    {"infraction":"Dépassement interdit par la droite","lieu":"Route 138, La Malbaie","date":"2025-10-25","province":"QC","nom":"Michel Simard"},
    {"infraction":"Non-respect de la priorité de passage (piéton)","lieu":"Rue Sainte-Catherine, Montréal","date":"2026-02-14","province":"QC","nom":"Chantal Labelle"},
    {"infraction":"Changement de voie dangereux","lieu":"Pont Champlain, Montréal","date":"2025-11-05","province":"QC","nom":"Rémi Gervais"},
    {"infraction":"Conduite dangereuse","lieu":"Boulevard Wilfrid-Hamel, Québec","date":"2025-08-20","province":"QC","nom":"Denis Lapointe"},
    {"infraction":"Suivre de trop près (tailgating)","lieu":"Autoroute 20, Drummondville","date":"2026-01-30","province":"QC","nom":"Sandra Bérubé"},
    # --- DIVERS (4) ---
    {"infraction":"Vitrage teinté non conforme","lieu":"Rue Jean-Talon, Montréal","date":"2026-02-12","province":"QC","nom":"Kevin Tremblay"},
    {"infraction":"Silencieux défectueux / bruit excessif","lieu":"Boulevard de Portland, Sherbrooke","date":"2025-09-15","province":"QC","nom":"Jonathan Roy"},
    {"infraction":"Stationnement interdit zone de remorquage","lieu":"Rue Saint-Urbain, Montréal","date":"2026-02-18","province":"QC","nom":"Geneviève Dubé"},
    {"infraction":"Défaut d'assurance automobile","lieu":"Boulevard Pie-IX, Montréal","date":"2025-12-01","province":"QC","nom":"Yannick Côté"},
]

results = []
total = len(TICKETS)
print(f"\n{'='*80}")
print(f"  AUDIT 30 TICKETS — AITicketInfo Production")
print(f"  API: {API}")
print(f"  Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*80}\n")

for i, t in enumerate(TICKETS):
    label = f"[{i+1}/{total}]"
    desc = t['infraction'][:50]
    lieu = t['lieu'][:30]
    print(f"{label} {desc} — {lieu}...", end=" ", flush=True)

    start = time.time()
    try:
        resp = requests.post(API, files={
            'ticket': (None, json.dumps({
                'infraction': t['infraction'],
                'type_infraction': t['infraction'].split(' - ')[0],
                'lieu': t['lieu'],
                'date': t['date'],
                'province': t['province']
            })),
            'client_info': (None, json.dumps({
                'nom': t['nom'],
                'permis': 'depuis 5 ans'
            }))
        }, timeout=300)
        elapsed = round(time.time() - start, 1)

        if resp.status_code != 200:
            print(f"ERREUR HTTP {resp.status_code} ({elapsed}s)")
            results.append({'ticket': t, 'status': 'ERROR', 'code': resp.status_code, 'temps': elapsed})
            continue

        d = resp.json()
        if d.get('error'):
            print(f"ERREUR: {d['error']} ({elapsed}s)")
            results.append({'ticket': t, 'status': 'ERROR', 'error': d['error'], 'temps': elapsed})
            continue

        a = d.get('analyse', {})
        score = d.get('score', 0)
        rec = a.get('recommandation', d.get('recommandation', ''))
        conf = d.get('confiance', a.get('confiance', ''))
        strat = a.get('strategie', '')[:100]
        args = a.get('arguments', [])
        prec = a.get('precedents_cites', [])
        taux = a.get('taux_acquittement_reel', '')
        typ = a.get('type_infraction_detecte', '')
        lois = d.get('lois_trouvees', 0)
        prec_count = d.get('precedents_trouves', len(prec))
        sup = d.get('supervision', {})

        print(f"OK — Score:{score} Rec:{rec} Conf:{conf} Args:{len(args)} Prec:{prec_count} ({elapsed}s)")

        results.append({
            'ticket': t,
            'status': 'OK',
            'score': score,
            'recommandation': rec,
            'confiance': conf,
            'arguments': args,
            'strategie': strat,
            'precedents_cites': prec,
            'precedents_count': prec_count,
            'lois': lois,
            'taux_acquittement': taux,
            'type_detecte': typ,
            'supervision': sup.get('decision', sup.get('agents_verifies', '')),
            'temps': elapsed
        })

    except requests.exceptions.Timeout:
        elapsed = round(time.time() - start, 1)
        print(f"TIMEOUT ({elapsed}s)")
        results.append({'ticket': t, 'status': 'TIMEOUT', 'temps': elapsed})
    except Exception as e:
        elapsed = round(time.time() - start, 1)
        print(f"EXCEPTION: {e} ({elapsed}s)")
        results.append({'ticket': t, 'status': 'EXCEPTION', 'error': str(e), 'temps': elapsed})

# === RAPPORT FINAL ===
print(f"\n{'='*80}")
print(f"  RAPPORT FINAL — {len(results)} tickets traités")
print(f"{'='*80}\n")

ok = [r for r in results if r['status'] == 'OK']
err = [r for r in results if r['status'] != 'OK']

print(f"Succès: {len(ok)}/{total}  |  Erreurs: {len(err)}/{total}\n")

if ok:
    temps_moy = round(sum(r['temps'] for r in ok) / len(ok), 1)
    score_moy = round(sum(r['score'] for r in ok) / len(ok), 1)
    scores = [r['score'] for r in ok]
    contester = sum(1 for r in ok if r['recommandation'] == 'contester')
    negocier = sum(1 for r in ok if r['recommandation'] == 'negocier')
    payer = sum(1 for r in ok if r['recommandation'] == 'payer')

    print(f"Score moyen: {score_moy}/100  |  Min: {min(scores)}  |  Max: {max(scores)}")
    print(f"Temps moyen: {temps_moy}s")
    print(f"Verdicts: Contester={contester}  Négocier={negocier}  Payer={payer}\n")

    print(f"{'#':<3} {'Infraction':<45} {'Lieu':<25} {'Score':<6} {'Verdict':<10} {'Conf':<5} {'Args':<5} {'Préc':<5} {'Taux%':<6} {'Temps':<6}")
    print("-" * 130)
    for i, r in enumerate(ok):
        inf = r['ticket']['infraction'][:44]
        lieu = r['ticket']['lieu'][:24]
        taux = str(r.get('taux_acquittement',''))[:5]
        print(f"{i+1:<3} {inf:<45} {lieu:<25} {r['score']:<6} {r['recommandation']:<10} {str(r['confiance']):<5} {len(r['arguments']):<5} {r['precedents_count']:<5} {taux:<6} {r['temps']:<6}")

    # Détails des arguments et précédents
    print(f"\n{'='*80}")
    print(f"  DÉTAILS PAR TICKET")
    print(f"{'='*80}")
    for i, r in enumerate(ok):
        print(f"\n--- Ticket {i+1}: {r['ticket']['infraction']} ---")
        print(f"    Lieu: {r['ticket']['lieu']}")
        print(f"    Score: {r['score']}/100 | Verdict: {r['recommandation'].upper()} | Confiance: {r['confiance']}")
        print(f"    Type détecté: {r['type_detecte']}")
        if r.get('taux_acquittement'):
            print(f"    Taux acquittement historique: {r['taux_acquittement']}%")
        if r['strategie']:
            print(f"    Stratégie: {r['strategie']}...")
        if r['arguments']:
            print(f"    Arguments ({len(r['arguments'])}):")
            for j, a in enumerate(r['arguments']):
                print(f"      {j+1}. {a[:150]}")
        if r['precedents_cites']:
            print(f"    Précédents cités ({len(r['precedents_cites'])}):")
            for p in r['precedents_cites'][:3]:
                cit = p.get('citation','')[:80]
                res = p.get('resultat','')
                print(f"      - {cit} → {res}")

if err:
    print(f"\n{'='*80}")
    print(f"  ERREURS ({len(err)})")
    print(f"{'='*80}")
    for r in err:
        print(f"  - {r['ticket']['infraction'][:50]}: {r['status']} — {r.get('error', r.get('code', ''))}")

print(f"\n{'='*80}")
print(f"  FIN DE L'AUDIT — {time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*80}\n")
