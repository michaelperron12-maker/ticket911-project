"""
Agent QC: PRECEDENTS QUEBEC — PostgreSQL tsvector + ChromaDB (optionnel)
Recherche hybride tsvector GIN specifique Quebec
Cour municipale (QCCM), Cour du Quebec (QCCQ), CS, CA du Quebec
"""

import time
from agents.base_agent import BaseAgent, CANLII_API_KEY


class AgentPrecedentsQC(BaseAgent):

    def __init__(self):
        super().__init__("Precedents_QC")
        self._embedding_service = None

    def _get_embedding_service(self):
        if self._embedding_service is None:
            try:
                import sys
                sys.path.insert(0, "/var/www/aiticketinfo")
                from embedding_service import embedding_service
                self._embedding_service = embedding_service
            except Exception as e:
                self.log(f"Embedding service indisponible: {e}", "WARN")
        return self._embedding_service

    def chercher_precedents(self, ticket, lois, n_results=10):
        """
        Input: ticket QC + lois CSR
        Output: precedents QC (Cour municipale, CS, CA)
        """
        infraction = ticket.get("infraction", "")
        self.log(f"Recherche precedents QC: {infraction[:50]}...", "STEP")
        start = time.time()

        # 1. PostgreSQL tsvector — recherche principale
        fts_results = self._recherche_tsvector_qc(infraction, n_results)
        self.log(f"  PostgreSQL tsvector: {len(fts_results)} cas QC", "OK" if fts_results else "WARN")

        # 2. Semantique (ChromaDB si disponible)
        semantic_results = self._recherche_semantique_qc(infraction, n_results)
        if semantic_results:
            self.log(f"  Semantique: {len(semantic_results)} cas QC", "OK")

        # 3. CanLII API (si cle configuree)
        canlii_results = []
        if CANLII_API_KEY:
            canlii_results = self._recherche_canlii(infraction, lois)
            self.log(f"  CanLII: {len(canlii_results)} cas", "OK" if canlii_results else "WARN")

        # 4. Fallback: recherche elargie si peu de resultats QC
        if len(fts_results) < 3:
            fallback = self._recherche_tsvector_federale(infraction, 5)
            if fallback:
                self.log(f"  Fallback federal: {len(fallback)} cas (CSC/CA)", "OK")
                fts_results.extend(fallback)

        # Combiner et deduplication
        combined = self._combiner(fts_results, semantic_results, canlii_results)
        top = combined[:n_results]

        # 5. Enrichir avec jurisprudence_citations (716 liens entre cas)
        jids = [p.get("id") for p in top if p.get("id") and isinstance(p.get("id"), int)]
        if jids:
            citations_links = self._fetch_jurisprudence_citations(jids)
            if citations_links:
                self.log(f"  Citations links: {len(citations_links)} liens entre cas", "OK")
                # Attacher les cas liés à chaque precedent
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
        self.log_run("chercher_precedents_qc", f"QC {infraction[:100]}",
                     f"{len(top)} precedents QC (+{len(jids)} enrichis)", duration=duration)
        self.log(f"{len(top)} precedents QC trouves en {duration:.1f}s", "OK")
        return top

    def _recherche_tsvector_qc(self, infraction, limit=15):
        """Recherche tsvector PostgreSQL dans la table jurisprudence"""
        results = []
        try:
            conn = self.get_db()
            cur = conn.cursor()
            queries = self._generer_requetes_qc(infraction)
            seen_ids = set()

            # Priorite 1: Cour municipale et Cour du Quebec — cases traffic directes
            for query in queries:
                try:
                    cur.execute("""
                        SELECT j.id, j.citation, j.database_id, j.date_decision,
                               j.resume, j.province, j.resultat,
                               ts_rank(j.tsv_fr, to_tsquery('french', %s)) AS rank
                        FROM jurisprudence j
                        WHERE j.province = 'QC'
                          AND j.database_id IN ('qccm', 'qccq', 'qccs', 'qcca')
                          AND j.tsv_fr @@ to_tsquery('french', %s)
                        ORDER BY rank DESC
                        LIMIT %s
                    """, (query, query, limit))
                    for row in cur.fetchall():
                        if row[0] not in seen_ids:
                            seen_ids.add(row[0])
                            tribunal_score = 90 if row[2] == 'qccm' else 85 if row[2] == 'qccq' else 75
                            results.append({
                                "id": row[0], "citation": row[1],
                                "tribunal": (row[2] or "").upper(),
                                "date": str(row[3]) if row[3] else "",
                                "resume": (row[4] or "")[:300],
                                "juridiction": row[5] or "QC",
                                "resultat": row[6] or "inconnu",
                                "source": "PostgreSQL-QC", "score": tribunal_score
                            })
                except Exception:
                    pass

            # Priorite 2: tout QC (tsvector)
            if len(results) < limit:
                for query in queries:
                    try:
                        cur.execute("""
                            SELECT j.id, j.citation, j.database_id, j.date_decision,
                                   j.resume, j.province, j.resultat
                            FROM jurisprudence j
                            WHERE j.province = 'QC'
                              AND j.tsv_fr @@ to_tsquery('french', %s)
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
                                    "juridiction": row[5] or "QC",
                                    "resultat": row[6] or "inconnu",
                                    "source": "PostgreSQL-QC", "score": 65
                                })
                    except Exception:
                        pass

            # Priorite 3: recherche ILIKE titre/resume si tsvector donne rien
            if not results:
                infraction_words = [w for w in infraction.lower().split() if len(w) > 3][:3]
                if infraction_words:
                    pattern = f"%{'%'.join(infraction_words)}%"
                    try:
                        cur.execute("""
                            SELECT j.id, j.citation, j.database_id, j.date_decision,
                                   j.resume, j.province, j.resultat
                            FROM jurisprudence j
                            WHERE j.province = 'QC'
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
                                    "juridiction": row[5] or "QC",
                                    "resultat": row[6] or "inconnu",
                                    "source": "PostgreSQL-ILIKE-QC", "score": 50
                                })
                    except Exception:
                        pass

            conn.close()
        except Exception as e:
            self.log(f"Erreur tsvector QC: {e}", "FAIL")
        return results

    def _recherche_tsvector_federale(self, infraction, limit=5):
        """Fallback: cherche precedents federaux (CSC) applicables au QC"""
        results = []
        try:
            conn = self.get_db()
            cur = conn.cursor()
            queries = self._generer_requetes_qc(infraction)
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
                                "juridiction": "QC",
                                "resultat": row[6] or "inconnu",
                                "source": "PostgreSQL-Federal", "score": 60
                            })
                except Exception:
                    pass
            conn.close()
        except Exception as e:
            self.log(f"Erreur tsvector Federal: {e}", "FAIL")
        return results

    def _recherche_semantique_qc(self, infraction, n_results=10):
        svc = self._get_embedding_service()
        if not svc:
            return []

        results = []
        try:
            pgvec_results = svc.search(
                f"{infraction} Quebec CSR Code securite routiere",
                top_k=n_results,
                juridiction="QC"
            )
            for r in pgvec_results:
                similarity = max(0, r.get("similarity", 0)) * 100
                results.append({
                    "id": r.get("id"),
                    "citation": r.get("citation", ""),
                    "tribunal": r.get("tribunal", ""),
                    "date": str(r.get("date_decision", "")) if r.get("date_decision") else "",
                    "resume": (r.get("resume") or "")[:300],
                    "juridiction": "QC",
                    "resultat": r.get("resultat", "inconnu"),
                    "source": "pgvector-QC", "score": round(similarity, 1)
                })
        except Exception as e:
            self.log(f"Erreur pgvector QC: {e}", "WARN")

        return results

    def _recherche_canlii(self, infraction, lois):
        """Recherche CanLII API v1 — rate-limited via BaseAgent"""
        results = []
        databases = ["qccm", "qccq", "qccs", "qcca"]
        for db_id in databases:
            cases = self.canlii_search_cases(db_id, result_count=5)
            for item in cases[:3]:
                case_id = item.get("caseId", {})
                cid = case_id.get("en", "") if isinstance(case_id, dict) else str(case_id)
                results.append({
                    "id": f"CANLII-{cid}",
                    "citation": item.get("citation", item.get("title", ""))[:100],
                    "tribunal": db_id.upper(),
                    "date": item.get("date", ""),
                    "resume": item.get("title", "")[:300],
                    "juridiction": "QC",
                    "resultat": "inconnu",
                    "source": "CanLII-QC", "score": 55
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

    def _generer_requetes_qc(self, infraction):
        queries = []
        lower = infraction.lower()

        if any(w in lower for w in ["vitesse", "excès", "exces", "km/h", "radar", "photo radar", "cinémomètre"]):
            queries.extend(["vitesse | exces | radar", "cinematometre | photo & radar"])
        if any(w in lower for w in ["feu rouge", "feu", "signalisation", "lumiere"]):
            queries.extend(["feu & rouge | signalisation"])
        if any(w in lower for w in ["cellulaire", "telephone", "portable", "texte", "texto"]):
            queries.extend(["cellulaire | telephone | appareil"])
        if any(w in lower for w in ["stop", "arrêt", "arret"]):
            queries.extend(["arret | stop", "panneau & arret"])
        if any(w in lower for w in ["alcool", "ivresse", "facultes", "alcootest", "capacité affaiblie"]):
            queries.extend(["alcool | facultes & affaiblies"])
        if any(w in lower for w in ["ceinture"]):
            queries.extend(["ceinture & securite"])
        if any(w in lower for w in ["dangereuse", "dangereux", "imprudent"]):
            queries.extend(["conduite & dangereuse"])
        if any(w in lower for w in ["permis", "suspendu", "suspension"]):
            queries.extend(["permis & suspendu | conduite & sans & permis"])

        if not queries:
            words = [w for w in lower.split() if len(w) > 3][:3]
            queries = [" & ".join(words)] if words else ["contravention & quebec"]

        return queries
