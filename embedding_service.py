"""
ScanTicket V1 — Embedding Service (Fireworks API)
Utilise qwen3-embedding-8b via l'API Fireworks (OpenAI-compatible)
Stocke dans PostgreSQL pgvector — zero PyTorch, zero RAM locale
"""

import os
import time
import psycopg2
import psycopg2.extras
from openai import OpenAI

# --- Config ---
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY", "fw_CVMaHgWPEZyTLgFFHj3E3a")
EMBEDDING_MODEL = "fireworks/qwen3-embedding-8b"  # 4096 dims, bilingue FR/EN
EMBEDDING_DIM = 4096
BATCH_SIZE = 50  # Fireworks supporte jusqu'a ~100, 50 = safe + rapide

DB_CONFIG = {
    "host": "172.18.0.3",
    "port": 5432,
    "dbname": "tickets_qc_on",
    "user": "ticketdb_user",
    "password": "Tk911PgSecure2026"
}


class EmbeddingService:

    def __init__(self):
        self.client = OpenAI(
            api_key=FIREWORKS_API_KEY,
            base_url="https://api.fireworks.ai/inference/v1"
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed une liste de textes via Fireworks API. Retourne les vecteurs."""
        if not texts:
            return []

        # Nettoyer les textes vides
        cleaned = [t.strip()[:8000] if t else "vide" for t in texts]

        resp = self.client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=cleaned
        )
        return [d.embedding for d in resp.data]

    def embed_single(self, text: str) -> list[float]:
        """Embed un seul texte."""
        return self.embed_texts([text])[0]

    def get_db(self):
        return psycopg2.connect(**DB_CONFIG)

    def build_embed_text(self, row: dict) -> str:
        """Construit le texte optimal a embedder pour un dossier jurisprudence."""
        parts = []

        titre = (row.get("titre") or "").strip()
        if titre:
            parts.append(titre)

        citation = (row.get("citation") or "").strip()
        if citation:
            parts.append(f"Citation: {citation}")

        tribunal = (row.get("tribunal") or "").strip()
        if tribunal:
            parts.append(f"Tribunal: {tribunal}")

        resume = (row.get("resume") or "").strip()
        if resume:
            parts.append(resume)

        mots_cles = row.get("mots_cles")
        if mots_cles:
            if isinstance(mots_cles, list):
                clean = ", ".join(str(m) for m in mots_cles if m)
            else:
                clean = str(mots_cles).strip("{}").replace(",", ", ")
            if clean:
                parts.append(f"Mots-cles: {clean}")

        resultat = (row.get("resultat") or "").strip()
        if resultat:
            parts.append(f"Resultat: {resultat}")

        province = (row.get("province") or "").strip()
        if province:
            parts.append(f"Province: {province}")

        text = " | ".join(parts)
        return text[:8000] if text else "dossier sans contenu"

    def populate_all(self, force=False):
        """Embed tous les dossiers sans embedding (ou tous si force=True)."""
        conn = self.get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        if force:
            cur.execute("SELECT id, titre, citation, tribunal, resume, mots_cles, resultat, province FROM jurisprudence ORDER BY id")
        else:
            cur.execute("SELECT id, titre, citation, tribunal, resume, mots_cles, resultat, province FROM jurisprudence WHERE embedding IS NULL ORDER BY id")

        rows = cur.fetchall()
        total = len(rows)

        if total == 0:
            print("Tous les dossiers ont deja un embedding.")
            cur.close()
            conn.close()
            return

        print(f"Dossiers a embedder: {total}")
        embedded = 0
        total_tokens = 0
        start = time.time()

        for i in range(0, total, BATCH_SIZE):
            batch = rows[i:i + BATCH_SIZE]
            texts = [self.build_embed_text(dict(r)) for r in batch]
            ids = [r["id"] for r in batch]

            try:
                resp = self.client.embeddings.create(
                    model=EMBEDDING_MODEL,
                    input=texts
                )
                embeddings = [d.embedding for d in resp.data]
                total_tokens += resp.usage.prompt_tokens

                # Bulk update PostgreSQL
                update_cur = conn.cursor()
                for doc_id, emb in zip(ids, embeddings):
                    vec_str = "[" + ",".join(str(x) for x in emb) + "]"
                    update_cur.execute(
                        "UPDATE jurisprudence SET embedding = %s::vector WHERE id = %s",
                        (vec_str, doc_id)
                    )
                conn.commit()
                update_cur.close()

                embedded += len(batch)
                elapsed = time.time() - start
                rate = embedded / elapsed if elapsed > 0 else 0
                print(f"  [{embedded}/{total}] {rate:.1f} docs/s | {total_tokens} tokens")

            except Exception as e:
                print(f"  ERREUR batch {i}-{i+len(batch)}: {e}")
                conn.rollback()
                time.sleep(2)

        elapsed = time.time() - start
        cost = total_tokens / 1_000_000 * 0.10
        print(f"\nTermine: {embedded}/{total} dossiers en {elapsed:.1f}s")
        print(f"Tokens: {total_tokens} | Cout: ${cost:.4f}")

        cur.close()
        conn.close()

    def search(self, query: str, top_k: int = 50, juridiction: str = None) -> list[dict]:
        """Recherche semantique pgvector — cosine similarity."""
        query_emb = self.embed_single(query)
        vec_str = "[" + ",".join(str(x) for x in query_emb) + "]"

        conn = self.get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        prov_filter = ""
        params = {"vec": vec_str, "limit": top_k}
        if juridiction:
            prov_filter = "AND province = %(prov)s"
            params["prov"] = juridiction

        cur.execute(f"""
            SELECT id, titre, citation, tribunal, resume, resultat,
                   province, date_decision,
                   1 - (embedding <=> %(vec)s::vector) AS similarity
            FROM jurisprudence
            WHERE embedding IS NOT NULL {prov_filter}
            ORDER BY embedding <=> %(vec)s::vector
            LIMIT %(limit)s
        """, params)

        results = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return results

    def hybrid_search(self, query: str, top_k: int = 50, juridiction: str = None) -> list[dict]:
        """
        Recherche hybride: tsvector (keyword) + pgvector (semantic)
        Combine les deux scores avec ponderation.
        """
        query_emb = self.embed_single(query)
        vec_str = "[" + ",".join(str(x) for x in query_emb) + "]"

        conn = self.get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        jur_filter = ""
        params = []
        if juridiction:
            jur_filter = "AND province = %(jur)s"
            params_dict = {"query": query, "vec": vec_str, "jur": juridiction, "limit": top_k}
        else:
            params_dict = {"query": query, "vec": vec_str, "limit": top_k}

        # Score hybride: 0.4 * keyword + 0.6 * semantic
        cur.execute(f"""
            WITH semantic AS (
                SELECT id,
                       1 - (embedding <=> %(vec)s::vector) AS sem_score
                FROM jurisprudence
                WHERE embedding IS NOT NULL {jur_filter}
                ORDER BY embedding <=> %(vec)s::vector
                LIMIT 200
            ),
            keyword AS (
                SELECT id,
                       ts_rank(tsv_fr, plainto_tsquery('french', %(query)s)) +
                       ts_rank(tsv_en, plainto_tsquery('english', %(query)s)) AS kw_score
                FROM jurisprudence
                WHERE (tsv_fr @@ plainto_tsquery('french', %(query)s)
                    OR tsv_en @@ plainto_tsquery('english', %(query)s))
                {jur_filter}
            )
            SELECT j.id, j.titre, j.citation, j.tribunal, j.resume,
                   j.resultat, j.province, j.date_decision,
                   COALESCE(s.sem_score, 0) AS sem_score,
                   COALESCE(k.kw_score, 0) AS kw_score,
                   0.6 * COALESCE(s.sem_score, 0) + 0.4 * COALESCE(k.kw_score, 0) AS hybrid_score
            FROM jurisprudence j
            LEFT JOIN semantic s ON j.id = s.id
            LEFT JOIN keyword k ON j.id = k.id
            WHERE (s.id IS NOT NULL OR k.id IS NOT NULL)
            ORDER BY hybrid_score DESC
            LIMIT %(limit)s
        """, params_dict)

        results = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return results


# Singleton
embedding_service = EmbeddingService()
