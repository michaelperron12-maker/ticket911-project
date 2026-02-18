"""Test rapide des 3 nouveaux providers AI — Groq, SambaNova, Cerebras"""
import os
import sys
import time

# Charger le .env
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

from openai import OpenAI

PROMPT = "Reponds en 1 phrase: quel est le delai pour contester un constat d'infraction au Quebec?"

PROVIDERS = [
    {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key": os.environ.get("GROQ_API_KEY", ""),
        "models": [
            ("llama-3.3-70b-versatile", "Llama 3.3 70B"),
            ("llama-3.1-8b-instant", "Llama 3.1 8B"),
            ("mixtral-8x7b-32768", "Mixtral 8x7B"),
        ]
    },
    {
        "name": "SambaNova",
        "base_url": "https://api.sambanova.ai/v1",
        "api_key": os.environ.get("SAMBANOVA_API_KEY", ""),
        "models": [
            ("Meta-Llama-3.3-70B-Instruct", "Llama 3.3 70B"),
            ("DeepSeek-V3-0324", "DeepSeek V3"),
        ]
    },
    {
        "name": "Cerebras",
        "base_url": "https://api.cerebras.ai/v1",
        "api_key": os.environ.get("CEREBRAS_API_KEY", ""),
        "models": [
            ("llama3.1-8b", "Llama 3.1 8B"),
        ]
    },
]

print("=" * 70)
print("TEST PROVIDERS AI — AITicketInfo")
print("=" * 70)
print(f"Prompt: {PROMPT}")
print()

results = []

for provider in PROVIDERS:
    print(f"--- {provider['name']} ---")
    if not provider["api_key"]:
        print(f"  [SKIP] Pas de cle API pour {provider['name']}")
        print()
        continue

    client = OpenAI(
        api_key=provider["api_key"],
        base_url=provider["base_url"],
        timeout=30.0
    )

    for model_id, model_name in provider["models"]:
        try:
            start = time.time()
            response = client.chat.completions.create(
                model=model_id,
                messages=[{"role": "user", "content": PROMPT}],
                temperature=0.1,
                max_tokens=200
            )
            duration = time.time() - start
            text = response.choices[0].message.content
            tokens = response.usage.total_tokens if response.usage else 0
            tps = tokens / duration if duration > 0 else 0

            print(f"  [OK] {model_name} ({model_id})")
            print(f"       Temps: {duration:.2f}s | Tokens: {tokens} | Vitesse: {tps:.0f} t/s")
            print(f"       Reponse: {text[:150]}...")
            results.append({
                "provider": provider["name"],
                "model": model_name,
                "model_id": model_id,
                "duration": round(duration, 2),
                "tokens": tokens,
                "tps": round(tps, 0),
                "status": "OK"
            })
        except Exception as e:
            duration = time.time() - start
            print(f"  [FAIL] {model_name} ({model_id})")
            print(f"         Erreur: {str(e)[:200]}")
            results.append({
                "provider": provider["name"],
                "model": model_name,
                "model_id": model_id,
                "duration": round(duration, 2),
                "status": "FAIL",
                "error": str(e)[:100]
            })
        print()

# Resume
print("=" * 70)
print("RESUME")
print("=" * 70)
ok = [r for r in results if r["status"] == "OK"]
fail = [r for r in results if r["status"] == "FAIL"]
print(f"Reussis: {len(ok)}/{len(results)}")
if ok:
    fastest = min(ok, key=lambda x: x["duration"])
    print(f"Plus rapide: {fastest['provider']} {fastest['model']} — {fastest['duration']}s ({fastest['tps']:.0f} t/s)")
if fail:
    print(f"\nEchecs ({len(fail)}):")
    for f in fail:
        print(f"  - {f['provider']} {f['model']}: {f.get('error', '?')}")
