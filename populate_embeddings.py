#!/usr/bin/env python3
"""
ScanTicket V1 — Populate embeddings dans PostgreSQL pgvector
Usage:
    python3 populate_embeddings.py              # Embed seulement les nouveaux
    python3 populate_embeddings.py --force      # Re-embed tout
    python3 populate_embeddings.py --stats      # Afficher stats
    python3 populate_embeddings.py --test       # Tester une recherche
"""

import sys
import psycopg2
import psycopg2.extras

DB_CONFIG = {
    "host": "172.18.0.3",
    "port": 5432,
    "dbname": "tickets_qc_on",
    "user": "ticketdb_user",
    "password": "Tk911PgSecure2026"
}


def show_stats():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute("SELECT count(*) FROM jurisprudence")
    total = cur.fetchone()[0]

    cur.execute("SELECT count(*) FROM jurisprudence WHERE embedding IS NOT NULL")
    embedded = cur.fetchone()[0]

    cur.execute("SELECT count(*) FROM jurisprudence WHERE embedding IS NULL")
    missing = cur.fetchone()[0]

    cur.execute("""
        SELECT province, count(*) as total,
               count(embedding) as embedded
        FROM jurisprudence
        GROUP BY province ORDER BY total DESC
    """)
    by_prov = cur.fetchall()

    cur.execute("""
        SELECT resultat, count(*) as total,
               count(embedding) as embedded
        FROM jurisprudence
        WHERE resultat IS NOT NULL
        GROUP BY resultat ORDER BY total DESC
        LIMIT 10
    """)
    by_resultat = cur.fetchall()

    print(f"\n=== STATS EMBEDDINGS ===")
    print(f"Total dossiers:  {total}")
    print(f"Avec embedding:  {embedded} ({embedded/total*100:.1f}%)" if total else "")
    print(f"Sans embedding:  {missing}")

    print(f"\nPar province:")
    for prov, t, e in by_prov:
        print(f"  {prov or '?':5} : {e}/{t} embedded")

    print(f"\nPar resultat:")
    for res, t, e in by_resultat:
        print(f"  {res or '?':15} : {e}/{t} embedded")

    cur.close()
    conn.close()


def test_search():
    from embedding_service import embedding_service

    queries = [
        ("exces de vitesse radar photo contestation", None),
        ("cellulaire au volant amende", "QC"),
        ("speeding school zone radar", "ON"),
        ("feu rouge camera automatique", None),
        ("alcool au volant refus souffler", None),
    ]

    for query, jur in queries:
        print(f"\n{'='*60}")
        print(f"QUERY: {query}" + (f" (jur={jur})" if jur else ""))
        print(f"{'='*60}")

        results = embedding_service.hybrid_search(query, top_k=5, juridiction=jur)

        if not results:
            print("  Aucun resultat.")
            continue

        for i, r in enumerate(results, 1):
            print(f"  #{i} [hybrid={r['hybrid_score']:.4f} sem={r['sem_score']:.4f} kw={r['kw_score']:.4f}]")
            print(f"      {r['titre'][:80] if r['titre'] else '?'}")
            print(f"      {r['citation'] or '?'} | {r['tribunal'] or '?'} | {r['resultat'] or '?'}")


def main():
    args = sys.argv[1:]

    if "--stats" in args:
        show_stats()
        return

    if "--test" in args:
        test_search()
        return

    force = "--force" in args

    from embedding_service import embedding_service
    print("=== ScanTicket V1 — Populate Embeddings ===")
    print(f"Modele: {embedding_service.client._base_url}")
    print(f"Force re-embed: {force}")
    print()

    embedding_service.populate_all(force=force)
    print()
    show_stats()


if __name__ == "__main__":
    main()
