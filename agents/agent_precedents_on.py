"""
Agent ON: PRECEDENTS ONTARIO — FTS local + CanLII API (optionnel)
Recherche hybride FTS5 + ChromaDB specifique Ontario
ONCJ, ONSC, ONCA — Provincial Offences Act
"""

import sqlite3
import time
import os
from agents.base_agent import BaseAgent, DB_PATH

CANLII_API_KEY = os.environ.get("CANLII_API_KEY", "")


class AgentPrecedentsON(BaseAgent):

    def __init__(self):
        super().__init__("Precedents_ON")
        self.chroma_collection = None
        self._init_chroma()

    def _init_chroma(self):
        try:
            import chromadb
            client = chromadb.PersistentClient(path="/var/www/ticket911/data/embeddings")
            self.chroma_collection = client.get_or_create_collection(
                name="jurisprudence",
                metadata={"hnsw:space": "cosine"}
            )
        except Exception:
            self.chroma_collection = None

    def chercher_precedents(self, ticket, lois, n_results=10):
        """
        Input: ticket ON + lois HTA
        Output: precedents Ontario
        """
        infraction = ticket.get("infraction", "")
        self.log(f"Recherche precedents ON: {infraction[:50]}...", "STEP")
        start = time.time()

        fts_results = self._recherche_fts_on(infraction, n_results)
        self.log(f"  FTS local: {len(fts_results)} cas ON", "OK" if fts_results else "WARN")

        semantic_results = self._recherche_semantique_on(infraction, n_results)
        if semantic_results:
            self.log(f"  Semantique: {len(semantic_results)} cas ON", "OK")

        canlii_results = []
        if CANLII_API_KEY:
            canlii_results = self._recherche_canlii_on(infraction, lois)
            self.log(f"  CanLII ON: {len(canlii_results)} cas", "OK" if canlii_results else "WARN")

        # Fallback: cherche aussi dans les cas federaux (CSC) applicables a ON
        if len(fts_results) < 3:
            fallback = self._recherche_fts_federale(infraction, 5)
            if fallback:
                self.log(f"  Fallback federal: {len(fallback)} cas (CSC)", "OK")
                fts_results.extend(fallback)

        combined = self._combiner(fts_results, semantic_results, canlii_results)
        top = combined[:n_results]

        duration = time.time() - start
        self.log_run("chercher_precedents_on", f"ON {infraction[:100]}",
                     f"{len(top)} precedents ON", duration=duration)
        self.log(f"{len(top)} precedents ON trouves en {duration:.1f}s", "OK")
        return top

    def _recherche_fts_on(self, infraction, limit=15):
        results = []
        conn = self.get_db()
        c = conn.cursor()

        try:
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jurisprudence_fts'")
            if not c.fetchone():
                conn.close()
                return results

            queries = self._generer_requetes_on(infraction)
            seen_ids = set()
            for query in queries:
                try:
                    c.execute("""SELECT j.id, j.citation, j.tribunal, j.date_decision,
                                        j.resume, j.juridiction, j.resultat
                                 FROM jurisprudence_fts fts
                                 JOIN jurisprudence j ON fts.rowid = j.id
                                 WHERE jurisprudence_fts MATCH ?
                                 AND j.juridiction = 'ON'
                                 LIMIT ?""", (query, limit))
                    for row in c.fetchall():
                        if row[0] not in seen_ids:
                            seen_ids.add(row[0])
                            results.append({
                                "id": row[0], "citation": row[1], "tribunal": row[2],
                                "date": row[3], "resume": (row[4] or "")[:300],
                                "juridiction": row[5], "resultat": row[6] or "inconnu",
                                "source": "FTS-ON", "score": 75
                            })
                except sqlite3.OperationalError:
                    pass
        except Exception as e:
            self.log(f"Erreur FTS ON: {e}", "FAIL")

        conn.close()
        return results

    def _recherche_fts_federale(self, infraction, limit=5):
        """Fallback: CSC decisions applicable to Ontario"""
        results = []
        conn = self.get_db()
        c = conn.cursor()
        try:
            queries = self._generer_requetes_on(infraction)
            seen_ids = set()
            for query in queries:
                try:
                    c.execute("""SELECT j.id, j.citation, j.tribunal, j.date_decision,
                                        j.resume, j.juridiction, j.resultat
                                 FROM jurisprudence_fts fts
                                 JOIN jurisprudence j ON fts.rowid = j.id
                                 WHERE jurisprudence_fts MATCH ?
                                 AND j.tribunal IN ('CSC', 'SCC')
                                 LIMIT ?""", (query, limit))
                    for row in c.fetchall():
                        if row[0] not in seen_ids:
                            seen_ids.add(row[0])
                            results.append({
                                "id": row[0], "citation": row[1], "tribunal": row[2],
                                "date": row[3], "resume": (row[4] or "")[:300],
                                "juridiction": "ON", "resultat": row[6] or "inconnu",
                                "source": "FTS-Federal", "score": 60
                            })
                except sqlite3.OperationalError:
                    pass
        except Exception as e:
            self.log(f"Erreur FTS Federal: {e}", "FAIL")
        conn.close()
        return results

    def _recherche_semantique_on(self, infraction, n_results=10):
        if not self.chroma_collection or self.chroma_collection.count() == 0:
            return []

        results = []
        try:
            chroma_results = self.chroma_collection.query(
                query_texts=[f"{infraction} Ontario HTA Highway Traffic Act"],
                n_results=n_results,
                where={"juridiction": "ON"}
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
                        "juridiction": "ON",
                        "resultat": metadata.get("resultat", "inconnu"),
                        "source": "Semantic-ON", "score": round(similarity, 1)
                    })
        except Exception as e:
            self.log(f"Erreur semantique ON: {e}", "WARN")

        return results

    def _recherche_canlii_on(self, infraction, lois):
        """CanLII API v1 — Ontario databases"""
        results = []
        if not CANLII_API_KEY:
            return results
        try:
            import requests
            databases = ["oncj", "onsc", "onca"]
            for db_id in databases:
                params = {
                    "api_key": CANLII_API_KEY,
                    "offset": 0,
                    "resultCount": 3
                }
                resp = requests.get(f"https://api.canlii.org/v1/caseBrowse/{db_id}/",
                                    params=params, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("cases", [])[:3]:
                        results.append({
                            "id": f"CANLII-ON-{item.get('caseId', {}).get('en', '')}",
                            "citation": item.get("citation", item.get("title", ""))[:100],
                            "tribunal": db_id.upper(),
                            "date": item.get("date", ""),
                            "resume": item.get("title", "")[:300],
                            "juridiction": "ON",
                            "resultat": "inconnu",
                            "source": "CanLII-ON", "score": 55
                        })
                if len(results) >= 5:
                    break
        except Exception as e:
            self.log(f"CanLII ON erreur: {e}", "WARN")
        return results

    def _combiner(self, fts, semantic, canlii):
        all_results = {}
        for r in fts + semantic + canlii:
            key = r.get("citation", r.get("id", ""))
            if key not in all_results:
                all_results[key] = r
            else:
                all_results[key]["score"] = min(100, all_results[key]["score"] + 15)
        return sorted(all_results.values(), key=lambda x: x.get("score", 0), reverse=True)

    def _generer_requetes_on(self, infraction):
        queries = []
        lower = infraction.lower()

        if any(w in lower for w in ["speed", "vitesse", "km/h", "speeding", "radar", "lidar"]):
            queries.extend(["speeding OR speed OR radar", "HTA 128", "lidar OR radar"])
        if any(w in lower for w in ["red light", "feu rouge", "traffic signal"]):
            queries.extend(["red light OR traffic signal", "HTA 144"])
        if any(w in lower for w in ["cell", "phone", "handheld", "distracted", "texting"]):
            queries.extend(["handheld OR distracted OR cell phone", "HTA 78"])
        if any(w in lower for w in ["stop", "arret", "stop sign"]):
            queries.extend(["stop sign OR fail to stop", "HTA 136"])
        if any(w in lower for w in ["careless", "dangereuse", "dangerous"]):
            queries.extend(["careless driving", "HTA 130"])
        if any(w in lower for w in ["stunt", "racing", "course", "street racing"]):
            queries.extend(["stunt driving OR racing", "HTA 172"])
        if any(w in lower for w in ["seatbelt", "ceinture", "belt"]):
            queries.extend(["seatbelt OR seat belt", "HTA 106"])
        if any(w in lower for w in ["impaired", "dui", "alcohol", "alcool"]):
            queries.extend(["impaired driving OR alcohol", "Criminal Code 253"])

        if not queries:
            words = [w for w in lower.split() if len(w) > 3][:3]
            queries = [" OR ".join(words)] if words else ["traffic Ontario HTA"]

        return queries
