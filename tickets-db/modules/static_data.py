"""
Module donnees statiques de reference.
Jurisprudence cle + articles de loi CSR/HTA.
"""
import logging
from utils.db import get_connection, log_import

logger = logging.getLogger(__name__)

# Jurisprudence cle - cas de reference
# (province, nom_cas, citation, annee, tribunal, loi, article, principe, type_infraction, resultat, url)
JURISPRUDENCE_CLE = [
    # === QUEBEC ===
    ('QC', 'Québec (PG) c. Paquette', '', None, 'Cour du Québec', 'CSR', '328',
     'Nier l\'infraction ou estimer sa vitesse ne repousse PAS la présomption de fiabilité du radar.',
     'exces_vitesse', 'coupable', ''),
    ('QC', 'Québec (PG) c. Robitaille', 'QCCA', None, 'Cour d\'appel QC', 'CSR', '328',
     'L\'odomètre est reconnu comme appareil de mesure sans preuve de calibration. Chaque conducteur a connaissance suffisante de son odomètre.',
     'exces_vitesse', 'reference', ''),
    ('QC', 'Fortin c. DPCP', '', None, 'Cour supérieure QC', 'CSR', '328',
     'Application des principes de Robitaille.', 'exces_vitesse', 'reference', ''),
    ('QC', 'Gaudet c. Gatineau (Ville de)', '', None, 'Cour supérieure QC', 'CSR', '328',
     'Application des principes de Robitaille.', 'exces_vitesse', 'reference', ''),
    ('QC', 'Ville de Québec c. Beaulieu', '2017 QCCM 249', 2017, 'Cour municipale QC', 'CSR', '328',
     'Regarder odomètre SEULEMENT en voyant la police = insuffisant pour contester.',
     'exces_vitesse', 'coupable', ''),
    ('QC', 'Bédard c. R.', '2025 QCCA 729', 2025, 'Cour d\'appel QC', 'Code criminel', '320.13',
     'Conduite dangereuse causant mort - deux erreurs du juge de première instance mènent à l\'acquittement.',
     'conduite_dangereuse', 'acquitte', ''),

    # === ONTARIO ===
    ('ON', 'R. v. Brown', '2009 ONCJ 6', 2009, 'Ontario Court of Justice', 'HTA', '172',
     'Classification absolute/strict liability pour s.172 (stunt driving).',
     'stunt_driving', 'reference', ''),
    ('ON', 'R. v. Sgotto', '2009 ONCJ 48', 2009, 'Ontario Court of Justice', 'HTA', '172',
     's.172 OHTA = strict liability (distinct de s.128 speeding = absolute liability).',
     'stunt_driving', 'reference', ''),
    ('ON', 'R. v. Raham', '2010 ONCA 206', 2010, 'Court of Appeal ON', 'HTA', '172',
     's.172 OHTA, constitutionnalité du stunt driving.', 'stunt_driving', 'reference', ''),
    ('ON', 'York (Regional Municipality) v. Winlow', '2009 ONCA 643', 2009, 'Court of Appeal ON', 'HTA', '128',
     '"Amending up" du ticket est permis - "nothing inherently unfair" (J. Laskin).',
     'exces_vitesse', 'reference', ''),
    ('ON', 'R. v. Martin', '2007 ONCJ 217', 2007, 'Ontario Court of Justice', 'HTA', '128',
     'Défaut de formation laser = affecte le POIDS de la preuve, pas l\'admissibilité.',
     'exces_vitesse', 'reference', ''),
    ('ON', 'R. v. Anghel', '2010 ONCJ 652', 2010, 'Ontario Court of Justice', 'HTA', '172',
     'Due diligence insuffisante pour stunt driving - "ludicrous to suggest due diligence".',
     'stunt_driving', 'coupable', ''),
    ('ON', 'Ontario v. Don\'s Triple F Transport', '2012 ONCA 536', 2012, 'Court of Appeal ON', 'HTA', '',
     'Certificat d\'infraction doit détailler la conduite reprochée (particularisation).',
     'general', 'reference', ''),
    ('ON', 'R. v. Wanamaker', '2005 OJ 1581', 2005, 'Ontario Court', 'HTA', '128',
     'Discrétion policière 113→100 km/h, juge accorde amendement à vitesse réelle.',
     'exces_vitesse', 'coupable', ''),
]

# Articles de loi - CSR (Quebec) + HTA (Ontario)
# (province, loi, code_loi, article, titre, texte_complet, categorie, amende_min, amende_max, pts_min, pts_max, type_resp, url)
ARTICLES_LOI = [
    # === QUEBEC - CSR C-24.2 ===
    ('QC', 'Code de la sécurité routière', 'C-24.2', '299',
     'Vitesse prudente et raisonnable',
     'Le conducteur d\'un véhicule routier doit conduire à une vitesse prudente et raisonnable eu égard aux circonstances.',
     'speed', None, None, 0, 0, 'absolute',
     'https://legisquebec.gouv.qc.ca/fr/showdoc/cs/c-24.2'),
    ('QC', 'Code de la sécurité routière', 'C-24.2', '327',
     'Conduite dangereuse (CSR)',
     'Nul ne peut conduire un véhicule routier ou en avoir la garde ou le contrôle de façon susceptible de mettre en péril la vie ou la sécurité des personnes ou la propriété.',
     'dangerous', 300, 600, 6, 6, 'strict',
     'https://legisquebec.gouv.qc.ca/fr/showdoc/cs/c-24.2'),
    ('QC', 'Code de la sécurité routière', 'C-24.2', '328',
     'Excès de vitesse',
     'Nul ne peut conduire un véhicule routier à une vitesse supérieure à la limite permise sur un chemin public.',
     'speed', 30, 630, 1, 6, 'absolute',
     'https://legisquebec.gouv.qc.ca/fr/showdoc/cs/c-24.2'),
    ('QC', 'Code de la sécurité routière', 'C-24.2', '329',
     'Grand excès de vitesse',
     'Grand excès de vitesse. Saisie du véhicule pour 7 jours. Points d\'inaptitude de 6 à 36.',
     'speed', 300, 3000, 6, 36, 'absolute',
     'https://legisquebec.gouv.qc.ca/fr/showdoc/cs/c-24.2'),
    ('QC', 'Code de la sécurité routière', 'C-24.2', '359',
     'Feu rouge',
     'Le conducteur d\'un véhicule routier ou d\'une bicyclette doit s\'immobiliser au feu rouge.',
     'red_light', 100, 200, 3, 3, 'absolute',
     'https://legisquebec.gouv.qc.ca/fr/showdoc/cs/c-24.2'),
    ('QC', 'Code de la sécurité routière', 'C-24.2', '396',
     'Ceinture de sécurité',
     'Le conducteur et chaque passager doivent porter correctement la ceinture de sécurité.',
     'seatbelt', 80, 100, 3, 3, 'absolute',
     'https://legisquebec.gouv.qc.ca/fr/showdoc/cs/c-24.2'),
    ('QC', 'Code de la sécurité routière', 'C-24.2', '443.1',
     'Cellulaire au volant',
     'Il est interdit d\'utiliser un appareil tenu en main comportant une fonction téléphonique pendant la conduite.',
     'handheld_device', 300, 600, 5, 5, 'absolute',
     'https://legisquebec.gouv.qc.ca/fr/showdoc/cs/c-24.2'),
    ('QC', 'Code de la sécurité routière', 'C-24.2', '368',
     'Arrêt obligatoire',
     'Le conducteur d\'un véhicule routier doit s\'immobiliser à un signal d\'arrêt.',
     'stop_sign', 100, 200, 3, 3, 'absolute',
     'https://legisquebec.gouv.qc.ca/fr/showdoc/cs/c-24.2'),

    # === ONTARIO - HTA R.S.O. 1990 c.H.8 ===
    ('ON', 'Highway Traffic Act', 'R.S.O. 1990 c.H.8', '128',
     'Speeding',
     'No person shall drive a motor vehicle at a rate of speed greater than the maximum speed posted.',
     'speed', None, None, 0, 6, 'absolute',
     'https://www.ontario.ca/laws/statute/90h08'),
    ('ON', 'Highway Traffic Act', 'R.S.O. 1990 c.H.8', '130',
     'Careless driving',
     'Every person is guilty of the offence of driving carelessly who drives a vehicle without due care and attention or without reasonable consideration for other persons.',
     'careless', 400, 2000, 6, 6, 'strict',
     'https://www.ontario.ca/laws/statute/90h08'),
    ('ON', 'Highway Traffic Act', 'R.S.O. 1990 c.H.8', '144',
     'Red light',
     'Every driver approaching a traffic control signal showing a circular red shall stop.',
     'red_light', None, None, 3, 3, 'absolute',
     'https://www.ontario.ca/laws/statute/90h08'),
    ('ON', 'Highway Traffic Act', 'R.S.O. 1990 c.H.8', '172',
     'Stunt driving / Racing',
     'No person shall drive a motor vehicle on a highway in a race or contest, while performing a stunt, or on a bet or wager. Includes 40+ km/h over in zones <80, 50+ km/h over in zones >=80, or 150+ km/h.',
     'stunt_driving', 2000, 10000, 6, 6, 'strict',
     'https://www.ontario.ca/laws/statute/90h08'),
    ('ON', 'Highway Traffic Act', 'R.S.O. 1990 c.H.8', '78.1',
     'Distracted driving / Hand-held device',
     'No person shall drive a motor vehicle while holding or using a hand-held wireless communication device.',
     'handheld_device', 615, 3000, 3, 6, 'absolute',
     'https://www.ontario.ca/laws/statute/90h08'),
    ('ON', 'Highway Traffic Act', 'R.S.O. 1990 c.H.8', '106',
     'Seatbelt',
     'Every person driving a motor vehicle shall wear a seatbelt assembly.',
     'seatbelt', None, None, 2, 2, 'absolute',
     'https://www.ontario.ca/laws/statute/90h08'),

    # === CODE CRIMINEL (federal) ===
    ('CA', 'Code criminel', 'L.R.C. 1985 c.C-46', '320.13',
     'Conduite dangereuse',
     'Commet une infraction quiconque conduit un moyen de transport d\'une façon dangereuse pour le public.',
     'dangerous', None, None, None, None, 'mens_rea',
     'https://laws-lois.justice.gc.ca/fra/lois/c-46/page-69.html'),
    ('CA', 'Code criminel', 'L.R.C. 1985 c.C-46', '320.14',
     'Conduite avec capacités affaiblies',
     'Commet une infraction quiconque conduit un moyen de transport avec les capacités affaiblies par l\'alcool ou la drogue.',
     'impaired', None, None, None, None, 'mens_rea',
     'https://laws-lois.justice.gc.ca/fra/lois/c-46/page-69.html'),
]


def run():
    """Insere les donnees statiques de reference."""
    logger.info("=" * 50)
    logger.info("MODULE DONNEES STATIQUES (reference)")
    logger.info("=" * 50)

    conn = get_connection()
    with conn:
        with conn.cursor() as cur:
            # Jurisprudence cle
            cur.execute("DELETE FROM ref_jurisprudence_cle")
            for j in JURISPRUDENCE_CLE:
                cur.execute("""
                    INSERT INTO ref_jurisprudence_cle
                    (province, nom_cas, citation, annee, tribunal, loi_applicable,
                     article_applicable, principe_juridique, type_infraction, resultat, url_canlii)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, j)
            logger.info(f"  {len(JURISPRUDENCE_CLE)} cas de jurisprudence cle inseres.")

            # Articles de loi
            cur.execute("DELETE FROM lois_articles")
            for a in ARTICLES_LOI:
                cur.execute("""
                    INSERT INTO lois_articles
                    (province, loi, code_loi, article, titre_article, texte_complet,
                     categorie, amende_min, amende_max, points_inaptitude_min,
                     points_inaptitude_max, type_responsabilite, url_source)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, a)
            logger.info(f"  {len(ARTICLES_LOI)} articles de loi inseres.")

    conn.close()
    log_import('ref_jurisprudence_cle', '', 'static_data', len(JURISPRUDENCE_CLE), len(JURISPRUDENCE_CLE))
    log_import('ref_lois_articles', '', 'static_data', len(ARTICLES_LOI), len(ARTICLES_LOI))
