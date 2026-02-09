# GOLD STANDARD — Plan Dossier de Preuve Client

## Concept

Le client upload son dossier complet (photos, videos, temoignages) et le systeme analyse TOUT pour batir la meilleure defense possible.

---

## Ce que le client peut soumettre

1. **Photo du ticket** (recto + verso) → OCR auto-rempli les champs
2. **Photos du lieu** → panneau cache, signalisation absente, etat de la route
3. **Photo radar/camera** → image envoyee par la ville
4. **Video dashcam** → conditions reelles au moment de l'infraction
5. **Temoignage ecrit** → ce qui s'est passe dans ses mots
6. **Temoins** → nom, contact, leur version
7. **Capture Google Maps** → prouver absence de panneau

---

## Pipeline de traitement

```
CLIENT UPLOAD
    |
    v
[1. RECEPTION]
    Upload securise → stockage chiffre → dossier unique par client
    |
    v
[2. OCR TICKET]
    Photo ticket → extraction auto de tous les champs
    (infraction, article, amende, points, lieu, date, agent, appareil)
    |
    v
[3. ANALYSE PHOTOS]
    Photos du lieu → detection AI :
    - Panneau present ou absent?
    - Panneau visible ou obstrue?
    - Conditions de route (meteo, eclairage, etat)
    - Position du radar/camera
    |
    v
[4. ANALYSE VIDEO]
    Dashcam → extraction frames cles :
    - Vitesse au compteur
    - Couleur du feu (vert/jaune/rouge)
    - Conditions de circulation
    - Comportement du conducteur
    |
    v
[5. ANALYSE TEMOIGNAGE]
    Texte du client + temoins → extraction :
    - Faits pertinents
    - Contradictions avec le constat
    - Elements de defense
    |
    v
[6. PIPELINE 5 AGENTS] (deja construit)
    Lecteur → Lois → Precedents → Analyste → Verificateur
    MAIS maintenant avec les VRAIES preuves du client
    |
    v
[7. RAPPORT DOSSIER COMPLET]
    Score de contestation ajuste selon les preuves
    + Dossier PDF avec toutes les preuves annotees
```

---

## Impact sur le score

| Scenario | Sans preuve | Avec preuves |
|---|---|---|
| Vitesse — panneau cache | 30% | 75% (photo prouve obstruction) |
| Feu rouge — etait jaune | 20% | 80% (dashcam prouve) |
| Radar — mal positionne | 25% | 70% (photo angle du radar) |
| Cellulaire — pas au volant | 15% | 65% (temoin confirme) |

---

## Composantes a construire

| # | Composante | Description | Effort |
|---|---|---|---|
| 1 | Upload securise | Formulaire multi-fichiers (photos, videos, PDF, texte) max 50 Mo | 2h |
| 2 | Stockage chiffre | Dossier par client, chiffrement AES-256, suppression auto 90 jours | 2h |
| 3 | OCR ticket | Mindee API — photo ticket → champs structures | 3h |
| 4 | Analyse photos | AI vision — detecter panneaux, signalisation, conditions | 4h |
| 5 | Analyse video | Extraction frames cles dashcam, detection elements | 3h |
| 6 | Analyse temoignage | NLP — extraire faits, contradictions, arguments | 2h |
| 7 | Rapport PDF | Compilation dossier complet avec preuves annotees | 3h |
| 8 | Securite | Token unique par dossier, acces limite, audit trail | 1h |

**Total : ~20h de developpement**

---

## Pourquoi c'est le Gold Standard

- **Aucun competiteur au Quebec** offre ca (SOS Ticket, TicketAide, Neolegal = telephone seulement)
- **Aucun competiteur en Ontario** offre ca (X-Copper, POINTTS = consultation humaine)
- **Off The Record** (USA) est le seul comparable mais pas au Canada
- **Le client fait tout depuis son telephone** — photo, upload, resultat
- **Score ajuste sur les VRAIES preuves** — pas juste de la theorie juridique

---

## Stack technique

- Upload : formulaire HTML5 + Flask endpoint
- Stockage : serveur OVH chiffre (ou S3 compatible)
- OCR : Mindee API (gratuit 250 pages/mois)
- Vision AI : Claude Vision ou equivalent (analyse photos)
- Video : FFmpeg (extraction frames) + AI analyse
- NLP : moteur existant (analyse temoignage)
- PDF : WeasyPrint ou ReportLab (generation rapport)
- Securite : AES-256 + token UUID + expiration auto

---

*Gold Standard — SEO par AI | Ticket911*
