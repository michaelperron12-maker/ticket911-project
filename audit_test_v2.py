"""
AUDIT V2: 10 vrais tickets avec PREUVES ENRICHIES vs prediction AI
- Resume + moyens defense + article CSR + motifs juge
- Recherche precedents similaires dans la DB
- Lois applicables
"""
import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

from agents.base_agent import BaseAgent, GROQ_LLAMA70B
import psycopg2

agent = BaseAgent("Audit_V2")

# Charger les 10 dossiers avec toutes les preuves
conn = agent.get_db()
cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
cur.execute("""
    SELECT id, citation, resultat, type_infraction, article_csr,
           resume, moyens_defense, motifs_juge, date_decision, lois_pertinentes
    FROM jurisprudence
    WHERE id IN (56645, 56666, 56954, 56721, 57915, 56783, 5474, 2247, 56946, 5720)
    ORDER BY id
""")
cases = [dict(r) for r in cur.fetchall()]

SYSTEM = """Tu es un analyste juridique expert en droit routier quebecois avec acces a la jurisprudence et aux lois.
On te donne les faits d'un dossier + des precedents similaires + les lois applicables.
Tu dois predire le verdict probable SANS connaitre le jugement final.
Reponds UNIQUEMENT en JSON:
{"verdict_predit": "acquitte|coupable|reduit|rejete", "score_contestation": 0-100, "confiance": 0-100, "raison": "2 phrases max"}"""

print("=" * 70)
print("AUDIT V2 — AVEC PREUVES ENRICHIES (precedents + lois)")
print("=" * 70)
print()

results = []
correct = 0

for i, case in enumerate(cases, 1):
    vrai = case["resultat"]
    infraction = case["type_infraction"] or "?"
    article = case["article_csr"] or "?"
    moyens = case["moyens_defense"] or []
    citation = case["citation"]

    # Chercher precedents similaires (meme type, exclure ce dossier)
    cur.execute("""
        SELECT citation, resultat, LEFT(resume, 200), moyens_defense
        FROM jurisprudence
        WHERE type_infraction = %s AND province = 'QC' AND id != %s
          AND resultat IN ('acquitte','coupable','reduit','rejete')
        ORDER BY RANDOM() LIMIT 5
    """, (infraction, case["id"]))
    precedents = cur.fetchall()

    prec_txt = ""
    for p in precedents:
        prec_txt += f"  - {p[0]}: {p[1]} — {(p[2] or '')[:150]}\n"

    # Chercher loi applicable
    loi_txt = ""
    if article and article != "?":
        import re
        art_num = re.search(r'(\d+(?:\.\d+)?)', article)
        if art_num:
            cur.execute("""
                SELECT article, titre_article, LEFT(texte_complet, 300), amende_min, amende_max, points_inaptitude_min, points_inaptitude_max
                FROM lois_articles WHERE article = %s AND province = 'QC' LIMIT 1
            """, (art_num.group(1),))
            loi = cur.fetchone()
            if loi:
                loi_txt = f"Art. {loi[0]} — {loi[1] or ''}\n  Texte: {(loi[2] or '')[:250]}\n  Amende: {loi[3]}-{loi[4]}$ | Points: {loi[5]}-{loi[6]}"

    # Construire prompt SANS le verdict
    prompt = f"""DOSSIER #{i} — {citation}
Type: {infraction}
Article: {article}
Juridiction: Quebec (Cour municipale)
Date: {case.get('date_decision', '?')}

RESUME DES FAITS (sans verdict):
{(case['resume'] or '?')}

MOYENS DE DEFENSE INVOQUES:
{json.dumps(moyens, ensure_ascii=False) if moyens else 'Non specifies'}

LOI APPLICABLE:
{loi_txt if loi_txt else 'Non trouvee'}

PRECEDENTS SIMILAIRES ({len(precedents)} cas):
{prec_txt if prec_txt else 'Aucun precedent trouve'}

Analyse les preuves et predit le verdict."""

    print(f"[{i}/10] {citation} ({infraction}, art. {article})")

    start = time.time()
    resp = agent.call_ai(prompt, system_prompt=SYSTEM, model=GROQ_LLAMA70B, temperature=0.1, max_tokens=400)
    dur = time.time() - start

    if resp["success"]:
        try:
            data = agent.parse_json_response(resp["text"])
            predit = data.get("verdict_predit", "?")
            score = data.get("score_contestation", 0)
            confiance = data.get("confiance", 0)
            raison = data.get("raison", "")

            match = predit == vrai
            if match:
                correct += 1

            sym = "OK" if match else "MISS"
            print(f"  Vrai: {vrai:10s} | AI: {predit:10s} | Score: {score}% | Confiance: {confiance}% | [{sym}] | {dur:.1f}s")
            print(f"  Raison: {raison[:120]}")
            results.append({"citation": citation, "vrai": vrai, "predit": predit,
                          "score": score, "confiance": confiance, "match": match, "time": round(dur, 1)})
        except Exception as e:
            print(f"  [PARSE ERROR] {str(e)[:80]}")
            results.append({"citation": citation, "vrai": vrai, "predit": "error", "match": False})
    else:
        print(f"  [AI ERROR] {resp.get('error', '?')[:80]}")
        results.append({"citation": citation, "vrai": vrai, "predit": "error", "match": False})
    print()

conn.close()

# Resume
print("=" * 70)
print(f"RESULTAT: {correct}/10 ({correct*10}%)")
print("=" * 70)
for r in results:
    sym = "OK  " if r["match"] else "MISS"
    print(f"  [{sym}] {r['citation']:25s} Vrai: {r['vrai']:10s} AI: {r['predit']:10s} Score:{r.get('score',0):3d}% Conf:{r.get('confiance',0):3d}%")

print()
avg_time = sum(r.get("time", 0) for r in results) / len(results) if results else 0
print(f"Temps moyen: {avg_time:.1f}s | Provider: Groq Llama 70B (gratuit)")
v1 = 70
print(f"Comparaison: V1 (sans preuves) = {v1}% | V2 (avec preuves) = {correct*10}%")
