"""
Agent QC: PRECEDENTS QUEBEC — PostgreSQL tsvector + ChromaDB (optionnel)
Recherche hybride tsvector GIN specifique Quebec
V2: Requetes specifiques au ticket + diversification + recherche par article/mots_cles
"""

import re
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
        V2: Recherche specifique au ticket + diversification resultats
        """
        infraction = ticket.get("infraction", "")
        self.log(f"Recherche precedents QC: {infraction[:50]}...", "STEP")
        start = time.time()

        # Extraire le contexte specifique du ticket
        contexte = self._extraire_contexte_ticket(ticket)
        self.log(f"  Contexte: {contexte.get('type', '?')} | Tags: {contexte.get('tags', [])}", "INFO")

        # 1. PostgreSQL tsvector — requetes SPECIFIQUES au ticket
        fts_results = self._recherche_tsvector_qc(ticket, contexte, n_results)
        self.log(f"  PostgreSQL tsvector: {len(fts_results)} cas QC", "OK" if fts_results else "WARN")

        # 2. Recherche par article de loi cite
        article_results = self._recherche_par_article(ticket, lois, n_results)
        if article_results:
            self.log(f"  Par article loi: {len(article_results)} cas QC", "OK")

        # 3. Recherche par mots_cles array (index GIN)
        mots_cles_results = self._recherche_par_mots_cles(contexte, n_results)
        if mots_cles_results:
            self.log(f"  Par mots-cles: {len(mots_cles_results)} cas QC", "OK")

        # 4. Semantique (ChromaDB si disponible)
        semantic_results = self._recherche_semantique_qc(ticket, contexte, n_results)
        if semantic_results:
            self.log(f"  Semantique: {len(semantic_results)} cas QC", "OK")

        # 5. CanLII API (si cle configuree)
        canlii_results = []
        if CANLII_API_KEY:
            canlii_results = self._recherche_canlii(infraction, lois)
            self.log(f"  CanLII: {len(canlii_results)} cas", "OK" if canlii_results else "WARN")

        # 6. Combiner, diversifier et equilibrer acquittes/coupables
        combined = self._combiner_et_diversifier(
            fts_results, article_results, mots_cles_results,
            semantic_results, canlii_results,
            n_results
        )
        top = combined[:n_results]

        # 7. Enrichir avec jurisprudence_citations
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
        # Stats acquitte vs coupable
        nb_acquitte = sum(1 for p in top if p.get("resultat", "").lower() in ("acquitte", "accueilli"))
        nb_coupable = sum(1 for p in top if p.get("resultat", "").lower() in ("coupable", "condamne"))
        self.log_run("chercher_precedents_qc", f"QC {infraction[:100]}",
                     f"{len(top)} precedents ({nb_acquitte}A/{nb_coupable}C)", duration=duration)
        self.log(f"{len(top)} precedents QC ({nb_acquitte} acquittes, {nb_coupable} coupables) en {duration:.1f}s", "OK")
        return top

    def _extraire_contexte_ticket(self, ticket):
        """Extraire le contexte specifique du ticket pour personnaliser les requetes"""
        ctx = {
            "type": "general",
            "tags": [],
            "queries_specifiques": [],
            "mots_cles_recherche": [],
        }

        infraction = (ticket.get("infraction", "") or "").lower()
        lieu = (ticket.get("lieu", "") or "").lower()
        appareil = (ticket.get("appareil", "") or "").lower()
        vehicule = (ticket.get("vehicule", "") or "").lower()
        loi = (ticket.get("loi", "") or "").lower()

        v_captee = ticket.get("vitesse_captee")
        v_permise = ticket.get("vitesse_permise")
        exces = 0
        if v_captee and v_permise:
            try:
                exces = int(v_captee) - int(v_permise)
            except (ValueError, TypeError):
                pass

        # === TYPE D'INFRACTION ===
        if any(w in infraction for w in ["vitesse", "excès", "exces", "km/h"]):
            ctx["type"] = "vitesse"
            ctx["mots_cles_recherche"].extend(["vitesse", "excès de vitesse"])

            # Sous-type par appareil
            if "cinematometre" in appareil or "cinémomètre" in appareil:
                ctx["tags"].append("cinematometre")
                ctx["queries_specifiques"].append("cinematometre & calibration | etalonnage | numero & serie")
                ctx["mots_cles_recherche"].extend(["cinémomètre", "calibration"])
            if "radar" in appareil or "photo" in appareil:
                ctx["tags"].append("radar_photo")
                ctx["queries_specifiques"].append("photo & radar & identification | plaque")
                ctx["queries_specifiques"].append("proprietaire & vehicule | art & 592")
                ctx["mots_cles_recherche"].extend(["photo radar", "identification", "plaque"])
            if "laser" in appareil or "lidar" in appareil:
                ctx["tags"].append("laser")
                ctx["queries_specifiques"].append("laser | lidar & precision | erreur")

            # Sous-type par severite
            if exces >= 40:
                ctx["tags"].append("grand_exces")
                ctx["queries_specifiques"].append("grand & exces | saisie & vehicule | suspension & permis")
                ctx["mots_cles_recherche"].append("grand excès")
            elif exces >= 20:
                ctx["tags"].append("exces_moyen")
            else:
                ctx["tags"].append("exces_leger")

            # Sous-type par lieu
            if any(w in lieu for w in ["scolaire", "ecole", "école"]):
                ctx["tags"].append("zone_scolaire")
                ctx["queries_specifiques"].append("zone & scolaire & vitesse | ecole")
                ctx["mots_cles_recherche"].append("zone scolaire")
            if any(w in lieu for w in ["travaux", "construction", "chantier"]):
                ctx["tags"].append("zone_travaux")
                ctx["queries_specifiques"].append("travaux & signalisation | temporaire | cone")
                ctx["mots_cles_recherche"].append("zone de travaux")
            if any(w in lieu for w in ["autoroute", "highway"]):
                ctx["tags"].append("autoroute")
                ctx["queries_specifiques"].append("autoroute & vitesse")
            if any(w in lieu for w in ["pont", "bridge"]):
                ctx["tags"].append("pont")
                ctx["queries_specifiques"].append("pont & juridiction | competence")

            # Sous-type par vehicule
            if any(w in vehicule for w in ["moto", "motocyclette"]):
                ctx["tags"].append("moto")
                ctx["queries_specifiques"].append("motocyclette | moto & identification | plaque")
                ctx["mots_cles_recherche"].append("motocyclette")
            if any(w in vehicule for w in ["trottinette"]):
                ctx["tags"].append("trottinette")
                ctx["queries_specifiques"].append("trottinette & vitesse | electrique")
                ctx["mots_cles_recherche"].append("trottinette")
            if any(w in vehicule for w in ["camion", "poids lourd"]):
                ctx["tags"].append("camion")
                ctx["queries_specifiques"].append("camion | vehicule & lourd & vitesse")

        elif any(w in infraction for w in ["feu rouge", "signalisation"]):
            ctx["type"] = "feu_rouge"
            ctx["queries_specifiques"].append("feu & rouge | signalisation")
            ctx["mots_cles_recherche"].extend(["feu rouge", "signalisation"])
        elif any(w in infraction for w in ["cellulaire", "telephone", "portable"]):
            ctx["type"] = "cellulaire"
            ctx["queries_specifiques"].append("cellulaire | telephone & conduite")
            ctx["mots_cles_recherche"].extend(["cellulaire", "téléphone"])
        elif any(w in infraction for w in ["alcool", "ivresse", "facultes", "capacites"]):
            ctx["type"] = "alcool"
            ctx["queries_specifiques"].append("alcool | facultes & affaiblies")
            ctx["mots_cles_recherche"].extend(["alcool", "facultés affaiblies"])
        elif any(w in infraction for w in ["imprudent", "dangereuse", "slalom"]):
            ctx["type"] = "conduite_dangereuse"
            ctx["queries_specifiques"].append("conduite & dangereuse | imprudente")
            ctx["queries_specifiques"].append("slalom | changement & voie | coupe")
            ctx["mots_cles_recherche"].extend(["conduite imprudente", "conduite dangereuse"])
        elif any(w in infraction for w in ["stop", "arret", "arrêt"]):
            ctx["type"] = "stop"
            ctx["queries_specifiques"].append("arret | stop & panneau")
            ctx["mots_cles_recherche"].extend(["panneau d'arrêt", "stop"])
        elif any(w in infraction for w in ["stationnement"]):
            ctx["type"] = "stationnement"
            ctx["queries_specifiques"].append("stationnement & interdit | contravention")
            ctx["mots_cles_recherche"].extend(["stationnement"])
        else:
            ctx["type"] = "autre"
            words = [w for w in infraction.split() if len(w) > 3][:4]
            if words:
                ctx["queries_specifiques"].append(" & ".join(words))
            ctx["mots_cles_recherche"].append(infraction[:50])

        # Toujours ajouter une requete generique basee sur l'infraction
        if ctx["type"] == "vitesse":
            ctx["queries_specifiques"].insert(0, "vitesse | exces")

        return ctx

    def _recherche_tsvector_qc(self, ticket, contexte, limit=15):
        """Recherche tsvector PostgreSQL avec requetes SPECIFIQUES au ticket"""
        results = []
        try:
            conn = self.get_db()
            cur = conn.cursor()
            seen_ids = set()

            queries = contexte.get("queries_specifiques", ["contravention & quebec"])

            for query in queries:
                try:
                    cur.execute("""
                        SELECT j.id, j.citation, j.database_id, j.date_decision,
                               j.resume, j.province, j.resultat, j.titre,
                               ts_rank(j.tsv_fr, to_tsquery('french', %s)) AS rank
                        FROM jurisprudence j
                        WHERE j.province = 'QC'
                          AND j.database_id IN ('qccm', 'qccq', 'qccs', 'qcca')
                          AND j.est_ticket_related = true
                          AND j.tsv_fr @@ to_tsquery('french', %s)
                        ORDER BY
                          CASE WHEN j.resultat IS NOT NULL THEN 0 ELSE 1 END,
                          rank DESC,
                          j.date_decision DESC NULLS LAST
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
                                "titre": (row[7] or "")[:200],
                                "juridiction": row[5] or "QC",
                                "resultat": row[6] or "inconnu",
                                "source": "PostgreSQL-QC",
                                "score": tribunal_score,
                                "requete": query[:50]
                            })
                except Exception:
                    pass

            conn.close()
        except Exception as e:
            self.log(f"Erreur tsvector QC: {e}", "FAIL")
        return results

    def _recherche_par_article(self, ticket, lois, limit=10):
        """Recherche par article de loi cite — utilise lois_pertinentes array"""
        results = []
        loi_ticket = (ticket.get("loi", "") or "").lower()

        # Extraire numeros d'articles
        articles = re.findall(r'art\.?\s*(\d+(?:\.\d+)?)', loi_ticket)
        if not articles and lois:
            for l in lois[:3]:
                if isinstance(l, dict):
                    art = l.get("article", "")
                    if art:
                        articles.append(str(art))

        if not articles:
            return []

        try:
            conn = self.get_db()
            cur = conn.cursor()
            seen_ids = set()

            for art_num in articles[:3]:
                # Chercher les cas qui citent cet article
                art_patterns = [f"%art. {art_num}%", f"%art.{art_num}%", f"%article {art_num}%"]
                for pattern in art_patterns:
                    try:
                        cur.execute("""
                            SELECT j.id, j.citation, j.database_id, j.date_decision,
                                   j.resume, j.province, j.resultat, j.titre
                            FROM jurisprudence j
                            WHERE j.province = 'QC'
                              AND j.est_ticket_related = true
                              AND (
                                  j.titre ILIKE %s
                                  OR j.resume ILIKE %s
                                  OR array_to_string(j.mots_cles, ' ') ILIKE %s
                              )
                            ORDER BY
                              CASE WHEN j.resultat IS NOT NULL THEN 0 ELSE 1 END,
                              j.date_decision DESC NULLS LAST
                            LIMIT %s
                        """, (pattern, pattern, pattern, limit))
                        for row in cur.fetchall():
                            if row[0] not in seen_ids:
                                seen_ids.add(row[0])
                                results.append({
                                    "id": row[0], "citation": row[1],
                                    "tribunal": (row[2] or "").upper(),
                                    "date": str(row[3]) if row[3] else "",
                                    "resume": (row[4] or "")[:300],
                                    "titre": (row[7] or "")[:200],
                                    "juridiction": row[5] or "QC",
                                    "resultat": row[6] or "inconnu",
                                    "source": "PostgreSQL-article",
                                    "score": 88,
                                    "requete": f"art.{art_num}"
                                })
                    except Exception:
                        pass

            conn.close()
        except Exception as e:
            self.log(f"Erreur recherche par article: {e}", "WARN")

        return results

    def _recherche_par_mots_cles(self, contexte, limit=10):
        """Recherche par mots_cles array (index GIN) — tres specifique"""
        results = []
        mots = contexte.get("mots_cles_recherche", [])
        if not mots:
            return []

        try:
            conn = self.get_db()
            cur = conn.cursor()
            seen_ids = set()

            # Chercher par combinaison de mots-cles
            for mot in mots[:5]:
                mot_clean = mot.strip().lower()
                if len(mot_clean) < 3:
                    continue
                try:
                    cur.execute("""
                        SELECT j.id, j.citation, j.database_id, j.date_decision,
                               j.resume, j.province, j.resultat, j.titre
                        FROM jurisprudence j
                        WHERE j.province = 'QC'
                          AND j.est_ticket_related = true
                          AND array_to_string(j.mots_cles, ' ') ILIKE %s
                        ORDER BY
                          CASE WHEN j.resultat IS NOT NULL THEN 0 ELSE 1 END,
                          j.date_decision DESC NULLS LAST
                        LIMIT %s
                    """, (f"%{mot_clean}%", limit))
                    for row in cur.fetchall():
                        if row[0] not in seen_ids:
                            seen_ids.add(row[0])
                            results.append({
                                "id": row[0], "citation": row[1],
                                "tribunal": (row[2] or "").upper(),
                                "date": str(row[3]) if row[3] else "",
                                "resume": (row[4] or "")[:300],
                                "titre": (row[7] or "")[:200],
                                "juridiction": row[5] or "QC",
                                "resultat": row[6] or "inconnu",
                                "source": "PostgreSQL-mots_cles",
                                "score": 82,
                                "requete": f"mc:{mot_clean}"
                            })
                except Exception:
                    pass

            conn.close()
        except Exception as e:
            self.log(f"Erreur recherche mots-cles: {e}", "WARN")

        return results

    def _recherche_semantique_qc(self, ticket, contexte, n_results=10):
        """Recherche semantique avec contexte SPECIFIQUE au ticket"""
        svc = self._get_embedding_service()
        if not svc:
            return []

        results = []
        # Construire une requete semantique riche et specifique
        parts = [ticket.get("infraction", "")]
        if contexte.get("tags"):
            parts.append(" ".join(contexte["tags"]))
        if ticket.get("lieu"):
            parts.append(ticket["lieu"])
        if ticket.get("appareil"):
            parts.append(ticket["appareil"])
        v_captee = ticket.get("vitesse_captee")
        v_permise = ticket.get("vitesse_permise")
        if v_captee and v_permise:
            parts.append(f"{v_captee} km/h zone {v_permise}")

        query = " ".join(parts) + " Quebec CSR"

        try:
            pgvec_results = svc.search(query, top_k=n_results, juridiction="QC")
            for r in pgvec_results:
                similarity = max(0, r.get("similarity", 0)) * 100
                results.append({
                    "id": r.get("id"),
                    "citation": r.get("citation", ""),
                    "tribunal": r.get("tribunal", ""),
                    "date": str(r.get("date_decision", "")) if r.get("date_decision") else "",
                    "resume": (r.get("resume") or "")[:300],
                    "titre": (r.get("titre") or "")[:200],
                    "juridiction": "QC",
                    "resultat": r.get("resultat", "inconnu"),
                    "source": "pgvector-QC",
                    "score": round(similarity, 1),
                    "requete": f"semantic:{query[:40]}"
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
                    "titre": item.get("title", "")[:200],
                    "juridiction": "QC",
                    "resultat": "inconnu",
                    "source": "CanLII-QC",
                    "score": 55,
                    "requete": "canlii"
                })
            if len(results) >= 5:
                break
        remaining = self.canlii_remaining_quota()
        if remaining < 100:
            self.log(f"CanLII quota bas: {remaining} restant", "WARN")
        return results

    def _combiner_et_diversifier(self, fts, articles, mots_cles, semantic, canlii, n_results=10):
        """Combiner tous les resultats avec diversification et equilibre acquitte/coupable"""
        all_results = {}

        # Fusionner avec bonus pour multi-source
        for source_list in [fts, articles, mots_cles, semantic, canlii]:
            for r in (source_list or []):
                key = r.get("citation", r.get("id", ""))
                if not key:
                    continue
                if key not in all_results:
                    all_results[key] = r
                else:
                    # Bonus si trouve dans multiple sources
                    all_results[key]["score"] = min(100, all_results[key]["score"] + 15)
                    # Garder le meilleur resume
                    if len(r.get("resume", "")) > len(all_results[key].get("resume", "")):
                        all_results[key]["resume"] = r["resume"]

        # Trier par score
        sorted_results = sorted(all_results.values(), key=lambda x: x.get("score", 0), reverse=True)

        # Diversifier: equilibrer acquittes et coupables
        acquittes = [r for r in sorted_results if r.get("resultat", "").lower() in ("acquitte", "accueilli", "annule")]
        coupables = [r for r in sorted_results if r.get("resultat", "").lower() in ("coupable", "condamne")]
        autres = [r for r in sorted_results if r.get("resultat", "").lower() not in
                  ("acquitte", "accueilli", "annule", "coupable", "condamne")]

        # Objectif: ~40% acquittes, ~40% coupables, ~20% autres
        n_acquittes = min(len(acquittes), max(3, n_results * 4 // 10))
        n_coupables = min(len(coupables), max(3, n_results * 4 // 10))
        n_autres = min(len(autres), n_results - n_acquittes - n_coupables)

        diversified = acquittes[:n_acquittes] + coupables[:n_coupables] + autres[:n_autres]

        # Si pas assez, completer avec ce qu'on a
        if len(diversified) < n_results:
            used_ids = {r.get("citation", r.get("id")) for r in diversified}
            for r in sorted_results:
                if len(diversified) >= n_results:
                    break
                key = r.get("citation", r.get("id"))
                if key not in used_ids:
                    diversified.append(r)
                    used_ids.add(key)

        # Re-trier par score
        diversified.sort(key=lambda x: x.get("score", 0), reverse=True)

        return diversified

    def _recherche_tsvector_federale(self, infraction, limit=5):
        """Fallback: cherche precedents federaux (CSC) applicables au QC"""
        results = []
        try:
            conn = self.get_db()
            cur = conn.cursor()
            queries = ["vitesse | exces | radar"]
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
                                "source": "PostgreSQL-Federal",
                                "score": 60
                            })
                except Exception:
                    pass
            conn.close()
        except Exception as e:
            self.log(f"Erreur tsvector Federal: {e}", "FAIL")
        return results
