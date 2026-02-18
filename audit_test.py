"""
AUDIT: 10 vrais tickets vs prediction AI
Prend des vrais dossiers, cache le verdict, fait analyser par les agents, compare.
"""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

from agents.base_agent import BaseAgent, GROQ_LLAMA70B

# 10 vrais dossiers (id, citation, vrai_verdict, type, resume SANS verdict)
CASES = [
    (56645, "2008 QCCM 70", "coupable", "feu_rouge",
     "Conducteur qui a tourne a gauche malgre un feu de circulation rouge, article 359 CSR."),
    (56666, "2008 QCCM 415", "acquitte", "feu_rouge",
     "Conducteur qui n'a pas pu s'immobiliser en toute securite lorsque le feu est passe au jaune."),
    (56954, "2007 QCCM 592", "acquitte", "feu_rouge",
     "Conducteur qui a traverse un feu rouge, chaussee verglacee, defense d'impossibilite invoquee."),
    (56721, "2008 QCCM 387", "acquitte", "feu_rouge",
     "Conducteur accuse d'avoir redemarre sur un feu rouge, vehicule deja immobilise a l'intersection."),
    (57915, "2006 QCCM 441", "acquitte", "exces_vitesse",
     "Accuse d'exces de vitesse, preuve basee sur l'odometre du vehicule de police."),
    (56783, "2007 QCCM 415", "acquitte", "exces_vitesse",
     "Accuse d'exces de vitesse, preuve du radar contestee, policier n'a pas pu etablir la vitesse reelle."),
    (5474, "2009 QCCM 466", "acquitte", "exces_vitesse",
     "Accuse d'exces de vitesse, radar utilise hors de la zone de 50 km/h requise."),
    (2247, "2015 QCCM 365", "coupable", "cellulaire",
     "Conducteur tenant un appareil cellulaire en main en conduisant, art. 443.1 CSR."),
    (56946, "2007 QCCM 605", "acquitte", "feu_rouge",
     "Vehicule immobilise sur chaussee glissante, infraction au Code de la securite routiere contestee."),
    (5720, "2008 QCCM 507", "acquitte", "exces_vitesse",
     "Accuse d'exces de vitesse, agent n'a pu identifier le vehicule cible par le radar apres un demi-tour."),
]

agent = BaseAgent("Audit_Test")

SYSTEM = """Tu es un analyste juridique expert en droit routier quebecois.
On te donne les faits d'un dossier de contravention routiere.
Tu dois predire le verdict probable (acquitte, coupable, reduit, rejete) et donner un score de contestation (0-100).
Reponds UNIQUEMENT en JSON:
{"verdict_predit": "acquitte|coupable|reduit|rejete", "score_contestation": 0-100, "raison": "1 phrase"}"""

print("=" * 70)
print("AUDIT — 10 VRAIS DOSSIERS vs PREDICTION AI")
print("=" * 70)
print()

results = []
correct = 0

for i, (case_id, citation, vrai_verdict, infraction, faits) in enumerate(CASES, 1):
    prompt = f"""DOSSIER #{i} — {citation}
Type: {infraction}
Juridiction: Quebec (Cour municipale)

FAITS:
{faits}

Predit le verdict et le score de contestation."""

    print(f"[{i}/10] {citation} ({infraction})")
    print(f"  Faits: {faits[:80]}...")

    start = time.time()
    resp = agent.call_ai(prompt, system_prompt=SYSTEM, model=GROQ_LLAMA70B, temperature=0.1, max_tokens=300)
    dur = time.time() - start

    if resp["success"]:
        try:
            data = agent.parse_json_response(resp["text"])
            predit = data.get("verdict_predit", "?")
            score = data.get("score_contestation", 0)
            raison = data.get("raison", "")

            match = predit == vrai_verdict
            if match:
                correct += 1

            symbol = "OK" if match else "MISS"
            print(f"  Vrai: {vrai_verdict:10s} | AI: {predit:10s} | Score: {score}% | [{symbol}] | {dur:.1f}s")
            print(f"  Raison AI: {raison[:100]}")
            results.append({"citation": citation, "vrai": vrai_verdict, "predit": predit,
                          "score": score, "match": match, "raison": raison, "time": round(dur, 1)})
        except Exception as e:
            print(f"  [PARSE ERROR] {str(e)[:80]}")
            results.append({"citation": citation, "vrai": vrai_verdict, "predit": "error", "match": False})
    else:
        print(f"  [AI ERROR] {resp.get('error', '?')[:80]}")
        results.append({"citation": citation, "vrai": vrai_verdict, "predit": "error", "match": False})
    print()

# Resume
print("=" * 70)
print(f"RESULTAT: {correct}/10 predictions correctes ({correct*10}%)")
print("=" * 70)
print()
for r in results:
    sym = "OK  " if r["match"] else "MISS"
    print(f"  [{sym}] {r['citation']:20s} Vrai: {r['vrai']:10s} AI: {r['predit']:10s} ({r.get('score',0)}%)")

print()
avg_time = sum(r.get("time", 0) for r in results) / len(results) if results else 0
print(f"Temps moyen: {avg_time:.1f}s par dossier")
print(f"Provider: Groq Llama 70B (gratuit, no thinking)")
