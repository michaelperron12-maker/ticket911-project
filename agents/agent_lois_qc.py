"""
Agent QC: LOIS QUEBEC — Code de la securite routiere (CSR) + Code criminel
Recherche PostgreSQL tsvector specifique Quebec (articles CSR, C-24.2, reglements municipaux)
V2: Recherche par article + severite + contexte
"""

import re
import time
from agents.base_agent import BaseAgent


class AgentLoisQC(BaseAgent):

    # Articles CSR par categorie de vitesse
    ARTICLES_VITESSE = {
        "base": ["299", "328", "329"],           # Limites + appareil + zone scolaire
        "grand_exces": ["299", "328", "329.2", "329.3"],  # + saisie vehicule
        "photo_radar": ["299", "592", "328"],     # + presomption proprietaire
        "zone_scolaire": ["299", "329"],
        "zone_travaux": ["299", "329.1"],
    }

    ARTICLES_PAR_TYPE = {
        "feu_rouge": ["359", "360", "362"],
        "cellulaire": ["443.1", "443.2"],
        "stop": ["368", "369"],
        "ceinture": ["396", "397"],
        "alcool": ["202.1", "202.2", "202.3", "202.4"],
        "depassement": ["344", "345", "346"],
        "permis": ["65", "66", "93.1"],
        "conduite_dangereuse": ["327", "328"],
    }

    def __init__(self):
        super().__init__("Lois_QC")

    def chercher_loi(self, ticket):
        """
        Input: ticket QC
        Output: articles CSR et reglements applicables au Quebec
        V2: Recherche par article direct + severite + tsvector
        """
        self.log(f"Recherche lois QC/CSR: {ticket.get('infraction', '?')}", "STEP")
        start = time.time()
        resultats = []

        infraction = ticket.get("infraction", "")
        loi_ticket = ticket.get("loi", "")

        try:
            conn = self.get_db()
            cur = conn.cursor()

            # ═══ ETAPE 1: Recherche directe par numero d'article ═══
            article_nums = self._extraire_articles(loi_ticket, infraction)
            if article_nums:
                for art_num in article_nums:
                    try:
                        cur.execute("""
                            SELECT id, province, article, titre_article,
                                   texte_complet, loi, code_loi
                            FROM lois_articles
                            WHERE province = 'QC'
                              AND (article = %s OR article LIKE %s)
                            ORDER BY article
                        """, (art_num, art_num + '.%'))
                        for row in cur.fetchall():
                            resultats.append({
                                "id": row[0], "juridiction": row[1],
                                "article": row[2],
                                "titre_article": row[3] or "",
                                "texte": (row[4] or row[3] or "")[:500],
                                "source": row[5] or row[6] or "CSR",
                                "recherche": f"article_direct:{art_num}",
                                "pertinence": "directe"
                            })
                            self.log(f"  Art. {row[2]} trouve (recherche directe)", "OK")
                    except Exception as e:
                        self.log(f"  Erreur recherche art. {art_num}: {e}", "WARN")

            # ═══ ETAPE 2: Articles par severite (vitesse) ═══
            v_captee = ticket.get("vitesse_captee")
            v_permise = ticket.get("vitesse_permise")
            if v_captee and v_permise:
                exces = int(v_captee) - int(v_permise)
                articles_severite = self._articles_par_severite(ticket, exces)
                for art_num in articles_severite:
                    # Eviter doublons
                    if any(r["article"] == art_num for r in resultats):
                        continue
                    try:
                        cur.execute("""
                            SELECT id, province, article, titre_article,
                                   texte_complet, loi, code_loi
                            FROM lois_articles
                            WHERE province = 'QC'
                              AND (article = %s OR article LIKE %s)
                            LIMIT 3
                        """, (art_num, art_num + '.%'))
                        for row in cur.fetchall():
                            resultats.append({
                                "id": row[0], "juridiction": row[1],
                                "article": row[2],
                                "titre_article": row[3] or "",
                                "texte": (row[4] or row[3] or "")[:500],
                                "source": row[5] or row[6] or "CSR",
                                "recherche": f"severite:+{exces}km/h",
                                "pertinence": "severite"
                            })
                            self.log(f"  Art. {row[2]} trouve (severite +{exces}km/h)", "OK")
                    except Exception:
                        pass

            # ═══ ETAPE 3: Articles par type d'infraction ═══
            type_articles = self._articles_par_type(infraction)
            for art_num in type_articles:
                if any(r["article"] == art_num for r in resultats):
                    continue
                try:
                    cur.execute("""
                        SELECT id, province, article, titre_article,
                               texte_complet, loi, code_loi
                        FROM lois_articles
                        WHERE province = 'QC'
                          AND (article = %s OR article LIKE %s)
                        LIMIT 2
                    """, (art_num, art_num + '.%'))
                    for row in cur.fetchall():
                        resultats.append({
                            "id": row[0], "juridiction": row[1],
                            "article": row[2],
                            "titre_article": row[3] or "",
                            "texte": (row[4] or row[3] or "")[:500],
                            "source": row[5] or row[6] or "CSR",
                            "recherche": "type_infraction",
                            "pertinence": "type"
                        })
                        self.log(f"  Art. {row[2]} trouve (type infraction)", "OK")
                except Exception:
                    pass

            # ═══ ETAPE 4: Recherche tsvector (complement) ═══
            if len(resultats) < 5:
                mots_cles = self._extraire_mots_cles_qc(infraction)
                for query in mots_cles:
                    try:
                        tsquery = " | ".join(query.split())
                        cur.execute("""
                            SELECT id, province, article, titre_article,
                                   texte_complet, loi, code_loi,
                                   ts_rank(tsv, to_tsquery('french', %s)) AS rank
                            FROM lois_articles
                            WHERE province = 'QC'
                              AND tsv @@ to_tsquery('french', %s)
                            ORDER BY rank DESC
                            LIMIT 5
                        """, (tsquery, tsquery))
                        for row in cur.fetchall():
                            resultats.append({
                                "id": row[0], "juridiction": row[1],
                                "article": row[2],
                                "titre_article": row[3] or "",
                                "texte": (row[4] or row[3] or "")[:500],
                                "source": row[5] or row[6] or "CSR",
                                "recherche": f"tsvector:{query}",
                                "pertinence": "tsvector"
                            })
                            self.log(f"  Art. {row[2]} trouve (tsvector)", "OK")
                    except Exception:
                        pass

            # ═══ ETAPE 5: Code criminel si alcool/capacites ═══
            if any(w in infraction.lower() for w in ["alcool", "ivresse", "facultes", "capacites"]):
                try:
                    cur.execute("""
                        SELECT id, province, article, titre_article, texte_complet, loi
                        FROM lois_articles
                        WHERE province = 'CA'
                          AND tsv @@ to_tsquery('french', 'alcool | capacites | ivresse | conduite')
                        LIMIT 3
                    """)
                    for row in cur.fetchall():
                        resultats.append({
                            "id": row[0], "juridiction": "CA",
                            "article": row[2],
                            "titre_article": row[3] or "",
                            "texte": (row[4] or row[3] or "")[:500],
                            "source": row[5] or "Code criminel",
                            "recherche": "Code criminel",
                            "pertinence": "federal"
                        })
                except Exception:
                    pass

            conn.close()
        except Exception as e:
            self.log(f"Erreur recherche lois QC: {e}", "FAIL")

        # Deduplication
        seen = set()
        unique = []
        for r in resultats:
            key = f"{r['juridiction']}_{r['article']}"
            if key not in seen:
                seen.add(key)
                unique.append(r)

        duration = time.time() - start
        self.log_run("chercher_loi_qc", f"QC {infraction[:100]}", f"{len(unique)} articles CSR", duration=duration)
        self.log(f"{len(unique)} articles CSR trouves en {duration:.1f}s", "OK")
        return unique

    def _extraire_articles(self, loi_ticket, infraction):
        """Extraire les numeros d'articles depuis la loi mentionnee sur le ticket"""
        articles = []
        texte = f"{loi_ticket} {infraction}".lower()

        # Pattern: Art. 299, art 299, article 299, Art.299
        matches = re.findall(r'art\.?\s*(\d+(?:\.\d+)?)', texte)
        articles.extend(matches)

        # Pattern: (R-25 art. 14), par. 17
        matches2 = re.findall(r'(?:paragraphe|par\.?)\s*(\d+)', texte)
        # Ne pas ajouter les paragraphes comme articles principaux

        # Pattern: C-24.2 (code CSR)
        if 'c-24.2' in texte or 'csr' in texte:
            # C'est le CSR, on cherche l'article specifique
            pass

        return list(set(articles))

    def _articles_par_severite(self, ticket, exces_kmh):
        """Retourner les articles pertinents selon le niveau d'exces"""
        articles = ["299"]  # Toujours l'article de base

        appareil = (ticket.get("appareil", "") or "").lower()
        lieu = (ticket.get("lieu", "") or "").lower()

        # Appareil de mesure
        if appareil or exces_kmh > 0:
            articles.append("328")  # Appareil de controle

        # Grand exces
        if exces_kmh >= 40:
            articles.extend(["329.2", "329.3"])  # Saisie + suspension
            articles.append("516")  # Amendes majorees

        # Zone scolaire
        if "scolaire" in lieu or "ecole" in lieu:
            articles.append("329")

        # Zone de travaux
        if "travaux" in lieu or "construction" in lieu or "chantier" in lieu:
            articles.append("329.1")

        # Photo radar
        if "radar" in appareil or "photo" in appareil:
            articles.append("592")  # Presomption proprietaire

        # Amendes selon exces
        if exces_kmh > 20:
            articles.append("516")

        return list(set(articles))

    def _articles_par_type(self, infraction):
        """Retourner les articles pertinents selon le type d'infraction"""
        lower = infraction.lower()
        articles = []

        for type_key, art_list in self.ARTICLES_PAR_TYPE.items():
            keywords = {
                "feu_rouge": ["feu rouge", "feu", "signalisation"],
                "cellulaire": ["cellulaire", "telephone", "portable", "textos"],
                "stop": ["stop", "arret", "arrêt"],
                "ceinture": ["ceinture", "securite"],
                "alcool": ["alcool", "ivresse", "facultes", "capacites", "alcootest"],
                "depassement": ["depassement", "depasser"],
                "permis": ["permis", "licence", "conduire sans"],
                "conduite_dangereuse": ["dangereuse", "dangereux", "imprudent", "imprudente"],
            }
            if type_key in keywords:
                if any(w in lower for w in keywords[type_key]):
                    articles.extend(art_list)

        return list(set(articles))

    def _extraire_mots_cles_qc(self, infraction):
        """Mots-cles specifiques au Code de la securite routiere du Quebec"""
        queries = []
        lower = infraction.lower()

        if any(w in lower for w in ["vitesse", "excès", "exces", "km/h", "radar", "cinémomètre", "cinematometre"]):
            queries.extend(["vitesse", "exces & vitesse", "cinematometre"])
        if any(w in lower for w in ["feu rouge", "feu", "signalisation"]):
            queries.extend(["feu & rouge", "signalisation & lumineuse"])
        if any(w in lower for w in ["cellulaire", "telephone", "portable", "textos"]):
            queries.extend(["cellulaire", "appareil & portatif"])
        if any(w in lower for w in ["stop", "arrêt", "arret"]):
            queries.extend(["arret", "panneau & arret"])
        if any(w in lower for w in ["ceinture", "securite"]):
            queries.extend(["ceinture & securite"])
        if any(w in lower for w in ["alcool", "ivresse", "facultes", "alcootest"]):
            queries.extend(["facultes & affaiblies", "alcool"])
        if any(w in lower for w in ["depassement", "depasser", "interdit"]):
            queries.extend(["depassement"])
        if any(w in lower for w in ["permis", "licence", "conduire sans"]):
            queries.extend(["permis & conduire"])
        if any(w in lower for w in ["zone scolaire", "ecole"]):
            queries.extend(["zone & scolaire"])
        if any(w in lower for w in ["construction", "chantier", "travaux"]):
            queries.extend(["zone & construction | travaux"])
        if any(w in lower for w in ["trottinette", "velo", "cycliste"]):
            queries.extend(["trottinette | velo | cycliste"])
        if any(w in lower for w in ["imprudent", "dangereuse"]):
            queries.extend(["conduite & dangereuse | imprudente"])

        if not queries:
            words = [w for w in lower.split() if len(w) > 3][:3]
            queries = [" & ".join(words)] if words else ["securite & routiere"]

        return queries
