
# PLAN — Rapport PDF Gold Standard
## A faire demain

---

## Objectif

Quand le client soumet un ticket + preuves → le systeme genere un **rapport PDF complet** avec :
- Toutes les infos du ticket
- Les preuves soumises (photos, temoignages)
- L'analyse AI complete
- Le score de contestation
- La strategie de defense
- Les lois applicables
- Les precedents trouves
- Les arguments a utiliser en cour

---

## Etapes de construction (ordre)

### 1. Upload de preuves (~2h)
- Ajouter au formulaire web : upload multi-fichiers
- Types acceptes : JPG, PNG, PDF, MP4, MOV, TXT
- Max 50 Mo par fichier, 5 fichiers max
- Stockage : `/var/www/aiticketinfo/uploads/{uuid}/`
- Chaque dossier a un ID unique (UUID)

### 2. OCR photo ticket (~3h)
- Integrer Mindee API (cle gratuite a creer)
- Le client upload la photo de son ticket
- Mindee extrait : infraction, article, amende, points, lieu, date, agent, numero dossier
- Auto-remplir le formulaire avec les donnees extraites
- Le client peut corriger si necessaire

### 3. Analyse des preuves (~3h)
- Photos du lieu → envoyer a l'AI vision pour detecter :
  - Panneau present/absent/cache
  - Signalisation visible ou pas
  - Conditions de route
  - Position de la camera/radar
- Temoignage texte → extraire les faits cles
- Integrer les resultats dans le pipeline des 5 agents

### 4. Generation rapport PDF (~3h)
- Installer WeasyPrint sur le serveur
- Template HTML → PDF avec le style AITicketInfo
- Sections du rapport :

```
PAGE 1 — COUVERTURE
  - Logo AITicketInfo par SeoAI
  - Numero de dossier
  - Date
  - Juridiction

PAGE 2 — RESUME DU TICKET
  - Infraction
  - Article de loi
  - Amende + points
  - Lieu + date
  - Appareil de mesure

PAGE 3 — SCORE DE CONTESTATION
  - Score en gros (ex: 72%)
  - Recommandation (contester/negocier/payer)
  - Niveau de confiance
  - Graphique visuel

PAGE 4 — ARGUMENTS DE DEFENSE
  - Liste numerotee des arguments
  - Pour chaque : explication + force de l'argument

PAGE 5 — LOI APPLICABLE
  - Texte exact de l'article
  - Explication en langage simple

PAGE 6 — JURISPRUDENCE
  - Precedents trouves (citation, tribunal, date, resultat)
  - Pertinence de chaque precedent

PAGE 7 — PREUVES SOUMISES
  - Photos du client (avec annotations AI)
  - Resume des temoignages
  - Elements detectes par l'AI

PAGE 8 — STRATEGIE RECOMMANDEE
  - Plan d'action etape par etape
  - Quoi dire en cour
  - Quoi apporter comme preuve
  - Delais a respecter

PAGE 9 — AVERTISSEMENTS
  - Ce rapport ne constitue pas un avis juridique
  - Consulter un avocat recommande si score < 50%
  - Donnees basees sur la jurisprudence disponible
```

### 5. Endpoint API rapport (~1h)
- `POST /api/analyze` → retourne le resultat + genere le PDF
- `GET /api/rapport/{uuid}` → telecharger le PDF
- Lien de telechargement affiche sur la page resultats
- Bouton "Telecharger mon rapport PDF"

### 6. Mise a jour page web (~1h)
- Ajouter zone upload fichiers dans le formulaire
- Ajouter bouton "Telecharger le rapport PDF" dans les resultats
- Preview des photos uploadees
- Barre de progression pendant l'analyse

---

## Ordre d'execution demain

| # | Tache | Temps | Priorite |
|---|---|---|---|
| 1 | Creer compte Mindee + cle API | 10 min | Premier |
| 2 | Upload fichiers (formulaire + backend) | 2h | Haut |
| 3 | OCR Mindee integration | 3h | Haut |
| 4 | Template rapport PDF + WeasyPrint | 3h | Haut |
| 5 | Analyse photos AI | 3h | Moyen |
| 6 | Endpoint API rapport + download | 1h | Haut |
| 7 | Mise a jour page web | 1h | Haut |
| 8 | Test complet end-to-end | 1h | Haut |

**Total : ~14h de travail**
**Priorite jour 1 : etapes 1, 2, 4, 6, 7 (~7h) → rapport PDF fonctionnel**
**Jour 2 si necessaire : etapes 3, 5, 8 (~7h) → OCR + analyse photos**

---

## Dependances

- [ ] Creer compte Mindee (mindee.com) → cle API gratuite
- [ ] Installer WeasyPrint sur serveur OVH : `pip install weasyprint`
- [ ] Installer dependances systeme : `sudo apt install libpango1.0-dev libcairo2-dev`
- [ ] Creer dossier uploads : `mkdir -p /var/www/aiticketinfo/uploads`

---

## Resultat final

Le client va sur seoparai.com/scanticket :
1. Upload sa photo de ticket → champs auto-remplis
2. Upload ses preuves (photos lieu, dashcam, temoignage)
3. Clique "Analyser"
4. Voit le resultat avec score + strategie
5. Clique "Telecharger mon rapport PDF"
6. Recoit un dossier PDF de 8-9 pages pret pour la cour

---

*Gold Standard — SEO par AI | AITicketInfo*
