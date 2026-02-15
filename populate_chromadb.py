#!/usr/bin/env python3
"""
Populate ChromaDB embeddings from SQLite jurisprudence
Run: python3 populate_chromadb.py
"""

import sqlite3
import chromadb

import os
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_PROJECT_DIR, "db", "aiticketinfo.db")
CHROMA_PATH = os.path.join(_PROJECT_DIR, "data", "embeddings")


def main():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    coll = client.get_or_create_collection("jurisprudence", metadata={"hnsw:space": "cosine"})
    print(f"ChromaDB collection: {coll.count()} documents")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Get QC and ON cases with resumes
    c.execute("""SELECT id, citation, tribunal, juridiction, date_decision,
                        resume, resultat, mots_cles
                 FROM jurisprudence
                 WHERE juridiction IN ('QC', 'ON')
                 AND resume IS NOT NULL
                 AND length(resume) > 10""")
    rows = c.fetchall()
    print(f"Cases to embed: {len(rows)}")

    batch_ids = []
    batch_docs = []
    batch_metas = []

    for row in rows:
        doc_id = f"juris-{row[0]}"
        doc_text = f"{row[1]} {row[5]} {row[7] or ''}"
        meta = {
            "db_id": row[0],
            "citation": row[1] or "",
            "tribunal": row[2] or "",
            "juridiction": row[3] or "",
            "date": row[4] or "",
            "resultat": row[6] or "inconnu"
        }
        batch_ids.append(doc_id)
        batch_docs.append(doc_text[:1000])
        batch_metas.append(meta)

    # Upsert in batches
    batch_size = 50
    for i in range(0, len(batch_ids), batch_size):
        end = min(i + batch_size, len(batch_ids))
        coll.upsert(
            ids=batch_ids[i:end],
            documents=batch_docs[i:end],
            metadatas=batch_metas[i:end]
        )
        print(f"  Batch {i // batch_size + 1}: {end - i} docs")

    print(f"\nChromaDB total: {coll.count()} documents")

    # Test QC
    results = coll.query(
        query_texts=["exces de vitesse radar cinematometre Quebec"],
        n_results=3,
        where={"juridiction": "QC"}
    )
    print(f"\nTest QC 'vitesse': {len(results['ids'][0])} results")
    for i, doc_id in enumerate(results["ids"][0]):
        meta = results["metadatas"][0][i]
        dist = results["distances"][0][i]
        print(f"  {meta['citation'][:50]} | dist={dist:.3f} | {meta['resultat']}")

    # Test ON
    results = coll.query(
        query_texts=["speeding radar highway Ontario"],
        n_results=3,
        where={"juridiction": "ON"}
    )
    print(f"\nTest ON 'speeding': {len(results['ids'][0])} results")
    for i, doc_id in enumerate(results["ids"][0]):
        meta = results["metadatas"][0][i]
        dist = results["distances"][0][i]
        print(f"  {meta['citation'][:50]} | dist={dist:.3f} | {meta['resultat']}")

    conn.close()


if __name__ == "__main__":
    main()
