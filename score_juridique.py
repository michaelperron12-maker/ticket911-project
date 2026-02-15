"""
AITicketInfo — Score Juridique
Calcul de score statistique base sur 5 facteurs ponderes.
Source: jugements publics PostgreSQL (CanLII, SOQUIJ)
AUCUN avis juridique — statistiques seulement.
"""

import json
import psycopg2
import psycopg2.extras

PG_CONFIG = {
    "host": "172.18.0.3",
    "port": 5432,
    "dbname": "tickets_qc_on",
    "user": "ticketdb_user",
    "password": "Tk911PgSecure2026"
}


class ScoreJuridique:
    """
    Score statistique sur 10 base sur 5 facteurs ponderes.
    FORMULE: (F1*0.30) + (F2*0.25) + (F3*0.20) + (F4*0.15) + (F5*0.10)
    """

    def __init__(self):
        self.conn = None

    def get_db(self):
        if self.conn is None or self.conn.closed:
            self.conn = psycopg2.connect(**PG_CONFIG)
        return self.conn

    def calculer(self, ticket: dict, preuves_client: list = None) -> dict:
        if preuves_client is None:
            preuves_client = []

        province = ticket.get("province", "QC")
        infraction = ticket.get("infraction", "")
        article = ticket.get("article", "")

        jugements = self._trouver_jugements_similaires(infraction, article, province)

        f1 = self._f1_taux_acquittement(jugements)
        f2 = self._f2_force_preuves(preuves_client, jugements)
        f3 = self._f3_arguments_applicables(ticket, jugements)
        f4 = self._f4_coherence_dossier(ticket, preuves_client)
        f5 = self._f5_facteurs_contextuels(ticket, province)

        score = round(
            f1["score"] * 0.30 +
            f2["score"] * 0.25 +
            f3["score"] * 0.20 +
            f4["score"] * 0.15 +
            f5["score"] * 0.10,
            1
        )

        for f, p in [(f1, 0.30), (f2, 0.25), (f3, 0.20), (f4, 0.15), (f5, 0.10)]:
            f["poids"] = p
            f["pondere"] = round(f["score"] * p, 2)

        resultat = {
            "score": score,
            "f1": f1, "f2": f2, "f3": f3, "f4": f4, "f5": f5,
            "nb_jugements_similaires": len(jugements),
            "nb_acquittements": len([j for j in jugements if self._est_acquitte(j)]),
            "nb_condamnations": len([j for j in jugements if not self._est_acquitte(j)]),
            "jugements_top5": jugements[:5],
            "sources": ["CanLII", "SOQUIJ", "LegisQuebec"],
            "methode": "Moyenne ponderee de 5 facteurs statistiques",
            "avertissement": "Ce score est une statistique, pas un avis juridique."
        }

        self._sauvegarder_score(ticket.get("dossier_uuid", ""), resultat)
        return resultat

    def _f1_taux_acquittement(self, jugements):
        total = len(jugements)
        if total == 0:
            return {"score": 5.0, "explication": "Aucun jugement similaire trouve", "acquittements": 0, "condamnations": 0, "total": 0}

        acquittements = len([j for j in jugements if self._est_acquitte(j)])
        taux = acquittements / total
        return {
            "score": min(round(taux * 10, 1), 10.0),
            "explication": f"{acquittements} acquittements sur {total} cas similaires ({round(taux * 100)}%)",
            "acquittements": acquittements, "condamnations": total - acquittements, "total": total,
            "taux": round(taux * 100, 1),
            "dossiers": [j.get("citation", "") for j in jugements[:10]]
        }

    def _f2_force_preuves(self, preuves_client, jugements):
        if not preuves_client:
            return {"score": 3.0, "explication": "Aucune preuve fournie", "matchs": 0, "preuves_connues": 0}

        preuves_gagnantes = self._extraire_preuves_acquittements(jugements)
        if not preuves_gagnantes:
            return {"score": 5.0, "explication": "Pas assez de donnees pour comparer", "matchs": 0, "preuves_connues": 0}

        matchs = []
        for preuve in preuves_client:
            preuve_lower = preuve.lower()
            for pg in preuves_gagnantes:
                if self._preuve_similaire(preuve_lower, pg["type"]):
                    matchs.append({"preuve_client": preuve, "type_connu": pg["type"], "vue_dans": pg["count"], "dossiers": pg["dossiers"][:3]})
                    break

        score = min(round((len(matchs) / len(preuves_gagnantes)) * 10, 1), 10.0) if preuves_gagnantes else 5.0
        return {
            "score": score,
            "explication": f"{len(matchs)} preuves correspondent a des preuves vues dans des acquittements",
            "matchs": len(matchs), "preuves_connues": len(preuves_gagnantes), "detail": matchs
        }

    def _f3_arguments_applicables(self, ticket, jugements):
        arguments_connus = self._get_arguments_connus(ticket.get("province", "QC"))
        full_text = f"{ticket.get('infraction', '')} {ticket.get('article', '')} {ticket.get('lieu', '')} {ticket.get('appareil', '')}".lower()

        applicables = [arg for arg in arguments_connus if any(mot in full_text for mot in arg["declencheurs"])]
        total_args = len(arguments_connus)
        score = min(round((len(applicables) / total_args * 10), 1), 10.0) if total_args > 0 else 5.0

        return {
            "score": score,
            "explication": f"{len(applicables)} arguments identifies sur {total_args} connus",
            "applicables": len(applicables), "total_connus": total_args,
            "detail": [{"argument": a["nom"], "frequence": a["frequence"], "taux_succes": a["taux_succes"], "source": a["source"]} for a in applicables]
        }

    def _f4_coherence_dossier(self, ticket, preuves):
        checks = {
            "ticket_complet": all(ticket.get(c) for c in ["infraction", "date", "lieu"]),
            "preuves_fournies": len(preuves) > 0,
            "article_specifie": bool(ticket.get("article")),
            "province_identifiee": ticket.get("province") in ("QC", "ON", "BC", "AB")
        }
        nb_ok = sum(1 for v in checks.values() if v)
        return {"score": round((nb_ok / len(checks)) * 10, 1), "explication": f"{nb_ok} verifications sur {len(checks)}", "checks": checks, "nb_ok": nb_ok, "nb_total": len(checks)}

    def _f5_facteurs_contextuels(self, ticket, province):
        try:
            conn = self.get_db()
            cur = conn.cursor()

            cur.execute("""
                SELECT COUNT(*) FILTER (WHERE resultat IN ('acquitte', 'acquitted', 'dismissed')) AS acq, COUNT(*) AS total
                FROM jurisprudence WHERE province = %s
            """, (province,))
            row = cur.fetchone()
            taux_province = row[0] / row[1] if row and row[1] > 0 else 0.5

            infraction = ticket.get("infraction", "")
            mots = [w for w in infraction.lower().split() if len(w) > 3][:2]
            taux_infraction = 0.5

            if mots:
                pattern = " & ".join(mots)
                try:
                    cur.execute("""
                        SELECT COUNT(*) FILTER (WHERE resultat IN ('acquitte', 'acquitted', 'dismissed')) AS acq, COUNT(*) AS total
                        FROM jurisprudence WHERE province = %s AND tsv_fr @@ to_tsquery('french', %s)
                    """, (province, pattern))
                    r2 = cur.fetchone()
                    if r2 and r2[1] > 5:
                        taux_infraction = r2[0] / r2[1]
                except Exception:
                    pass

            score = round(((taux_province + taux_infraction) / 2) * 10, 1)
            return {"score": min(score, 10.0), "explication": f"Taux acquittement {province}: {round(taux_province * 100)}% | Infraction: {round(taux_infraction * 100)}%", "taux_province": round(taux_province * 100, 1), "taux_infraction": round(taux_infraction * 100, 1)}
        except Exception as e:
            return {"score": 5.0, "explication": f"Erreur: {e}", "taux_province": 50.0, "taux_infraction": 50.0}

    def _est_acquitte(self, jugement):
        resultat = (jugement.get("resultat") or "").lower()
        return any(mot in resultat for mot in ["acquit", "dismissed", "rejete", "rejected", "not guilty"])

    def _trouver_jugements_similaires(self, infraction, article, province):
        results = []
        try:
            conn = self.get_db()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            mots = [w for w in infraction.lower().split() if len(w) > 3][:4]
            if not mots:
                mots = ["infraction"]
            tsquery = " | ".join(mots)
            lang = "french" if province == "QC" else "english"
            tsv_col = "tsv_fr" if province == "QC" else "tsv_en"

            cur.execute(f"""
                SELECT id, citation, database_id, tribunal, date_decision, resume, resultat, province, mots_cles,
                       ts_rank({tsv_col}, to_tsquery(%s, %s)) AS rank
                FROM jurisprudence WHERE province = %s AND {tsv_col} @@ to_tsquery(%s, %s)
                ORDER BY rank DESC LIMIT 50
            """, (lang, tsquery, province, lang, tsquery))
            results = [dict(row) for row in cur.fetchall()]

            if len(results) < 10:
                cur.execute("""
                    SELECT id, citation, database_id, tribunal, date_decision, resume, resultat, province, mots_cles,
                           ts_rank(tsv_fr, to_tsquery('french', %s)) AS rank
                    FROM jurisprudence WHERE tsv_fr @@ to_tsquery('french', %s)
                    ORDER BY rank DESC LIMIT 50
                """, (tsquery, tsquery))
                seen_ids = {r["id"] for r in results}
                for row in cur.fetchall():
                    row = dict(row)
                    if row["id"] not in seen_ids:
                        results.append(row)
                        seen_ids.add(row["id"])
        except Exception as e:
            print(f"Erreur recherche jugements: {e}")
        return results

    def _extraire_preuves_acquittements(self, jugements):
        types_preuves = [
            {"type": "calibration_appareil", "mots": ["calibr", "verif", "certificat", "appareil", "radar", "cinematometre"]},
            {"type": "signalisation", "mots": ["signal", "panneau", "affich", "visib"]},
            {"type": "photo_video", "mots": ["photo", "video", "dashcam", "camera", "enregistr"]},
            {"type": "temoignage", "mots": ["temoin", "temoign", "passager", "declaration"]},
            {"type": "expert", "mots": ["expert", "expertise", "rapport technique"]},
            {"type": "delai", "mots": ["delai", "signif", "prescription", "expir"]},
            {"type": "identification", "mots": ["identif", "conducteur", "photo floue", "plaque"]},
            {"type": "procedure", "mots": ["procedur", "vice", "irregul", "nul"]},
        ]
        resultats = []
        acquittements = [j for j in jugements if self._est_acquitte(j)]
        for tp in types_preuves:
            dossiers = []
            for j in acquittements:
                texte = f"{j.get('resume', '')} {j.get('mots_cles', '')}".lower()
                if any(mot in texte for mot in tp["mots"]):
                    dossiers.append(j.get("citation", str(j.get("id", ""))))
            if dossiers:
                resultats.append({"type": tp["type"], "count": len(dossiers), "dossiers": dossiers})
        return sorted(resultats, key=lambda x: x["count"], reverse=True)

    def _preuve_similaire(self, preuve_client, type_connu):
        mappings = {
            "calibration_appareil": ["calibr", "radar", "appareil", "cinematometre", "verif"],
            "signalisation": ["signal", "panneau", "affich", "limite", "zone"],
            "photo_video": ["photo", "video", "dashcam", "camera", "film"],
            "temoignage": ["temoin", "temoign", "passager", "declar"],
            "expert": ["expert", "expertise", "technique", "rapport"],
            "delai": ["delai", "retard", "signif", "expir", "prescription"],
            "identification": ["identif", "conducteur", "plaque", "visage"],
            "procedure": ["procedur", "vice", "irregul", "nul", "erreur"],
        }
        return any(mot in preuve_client for mot in mappings.get(type_connu, []))

    def _get_arguments_connus(self, province):
        if province == "QC":
            return [
                {"nom": "Radar/cinematometre non calibre", "declencheurs": ["vitesse", "exces", "radar", "cinematometre", "photo radar", "km/h"], "frequence": 15, "taux_succes": 87, "source": "CanLII QC"},
                {"nom": "Signalisation non conforme", "declencheurs": ["vitesse", "zone", "signal", "panneau", "limite"], "frequence": 9, "taux_succes": 78, "source": "CanLII QC"},
                {"nom": "Delai de signification depasse", "declencheurs": ["delai", "signif", "date", "constat"], "frequence": 7, "taux_succes": 92, "source": "CanLII QC"},
                {"nom": "Identification du conducteur", "declencheurs": ["photo", "conducteur", "identif", "radar", "photo radar"], "frequence": 5, "taux_succes": 60, "source": "CanLII QC"},
                {"nom": "Vice de procedure", "declencheurs": ["procedur", "constat", "erreur", "agent", "numero"], "frequence": 4, "taux_succes": 75, "source": "CanLII QC"},
            ]
        else:
            return [
                {"nom": "Radar/lidar not calibrated", "declencheurs": ["speed", "radar", "lidar", "km/h", "speeding"], "frequence": 12, "taux_succes": 82, "source": "CanLII ON"},
                {"nom": "Officer training/certification", "declencheurs": ["speed", "officer", "training", "certif"], "frequence": 8, "taux_succes": 70, "source": "CanLII ON"},
                {"nom": "Disclosure issues", "declencheurs": ["disclos", "evidence", "procedur"], "frequence": 6, "taux_succes": 88, "source": "CanLII ON"},
                {"nom": "Charter violation (s.11b delay)", "declencheurs": ["delay", "charter", "11b", "trial"], "frequence": 5, "taux_succes": 90, "source": "CanLII ON"},
                {"nom": "Signage not visible", "declencheurs": ["sign", "speed limit", "visib", "posted"], "frequence": 4, "taux_succes": 65, "source": "CanLII ON"},
            ]

    def _sauvegarder_score(self, dossier_uuid, resultat):
        if not dossier_uuid:
            return
        try:
            conn = self.get_db()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO scores_juridiques
                    (dossier_uuid, score_global, f1_taux_acquittement, f2_force_preuves,
                     f3_arguments_applicables, f4_coherence_dossier, f5_facteurs_contextuels,
                     nb_jugements_similaires, nb_acquittements, nb_condamnations, detail_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (dossier_uuid, resultat["score"], resultat["f1"]["score"], resultat["f2"]["score"],
                  resultat["f3"]["score"], resultat["f4"]["score"], resultat["f5"]["score"],
                  resultat["nb_jugements_similaires"], resultat["nb_acquittements"],
                  resultat["nb_condamnations"], json.dumps(resultat, default=str)))
            conn.commit()
        except Exception as e:
            print(f"Erreur sauvegarde score: {e}")
            if self.conn:
                self.conn.rollback()
