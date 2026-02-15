"""
Agent ON: PRECEDENTS ONTARIO — PostgreSQL tsvector + ChromaDB (optionnel)
Recherche hybride tsvector GIN specifique Ontario
ONCJ, ONSC, ONCA — Provincial Offences Act
"""

import time
import os
from agents.base_agent import BaseAgent, CANLII_API_KEY


class AgentPrecedentsON(BaseAgent):

    def __init__(self):
        super().__init__("Precedents_ON")
        self.chroma_collection = None
        self._init_chroma()

    def _init_chroma(self):
        try:
            import chromadb
            _proj = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            client = chromadb.PersistentClient(path=os.path.join(_proj, "data", "embeddings"))
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

        fts_results = self._recherche_tsvector_on(infraction, n_results)
        self.log(f"  PostgreSQL tsvector: {len(fts_results)} cas ON", "OK" if fts_results else "WARN")

        semantic_results = self._recherche_semantique_on(infraction, n_results)
        if semantic_results:
            self.log(f"  Semantique: {len(semantic_results)} cas ON", "OK")

        canlii_results = []
        if CANLII_API_KEY:
            canlii_results = self._recherche_canlii_on(infraction, lois)
            self.log(f"  CanLII ON: {len(canlii_results)} cas", "OK" if canlii_results else "WARN")

        # Fallback federal
        if len(fts_results) < 3:
            fallback = self._recherche_tsvector_federale(infraction, 5)
            if fallback:
                self.log(f"  Fallback federal: {len(fallback)} cas (CSC)", "OK")
                fts_results.extend(fallback)

        combined = self._combiner(fts_results, semantic_results, canlii_results)
        top = combined[:n_results]

        # 5. Enrichir avec jurisprudence_citations (716 liens entre cas)
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
        self.log_run("chercher_precedents_on", f"ON {infraction[:100]}",
                     f"{len(top)} precedents ON (+{len(jids)} enrichis)", duration=duration)
        self.log(f"{len(top)} precedents ON trouves en {duration:.1f}s", "OK")
        return top

    def _recherche_tsvector_on(self, infraction, limit=15):
        """Recherche tsvector PostgreSQL dans la table jurisprudence"""
        results = []
        try:
            conn = self.get_db()
            cur = conn.cursor()
            queries = self._generer_requetes_on(infraction)
            seen_ids = set()

            # Priorite 1: tribunaux traffic (ONCJ, ONSCDC)
            for query in queries:
                try:
                    cur.execute("""
                        SELECT j.id, j.citation, j.database_id, j.date_decision,
                               j.resume, j.province, j.resultat,
                               ts_rank(j.tsv_en, to_tsquery('english', %s)) AS rank
                        FROM jurisprudence j
                        WHERE j.province = 'ON'
                          AND j.database_id IN ('oncj', 'onscdc')
                          AND j.tsv_en @@ to_tsquery('english', %s)
                        ORDER BY rank DESC
                        LIMIT %s
                    """, (query, query, limit))
                    for row in cur.fetchall():
                        if row[0] not in seen_ids:
                            seen_ids.add(row[0])
                            results.append({
                                "id": row[0], "citation": row[1],
                                "tribunal": (row[2] or "").upper(),
                                "date": str(row[3]) if row[3] else "",
                                "resume": (row[4] or "")[:300],
                                "juridiction": row[5] or "ON",
                                "resultat": row[6] or "inconnu",
                                "source": "PostgreSQL-ON", "score": 85
                            })
                except Exception:
                    pass

            # Priorite 2: ONCA (Court of Appeal)
            if len(results) < limit:
                for query in queries:
                    try:
                        cur.execute("""
                            SELECT j.id, j.citation, j.database_id, j.date_decision,
                                   j.resume, j.province, j.resultat
                            FROM jurisprudence j
                            WHERE j.province = 'ON'
                              AND j.database_id = 'onca'
                              AND j.tsv_en @@ to_tsquery('english', %s)
                            LIMIT %s
                        """, (query, limit - len(results)))
                        for row in cur.fetchall():
                            if row[0] not in seen_ids:
                                seen_ids.add(row[0])
                                results.append({
                                    "id": row[0], "citation": row[1],
                                    "tribunal": (row[2] or "").upper(),
                                    "date": str(row[3]) if row[3] else "",
                                    "resume": (row[4] or "")[:300],
                                    "juridiction": row[5] or "ON",
                                    "resultat": row[6] or "inconnu",
                                    "source": "PostgreSQL-ON", "score": 65
                                })
                    except Exception:
                        pass

            # Priorite 3: recherche ILIKE si tsvector donne rien
            if not results:
                infraction_words = [w for w in infraction.lower().split() if len(w) > 3][:3]
                if infraction_words:
                    pattern = f"%{'%'.join(infraction_words)}%"
                    try:
                        cur.execute("""
                            SELECT j.id, j.citation, j.database_id, j.date_decision,
                                   j.resume, j.province, j.resultat
                            FROM jurisprudence j
                            WHERE j.province = 'ON'
                              AND (j.titre ILIKE %s OR j.resume ILIKE %s)
                            ORDER BY j.date_decision DESC NULLS LAST
                            LIMIT %s
                        """, (pattern, pattern, limit))
                        for row in cur.fetchall():
                            if row[0] not in seen_ids:
                                seen_ids.add(row[0])
                                results.append({
                                    "id": row[0], "citation": row[1],
                                    "tribunal": (row[2] or "").upper(),
                                    "date": str(row[3]) if row[3] else "",
                                    "resume": (row[4] or "")[:300],
                                    "juridiction": row[5] or "ON",
                                    "resultat": row[6] or "inconnu",
                                    "source": "PostgreSQL-ILIKE-ON", "score": 50
                                })
                    except Exception:
                        pass

            conn.close()
        except Exception as e:
            self.log(f"Erreur tsvector ON: {e}", "FAIL")
        return results

    def _recherche_tsvector_federale(self, infraction, limit=5):
        """Fallback: CSC decisions applicable to Ontario"""
        results = []
        try:
            conn = self.get_db()
            cur = conn.cursor()
            queries = self._generer_requetes_on(infraction)
            seen_ids = set()
            for query in queries:
                try:
                    cur.execute("""
                        SELECT j.id, j.citation, j.database_id, j.date_decision,
                               j.resume, j.province, j.resultat
                        FROM jurisprudence j
                        WHERE j.database_id IN ('scc', 'csc')
                          AND j.tsv_en @@ to_tsquery('english', %s)
                        LIMIT %s
                    """, (query, limit))
                    for row in cur.fetchall():
                        if row[0] not in seen_ids:
                            seen_ids.add(row[0])
                            results.append({
                                "id": row[0], "citation": row[1],
                                "tribunal": (row[2] or "").upper(),
                                "date": str(row[3]) if row[3] else "",
                                "resume": (row[4] or "")[:300],
                                "juridiction": "ON",
                                "resultat": row[6] or "inconnu",
                                "source": "PostgreSQL-Federal", "score": 60
                            })
                except Exception:
                    pass
            conn.close()
        except Exception as e:
            self.log(f"Erreur tsvector Federal: {e}", "FAIL")
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
        """CanLII API v1 — Ontario databases (rate-limited via BaseAgent)"""
        results = []
        databases = ["oncj", "onscdc", "onca"]
        for db_id in databases:
            cases = self.canlii_search_cases(db_id, result_count=5)
            for item in cases[:3]:
                case_id = item.get("caseId", {})
                cid = case_id.get("en", "") if isinstance(case_id, dict) else str(case_id)
                results.append({
                    "id": f"CANLII-ON-{cid}",
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
        remaining = self.canlii_remaining_quota()
        if remaining < 100:
            self.log(f"CanLII quota bas: {remaining} restant", "WARN")
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
            queries.extend(["speeding | speed | radar", "lidar | radar"])
        if any(w in lower for w in ["red light", "feu rouge", "traffic signal"]):
            queries.extend(["red & light | traffic & signal"])
        if any(w in lower for w in ["cell", "phone", "handheld", "distracted", "texting"]):
            queries.extend(["handheld | distracted | cell & phone"])
        if any(w in lower for w in ["stop", "arret", "stop sign"]):
            queries.extend(["stop & sign | fail & stop"])
        if any(w in lower for w in ["careless", "dangereuse", "dangerous"]):
            queries.extend(["careless & driving"])
        if any(w in lower for w in ["stunt", "racing", "course", "street racing"]):
            queries.extend(["stunt & driving | racing"])
        if any(w in lower for w in ["seatbelt", "ceinture", "belt"]):
            queries.extend(["seatbelt | seat & belt"])
        if any(w in lower for w in ["impaired", "dui", "alcohol", "alcool"]):
            queries.extend(["impaired & driving | alcohol"])

        if not queries:
            words = [w for w in lower.split() if len(w) > 3][:3]
            queries = [" & ".join(words)] if words else ["traffic & ontario"]

        return queries
