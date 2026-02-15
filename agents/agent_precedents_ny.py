"""
Agent NY: PRECEDENTS NEW YORK — CourtListener + local DB
Recherche hybride pour jurisprudence NY (TVB, Supreme Court, Appellate)
PostgreSQL tsvector backend
"""

import time
import json
import os
from agents.base_agent import BaseAgent

COURTLISTENER_TOKEN = os.environ.get("COURTLISTENER_TOKEN", "")


class AgentPrecedentsNY(BaseAgent):

    def __init__(self):
        super().__init__("Precedents_NY")
        self.chroma_collection = None
        self._init_chroma()

    def _init_chroma(self):
        try:
            import chromadb
            client = chromadb.PersistentClient(path="/var/www/aiticketinfo/data/embeddings")
            self.chroma_collection = client.get_or_create_collection(
                name="jurisprudence",
                metadata={"hnsw:space": "cosine"}
            )
        except Exception:
            self.chroma_collection = None

    def chercher_precedents(self, ticket, lois, n_results=10):
        """
        Input: ticket NY + lois VTL
        Output: precedents NY (local DB + CourtListener si dispo)
        """
        infraction = ticket.get("infraction", "")
        self.log(f"Recherche precedents NY: {infraction[:50]}...", "STEP")
        start = time.time()

        # 1. Recherche locale FTS
        fts_results = self._recherche_fts_ny(infraction, n_results)
        self.log(f"  FTS local: {len(fts_results)} cas NY", "OK" if fts_results else "WARN")

        # 2. Recherche semantique locale
        semantic_results = self._recherche_semantique_ny(infraction, n_results)
        self.log(f"  Semantique: {len(semantic_results)} cas NY", "OK" if semantic_results else "WARN")

        # 3. CourtListener API (si token dispo)
        cl_results = []
        if COURTLISTENER_TOKEN:
            cl_results = self._recherche_courtlistener(infraction)
            self.log(f"  CourtListener: {len(cl_results)} cas", "OK" if cl_results else "WARN")
        else:
            self.log("  CourtListener: token non configure", "WARN")

        # Combiner
        combined = self._combiner(fts_results, semantic_results, cl_results)
        top = combined[:n_results]

        # 4. Enrichir avec jurisprudence_citations (716 liens entre cas)
        jids = [p.get("id") for p in top if p.get("id") and isinstance(p.get("id"), int)]
        if jids:
            citations_links = self._fetch_jurisprudence_citations(jids)
            if citations_links:
                self.log(f"  Citations links: {len(citations_links)} liens entre cas", "OK")
                links_by_parent = {}
                for cl in citations_links:
                    pid = cl["parent_id"]
                    if pid not in links_by_parent:
                        links_by_parent[pid] = []
                    links_by_parent[pid].append(cl)
                for p in top:
                    pid = p.get("id")
                    if pid in links_by_parent:
                        p["cas_lies"] = links_by_parent[pid]

        duration = time.time() - start
        self.log_run("chercher_precedents_ny", f"NY {infraction[:100]}",
                     f"{len(top)} precedents NY (+{len(jids)} enrichis)", duration=duration)
        self.log(f"{len(top)} precedents NY trouves en {duration:.1f}s", "OK")
        return top

    def _recherche_fts_ny(self, infraction, limit=15):
        results = []
        conn = self.get_db()
        c = conn.cursor()

        try:
            queries = self._generer_requetes_ny(infraction)
            for query in queries:
                try:
                    c.execute("""SELECT j.id, j.citation, j.tribunal, j.date_decision,
                                        j.resume, j.province, j.resultat
                                 FROM jurisprudence j
                                 WHERE j.tsv_en @@ to_tsquery('english', %s)
                                 AND j.province = 'NY'
                                 LIMIT %s""", (query, limit))
                    for row in c.fetchall():
                        results.append({
                            "id": row[0], "citation": row[1], "tribunal": row[2],
                            "date": row[3], "resume": (row[4] or "")[:300],
                            "juridiction": row[5], "resultat": row[6] or "inconnu",
                            "source": "FTS-NY", "score": 70
                        })
                except Exception:
                    pass
        except Exception as e:
            self.log(f"Erreur FTS NY: {e}", "FAIL")

        conn.close()
        return results

    def _recherche_semantique_ny(self, infraction, n_results=10):
        if not self.chroma_collection or self.chroma_collection.count() == 0:
            return []

        results = []
        try:
            chroma_results = self.chroma_collection.query(
                query_texts=[f"{infraction} New York VTL"],
                n_results=n_results,
                where={"juridiction": "NY"}
            )
            if chroma_results and chroma_results["ids"][0]:
                for i, doc_id in enumerate(chroma_results["ids"][0]):
                    metadata = chroma_results["metadatas"][0][i] if chroma_results["metadatas"] else {}
                    distance = chroma_results["distances"][0][i] if chroma_results["distances"] else 1.0
                    similarity = max(0, (1 - distance / 2)) * 100
                    results.append({
                        "id": metadata.get("db_id", doc_id),
                        "citation": metadata.get("citation", doc_id),
                        "tribunal": metadata.get("tribunal", ""),
                        "date": metadata.get("date", ""),
                        "resume": (chroma_results["documents"][0][i] or "")[:300],
                        "juridiction": "NY",
                        "resultat": metadata.get("resultat", "inconnu"),
                        "source": "Semantic-NY", "score": round(similarity, 1)
                    })
        except Exception as e:
            self.log(f"Erreur semantique NY: {e}", "WARN")

        return results

    def _recherche_courtlistener(self, infraction):
        """Recherche via CourtListener API (opinions NY traffic)"""
        results = []
        try:
            import requests
            headers = {"Authorization": f"Token {COURTLISTENER_TOKEN}"}
            params = {
                "q": f"{infraction} traffic violation",
                "court": "nyappdiv,nysupcl,nycrimct",
                "type": "o",
                "order_by": "score desc",
                "page_size": 5
            }
            resp = requests.get("https://www.courtlistener.com/api/rest/v4/search/",
                                headers=headers, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("results", [])[:5]:
                    results.append({
                        "id": f"CL-{item.get('id', '')}",
                        "citation": item.get("caseName", item.get("case_name", ""))[:100],
                        "tribunal": item.get("court", "NY Court"),
                        "date": item.get("dateFiled", item.get("date_filed", "")),
                        "resume": (item.get("snippet", "") or "")[:300],
                        "juridiction": "NY",
                        "resultat": "inconnu",
                        "source": "CourtListener", "score": 60
                    })
        except Exception as e:
            self.log(f"CourtListener erreur: {e}", "WARN")
        return results

    def _combiner(self, fts, semantic, courtlistener):
        all_results = {}
        for r in fts + semantic + courtlistener:
            key = r.get("citation", r.get("id", ""))
            if key not in all_results:
                all_results[key] = r
            else:
                all_results[key]["score"] = min(100, all_results[key]["score"] + 15)
        return sorted(all_results.values(), key=lambda x: x.get("score", 0), reverse=True)

    def _generer_requetes_ny(self, infraction):
        queries = []
        lower = infraction.lower()
        if any(w in lower for w in ["speed", "speeding", "mph", "vitesse"]):
            queries.extend(["speeding | speed & limit", "VTL & 1180", "radar | lidar"])
        if any(w in lower for w in ["red light", "traffic signal", "feu rouge"]):
            queries.extend(["red & light | traffic & signal", "VTL & 1111"])
        if any(w in lower for w in ["cell phone", "texting", "handheld"]):
            queries.extend(["cell & phone | texting", "VTL & 1225"])
        if any(w in lower for w in ["stop sign"]):
            queries.extend(["stop & sign", "VTL & 1172"])
        if not queries:
            words = [w for w in lower.split() if len(w) > 3][:3]
            queries = [" | ".join(words)] if words else ["traffic & violation & NY"]
        return queries
