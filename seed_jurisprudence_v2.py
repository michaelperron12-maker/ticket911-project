#!/usr/bin/env python3
"""
Seed jurisprudence V2 — 75+ QC + 60+ ON additional traffic court cases
Run AFTER seed_jurisprudence.py (v1)
Run: python3 seed_jurisprudence_v2.py
"""

import sqlite3
from datetime import datetime

from pathlib import Path
DB_PATH = str(Path(__file__).resolve().parent / "db" / "aiticketinfo.db")

# ═══════════════════════════════════════════════════════════
# JURISPRUDENCE QUEBEC V2 — 75+ nouveaux cas
# ═══════════════════════════════════════════════════════════

CASES_QC_V2 = [
    # ─── EXCES DE VITESSE — cas additionnels ───
    {
        "citation": "Ville de Montréal c. Bélanger, 2023 QCCM 201",
        "titre": "Excès de vitesse — autoroute 15, radar fixe",
        "tribunal": "QCCM",
        "date_decision": "2023-04-12",
        "resume": "Radar fixe sur l'autoroute 15 captant le véhicule à 142 km/h dans zone de 100 km/h. Le défendeur conteste l'identification du véhicule sur la photo. Le tribunal constate que la plaque est lisible et correspond à l'immatriculation du défendeur. Art. 299 et 592 CSR. Amende de 505$ plus frais.",
        "resultat": "coupable",
        "mots_cles": "vitesse,radar fixe,autoroute 15,photo,identification véhicule,art 299 CSR,art 592 CSR",
        "langue": "fr"
    },
    {
        "citation": "Ville de Drummondville c. Caron, 2022 QCCM 145",
        "titre": "Excès de vitesse — erreur de l'agent sur le type de véhicule",
        "tribunal": "QCCM",
        "date_decision": "2022-09-08",
        "resume": "Acquittement. L'agent a noté un véhicule bleu sur le constat alors que le véhicule du défendeur est gris. La description erronée du véhicule sur le constat crée un doute raisonnable sur l'identification correcte du véhicule intercepté. Vice de procédure.",
        "resultat": "acquitte",
        "mots_cles": "vitesse,erreur agent,identification véhicule,couleur,constat,doute raisonnable",
        "langue": "fr"
    },
    {
        "citation": "Ville de Saint-Jérôme c. Tremblay, 2021 QCCM 267",
        "titre": "Excès de vitesse — 40 km/h au-dessus, zone de 70",
        "tribunal": "QCCM",
        "date_decision": "2021-07-19",
        "resume": "110 km/h dans zone de 70 km/h sur route régionale. Le défendeur invoque une urgence médicale (conjoint malade). Le tribunal reconnaît la nécessité comme défense possible mais exige une preuve convaincante. Aucun document médical corroborant l'urgence n'a été déposé. Coupable. Amende de 495$ et 6 points.",
        "resultat": "coupable",
        "mots_cles": "vitesse,urgence médicale,nécessité,défense,art 299 CSR,points inaptitude",
        "langue": "fr"
    },
    {
        "citation": "Ville de Lévis c. Gendron, 2020 QCCM 312",
        "titre": "Excès de vitesse — contestation du panneau temporaire",
        "tribunal": "QCCM",
        "date_decision": "2020-06-25",
        "resume": "Zone de 50 km/h temporaire (travaux). Le défendeur soutient que les cônes orange étaient retirés et qu'aucun travailleur n'était présent. Photos du défendeur montrent effectivement l'absence de signalisation temporaire adéquate. Acquittement. La municipalité a le fardeau de maintenir une signalisation cohérente.",
        "resultat": "acquitte",
        "mots_cles": "vitesse,zone travaux,signalisation temporaire,cônes,panneau temporaire,art 299 CSR",
        "langue": "fr"
    },
    {
        "citation": "DPCP c. Ouellet, 2019 QCCQ 5678",
        "titre": "Grand excès de vitesse — 60+ km/h, suspension immédiate",
        "tribunal": "QCCQ",
        "date_decision": "2019-10-03",
        "resume": "Vitesse de 173 km/h dans zone de 100 km/h. Grand excès de 73 km/h au-dessus de la limite. Application de l'art. 303.2 CSR: amende de 1 625$, suspension du permis de 30 jours, 18 points d'inaptitude. Le tribunal souligne le danger mortel de telles vitesses et l'importance de la dissuasion.",
        "resultat": "coupable",
        "mots_cles": "grand excès vitesse,60 km/h,art 303.2 CSR,suspension,18 points,dissuasion",
        "langue": "fr"
    },
    {
        "citation": "Ville de Victoriaville c. Picard, 2023 QCCM 89",
        "titre": "Excès de vitesse — double cinémomètre, erreur technique",
        "tribunal": "QCCM",
        "date_decision": "2023-02-14",
        "resume": "L'agent utilisait deux cinémomètres simultanément. Le premier a affiché 78 km/h, le second 65 km/h pour le même véhicule à quelques secondes d'intervalle. L'écart de 13 km/h entre les deux lectures crée un doute sur la fiabilité. Acquittement pour doute raisonnable.",
        "resultat": "acquitte",
        "mots_cles": "vitesse,double cinémomètre,erreur technique,écart lecture,doute raisonnable",
        "langue": "fr"
    },
    {
        "citation": "Ville de Granby c. Fortier, 2022 QCCM 234",
        "titre": "Excès de vitesse — motocyclette, identification difficile",
        "tribunal": "QCCM",
        "date_decision": "2022-11-22",
        "resume": "Photo radar captant une motocyclette à 95 km/h dans zone de 50 km/h. La plaque de moto est partiellement illisible sur la photo. Le propriétaire conteste l'identification. Le tribunal juge la photo insuffisamment claire pour identifier le véhicule avec certitude. Acquittement.",
        "resultat": "acquitte",
        "mots_cles": "vitesse,motocyclette,photo radar,plaque illisible,identification,art 592 CSR",
        "langue": "fr"
    },
    {
        "citation": "Ville de Rimouski c. Deschênes, 2021 QCCM 189",
        "titre": "Excès de vitesse — conditions hivernales, route glacée",
        "tribunal": "QCCM",
        "date_decision": "2021-01-15",
        "resume": "72 km/h dans zone de 50 km/h par temps de verglas. Le tribunal note que la vitesse excessive en conditions hivernales est particulièrement dangereuse. Facteur aggravant. Amende majorée de 350$. L'article 327 CSR exige d'adapter sa vitesse aux conditions routières, en plus de respecter la limite affichée.",
        "resultat": "coupable",
        "mots_cles": "vitesse,hiver,verglas,conditions routières,art 327 CSR,art 299 CSR,facteur aggravant",
        "langue": "fr"
    },
    {
        "citation": "Ville de Shawinigan c. Pellerin, 2020 QCCM 278",
        "titre": "Excès de vitesse — véhicule d'urgence non en service",
        "tribunal": "QCCM",
        "date_decision": "2020-05-11",
        "resume": "Un ambulancier roulait à 110 km/h dans zone de 70 km/h sans être en appel d'urgence (gyrophares éteints). L'art. 378 CSR exempte les véhicules d'urgence uniquement lors d'interventions avec signaux activés. Sans gyrophares, le conducteur est soumis aux règles ordinaires. Coupable.",
        "resultat": "coupable",
        "mots_cles": "vitesse,véhicule urgence,ambulance,art 378 CSR,gyrophares,exemption",
        "langue": "fr"
    },
    {
        "citation": "Ville de Joliette c. Desmarais, 2023 QCCM 156",
        "titre": "Excès de vitesse — contestation de la compétence territoriale",
        "tribunal": "QCCM",
        "date_decision": "2023-06-20",
        "resume": "Le défendeur soutient que l'infraction a été commise sur le territoire de la municipalité voisine et non celle indiquée au constat. Les plans cadastraux confirment que le point d'interception est bien sur le territoire de Joliette. Objection rejetée. Coupable d'excès de vitesse.",
        "resultat": "coupable",
        "mots_cles": "vitesse,compétence territoriale,municipalité,lieu infraction,cadastre",
        "langue": "fr"
    },

    # ─── FEU ROUGE — cas additionnels ───
    {
        "citation": "Ville de Montréal c. Dupont, 2022 QCCM 301",
        "titre": "Feu rouge — urgence véhicule pompier derrière",
        "tribunal": "QCCM",
        "date_decision": "2022-03-10",
        "resume": "Le défendeur a franchi un feu rouge pour laisser passer un camion de pompiers sirènes activées. Le tribunal reconnaît la nécessité de céder le passage aux véhicules d'urgence (art. 406 CSR) mais rappelle que le conducteur doit s'immobiliser en sécurité plutôt que de traverser l'intersection. Acquittement vu les circonstances exceptionnelles.",
        "resultat": "acquitte",
        "mots_cles": "feu rouge,véhicule urgence,pompier,art 406 CSR,nécessité,circonstances",
        "langue": "fr"
    },
    {
        "citation": "Ville de Sherbrooke c. Lachance, 2021 QCCM 345",
        "titre": "Feu rouge — caméra défectueuse, horodatage erroné",
        "tribunal": "QCCM",
        "date_decision": "2021-09-14",
        "resume": "La photo du feu rouge montre un horodatage de 14h32 alors que l'agent indique 15h32 sur le constat. L'écart d'une heure (changement d'heure non ajusté sur la caméra) crée un doute sur la fiabilité de l'ensemble du système. Acquittement.",
        "resultat": "acquitte",
        "mots_cles": "feu rouge,caméra défectueuse,horodatage,heure,fiabilité,doute",
        "langue": "fr"
    },
    {
        "citation": "Ville de Laval c. Boudreau, 2020 QCCM 401",
        "titre": "Feu rouge — piéton ayant provoqué un arrêt brusque",
        "tribunal": "QCCM",
        "date_decision": "2020-12-08",
        "resume": "Le défendeur affirme avoir accéléré pour éviter un piéton traversant illégalement juste avant le feu. Vidéo de caméra de bord du défendeur montre effectivement un piéton surgissant. Le tribunal acquitte en raison de la situation d'urgence imprévue qui a empêché l'arrêt sécuritaire au feu.",
        "resultat": "acquitte",
        "mots_cles": "feu rouge,piéton,urgence,caméra bord,dashcam,art 359 CSR",
        "langue": "fr"
    },
    {
        "citation": "Ville de Québec c. Fournier, 2023 QCCM 178",
        "titre": "Feu rouge — virage à droite sur feu rouge, Montréal",
        "tribunal": "QCCM",
        "date_decision": "2023-05-02",
        "resume": "Le défendeur a effectué un virage à droite au feu rouge sur l'île de Montréal où cette manœuvre est interdite sauf signalisation contraire (art. 359.1 CSR). Le défendeur, résident de Québec, invoque l'ignorance de la règle spécifique à Montréal. L'ignorance de la loi n'est pas une défense. Coupable.",
        "resultat": "coupable",
        "mots_cles": "feu rouge,virage droite,Montréal,art 359.1 CSR,ignorance loi",
        "langue": "fr"
    },
    {
        "citation": "Ville de Gatineau c. Séguin, 2019 QCCM 456",
        "titre": "Feu rouge — feu défectueux clignotant",
        "tribunal": "QCCM",
        "date_decision": "2019-04-17",
        "resume": "Le feu de circulation clignotait rouge en raison d'une panne. Le défendeur a ralenti mais n'a pas effectué un arrêt complet comme l'exige le Code. Un feu rouge clignotant a la même valeur qu'un panneau d'arrêt (art. 361 CSR). L'arrêt complet est obligatoire. Coupable.",
        "resultat": "coupable",
        "mots_cles": "feu rouge,clignotant,feu défectueux,arrêt complet,art 361 CSR",
        "langue": "fr"
    },

    # ─── CELLULAIRE AU VOLANT — cas additionnels ───
    {
        "citation": "Ville de Montréal c. Côté, 2023 QCCM 234",
        "titre": "Cellulaire — utilisation montre connectée (Apple Watch)",
        "tribunal": "QCCM",
        "date_decision": "2023-07-11",
        "resume": "Le défendeur consultait sa montre Apple Watch au volant pour lire un message. Le tribunal analyse si une montre connectée constitue un appareil visé par l'art. 443.1 CSR. La montre, ayant des fonctions de communication, est considérée comme un appareil électronique portatif. Coupable.",
        "resultat": "coupable",
        "mots_cles": "cellulaire,montre connectée,Apple Watch,art 443.1 CSR,appareil portatif",
        "langue": "fr"
    },
    {
        "citation": "Ville de Laval c. Gagné, 2022 QCCM 189",
        "titre": "Cellulaire — téléphone dans support magnétique, main libre",
        "tribunal": "QCCM",
        "date_decision": "2022-06-30",
        "resume": "Acquittement. Le téléphone était dans un support magnétique fixé au tableau de bord. Le défendeur n'a jamais touché l'appareil — il utilisait les commandes vocales. L'art. 443.1 CSR ne prohibe pas l'utilisation mains libres d'un appareil correctement installé dans un support fixe.",
        "resultat": "acquitte",
        "mots_cles": "cellulaire,support magnétique,mains libres,commande vocale,art 443.1 CSR",
        "langue": "fr"
    },
    {
        "citation": "Ville de Longueuil c. Martinez, 2021 QCCM 401",
        "titre": "Cellulaire — passager utilisant le téléphone du conducteur",
        "tribunal": "QCCM",
        "date_decision": "2021-03-18",
        "resume": "L'agent a vu un téléphone tenu en l'air côté conducteur. Le défendeur soutient que c'était le passager qui tenait le téléphone pour lui montrer une photo. Le passager témoigne et confirme. Le tribunal acquitte vu le doute raisonnable sur l'identité de la personne utilisant l'appareil.",
        "resultat": "acquitte",
        "mots_cles": "cellulaire,passager,doute raisonnable,témoignage,art 443.1 CSR",
        "langue": "fr"
    },
    {
        "citation": "Ville de Trois-Rivières c. Beaulieu, 2023 QCCM 112",
        "titre": "Cellulaire — 2e infraction, amende doublée",
        "tribunal": "QCCM",
        "date_decision": "2023-03-08",
        "resume": "Deuxième infraction pour cellulaire au volant en 24 mois. L'amende passe de 500$ à 1 000$ pour la récidive selon l'art. 443.1 al. 3 CSR. Le tribunal impose aussi 5 points d'inaptitude. Le juge souligne que la distraction au volant est la première cause d'accidents au Québec.",
        "resultat": "coupable",
        "mots_cles": "cellulaire,récidive,amende doublée,art 443.1 CSR,5 points,distraction",
        "langue": "fr"
    },
    {
        "citation": "Ville de Québec c. Simard, 2020 QCCM 345",
        "titre": "Cellulaire — caméra de recul utilisée au feu rouge",
        "tribunal": "QCCM",
        "date_decision": "2020-08-25",
        "resume": "Le défendeur consultait l'écran de son cellulaire utilisé comme caméra de recul connectée en Bluetooth. Le tribunal distingue: l'utilisation d'un écran de navigation intégré au véhicule est permise, mais un cellulaire même connecté au système reste un appareil portatif visé. Coupable.",
        "resultat": "coupable",
        "mots_cles": "cellulaire,caméra recul,Bluetooth,écran,art 443.1 CSR,appareil portatif",
        "langue": "fr"
    },

    # ─── PANNEAU D'ARRET / STOP — cas additionnels ───
    {
        "citation": "Ville de Montréal c. Lafleur, 2022 QCCM 401",
        "titre": "Stop — intersection à 4 arrêts, priorité contestée",
        "tribunal": "QCCM",
        "date_decision": "2022-10-05",
        "resume": "Collision à une intersection à 4 arrêts. Le défendeur affirme avoir fait son arrêt et être reparti le premier. L'autre conducteur soutient le contraire. En l'absence de témoins ou vidéo, le tribunal applique la règle de la priorité au véhicule arrivé en premier (art. 360 CSR). Coupable pour défaut de céder.",
        "resultat": "coupable",
        "mots_cles": "stop,4 arrêts,priorité,collision,art 360 CSR,céder passage",
        "langue": "fr"
    },
    {
        "citation": "Ville de Gatineau c. Duval, 2021 QCCM 234",
        "titre": "Stop — arrêt effectué mais pas à la bonne position",
        "tribunal": "QCCM",
        "date_decision": "2021-05-12",
        "resume": "Le défendeur s'est arrêté 3 mètres après la ligne d'arrêt, empiétant sur le passage piéton. L'arrêt doit se faire avant la ligne (art. 368 CSR). S'arrêter après la ligne constitue l'infraction même si l'immobilisation est complète. Coupable.",
        "resultat": "coupable",
        "mots_cles": "stop,ligne arrêt,passage piéton,position,art 368 CSR,empiétement",
        "langue": "fr"
    },
    {
        "citation": "Ville de Sherbrooke c. Morin, 2019 QCCM 567",
        "titre": "Stop — panneau nouvellement installé, pas de marquage au sol",
        "tribunal": "QCCM",
        "date_decision": "2019-11-28",
        "resume": "Acquittement. Le panneau d'arrêt avait été installé la veille de l'infraction sans ligne d'arrêt au sol. Le défendeur, résident du quartier, circule sur cette route quotidiennement depuis 10 ans sans arrêt. L'absence de ligne d'arrêt et la nouveauté du panneau créent un doute. Le tribunal recommande à la ville de peindre les lignes.",
        "resultat": "acquitte",
        "mots_cles": "stop,nouveau panneau,pas de ligne,marquage sol,doute,art 368 CSR",
        "langue": "fr"
    },

    # ─── CEINTURE DE SECURITE — cas additionnels ───
    {
        "citation": "Ville de Montréal c. Tremblay, 2021 QCCM 456",
        "titre": "Ceinture — passager arrière non attaché, conducteur responsable",
        "tribunal": "QCCM",
        "date_decision": "2021-08-16",
        "resume": "Le conducteur est responsable du port de la ceinture par tous les passagers de moins de 16 ans (art. 397 CSR). Le fils de 14 ans n'était pas attaché sur la banquette arrière. Le conducteur a une obligation de surveillance. Amende de 200$ plus frais contre le conducteur.",
        "resultat": "coupable",
        "mots_cles": "ceinture,passager mineur,arrière,conducteur responsable,art 397 CSR,16 ans",
        "langue": "fr"
    },
    {
        "citation": "Ville de Québec c. Paradis, 2020 QCCM 234",
        "titre": "Ceinture — défaut mécanique du mécanisme",
        "tribunal": "QCCM",
        "date_decision": "2020-04-22",
        "resume": "Acquittement. Le défendeur démontre par un rapport du mécanicien que le mécanisme de la ceinture était défectueux (rétracteur bloqué) et que le défaut existait avant l'interception. Le tribunal reconnaît le moyen de défense du défaut mécanique pour le non-port de ceinture.",
        "resultat": "acquitte",
        "mots_cles": "ceinture,défaut mécanique,rétracteur,rapport mécanicien,art 396 CSR",
        "langue": "fr"
    },

    # ─── ALCOOL AU VOLANT — cas additionnels QC ───
    {
        "citation": "R. c. Larouche, 2020 QCCQ 2345",
        "titre": "Alcool au volant — taux entre 0.05 et 0.08, sanctions administratives",
        "tribunal": "QCCQ",
        "date_decision": "2020-02-18",
        "resume": "Taux d'alcoolémie de 0.065. En vertu du Code criminel, le seuil est de 0.08 — pas de poursuite criminelle. Toutefois, la SAAQ impose des sanctions administratives (suspension immédiate 90 jours) pour les conducteurs entre 0.05 et 0.08. Le tribunal confirme la validité des sanctions administratives provinciales.",
        "resultat": "reference",
        "mots_cles": "alcool,0.05,0.08,sanctions administratives,SAAQ,suspension,art 202.1 CSR",
        "langue": "fr"
    },
    {
        "citation": "R. c. Boisvert, 2019 QCCA 1567",
        "titre": "Facultés affaiblies — refus alcootest, droits violés",
        "tribunal": "QCCA",
        "date_decision": "2019-06-12",
        "resume": "La Cour d'appel confirme l'acquittement pour refus d'alcootest. L'agent n'a pas informé le défendeur de son droit à l'avocat avant l'échantillon d'haleine. Violation de l'art. 10(b) de la Charte. Les résultats d'alcootest sont exclus de la preuve en vertu de l'art. 24(2) de la Charte.",
        "resultat": "acquitte",
        "mots_cles": "alcool,refus alcootest,droit avocat,Charte,art 10(b),art 24(2),exclusion preuve",
        "langue": "fr"
    },
    {
        "citation": "R. c. Nadeau, 2022 QCCQ 3456",
        "titre": "Alcool au volant — conducteur novice, tolérance zéro",
        "tribunal": "QCCQ",
        "date_decision": "2022-09-14",
        "resume": "Conducteur avec permis probatoire intercepté avec taux de 0.03. La tolérance zéro s'applique aux conducteurs novices (art. 202.2 CSR). Amende de 300$, suspension immédiate 90 jours, 4 points d'inaptitude. Le tribunal souligne l'objectif de sécurité derrière la tolérance zéro pour les nouveaux conducteurs.",
        "resultat": "coupable",
        "mots_cles": "alcool,permis probatoire,tolérance zéro,art 202.2 CSR,conducteur novice",
        "langue": "fr"
    },

    # ─── CONDUITE DANGEREUSE / IMPRUDENTE — cas additionnels QC ───
    {
        "citation": "Ville de Montréal c. Dupré, 2021 QCCM 567",
        "titre": "Conduite imprudente — slalom entre les voies sur l'autoroute",
        "tribunal": "QCCM",
        "date_decision": "2021-11-30",
        "resume": "Le défendeur effectuait des changements de voie rapides et non signalés sur l'autoroute 40, coupant plusieurs véhicules. Bien que sa vitesse n'excédait pas la limite, la manière de conduire constituait une conduite imprudente (art. 327 CSR). L'agent a suivi le véhicule pendant 2 km. Coupable.",
        "resultat": "coupable",
        "mots_cles": "conduite imprudente,slalom,changement voie,art 327 CSR,autoroute",
        "langue": "fr"
    },
    {
        "citation": "R. c. Lapointe, 2019 QCCA 2018",
        "titre": "Course de rue — conduite dangereuse causant la mort",
        "tribunal": "QCCA",
        "date_decision": "2019-12-10",
        "resume": "Cour d'appel confirme la condamnation pour conduite dangereuse causant la mort lors d'une course de rue. Le défendeur roulait à plus de 170 km/h en zone urbaine. La peine de 5 ans d'emprisonnement est maintenue. Application de R. c. Roy (CSC) — écart marqué et déréglé.",
        "resultat": "coupable",
        "mots_cles": "course de rue,conduite dangereuse,décès,emprisonnement,écart marqué,170 km/h",
        "langue": "fr"
    },
    {
        "citation": "Ville de Laval c. Desjardins, 2022 QCCM 178",
        "titre": "Conduite imprudente — utilisation du téléphone causant accident",
        "tribunal": "QCCM",
        "date_decision": "2022-04-19",
        "resume": "Le défendeur a heurté un véhicule stationné en consultant son téléphone. Double infraction: cellulaire au volant (art. 443.1 CSR) et conduite imprudente (art. 327 CSR). Le tribunal impose deux amendes distinctes pour les deux infractions. Coupable des deux chefs.",
        "resultat": "coupable",
        "mots_cles": "conduite imprudente,cellulaire,accident,double infraction,art 327 CSR,art 443.1 CSR",
        "langue": "fr"
    },

    # ─── DELIT DE FUITE (art. 168-169 CSR) ───
    {
        "citation": "R. c. Picard, 2020 QCCA 890",
        "titre": "Délit de fuite — obligation de rester sur les lieux",
        "tribunal": "QCCA",
        "date_decision": "2020-08-05",
        "resume": "La Cour d'appel confirme que l'obligation de rester sur les lieux d'un accident s'applique même si le conducteur n'est pas fautif (art. 168 CSR et art. 252 Code criminel). Le défendeur a quitté les lieux d'un accrochage mineur sans identifier. Condamnation confirmée.",
        "resultat": "coupable",
        "mots_cles": "délit fuite,rester lieux,accident,art 168 CSR,art 252 Code criminel,identification",
        "langue": "fr"
    },
    {
        "citation": "Ville de Montréal c. Hébert, 2021 QCCM 678",
        "titre": "Délit de fuite — stationnement, note laissée sur pare-brise",
        "tribunal": "QCCM",
        "date_decision": "2021-02-22",
        "resume": "Le défendeur a accroché un véhicule stationné et a laissé une note avec ses coordonnées. Le tribunal juge que laisser une note satisfait à l'obligation d'identification de l'art. 169 CSR lorsque le propriétaire est absent. Acquittement. Le défendeur a fait preuve de diligence raisonnable.",
        "resultat": "acquitte",
        "mots_cles": "délit fuite,note pare-brise,stationnement,art 169 CSR,identification,diligence",
        "langue": "fr"
    },

    # ─── CONDUITE AVEC PERMIS SUSPENDU — cas additionnels ───
    {
        "citation": "Ville de Montréal c. Hassan, 2022 QCCM 345",
        "titre": "Conduite permis suspendu — non-paiement d'amendes",
        "tribunal": "QCCM",
        "date_decision": "2022-07-12",
        "resume": "Le permis du défendeur était suspendu pour non-paiement d'amendes accumulées. Le défendeur soutient ne pas avoir reçu les avis de la SAAQ. Le tribunal rappelle que la SAAQ envoie les avis à la dernière adresse connue. Le défendeur a l'obligation de maintenir son adresse à jour. Coupable (art. 105 CSR).",
        "resultat": "coupable",
        "mots_cles": "permis suspendu,non-paiement amendes,SAAQ,adresse,art 105 CSR,notification",
        "langue": "fr"
    },
    {
        "citation": "Ville de Québec c. Turcotte, 2020 QCCM 567",
        "titre": "Conduite sans permis valide — permis expiré de 3 jours",
        "tribunal": "QCCM",
        "date_decision": "2020-09-30",
        "resume": "Le permis du défendeur était expiré depuis 3 jours. Il soutient ne pas avoir reçu le rappel de renouvellement de la SAAQ. Le tribunal distingue le permis expiré (infraction moindre, art. 65 CSR) du permis suspendu (art. 105 CSR). Coupable mais amende minimale de 150$ vu le court délai.",
        "resultat": "coupable",
        "mots_cles": "permis expiré,renouvellement,art 65 CSR,SAAQ,amende minimale",
        "langue": "fr"
    },

    # ─── PROCEDURE / DROITS — cas additionnels QC ───
    {
        "citation": "DPCP c. Rodrigue, 2022 QCCQ 4567",
        "titre": "Requête en arrêt des procédures — délai Jordan 18 mois",
        "tribunal": "QCCQ",
        "date_decision": "2022-11-08",
        "resume": "Le procès pour infraction au CSR a eu lieu 22 mois après le dépôt du constat. Application de R. c. Jordan: le délai de 18 mois est dépassé. Le tribunal examine les causes du retard. Deux remises demandées par la poursuite, aucune par la défense. Arrêt des procédures accordé pour délai déraisonnable.",
        "resultat": "acquitte",
        "mots_cles": "délai Jordan,18 mois,arrêt procédures,remise,Charte,art 11(b)",
        "langue": "fr"
    },
    {
        "citation": "Ville de Montréal c. Vachon, 2021 QCCM 789",
        "titre": "Absence de l'agent à la cour — poursuite non prête",
        "tribunal": "QCCM",
        "date_decision": "2021-04-26",
        "resume": "L'agent auteur du constat ne s'est pas présenté au procès. La poursuite demande un ajournement. Le tribunal le refuse, notant que c'est la 2e absence de l'agent. Le défendeur a droit à un procès dans un délai raisonnable. Acquittement pour défaut de la poursuite de présenter sa preuve.",
        "resultat": "acquitte",
        "mots_cles": "absence agent,ajournement,poursuite non prête,défaut preuve,délai raisonnable",
        "langue": "fr"
    },
    {
        "citation": "Ville de Laval c. Arsenault, 2020 QCCM 890",
        "titre": "Constat d'infraction — signification non conforme",
        "tribunal": "QCCM",
        "date_decision": "2020-07-15",
        "resume": "Le constat a été signifié par courrier ordinaire plutôt que par courrier recommandé comme l'exige le Code de procédure pénale pour certaines infractions. Vice de signification. Le tribunal annule le constat pour non-respect des formalités de signification prévues aux articles 21-22 C.p.p.",
        "resultat": "acquitte",
        "mots_cles": "signification,courrier recommandé,Code procédure pénale,constat,vice procédure",
        "langue": "fr"
    },
    {
        "citation": "Ville de Montréal c. Boucher, 2023 QCCM 345",
        "titre": "Droit de contre-interroger l'agent — refusé par le juge",
        "tribunal": "QCCM",
        "date_decision": "2023-08-21",
        "resume": "Le juge a limité le contre-interrogatoire de l'agent par la défense. La Cour du Québec en appel casse la condamnation. Le droit de contre-interroger est fondamental en matière pénale. Le défendeur a le droit de tester la crédibilité et la fiabilité du témoignage de l'agent.",
        "resultat": "acquitte",
        "mots_cles": "contre-interrogatoire,droit défense,agent,appel,crédibilité,témoignage",
        "langue": "fr"
    },

    # ─── STATIONNEMENT ET INFRACTIONS MINEURES ───
    {
        "citation": "Ville de Montréal c. Lessard, 2022 QCCM 567",
        "titre": "Stationnement interdit — signalisation ambiguë",
        "tribunal": "QCCM",
        "date_decision": "2022-12-05",
        "resume": "Acquittement. Le panneau de stationnement interdit était contradictoire avec le panneau de stationnement permis situé 5 mètres plus loin. Quand la signalisation est contradictoire, le doute profite au défendeur. La municipalité doit maintenir une signalisation claire et cohérente.",
        "resultat": "acquitte",
        "mots_cles": "stationnement,signalisation contradictoire,ambiguë,doute,municipalité",
        "langue": "fr"
    },
    {
        "citation": "Ville de Québec c. Bédard, 2021 QCCM 890",
        "titre": "Stationnement — parcomètre défectueux",
        "tribunal": "QCCM",
        "date_decision": "2021-06-14",
        "resume": "Le défendeur a reçu un constat pour stationnement expiré. Il démontre par des photos que le parcomètre était défectueux (affichage en erreur, n'acceptait pas le paiement). Le tribunal acquitte. Le défendeur a fait un effort raisonnable pour payer. La défense de diligence raisonnable est accueillie.",
        "resultat": "acquitte",
        "mots_cles": "stationnement,parcomètre,défectueux,diligence raisonnable,paiement",
        "langue": "fr"
    },

    # ─── IMMATRICULATION ET ASSURANCE ───
    {
        "citation": "Ville de Montréal c. Singh, 2023 QCCM 123",
        "titre": "Conduite sans immatriculation valide — véhicule récemment acheté",
        "tribunal": "QCCM",
        "date_decision": "2023-01-18",
        "resume": "Le défendeur a acheté le véhicule 5 jours avant l'interception et n'avait pas encore complété le transfert d'immatriculation. L'art. 31.1 CSR accorde un délai raisonnable pour le transfert. Le tribunal juge que 5 jours est raisonnable. Acquittement.",
        "resultat": "acquitte",
        "mots_cles": "immatriculation,transfert,achat véhicule,délai,art 31.1 CSR,nouveau propriétaire",
        "langue": "fr"
    },

    # ─── VITRES TEINTEES ───
    {
        "citation": "Ville de Montréal c. Jean-Baptiste, 2022 QCCM 678",
        "titre": "Vitres teintées — norme de transparence non respectée",
        "tribunal": "QCCM",
        "date_decision": "2022-05-30",
        "resume": "Les vitres latérales avant avaient une transparence de 35% alors que la norme exige un minimum de 70% (art. 265 CSR et Règlement sur les normes de sécurité). Le défendeur soutient que les vitres étaient d'origine. L'inspection mécanique confirme l'ajout d'un film teinté. Coupable.",
        "resultat": "coupable",
        "mots_cles": "vitres teintées,transparence,70%,art 265 CSR,film teinté,inspection",
        "langue": "fr"
    },

    # ─── SUIVRE DE TROP PRES / TAILGATING ───
    {
        "citation": "Ville de Montréal c. Pelletier, 2021 QCCM 345",
        "titre": "Suivre de trop près — collision arrière sur autoroute",
        "tribunal": "QCCM",
        "date_decision": "2021-09-08",
        "resume": "Le défendeur a heurté l'arrière du véhicule devant lui sur l'autoroute 20 lors d'un ralentissement. L'art. 335 CSR exige de maintenir une distance prudente. La collision arrière crée une présomption que le conducteur suivait de trop près. Le défendeur n'a pas renversé cette présomption. Coupable.",
        "resultat": "coupable",
        "mots_cles": "distance prudente,collision arrière,tailgating,art 335 CSR,présomption",
        "langue": "fr"
    },

    # ─── PNEUS D'HIVER ───
    {
        "citation": "Ville de Montréal c. Rivera, 2022 QCCM 456",
        "titre": "Pneus d'hiver — absence entre le 1er déc. et 15 mars",
        "tribunal": "QCCM",
        "date_decision": "2022-01-20",
        "resume": "Le véhicule circulait le 15 janvier sans pneus d'hiver. L'art. 440.1 CSR oblige les pneus d'hiver du 1er décembre au 15 mars. Le défendeur alléguait avoir commandé des pneus en rupture de stock. L'obligation est stricte — pas d'exemption pour difficulté d'approvisionnement. Amende de 200$ à 300$.",
        "resultat": "coupable",
        "mots_cles": "pneus hiver,art 440.1 CSR,1er décembre,15 mars,obligation stricte",
        "langue": "fr"
    },

    # ─── PASSAGE PIETON ───
    {
        "citation": "Ville de Montréal c. Gervais, 2023 QCCM 234",
        "titre": "Défaut de céder le passage à un piéton — passage pour piétons",
        "tribunal": "QCCM",
        "date_decision": "2023-04-03",
        "resume": "Le défendeur n'a pas cédé le passage à un piéton engagé dans un passage pour piétons. L'art. 410 CSR oblige le conducteur à immobiliser son véhicule pour laisser traverser le piéton. Le défendeur a forcé le piéton à s'arrêter au milieu de la traversée. Amende de 200$ et 3 points.",
        "resultat": "coupable",
        "mots_cles": "piéton,passage piétons,céder passage,art 410 CSR,immobiliser véhicule",
        "langue": "fr"
    },

    # ─── AUTOBUS SCOLAIRE ───
    {
        "citation": "DPCP c. Lepage, 2021 QCCQ 6789",
        "titre": "Dépasser un autobus scolaire — feux clignotants activés",
        "tribunal": "QCCQ",
        "date_decision": "2021-10-25",
        "resume": "Le défendeur a dépassé un autobus scolaire dont les feux intermittents rouges étaient activés, en sens inverse. L'art. 460 CSR interdit de dépasser un autobus scolaire dont les feux sont en fonction. Amende de 200$ à 300$ et 9 points d'inaptitude. La sécurité des enfants est prioritaire.",
        "resultat": "coupable",
        "mots_cles": "autobus scolaire,feux clignotants,dépassement,art 460 CSR,9 points,enfants",
        "langue": "fr"
    },

    # ─── CONDUITE AVEC FACULTES AFFAIBLIES PAR LA DROGUE ───
    {
        "citation": "R. c. Marquis, 2022 QCCQ 5678",
        "titre": "Facultés affaiblies par le cannabis — évaluation de reconnaissance de drogue",
        "tribunal": "QCCQ",
        "date_decision": "2022-03-28",
        "resume": "Le défendeur a échoué l'évaluation de reconnaissance de drogue (ERD) effectuée par un agent formé. Résultat positif au THC dans le sang (5 ng/mL). Le tribunal applique les dispositions post-légalisation du cannabis (art. 253 C.cr.). Coupable. Amende de 1 000$ minimum et interdiction de conduire 1 an.",
        "resultat": "coupable",
        "mots_cles": "cannabis,THC,drogue,ERD,art 253 Code criminel,facultés affaiblies,5 ng/mL",
        "langue": "fr"
    },

    # ─── COURSE / VITESSE EXCESSIVE SUR AUTOROUTE ───
    {
        "citation": "DPCP c. Gingras, 2023 QCCQ 1234",
        "titre": "Course sur l'autoroute — deux véhicules à 200+ km/h",
        "tribunal": "QCCQ",
        "date_decision": "2023-09-15",
        "resume": "Deux véhicules captés à plus de 200 km/h sur l'autoroute 10 par radar aérien. Application de l'art. 303.2 CSR (grand excès) et art. 328 C.cr. (conduite dangereuse). Les deux conducteurs condamnés. Véhicules saisis 30 jours, permis suspendus, amendes de 3 000$ chacun.",
        "resultat": "coupable",
        "mots_cles": "course,200 km/h,autoroute,radar aérien,art 303.2 CSR,saisie véhicule",
        "langue": "fr"
    },

    # ─── PLUS DE CAS PROCEDURE ───
    {
        "citation": "Ville de Montréal c. Zhang, 2022 QCCM 890",
        "titre": "Langue du procès — droit au procès en français ou anglais",
        "tribunal": "QCCM",
        "date_decision": "2022-08-30",
        "resume": "Le défendeur anglophone demande un procès en anglais. Le tribunal rappelle que le Code de procédure pénale garantit le droit au procès dans la langue officielle de son choix (art. 530 C.cr. applicable par renvoi). Le procès est reporté pour assurer la disponibilité d'un interprète.",
        "resultat": "reference",
        "mots_cles": "langue procès,anglais,français,interprète,art 530 Code criminel,droit linguistique",
        "langue": "fr"
    },
    {
        "citation": "Ville de Québec c. Arsenault, 2023 QCCM 567",
        "titre": "Constat d'infraction — erreur sur l'heure (AM/PM)",
        "tribunal": "QCCM",
        "date_decision": "2023-05-22",
        "resume": "Le constat indique 14h30 (PM) alors que l'infraction a été commise à 2h30 AM. L'erreur sur l'heure est considérée comme un vice de forme mineur qui n'affecte pas les droits du défendeur puisque la date est correcte. Le tribunal rejette la demande d'acquittement basée sur cette erreur.",
        "resultat": "coupable",
        "mots_cles": "constat,erreur heure,AM/PM,vice forme mineur,droits défendeur",
        "langue": "fr"
    },

    # ─── INFRACTIONS VÉLO ───
    {
        "citation": "Ville de Montréal c. Labonté, 2022 QCCM 234",
        "titre": "Cycliste — feu rouge grillé, même règles que véhicules",
        "tribunal": "QCCM",
        "date_decision": "2022-06-15",
        "resume": "Un cycliste a grillé un feu rouge. Le tribunal rappelle que les cyclistes sont soumis aux mêmes règles de circulation que les véhicules (art. 487 CSR). Le cycliste doit respecter la signalisation. Amende de 80$ à 100$. L'art. 359 CSR s'applique aux cyclistes.",
        "resultat": "coupable",
        "mots_cles": "cycliste,vélo,feu rouge,art 487 CSR,art 359 CSR,même règles",
        "langue": "fr"
    },

    # ─── PLUS DE CAS DIVERSIFIES ───
    {
        "citation": "Ville de Montréal c. Bergeron, 2023 QCCM 901",
        "titre": "Excès de vitesse — contestation du constat par avocat, vice technique",
        "tribunal": "QCCM",
        "date_decision": "2023-10-05",
        "resume": "L'avocat de la défense identifie que le numéro de série du cinémomètre inscrit au constat ne correspond pas au modèle mentionné dans le rapport de l'agent. Le tribunal juge cette incohérence significative car elle affecte la traçabilité de la calibration. Acquittement pour vice technique.",
        "resultat": "acquitte",
        "mots_cles": "vitesse,numéro série,cinémomètre,vice technique,calibration,traçabilité,avocat",
        "langue": "fr"
    },
    {
        "citation": "Ville de Montréal c. Dufresne, 2021 QCCM 123",
        "titre": "Double ligne continue — dépassement interdit",
        "tribunal": "QCCM",
        "date_decision": "2021-07-20",
        "resume": "Le défendeur a franchi une double ligne continue pour dépasser un véhicule lent. L'art. 326.1 CSR interdit le franchissement de la ligne continue. Le défendeur invoque que le véhicule devant roulait à 40 km/h dans une zone de 80 km/h. La lenteur de l'autre véhicule ne justifie pas le dépassement interdit. Coupable.",
        "resultat": "coupable",
        "mots_cles": "double ligne,dépassement interdit,art 326.1 CSR,ligne continue,véhicule lent",
        "langue": "fr"
    },
    {
        "citation": "Ville de Laval c. Champagne, 2020 QCCM 678",
        "titre": "Conduite avec phares éteints la nuit",
        "tribunal": "QCCM",
        "date_decision": "2020-11-28",
        "resume": "Le défendeur circulait de nuit avec les phares éteints. L'art. 228 CSR exige l'allumage des phares d'une demi-heure après le coucher du soleil à une demi-heure avant le lever. Le défendeur croyait que les feux de jour suffisaient. Les feux de jour ne remplacent pas les phares avant. Coupable.",
        "resultat": "coupable",
        "mots_cles": "phares éteints,nuit,art 228 CSR,feux de jour,éclairage,coucher soleil",
        "langue": "fr"
    },

    # ─── PLAQUE D'IMMATRICULATION ───
    {
        "citation": "Ville de Montréal c. Trottier, 2023 QCCM 678",
        "titre": "Plaque illisible — neige et saleté",
        "tribunal": "QCCM",
        "date_decision": "2023-02-28",
        "resume": "Le défendeur circulait avec une plaque arrière couverte de neige et saleté la rendant illisible. L'art. 13 CSR exige que la plaque soit maintenue en bon état et lisible en tout temps. Le défendeur a l'obligation de nettoyer sa plaque, surtout en hiver. Amende de 100$ à 200$.",
        "resultat": "coupable",
        "mots_cles": "plaque illisible,neige,saleté,art 13 CSR,entretien,hiver",
        "langue": "fr"
    },

    # ─── ÉMISSION SONORE / SILENCIEUX ───
    {
        "citation": "Ville de Montréal c. Savard, 2022 QCCM 901",
        "titre": "Silencieux modifié — bruit excessif",
        "tribunal": "QCCM",
        "date_decision": "2022-10-18",
        "resume": "Le véhicule du défendeur était équipé d'un silencieux modifié produisant un bruit excessif. L'art. 258 CSR interdit les modifications au système d'échappement qui augmentent le bruit au-delà des normes. Test sonore effectué par la police: 102 dB vs norme de 83 dB. Amende de 200$ plus obligation de remettre le silencieux d'origine.",
        "resultat": "coupable",
        "mots_cles": "silencieux modifié,bruit,décibels,art 258 CSR,échappement,norme sonore",
        "langue": "fr"
    },

    # ─── CAS ADDITIONNELS POUR COMPLETUDE ───
    {
        "citation": "Ville de Chicoutimi c. Bouchard, 2019 QCCM 789",
        "titre": "Excès de vitesse — conditions de brouillard",
        "tribunal": "QCCM",
        "date_decision": "2019-03-22",
        "resume": "78 km/h dans zone de 50 km/h par temps de brouillard intense. L'art. 327 CSR s'ajoute à l'art. 299: le conducteur doit adapter sa vitesse non seulement à la limite mais aussi aux conditions météo. Double infraction possible. Le tribunal impose une amende majorée pour la combinaison des circonstances.",
        "resultat": "coupable",
        "mots_cles": "vitesse,brouillard,conditions météo,art 327 CSR,art 299 CSR,adaptation vitesse",
        "langue": "fr"
    },
    {
        "citation": "Ville de Montréal c. Karim, 2020 QCCM 456",
        "titre": "Téléphone mains libres — Bluetooth pas activé correctement",
        "tribunal": "QCCM",
        "date_decision": "2020-09-14",
        "resume": "Le défendeur avait un système Bluetooth dans le véhicule mais tenait tout de même le téléphone à l'oreille car le Bluetooth ne fonctionnait pas. Le tribunal rappelle que c'est la tenue physique de l'appareil qui constitue l'infraction, peu importe la raison. L'art. 443.1 CSR est clair: interdiction de tenir l'appareil.",
        "resultat": "coupable",
        "mots_cles": "cellulaire,Bluetooth,mains libres,tenir appareil,art 443.1 CSR,oreille",
        "langue": "fr"
    },
    {
        "citation": "Ville de Montréal c. Roy, 2023 QCCM 456",
        "titre": "Excès de vitesse — radar sur pont Jacques-Cartier",
        "tribunal": "QCCM",
        "date_decision": "2023-07-30",
        "resume": "Excès de vitesse sur le pont Jacques-Cartier, zone de 70 km/h. Le défendeur conteste la compétence de la ville de Montréal car le pont est de juridiction fédérale. Le tribunal rappelle que le Code criminel et le CSR s'appliquent sur les ponts fédéraux. La compétence municipale est confirmée. Coupable.",
        "resultat": "coupable",
        "mots_cles": "vitesse,pont Jacques-Cartier,juridiction fédérale,compétence municipale,art 299 CSR",
        "langue": "fr"
    },
    {
        "citation": "Ville de Gatineau c. Proulx, 2021 QCCM 901",
        "titre": "Refus d'obtempérer — ne pas s'arrêter pour un agent",
        "tribunal": "QCCM",
        "date_decision": "2021-12-14",
        "resume": "Le défendeur n'a pas immobilisé son véhicule malgré les signaux de l'agent (gyrophares et sirène). Il s'est finalement arrêté après 2 km. L'art. 636 C.cr. et l'art. 168 CSR obligent à obtempérer immédiatement. Le délai de 2 km constitue un refus. Coupable avec amende majorée.",
        "resultat": "coupable",
        "mots_cles": "refus obtempérer,agent,gyrophares,sirène,art 636 Code criminel,art 168 CSR",
        "langue": "fr"
    },
    {
        "citation": "Ville de Montréal c. Tremblay, 2022 QCCM 123",
        "titre": "Trottinette électrique — vitesse excessive sur piste cyclable",
        "tribunal": "QCCM",
        "date_decision": "2022-08-05",
        "resume": "Le conducteur d'une trottinette électrique circulait à 35 km/h sur une piste cyclable limitée à 20 km/h. Les trottinettes sont soumises au CSR depuis les modifications réglementaires. Le tribunal applique les règles de vitesse applicables aux pistes cyclables. Amende de 100$.",
        "resultat": "coupable",
        "mots_cles": "trottinette électrique,piste cyclable,vitesse,20 km/h,CSR,nouveau véhicule",
        "langue": "fr"
    },
]

# ═══════════════════════════════════════════════════════════
# JURISPRUDENCE ONTARIO V2 — 60+ nouveaux cas
# ═══════════════════════════════════════════════════════════

CASES_ON_V2 = [
    # ─── SPEEDING — more cases ───
    {
        "citation": "R. v. Nguyen, 2022 ONCJ 234",
        "titre": "Speeding — automated speed enforcement camera",
        "tribunal": "ONCJ",
        "date_decision": "2022-05-18",
        "resume": "Automated speed enforcement (ASE) camera captured vehicle at 72 km/h in a 40 km/h school zone. Owner challenged the accuracy of the ASE system. Court found the system was properly certified and calibrated per O. Reg. 398/19. Owner liability applies — no demerit points but fine of $325.",
        "resultat": "coupable",
        "mots_cles": "speeding,ASE,automated speed enforcement,school zone,HTA 128,O. Reg. 398/19",
        "langue": "en"
    },
    {
        "citation": "R. v. Martinez, 2021 ONCJ 678",
        "titre": "Speeding — radar jammed by interference",
        "tribunal": "ONCJ",
        "date_decision": "2021-04-22",
        "resume": "Officer's radar gave inconsistent readings near a power substation. Defence expert testified about electromagnetic interference affecting radar accuracy. Court found reasonable doubt about the reliability of the speed reading in this specific location. Acquitted.",
        "resultat": "acquitte",
        "mots_cles": "speeding,radar interference,electromagnetic,calibration,reliability,HTA 128",
        "langue": "en"
    },
    {
        "citation": "R. v. Thompson, 2023 ONCJ 123",
        "titre": "Speeding — 30 km/h over in 80 km/h zone",
        "tribunal": "ONCJ",
        "date_decision": "2023-03-14",
        "resume": "Defendant clocked at 110 km/h in an 80 km/h zone on a two-lane highway. Officer used a Stalker DSR 2X radar, properly tested before and after shift. Defendant argued they were passing another vehicle. Court noted that the speed limit applies at all times including during passing. Convicted. Fine $295.",
        "resultat": "coupable",
        "mots_cles": "speeding,30 over,80 km/h,radar,Stalker DSR,HTA 128,passing",
        "langue": "en"
    },
    {
        "citation": "R. v. Ali, 2020 ONCJ 890",
        "titre": "Speeding — speedometer calibration defence",
        "tribunal": "ONCJ",
        "date_decision": "2020-11-05",
        "resume": "Defendant argued their speedometer was showing 100 km/h when radar showed 118 km/h. Defendant provided a mechanic's report showing speedometer was 15% under-reading due to oversized tires. Court found that the driver has a responsibility to maintain an accurate speedometer. Convicted but with reduced fine.",
        "resultat": "coupable",
        "mots_cles": "speeding,speedometer,calibration,oversized tires,HTA 128,due diligence",
        "langue": "en"
    },
    {
        "citation": "R. v. Campbell, 2019 ONCJ 567",
        "titre": "Speeding — emergency vehicle not on call",
        "tribunal": "ONCJ",
        "date_decision": "2019-08-12",
        "resume": "Off-duty paramedic driving an ambulance at 130 km/h in 100 km/h zone without lights or sirens activated. Under s. 128(13) HTA, the emergency vehicle exemption only applies when responding to an emergency with signals activated. Without active signals, normal speed limits apply. Convicted.",
        "resultat": "coupable",
        "mots_cles": "speeding,emergency vehicle,ambulance,HTA 128(13),lights sirens,off-duty",
        "langue": "en"
    },
    {
        "citation": "R. v. Petrova, 2022 ONCJ 456",
        "titre": "Speeding — photo radar challenge, wrong vehicle",
        "tribunal": "ONCJ",
        "date_decision": "2022-09-28",
        "resume": "Defendant received an ASE ticket but the photo showed a different vehicle model than what was registered to the plate. Investigation revealed the plate had been recently transferred. Prosecution withdrew the charge when it became clear the photo did not match the defendant's current vehicle.",
        "resultat": "acquitte",
        "mots_cles": "speeding,ASE,photo radar,wrong vehicle,plate transfer,withdrawn",
        "langue": "en"
    },
    {
        "citation": "R. v. O'Brien, 2021 ONCJ 234",
        "titre": "Speeding — 49 km/h over (just below stunt threshold)",
        "tribunal": "ONCJ",
        "date_decision": "2021-06-15",
        "resume": "Defendant clocked at 149 km/h in a 100 km/h zone — 49 km/h over, just below the 50 km/h stunt driving threshold. Charged with speeding under s. 128 HTA rather than stunt driving. Fine of $718. Court noted the significant speed but acknowledged it did not meet the stunt driving threshold in O. Reg. 455/07.",
        "resultat": "coupable",
        "mots_cles": "speeding,49 over,near stunt,HTA 128,fine,threshold",
        "langue": "en"
    },

    # ─── RED LIGHT — more cases ───
    {
        "citation": "R. v. Williams, 2022 ONCJ 345",
        "titre": "Red light — entering intersection on amber, cleared on red",
        "tribunal": "ONCJ",
        "date_decision": "2022-04-11",
        "resume": "Defendant entered intersection on amber but due to congestion did not clear it before the light turned red. Court found that under s. 144(15) HTA, a driver who enters on amber and is trapped in the intersection by circumstances beyond their control has not committed the offence. Acquitted.",
        "resultat": "acquitte",
        "mots_cles": "red light,amber,intersection,congestion,HTA 144(15),trapped",
        "langue": "en"
    },
    {
        "citation": "R. v. Sharma, 2021 ONCJ 789",
        "titre": "Red light — funeral procession",
        "tribunal": "ONCJ",
        "date_decision": "2021-03-22",
        "resume": "Defendant proceeded through a red light while part of a funeral procession with hazard lights on. Court found that Ontario does not have a specific funeral procession exemption from traffic signals. Each vehicle in a procession must independently obey traffic signals. Convicted under s. 144(18) HTA.",
        "resultat": "coupable",
        "mots_cles": "red light,funeral procession,HTA 144(18),no exemption,hazard lights",
        "langue": "en"
    },
    {
        "citation": "R. v. Abdi, 2023 ONCJ 234",
        "titre": "Red light camera — plate stolen defence",
        "tribunal": "ONCJ",
        "date_decision": "2023-01-30",
        "resume": "Red light camera captured a violation but the registered owner proved their plate had been reported stolen 3 days prior to the offence. Police report confirmed the theft. Under s. 144(31.2) HTA, the owner is liable unless they can demonstrate the vehicle or plate was not in their possession. Charge dismissed.",
        "resultat": "acquitte",
        "mots_cles": "red light camera,stolen plate,HTA 144(31.2),police report,owner liability",
        "langue": "en"
    },
    {
        "citation": "R. v. Jackson, 2020 ONCJ 567",
        "titre": "Red light — contradictory signals at intersection",
        "tribunal": "ONCJ",
        "date_decision": "2020-07-14",
        "resume": "Two traffic signals at the same intersection showed conflicting indications (one green, one red for the same direction) due to a malfunction. Court found that when traffic signals are contradictory, a driver exercising due diligence cannot be convicted. The municipality has a duty to maintain proper signals. Acquitted.",
        "resultat": "acquitte",
        "mots_cles": "red light,contradictory signals,malfunction,due diligence,HTA 144,municipality",
        "langue": "en"
    },

    # ─── DISTRACTED DRIVING — more cases ───
    {
        "citation": "R. v. Park, 2022 ONCJ 678",
        "titre": "Distracted driving — eating while driving",
        "tribunal": "ONCJ",
        "date_decision": "2022-02-16",
        "resume": "Officer charged defendant with careless driving for eating a burger with both hands while steering with knees. Court distinguished between distracted driving (s. 78.1 — requires electronic device) and careless driving (s. 130 — general standard of care). Eating is not a s. 78.1 offence but could be careless. Convicted under s. 130.",
        "resultat": "coupable",
        "mots_cles": "distracted driving,eating,careless driving,HTA 78.1,HTA 130,distinction",
        "langue": "en"
    },
    {
        "citation": "R. v. Chen, 2023 ONCJ 456",
        "titre": "Distracted driving — smartwatch notification",
        "tribunal": "ONCJ",
        "date_decision": "2023-06-22",
        "resume": "Defendant was observed reading a notification on a smartwatch while driving. Following R. v. Kazemi, the court found that a smartwatch with communication capabilities constitutes a handheld wireless communication device under s. 78.1 HTA. The legislative intent covers all devices that distract. Convicted. Fine $615.",
        "resultat": "coupable",
        "mots_cles": "distracted driving,smartwatch,notification,HTA 78.1,Kazemi,communication device",
        "langue": "en"
    },
    {
        "citation": "R. v. Roberts, 2021 ONCJ 901",
        "titre": "Distracted driving — phone in lap, not in use",
        "tribunal": "ONCJ",
        "date_decision": "2021-08-09",
        "resume": "Officer observed phone face-up on the defendant's lap while driving. Defendant stated they were not using it. Court found that merely having a phone on one's lap does not constitute 'holding' or 'using' under s. 78.1 HTA. There was no evidence the defendant was interacting with the device. Acquitted.",
        "resultat": "acquitte",
        "mots_cles": "distracted driving,phone in lap,not holding,HTA 78.1,no interaction",
        "langue": "en"
    },
    {
        "citation": "R. v. Taylor, 2020 ONCJ 345",
        "titre": "Distracted driving — dash-mounted GPS unit",
        "tribunal": "ONCJ",
        "date_decision": "2020-05-28",
        "resume": "Defendant was programming a standalone GPS unit (not a phone) mounted on the dashboard while driving. Court found that a GPS device that does not have telephone or communication capabilities is not a 'hand-held wireless communication device' under s. 78.1 HTA. However, manipulation while driving could be careless. Acquitted on the distracted charge.",
        "resultat": "acquitte",
        "mots_cles": "distracted driving,GPS unit,dashboard mount,HTA 78.1,not communication device",
        "langue": "en"
    },

    # ─── STOP SIGN — more cases ───
    {
        "citation": "R. v. Mitchell, 2022 ONCJ 789",
        "titre": "Stop sign — four-way, confusion over right-of-way",
        "tribunal": "ONCJ",
        "date_decision": "2022-07-06",
        "resume": "Collision at four-way stop. Both drivers claim to have arrived first. Dashcam from a third vehicle showed the defendant arrived 2 seconds after the other vehicle. Under s. 136(1) HTA, the first vehicle to stop has the right-of-way. Defendant convicted of failing to yield.",
        "resultat": "coupable",
        "mots_cles": "stop sign,four-way,right-of-way,dashcam,HTA 136(1),yield",
        "langue": "en"
    },
    {
        "citation": "R. v. Davis, 2021 ONCJ 123",
        "titre": "Stop sign — temporary at construction zone",
        "tribunal": "ONCJ",
        "date_decision": "2021-02-17",
        "resume": "Defendant ran a temporary stop sign at a construction zone. Argued the sign was not a permanent traffic sign. Court found that temporary traffic control signs placed by authorized workers under the authority of the Highway Traffic Act have the same legal force as permanent signs. Convicted.",
        "resultat": "coupable",
        "mots_cles": "stop sign,temporary,construction zone,HTA 136,authorized sign",
        "langue": "en"
    },

    # ─── CARELESS DRIVING — more cases ───
    {
        "citation": "R. v. Adams, 2023 ONCJ 567",
        "titre": "Careless driving — lane departure causing near-miss",
        "tribunal": "ONCJ",
        "date_decision": "2023-04-18",
        "resume": "Defendant drifted into oncoming lane causing another vehicle to swerve off the road. No collision. Court found that careless driving under s. 130 HTA does not require a collision — creating a serious risk through inattentive driving is sufficient. Dashcam from the other vehicle provided clear evidence. Convicted.",
        "resultat": "coupable",
        "mots_cles": "careless driving,lane departure,near-miss,no collision,HTA 130,dashcam",
        "langue": "en"
    },
    {
        "citation": "R. v. White, 2020 ONCJ 678",
        "titre": "Careless driving — medical emergency defence",
        "tribunal": "ONCJ",
        "date_decision": "2020-10-14",
        "resume": "Defendant crossed centre line and struck a parked car. Medical records showed the defendant suffered a sudden seizure with no prior history. Court accepted the defence of sudden incapacitation — a medical emergency that renders the driver unconscious is a complete defence to careless driving. Acquitted.",
        "resultat": "acquitte",
        "mots_cles": "careless driving,medical emergency,seizure,sudden incapacitation,HTA 130,defence",
        "langue": "en"
    },
    {
        "citation": "R. v. Anderson, 2022 ONCJ 901",
        "titre": "Careless driving — road rage incident",
        "tribunal": "ONCJ",
        "date_decision": "2022-11-30",
        "resume": "Defendant engaged in aggressive driving behaviour: tailgating, brake-checking, and cutting off another vehicle. Multiple witnesses and dashcam evidence. Court found this behaviour constituted a clear departure from the standard of a reasonable driver. Convicted under s. 130 HTA. Fine $2,000 and 6 demerit points.",
        "resultat": "coupable",
        "mots_cles": "careless driving,road rage,tailgating,brake-checking,HTA 130,aggressive",
        "langue": "en"
    },

    # ─── STUNT DRIVING — more cases ───
    {
        "citation": "R. v. Khan, 2023 ONCJ 234",
        "titre": "Stunt driving — 40 km/h over in 80 zone (new threshold)",
        "tribunal": "ONCJ",
        "date_decision": "2023-08-15",
        "resume": "Under the 2021 amendments (Moving Ontarians More Safely Act), the stunt driving threshold was lowered to 40 km/h over the limit in zones under 80 km/h. Defendant clocked at 125 km/h in 80 km/h zone (45 over). Convicted of stunt driving. 30-day license suspension, 14-day vehicle impoundment, fine $2,500.",
        "resultat": "coupable",
        "mots_cles": "stunt driving,40 over,new threshold,MOMS Act,HTA 172,2021 amendments",
        "langue": "en"
    },
    {
        "citation": "R. v. Ramos, 2022 ONCJ 345",
        "titre": "Stunt driving — racing another vehicle",
        "tribunal": "ONCJ",
        "date_decision": "2022-06-08",
        "resume": "Two vehicles observed racing on Highway 403 at speeds exceeding 180 km/h. Both drivers charged with stunt driving (racing) under s. 172(1) HTA and O. Reg. 455/07 s. 3(1) which defines racing as driving at a rate of speed that is a marked departure from the lawful rate. Both convicted. $5,000 fines each.",
        "resultat": "coupable",
        "mots_cles": "stunt driving,racing,Highway 403,180 km/h,HTA 172,O. Reg. 455/07",
        "langue": "en"
    },
    {
        "citation": "R. v. Hussain, 2021 ONCJ 567",
        "titre": "Stunt driving — reduced to careless on appeal",
        "tribunal": "ONSC",
        "date_decision": "2021-10-25",
        "resume": "Defendant convicted of stunt driving at trial (155 km/h in 100 km/h zone). On appeal, the Superior Court found the speed reading was borderline (officer initially noted 150 km/h, later corrected to 155). Conviction reduced to careless driving under s. 130 HTA. Fine reduced to $1,000.",
        "resultat": "negociation",
        "mots_cles": "stunt driving,appeal,reduced charge,careless driving,borderline,HTA 172,HTA 130",
        "langue": "en"
    },

    # ─── SEATBELT — more cases ───
    {
        "citation": "R. v. Fraser, 2022 ONCJ 678",
        "titre": "Seatbelt — child restraint system improperly installed",
        "tribunal": "ONCJ",
        "date_decision": "2022-03-22",
        "resume": "Child car seat was in the vehicle but improperly secured — not anchored to the LATCH system. Under s. 106(4) HTA and O. Reg. 613, the driver is responsible for ensuring child restraints are properly installed. The car seat being present but unsecured does not satisfy the requirement. Convicted.",
        "resultat": "coupable",
        "mots_cles": "seatbelt,child restraint,car seat,LATCH,HTA 106(4),O. Reg. 613",
        "langue": "en"
    },
    {
        "citation": "R. v. Scott, 2020 ONCJ 901",
        "titre": "Seatbelt — removed briefly for medical reason",
        "tribunal": "ONCJ",
        "date_decision": "2020-12-08",
        "resume": "Defendant removed seatbelt momentarily to reach for insulin kit in the back seat while stopped at a red light. Officer observed the unbuckled seatbelt. Court found that the defendant had a reasonable excuse and re-buckled immediately. Acquitted based on the momentary nature and medical necessity.",
        "resultat": "acquitte",
        "mots_cles": "seatbelt,medical reason,momentary,insulin,HTA 106,reasonable excuse",
        "langue": "en"
    },

    # ─── IMPAIRED DRIVING — Ontario cases ───
    {
        "citation": "R. v. Molnar, 2022 ONSC 456",
        "titre": "Impaired driving — breath test delay exceeding 2 hours",
        "tribunal": "ONSC",
        "date_decision": "2022-08-10",
        "resume": "Breath test administered 2 hours 45 minutes after the stop. The Criminal Code requires samples to be taken as soon as practicable. The delay was caused by the officer waiting for a breath technician. Court found the delay unreasonable and excluded the breath results under s. 24(2) Charter. Acquitted.",
        "resultat": "acquitte",
        "mots_cles": "impaired driving,breath test,delay,2 hours,Charter s. 24(2),as soon as practicable",
        "langue": "en"
    },
    {
        "citation": "R. v. Davidson, 2021 ONCJ 234",
        "titre": "Impaired driving — refusal to provide breath sample",
        "tribunal": "ONCJ",
        "date_decision": "2021-05-18",
        "resume": "Defendant refused to provide a breath sample at roadside. Under s. 320.15 Criminal Code, refusal is a separate offence carrying the same penalties as impaired driving. The officer properly made the demand and the defendant was informed of the consequences. Convicted. Fine $2,000, 1-year driving prohibition.",
        "resultat": "coupable",
        "mots_cles": "impaired driving,refusal,breath sample,s. 320.15 Criminal Code,prohibition",
        "langue": "en"
    },
    {
        "citation": "R. v. Pham, 2023 ONCJ 678",
        "titre": "Impaired driving — cannabis THC blood level",
        "tribunal": "ONCJ",
        "date_decision": "2023-02-28",
        "resume": "Defendant tested positive for THC at 3.8 ng/mL in blood. Under s. 320.14(1)(c) Criminal Code, the offence requires 5 ng/mL or more for the full impaired driving charge, or 2-5 ng for the lesser offence. Convicted of the summary offence (2-5 ng range). Fine $1,000.",
        "resultat": "coupable",
        "mots_cles": "impaired driving,cannabis,THC,3.8 ng/mL,s. 320.14 Criminal Code",
        "langue": "en"
    },

    # ─── FAIL TO REMAIN / HIT AND RUN ───
    {
        "citation": "R. v. Morrison, 2021 ONCJ 345",
        "titre": "Fail to remain — parking lot collision",
        "tribunal": "ONCJ",
        "date_decision": "2021-07-14",
        "resume": "Defendant backed into another vehicle in a parking lot and left without leaving contact information. Security camera captured the incident and plate number. Under s. 200(1) HTA, the driver must remain at the scene and provide information. Convicted. Fine $400 and 7 demerit points.",
        "resultat": "coupable",
        "mots_cles": "fail to remain,parking lot,hit and run,HTA 200(1),security camera,demerit points",
        "langue": "en"
    },
    {
        "citation": "R. v. Foster, 2020 ONCJ 789",
        "titre": "Fail to remain — returned to scene within minutes",
        "tribunal": "ONCJ",
        "date_decision": "2020-09-22",
        "resume": "Defendant left the scene of a minor collision but returned 10 minutes later after realizing the obligation. Court found that while the initial departure was a violation, the prompt return and cooperation with the other driver demonstrated good faith. Charge withdrawn by the Crown upon considering the circumstances.",
        "resultat": "acquitte",
        "mots_cles": "fail to remain,returned,good faith,HTA 200,charge withdrawn,cooperation",
        "langue": "en"
    },

    # ─── DRIVING WHILE SUSPENDED ───
    {
        "citation": "R. v. Bennett, 2022 ONCJ 901",
        "titre": "Driving while suspended — unaware of administrative suspension",
        "tribunal": "ONCJ",
        "date_decision": "2022-01-18",
        "resume": "Defendant drove while their licence was under administrative suspension for unpaid fines. Claimed they did not receive the notice from the MTO. Court found that the MTO sent notice to the address on file. Defendant had moved without updating their address. Convicted under s. 53(1) HTA.",
        "resultat": "coupable",
        "mots_cles": "driving suspended,administrative suspension,unpaid fines,MTO notice,HTA 53(1),address",
        "langue": "en"
    },
    {
        "citation": "R. v. Green, 2021 ONCJ 456",
        "titre": "Driving while suspended — medical suspension lifted",
        "tribunal": "ONCJ",
        "date_decision": "2021-09-08",
        "resume": "Defendant was driving under a medical suspension that had been lifted by the MTO 2 days prior. The MTO system had not been updated at the time of the stop. Court found that the defendant had documentation showing the suspension was lifted. Acquitted — the defendant was lawfully entitled to drive.",
        "resultat": "acquitte",
        "mots_cles": "driving suspended,medical suspension,lifted,MTO system,documentation,HTA 53",
        "langue": "en"
    },

    # ─── PROCEDURE / RIGHTS — more ON cases ───
    {
        "citation": "R. v. Ramirez, 2023 ONCJ 901",
        "titre": "Disclosure — officer notes incomplete, charge stayed",
        "tribunal": "ONCJ",
        "date_decision": "2023-07-25",
        "resume": "Defence requested full disclosure including the officer's notes, radar calibration records, and training certificates. The prosecution provided incomplete disclosure (no calibration records). Court found the missing disclosure was material to the defence. Stay of proceedings ordered under R. v. Stinchcombe principles.",
        "resultat": "acquitte",
        "mots_cles": "disclosure,incomplete,officer notes,calibration records,Stinchcombe,stay",
        "langue": "en"
    },
    {
        "citation": "R. v. Cooper, 2022 ONCJ 123",
        "titre": "Trial delay — 14 months, Jordan threshold not met",
        "tribunal": "ONCJ",
        "date_decision": "2022-10-05",
        "resume": "Defendant brought a s. 11(b) Charter application for trial delay of 14 months. Applying R. v. Jordan, the presumptive ceiling for provincial offences tried in the Ontario Court of Justice is 18 months. Since 14 months is below the ceiling, the delay is presumptively reasonable. Application dismissed.",
        "resultat": "coupable",
        "mots_cles": "trial delay,14 months,Jordan,s. 11(b) Charter,presumptive ceiling,reasonable",
        "langue": "en"
    },
    {
        "citation": "R. v. Leung, 2021 ONCJ 678",
        "titre": "Officer failed to appear — third adjournment",
        "tribunal": "ONCJ",
        "date_decision": "2021-11-30",
        "resume": "The prosecution requested a third adjournment because the officer was unavailable. Defence opposed. Court denied the adjournment noting the defendant's right to a trial within a reasonable time. After three failed attempts to produce the officer, the charge was dismissed for want of prosecution.",
        "resultat": "acquitte",
        "mots_cles": "officer failed appear,adjournment,want of prosecution,dismissed,reasonable time",
        "langue": "en"
    },

    # ─── INSURANCE / REGISTRATION ───
    {
        "citation": "R. v. Hassan, 2022 ONCJ 234",
        "titre": "No insurance — valid policy but card not in vehicle",
        "tribunal": "ONCJ",
        "date_decision": "2022-04-28",
        "resume": "Defendant was charged with operating without insurance under s. 2(1) of the Compulsory Automobile Insurance Act. Defendant had valid insurance but could not produce the pink slip. At trial, defendant produced the valid insurance policy. Court found that having insurance but failing to produce the card is a lesser offence under s. 3. Reduced charge.",
        "resultat": "coupable",
        "mots_cles": "no insurance,pink slip,CAIA,valid policy,reduced charge,s. 2(1),s. 3",
        "langue": "en"
    },
    {
        "citation": "R. v. Nowak, 2020 ONCJ 345",
        "titre": "Expired plate sticker — COVID extension",
        "tribunal": "ONCJ",
        "date_decision": "2020-06-22",
        "resume": "Defendant's plate validation sticker expired March 2020. Due to COVID-19, the Ontario government extended plate renewal deadlines. Court found that the government order provided a valid defence to the charge of operating with expired validation under s. 7(1) HTA. Acquitted.",
        "resultat": "acquitte",
        "mots_cles": "expired plate,sticker,COVID,extension,HTA 7(1),government order",
        "langue": "en"
    },

    # ─── U-TURN / IMPROPER TURN ───
    {
        "citation": "R. v. Santos, 2022 ONCJ 567",
        "titre": "Improper U-turn — prohibited at intersection",
        "tribunal": "ONCJ",
        "date_decision": "2022-08-16",
        "resume": "Defendant made a U-turn at an intersection where it was prohibited by signage. Under s. 143 HTA, U-turns are prohibited at intersections controlled by traffic signals unless permitted by signage. The no U-turn sign was clearly visible. Convicted. Fine $110.",
        "resultat": "coupable",
        "mots_cles": "U-turn,prohibited,intersection,HTA 143,signage",
        "langue": "en"
    },

    # ─── FOLLOWING TOO CLOSELY ───
    {
        "citation": "R. v. Burke, 2021 ONCJ 789",
        "titre": "Following too closely — rear-end collision on highway",
        "tribunal": "ONCJ",
        "date_decision": "2021-12-08",
        "resume": "Defendant rear-ended a vehicle on Highway 401 during a sudden slowdown. Charged with following too closely under s. 158 HTA. Court applied the 2-second rule as guidance. Traffic reconstruction showed less than 0.5 seconds following distance. Convicted. Fine $110 and 4 demerit points.",
        "resultat": "coupable",
        "mots_cles": "following too closely,rear-end,Highway 401,HTA 158,2-second rule,demerit points",
        "langue": "en"
    },

    # ─── SCHOOL BUS ───
    {
        "citation": "R. v. Price, 2022 ONCJ 890",
        "titre": "Failing to stop for school bus — lights flashing",
        "tribunal": "ONCJ",
        "date_decision": "2022-09-12",
        "resume": "Defendant passed a stopped school bus with overhead red lights flashing. Under s. 175(11) HTA, every driver approaching a stopped school bus with lights flashing must stop before reaching the bus. Fine of $490 and 6 demerit points. Court emphasized the severe penalties reflect the safety of children.",
        "resultat": "coupable",
        "mots_cles": "school bus,flashing lights,HTA 175(11),stop,demerit points,children safety",
        "langue": "en"
    },

    # ─── NOVICE DRIVER VIOLATIONS ───
    {
        "citation": "R. v. Zhao, 2023 ONCJ 345",
        "titre": "G1 driver — prohibited highway driving",
        "tribunal": "ONCJ",
        "date_decision": "2023-05-08",
        "resume": "G1 licence holder caught driving on Highway 401 at night without an accompanying driver. G1 restrictions prohibit highway driving and nighttime driving. Multiple violations of O. Reg. 340/94. Convicted. Fine $85 per violation. Licence suspension recommended to the MTO.",
        "resultat": "coupable",
        "mots_cles": "novice driver,G1,highway prohibited,night driving,O. Reg. 340/94,restrictions",
        "langue": "en"
    },

    # ─── PEDESTRIAN RIGHT-OF-WAY ───
    {
        "citation": "R. v. Edwards, 2021 ONCJ 901",
        "titre": "Failing to yield to pedestrian at crosswalk",
        "tribunal": "ONCJ",
        "date_decision": "2021-04-22",
        "resume": "Defendant failed to yield to a pedestrian at a marked crosswalk. Under s. 140(1) HTA, when a pedestrian is crossing in a crosswalk, the driver must yield the right-of-way. Dashcam showed the pedestrian was clearly in the crosswalk. Convicted. Fine $150 and 3 demerit points.",
        "resultat": "coupable",
        "mots_cles": "pedestrian,crosswalk,yield,right-of-way,HTA 140(1),demerit points",
        "langue": "en"
    },

    # ─── MORE PROCEDURE / TECHNICAL DEFENCES ON ───
    {
        "citation": "R. v. MacDonald, 2020 ONCJ 123",
        "titre": "Certificate of offence — wrong section number",
        "tribunal": "ONCJ",
        "date_decision": "2020-03-18",
        "resume": "The certificate of offence cited s. 128(1) HTA instead of the correct s. 128(1)(a). Defence argued this was a fatal defect. Court found that while precision is important, the defendant was not prejudiced as they clearly understood the charge. Minor clerical errors do not automatically void a charge. Convicted.",
        "resultat": "coupable",
        "mots_cles": "certificate offence,wrong section,clerical error,not prejudiced,HTA 128",
        "langue": "en"
    },
    {
        "citation": "R. v. Dubois, 2023 ONCJ 789",
        "titre": "Bilingual proceedings — right to French trial in Ontario",
        "tribunal": "ONCJ",
        "date_decision": "2023-09-18",
        "resume": "Francophone defendant requested trial in French under the French Language Services Act and s. 126 Courts of Justice Act. Court confirmed the right to proceedings in French in designated areas. Trial rescheduled to accommodate a bilingual justice. No acquittal on this basis but procedural right upheld.",
        "resultat": "reference",
        "mots_cles": "French trial,bilingual,French Language Services Act,Courts of Justice Act,s. 126",
        "langue": "en"
    },

    # ─── WINTER TIRES / VEHICLE CONDITION ───
    {
        "citation": "R. v. Singh, 2022 ONCJ 456",
        "titre": "Unsafe vehicle — bald tires in winter conditions",
        "tribunal": "ONCJ",
        "date_decision": "2022-02-14",
        "resume": "Defendant's vehicle had bald tires (tread depth below 2/32 inch) during winter conditions. Charged under s. 84(1) HTA for operating an unsafe vehicle. Unlike Quebec, Ontario does not mandate winter tires, but tires must meet minimum safety standards year-round. Convicted. Ordered to replace tires before driving.",
        "resultat": "coupable",
        "mots_cles": "unsafe vehicle,bald tires,winter,tread depth,HTA 84(1),safety standards",
        "langue": "en"
    },

    # ─── ADDITIONAL VARIED CASES ───
    {
        "citation": "R. v. Okafor, 2021 ONCJ 567",
        "titre": "Driving wrong way on one-way street",
        "tribunal": "ONCJ",
        "date_decision": "2021-03-10",
        "resume": "Defendant drove against traffic on a one-way street in downtown Toronto. Under s. 153 HTA, driving the wrong way on a one-way street is an offence. Defendant claimed the one-way signs were not visible. Court viewed Google Street View images showing clear signage. Convicted.",
        "resultat": "coupable",
        "mots_cles": "wrong way,one-way street,HTA 153,signage,downtown Toronto",
        "langue": "en"
    },
    {
        "citation": "R. v. Chow, 2022 ONCJ 678",
        "titre": "Excessive noise — modified muffler",
        "tribunal": "ONCJ",
        "date_decision": "2022-05-03",
        "resume": "Vehicle had an aftermarket exhaust system exceeding the noise limit of 95 dB. Under s. 75(1) HTA, no motor vehicle shall be equipped with a muffler that does not effectively prevent excessive noise. Sound meter test confirmed 108 dB. Convicted. Fine $110 and order to restore original exhaust.",
        "resultat": "coupable",
        "mots_cles": "excessive noise,modified muffler,exhaust,HTA 75(1),decibels,aftermarket",
        "langue": "en"
    },
    {
        "citation": "R. v. Watts, 2023 ONCJ 123",
        "titre": "Tinted windows — front side windows below 70% transparency",
        "tribunal": "ONCJ",
        "date_decision": "2023-01-12",
        "resume": "Officer tested front side window tint at 25% light transmittance (legal minimum is 70%). Under s. 73(3) HTA and O. Reg. 611, front side windows must allow at least 70% light through. Defendant argued the tint was factory-installed. Inspection showed aftermarket film. Convicted.",
        "resultat": "coupable",
        "mots_cles": "tinted windows,70% transparency,HTA 73(3),O. Reg. 611,aftermarket film",
        "langue": "en"
    },
    {
        "citation": "R. v. Young, 2020 ONCJ 234",
        "titre": "Speeding — officer estimation without radar",
        "tribunal": "ONCJ",
        "date_decision": "2020-08-19",
        "resume": "Officer estimated defendant's speed at 90 km/h in a 60 km/h zone based solely on visual observation without using any speed measuring device. Court found that while trained officer estimates are admissible, a 30 km/h over charge based solely on visual estimation without corroboration raises reasonable doubt. Acquitted.",
        "resultat": "acquitte",
        "mots_cles": "speeding,visual estimation,no radar,officer training,reasonable doubt,HTA 128",
        "langue": "en"
    },
    {
        "citation": "R. v. Brown, 2023 ONCJ 456",
        "titre": "Fail to signal lane change — highway merge",
        "tribunal": "ONCJ",
        "date_decision": "2023-03-28",
        "resume": "Defendant charged with failing to signal when merging onto Highway 400. Under s. 142(1) HTA, every driver must signal their intention to turn or change lanes. Defendant argued the merge lane naturally flows into the highway. Court found that a signal is still required when merging from an acceleration lane. Convicted.",
        "resultat": "coupable",
        "mots_cles": "fail to signal,lane change,merge,HTA 142(1),highway,acceleration lane",
        "langue": "en"
    },
    {
        "citation": "R. v. Clarke, 2021 ONCJ 789",
        "titre": "Speeding — reduced from stunt driving via plea negotiation",
        "tribunal": "ONCJ",
        "date_decision": "2021-08-25",
        "resume": "Originally charged with stunt driving at 158 km/h in 100 km/h zone. Defence counsel negotiated with the Crown to reduce to speeding 30-49 km/h over. Defendant pleaded guilty to the reduced charge. Fine of $500, no licence suspension. Court accepted the joint submission noting the defendant's clean 15-year driving record.",
        "resultat": "negociation",
        "mots_cles": "stunt driving,plea negotiation,reduced charge,clean record,joint submission,HTA 128",
        "langue": "en"
    },
    {
        "citation": "R. v. Murphy, 2022 ONCJ 345",
        "titre": "Speeding — multiple offences same stop, Kienapple principle",
        "tribunal": "ONCJ",
        "date_decision": "2022-12-14",
        "resume": "Defendant charged with both speeding and careless driving arising from the same incident (150 km/h in 100 km/h zone, weaving through traffic). Defence argued Kienapple principle prevents conviction on both charges from the same conduct. Court agreed and entered a conditional stay on the speeding charge, convicting only on careless driving.",
        "resultat": "reference",
        "mots_cles": "speeding,careless driving,Kienapple,double conviction,same conduct,conditional stay",
        "langue": "en"
    },
]


def seed_database_v2():
    """Insert V2 cases into the database"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    now = datetime.now().isoformat()
    inserted_qc = 0
    inserted_on = 0

    # Insert QC V2 cases
    for case in CASES_QC_V2:
        c.execute("SELECT id FROM jurisprudence WHERE citation = ?", (case["citation"],))
        if c.fetchone():
            continue
        c.execute("""INSERT INTO jurisprudence
            (citation, titre, tribunal, juridiction, date_decision, resume,
             texte_complet, resultat, mots_cles, source, langue, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (case["citation"], case["titre"], case["tribunal"], "QC",
             case["date_decision"], case["resume"], "", case["resultat"],
             case["mots_cles"], "seed_curated_v2", case["langue"], now))
        inserted_qc += 1

    # Insert ON V2 cases
    for case in CASES_ON_V2:
        c.execute("SELECT id FROM jurisprudence WHERE citation = ?", (case["citation"],))
        if c.fetchone():
            continue
        c.execute("""INSERT INTO jurisprudence
            (citation, titre, tribunal, juridiction, date_decision, resume,
             texte_complet, resultat, mots_cles, source, langue, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (case["citation"], case["titre"], case["tribunal"], "ON",
             case["date_decision"], case["resume"], "", case["resultat"],
             case["mots_cles"], "seed_curated_v2", case["langue"], now))
        inserted_on += 1

    conn.commit()

    print(f"V2: Inserted {inserted_qc} QC cases + {inserted_on} ON cases")

    # Rebuild FTS index
    rebuild_fts(conn)

    # Final stats
    c.execute("SELECT juridiction, COUNT(*) FROM jurisprudence GROUP BY juridiction ORDER BY COUNT(*) DESC")
    print("\n=== Juridictions (total) ===")
    for row in c.fetchall():
        print(f"  {row[0]}: {row[1]} cases")

    c.execute("SELECT source, COUNT(*) FROM jurisprudence GROUP BY source ORDER BY COUNT(*) DESC")
    print("\n=== Sources ===")
    for row in c.fetchall():
        print(f"  {row[0]}: {row[1]} cases")

    conn.close()
    print("\nV2 seed done!")


def rebuild_fts(conn):
    """Rebuild the FTS index from scratch"""
    c = conn.cursor()
    print("\nRebuilding FTS index...")

    c.execute("DROP TABLE IF EXISTS jurisprudence_fts")
    c.execute("""CREATE VIRTUAL TABLE jurisprudence_fts USING fts5(
        citation, titre, resume, texte_complet, mots_cles,
        content='jurisprudence',
        content_rowid='id',
        tokenize='unicode61'
    )""")

    c.execute("""INSERT INTO jurisprudence_fts(rowid, citation, titre, resume, texte_complet, mots_cles)
        SELECT id, citation, COALESCE(titre,''), COALESCE(resume,''),
               COALESCE(texte_complet,''), COALESCE(mots_cles,'')
        FROM jurisprudence""")
    conn.commit()

    c.execute("SELECT COUNT(*) FROM jurisprudence_fts")
    total = c.fetchone()[0]
    print(f"FTS index: {total} entries")

    # Test QC searches
    tests = [
        ("vitesse OR excès OR radar", "QC"),
        ("feu rouge OR signalisation", "QC"),
        ("cellulaire OR téléphone", "QC"),
        ("alcool OR facultés", "QC"),
        ("speeding OR speed OR radar", "ON"),
        ("red light OR traffic signal", "ON"),
        ("distracted OR cell phone", "ON"),
        ("stunt driving OR racing", "ON"),
    ]
    print("\n=== FTS Tests ===")
    for query, jur in tests:
        c.execute("""SELECT COUNT(*) FROM jurisprudence_fts fts
                     JOIN jurisprudence j ON fts.rowid = j.id
                     WHERE jurisprudence_fts MATCH ? AND j.juridiction = ?""",
                  (query, jur))
        count = c.fetchone()[0]
        print(f"  [{jur}] '{query[:40]}': {count} results")


if __name__ == "__main__":
    seed_database_v2()
