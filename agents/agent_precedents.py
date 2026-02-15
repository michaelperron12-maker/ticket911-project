"""
Agent 3: CHERCHEUR DE PRECEDENTS — LE COEUR du systeme
Recherche hybride: PostgreSQL tsvector (mots-cles) + ChromaDB (semantique)
Ne retourne QUE des cas qui existent REELLEMENT dans la base
"""

import time
import json
from agents.base_agent import BaseAgent


class AgentPrecedents(BaseAgent):

    def __init__(self):
        super().__init__("Precedents")
        self.chroma_collection = None
        self._init_chroma()

    def _init_chroma(self):
        """Tente de charger ChromaDB si disponible"""
        try:
            import chromadb
            client = chromadb.PersistentClient(path="/var/www/aiticketinfo/data/embeddings")
            self.chroma_collection = client.get_or_create_collection(
                name="jurisprudence",
                metadata={"hnsw:space": "cosine"}
            )
            count = self.chroma_collection.count()
            if count > 0:
                self.log(f"ChromaDB charge: {count} documents", "OK")
        except Exception as e:
            self.log(f"ChromaDB non disponible: {e} — FTS uniquement", "WARN")
            self.chroma_collection = None

    def chercher_precedents(self, ticket, lois, n_results=10):
        """
        Input: ticket (dict) + lois trouvees (list)
        Output: liste de precedents REELS avec score de pertinence
        """
        infraction = ticket.get("infraction", "")
        juridiction = ticket.get("juridiction", "")
        self.log(f"Recherche precedents: {infraction[:50]}... ({juridiction})", "STEP")
        start = time.time()

        # --- 1. Recherche par mots-cles (PostgreSQL tsvector) ---
        fts_results = self._recherche_fts(infraction, juridiction)
        self.log(f"  FTS: {len(fts_results)} cas trouves", "OK" if fts_results else "WARN")

        # --- 2. Recherche semantique (ChromaDB) ---
        semantic_results = self._recherche_semantique(infraction, juridiction, n_results)
        self.log(f"  Semantique: {len(semantic_results)} cas trouves", "OK" if semantic_results else "WARN")

        # --- 3. Combiner et re-ranker ---
        combined = self._combiner_resultats(fts_results, semantic_results)
        self.log(f"  Combine: {len(combined)} cas uniques", "OK")

        # Limiter aux top N
        top_results = combined[:n_results]

        duration = time.time() - start
        self.log_run("chercher_precedents", f"{infraction[:100]} ({juridiction})",
                      f"{len(top_results)} precedents", duration=duration)

        for i, r in enumerate(top_results[:5], 1):
            self.log(f"  #{i} [{r.get('score', 0):.0f}%] {r.get('citation', '?')[:60]} -> {r.get('resultat', '?')}", "OK")

        self.log(f"{len(top_results)} precedents reels trouves en {duration:.1f}s", "OK")
        return top_results

    def _recherche_fts(self, infraction, juridiction, limit=20):
        """Recherche tsvector dans PostgreSQL"""
        results = []
        conn = self.get_db()
        c = conn.cursor()

        try:
            # Choisir la colonne tsvector et la config selon la juridiction
            if juridiction == "QC":
                tsv_col = "j.tsv_fr"
                ts_config = "french"
            else:
                tsv_col = "j.tsv_en"
                ts_config = "english"

            # Generer des requetes FTS
            queries = self._generer_requetes_fts(infraction, juridiction)

            for query in queries:
                try:
                    c.execute(f"""SELECT j.id, j.citation, j.tribunal, j.date_decision,
                                        j.resume, j.texte_complet, j.province, j.resultat
                                 FROM jurisprudence j
                                 WHERE {tsv_col} @@ to_tsquery(%s, %s)
                                 AND j.province = %s
                                 LIMIT %s""", (ts_config, query, juridiction, limit))

                    for row in c.fetchall():
                        results.append({
                            "id": row[0], "citation": row[1], "tribunal": row[2],
                            "date": row[3], "resume": (row[4] or "")[:300],
                            "juridiction": row[6], "resultat": row[7] or "inconnu",
                            "source": "FTS", "query": query, "score": 70
                        })
                except Exception:
                    pass

            # Fallback: recherche sans filtre juridiction
            if not results:
                for query in queries[:2]:
                    try:
                        c.execute(f"""SELECT j.id, j.citation, j.tribunal, j.date_decision,
                                            j.resume, j.texte_complet, j.province, j.resultat
                                     FROM jurisprudence j
                                     WHERE {tsv_col} @@ to_tsquery(%s, %s)
                                     LIMIT %s""", (ts_config, query, limit))
                        for row in c.fetchall():
                            results.append({
                                "id": row[0], "citation": row[1], "tribunal": row[2],
                                "date": row[3], "resume": (row[4] or "")[:300],
                                "juridiction": row[6], "resultat": row[7] or "inconnu",
                                "source": "FTS-all", "query": query, "score": 50
                            })
                    except Exception:
                        pass
        except Exception as e:
            self.log(f"Erreur FTS: {e}", "FAIL")

        conn.close()
        return results

    def _recherche_semantique(self, infraction, juridiction, n_results=10):
        """Recherche par similarite semantique dans ChromaDB"""
        if not self.chroma_collection or self.chroma_collection.count() == 0:
            return []

        results = []
        try:
            query_text = f"{infraction} {juridiction}"
            chroma_results = self.chroma_collection.query(
                query_texts=[query_text],
                n_results=n_results,
                where={"juridiction": juridiction} if juridiction else None
            )

            if chroma_results and chroma_results["ids"][0]:
                for i, doc_id in enumerate(chroma_results["ids"][0]):
                    metadata = chroma_results["metadatas"][0][i] if chroma_results["metadatas"] else {}
                    distance = chroma_results["distances"][0][i] if chroma_results["distances"] else 1.0
                    # ChromaDB cosine distance: 0 = identique, 2 = oppose
                    similarity = max(0, (1 - distance / 2)) * 100

                    results.append({
                        "id": metadata.get("db_id", doc_id),
                        "citation": metadata.get("citation", doc_id),
                        "tribunal": metadata.get("tribunal", ""),
                        "date": metadata.get("date", ""),
                        "resume": (chroma_results["documents"][0][i] or "")[:300],
                        "juridiction": metadata.get("juridiction", ""),
                        "resultat": metadata.get("resultat", "inconnu"),
                        "source": "Semantic",
                        "score": round(similarity, 1)
                    })
        except Exception as e:
            self.log(f"Erreur semantique: {e}", "WARN")

        return results

    def _combiner_resultats(self, fts_results, semantic_results):
        """Combine FTS + semantique, deduplique et re-rank"""
        all_results = {}

        # Ajouter FTS
        for r in fts_results:
            key = r.get("citation", r.get("id", ""))
            if key not in all_results:
                all_results[key] = r
            else:
                # Boost le score si trouve par les deux methodes
                all_results[key]["score"] = min(100, all_results[key]["score"] + 20)

        # Ajouter semantique
        for r in semantic_results:
            key = r.get("citation", r.get("id", ""))
            if key not in all_results:
                all_results[key] = r
            else:
                all_results[key]["score"] = min(100, all_results[key]["score"] + 15)
                all_results[key]["source"] = "FTS+Semantic"

        # Trier par score decroissant
        combined = sorted(all_results.values(), key=lambda x: x.get("score", 0), reverse=True)
        return combined

    def _generer_requetes_fts(self, infraction, juridiction):
        """Genere des variantes de requetes FTS"""
        queries = []
        lower = infraction.lower()

        if any(w in lower for w in ["vitesse", "speed", "excès", "exces", "km/h"]):
            queries.extend(["vitesse | speeding | speed", "radar | cinémomètre",
                           "excès & vitesse", "limite & vitesse"])
        if any(w in lower for w in ["feu rouge", "red light"]):
            queries.extend(["feu & rouge | red & light", "signalisation | signal"])
        if any(w in lower for w in ["cellulaire", "phone", "handheld"]):
            queries.extend(["cellulaire | téléphone | handheld", "appareil | device"])
        if any(w in lower for w in ["stop", "arrêt"]):
            queries.extend(["arrêt | stop", "panneau & arrêt | stop & sign"])

        if not queries:
            words = [w for w in lower.split() if len(w) > 3][:3]
            queries = [" | ".join(words)] if words else ["contravention"]

        return queries
