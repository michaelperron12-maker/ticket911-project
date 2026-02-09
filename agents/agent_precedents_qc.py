"""
Agent QC: PRECEDENTS QUEBEC — CanLII + local DB
Recherche hybride FTS + ChromaDB specifique Quebec
Cour municipale, Cour superieure, Cour d'appel du Quebec
"""

import sqlite3
import time
import os
from agents.base_agent import BaseAgent, DB_PATH


class AgentPrecedentsQC(BaseAgent):

    def __init__(self):
        super().__init__("Precedents_QC")
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
        Input: ticket QC + lois CSR
        Output: precedents QC (Cour municipale, CS, CA)
        """
        infraction = ticket.get("infraction", "")
        self.log(f"Recherche precedents QC: {infraction[:50]}...", "STEP")
        start = time.time()

        # 1. FTS local
        fts_results = self._recherche_fts_qc(infraction, n_results)
        self.log(f"  FTS local: {len(fts_results)} cas QC", "OK" if fts_results else "WARN")

        # 2. Semantique
        semantic_results = self._recherche_semantique_qc(infraction, n_results)
        self.log(f"  Semantique: {len(semantic_results)} cas QC", "OK" if semantic_results else "WARN")

        # 3. CanLII (si articles de loi connus)
        canlii_results = []
        if lois:
            canlii_results = self._recherche_canlii(infraction, lois)
            self.log(f"  CanLII: {len(canlii_results)} cas", "OK" if canlii_results else "WARN")

        # Combiner
        combined = self._combiner(fts_results, semantic_results, canlii_results)
        top = combined[:n_results]

        duration = time.time() - start
        self.log_run("chercher_precedents_qc", f"QC {infraction[:100]}",
                     f"{len(top)} precedents QC", duration=duration)
        self.log(f"{len(top)} precedents QC trouves en {duration:.1f}s", "OK")
        return top

    def _recherche_fts_qc(self, infraction, limit=15):
        results = []
        conn = self.get_db()
        c = conn.cursor()

        try:
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jurisprudence_fts'")
            if not c.fetchone():
                conn.close()
                return results

            queries = self._generer_requetes_qc(infraction)
            for query in queries:
                try:
                    c.execute("""SELECT j.id, j.citation, j.tribunal, j.date_decision,
                                        j.resume, j.juridiction, j.resultat
                                 FROM jurisprudence_fts fts
                                 JOIN jurisprudence j ON fts.rowid = j.id
                                 WHERE jurisprudence_fts MATCH ?
                                 AND j.juridiction = 'QC'
                                 LIMIT ?""", (query, limit))
                    for row in c.fetchall():
                        results.append({
                            "id": row[0], "citation": row[1], "tribunal": row[2],
                            "date": row[3], "resume": (row[4] or "")[:300],
                            "juridiction": row[5], "resultat": row[6] or "inconnu",
                            "source": "FTS-QC", "score": 70
                        })
                except sqlite3.OperationalError:
                    pass
        except Exception as e:
            self.log(f"Erreur FTS QC: {e}", "FAIL")

        conn.close()
        return results

    def _recherche_semantique_qc(self, infraction, n_results=10):
        if not self.chroma_collection or self.chroma_collection.count() == 0:
            return []

        results = []
        try:
            chroma_results = self.chroma_collection.query(
                query_texts=[f"{infraction} Quebec CSR Code securite routiere"],
                n_results=n_results,
                where={"juridiction": "QC"}
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
                        "juridiction": "QC",
                        "resultat": metadata.get("resultat", "inconnu"),
                        "source": "Semantic-QC", "score": round(similarity, 1)
                    })
        except Exception as e:
            self.log(f"Erreur semantique QC: {e}", "WARN")

        return results

    def _recherche_canlii(self, infraction, lois):
        """Recherche CanLII API pour jurisprudence QC additionnelle"""
        results = []
        try:
            import requests
            # CanLII API gratuite — jurisprudence quebecoise
            query = infraction[:80]
            params = {
                "q": query,
                "jurisdiction": "qc",
                "resultCount": 5
            }
            resp = requests.get("https://api.canlii.org/v1/caseBrowse/qc/",
                                params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("cases", [])[:5]:
                    results.append({
                        "id": f"CANLII-{item.get('caseId', '')}",
                        "citation": item.get("citation", item.get("title", ""))[:100],
                        "tribunal": item.get("court", "Cour QC"),
                        "date": item.get("date", ""),
                        "resume": item.get("title", "")[:300],
                        "juridiction": "QC",
                        "resultat": "inconnu",
                        "source": "CanLII", "score": 55
                    })
        except Exception as e:
            self.log(f"CanLII erreur: {e}", "WARN")
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

        if any(w in lower for w in ["vitesse", "excès", "exces", "km/h", "radar"]):
            queries.extend(["vitesse OR excès OR radar", "cinémomètre OR photo radar",
                           "art 299 OR art 303"])
        if any(w in lower for w in ["feu rouge", "signalisation"]):
            queries.extend(["feu rouge OR signalisation", "art 328 OR art 359"])
        if any(w in lower for w in ["cellulaire", "telephone", "portable"]):
            queries.extend(["cellulaire OR téléphone OR appareil", "art 443.1"])
        if any(w in lower for w in ["stop", "arrêt", "arret"]):
            queries.extend(["arrêt OR stop", "panneau arrêt"])
        if any(w in lower for w in ["alcool", "ivresse", "facultes"]):
            queries.extend(["alcool OR facultés affaiblies", "alcootest OR ivressomètre"])
        if any(w in lower for w in ["ceinture"]):
            queries.extend(["ceinture sécurité"])

        if not queries:
            words = [w for w in lower.split() if len(w) > 3][:3]
            queries = [" OR ".join(words)] if words else ["contravention Quebec"]

        return queries
