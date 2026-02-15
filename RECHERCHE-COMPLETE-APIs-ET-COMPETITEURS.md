# RECHERCHE COMPLETE — APIs, Bases de Donnees & Competiteurs
## Projet Ticket911 — Plateforme de defense de contraventions
### Quebec | Ontario | New York
### Date: 8 fevrier 2026 | Par: SeoAI (Michael Perron)

---

# TABLE DES MATIERES

1. [APIs GRATUITES — Bases de donnees ouvertes](#1-apis-gratuites)
2. [APIs PAYANTES — Legal, Court Records, DMV](#2-apis-payantes)
3. [APIs SPECIALISEES — OCR, AI, Paiements](#3-apis-specialisees)
4. [COMPETITEURS — Apps & Firmes existantes](#4-competiteurs)
5. [APPS MORTES & LECONS](#5-apps-mortes)
6. [ANALYSE STRATEGIQUE](#6-analyse-strategique)
7. [STACK MVP RECOMMANDE](#7-stack-mvp)

---

# 1. APIs GRATUITES — Bases de donnees ouvertes

## 1.1 NEW YORK (le jackpot — tout est ouvert)

### Open Parking & Camera Violations NYC (85M+ rows)
- **Endpoint:** `https://data.cityofnewyork.us/resource/nc67-uf89.json`
- **Donnees:** Plaque, amende, statut, montant du, image du ticket
- **Auth:** App token gratuit (1,000 req/heure)
- **MAJ:** Hebdomadaire (nouvelles) + quotidienne (resolues)
- **Doc:** https://dev.socrata.com/foundry/data.cityofnewyork.us/nc67-uf89
- **Exemple:**
```bash
# Par plaque
https://data.cityofnewyork.us/resource/nc67-uf89.json?plate=ABC1234&state=NY

# Avec filtre SoQL
https://data.cityofnewyork.us/resource/nc67-uf89.json?$where=issue_date>'2025-01-01'&$limit=1000
```
- **Python:**
```python
from sodapy import Socrata
client = Socrata("data.cityofnewyork.us", "TON_APP_TOKEN")
results = client.get("nc67-uf89", plate="ABC1234", limit=100)
```

### Moving Violations NYPD (5M+ rows)
- **Endpoint Historic:** `https://data.cityofnewyork.us/resource/bme5-7ty4.json`
- **Endpoint YTD:** `https://data.cityofnewyork.us/resource/57p3-pdcj.json`
- **Donnees:** Code VTL, date, lieu GPS, precinct, plaque, vehicule
- **Colonnes (21):** EVNT_KEY, VIOLATION_DATE, VIOLATION_TIME, CHG_LAW_CD, VIOLATION_CODE, VEH_CATEGORY, REG_PLATE_NUM, REG_STATE_CD, CITY_NM, RPT_OWNING_CMD, X_COORD_CD, Y_COORD_CD, Latitude, Longitude, location, JURIS_CD, Borough Boundaries, City Council Districts, Police Precincts, Zip Codes, Community Districts
- **Auth:** App token gratuit

### Traffic Tickets NYS Statewide (10.67M rows)
- **Endpoint:** `https://data.ny.gov/resource/q4hy-kbtf.json`
- **Donnees:** Code violation, description, annee, jour semaine, age, genre, etat permis, agence police, cour, source (TSLED ou TVB)
- **Auth:** App token gratuit
- **Doc:** https://dev.socrata.com/foundry/data.ny.gov/q4hy-kbtf
- **Exemple:**
```bash
# Par code de violation
https://data.ny.gov/resource/q4hy-kbtf.json?violation_charged_code=1180D

# Par annee et agence
https://data.ny.gov/resource/q4hy-kbtf.json?$where=violation_year=2024 AND police_agency='NYC POLICE DEPT'
```

### Speed Camera Violations NYC
- **Endpoint:** `https://data.cityofnewyork.us/resource/hekt-pqw7.json`
- **Donnees:** 43 champs — Summons Number, Plate ID, Registration State, Issue Date, Violation Code, Vehicle Body Type, Vehicle Make, Issuing Agency, Violation Location, Law Section, Sub Division, etc.
- **MAJ:** Mensuelle

### Red Light Camera Violations NYC
- **Inclus dans le dataset principal nc67-uf89** (filtrer par type de violation)
- **Historique FY14:** `https://data.cityofnewyork.us/resource/9mvu-a5i7.json`

### DOF Parking Violation Codes NYC (97 codes)
- **Endpoint:** `https://data.cityofnewyork.us/resource/ncbg-6agr.json`
- **Donnees:** CODE, DEFINITION, amende Manhattan 96th & below, amende All Other Areas
- **Valeur:** Table de reference essentielle pour decoder les violations

### NYS Vehicle & Traffic Law — Texte complet (API!)
- **Base:** `https://legislation.nysenate.gov/api/3/laws/VAT`
- **Auth:** API key gratuite (s'inscrire sur le site)
- **Exemples:**
```bash
# Arbre complet du VTL
GET https://legislation.nysenate.gov/api/3/laws/VAT?key=CLE

# Avec texte complet de chaque section
GET https://legislation.nysenate.gov/api/3/laws/VAT?full=true&key=CLE

# Section specifique (ex: VTL 1180 - Speed restrictions)
GET https://legislation.nysenate.gov/api/3/laws/VAT/1180?key=CLE

# Version historique (a une date donnee)
GET https://legislation.nysenate.gov/api/3/laws/VAT?date=2025-01-01&key=CLE
```
- **Doc:** https://legislation.nysenate.gov/static/docs/html/laws.html
- **GitHub (open source):** https://github.com/nysenate/OpenLegislation/

### NYS DMV Point System (changements majeurs 16 fev 2026!)
- **URL:** https://dmv.ny.gov/points-and-penalties/the-new-york-state-driver-point-system
- **Acces:** HTML (scraping)

| Violation | Points (avant) | Points (apres 16 fev 2026) |
|---|---|---|
| Speeding 1-10 MPH | 3 | 3 |
| Speeding 11-20 MPH | 4 | 4 |
| Speeding 21-30 MPH | 6 | 6 |
| Speeding 31-40 MPH | 8 | 8 |
| Speeding 40+ MPH | 11 | 11 |
| Reckless driving | 5 | 5 |
| School bus | 5 | **8** |
| Cellulaire | 5 | 5 |
| Texting | 5 | 5 |
| Red light | 3 | 3 |
| Work zone speeding | variable | **8 (fixe)** |
| Due care (VTL 1146) | 2 | **5** |
| Leaving scene injury | 3 | **5** |
| Overheight/bridge-strike | 0 | **8** |
| Equipment (eclairage) | 0 | **1** |
| Seuil suspension | 11 pts / 18 mois | **10 pts / 24 mois** |

### NYS DMV Charge Code Table
- **URL:** https://dmv.ny.gov/tickets/traffic-violation-charge-code-table
- **Format:** PDF — mapping complet Law Title, ADJ Code, Law Code, Description
- **Acces:** Telecharger + parser

### NYPD Motor Vehicle Collisions
- **Endpoint:** `https://data.cityofnewyork.us/resource/h9gi-nx95.json`
- **Donnees:** Tous les accidents reportes par la police a NYC

### Autres datasets NYC
- **511NY API (traffic temps reel):** https://511ny.org/developers/doc — API key gratuite
- **NYC DOT Speed Data:** https://linkdata.nyctmc.org/data/LinkSpeedQuery.txt — public
- **NYC Council Legistar API:** https://council.nyc.gov/legislation/api/ — lois locales NYC

---

## 1.2 QUEBEC

### CanLII API (jurisprudence + legislation)
- **Base:** `https://api.canlii.org/v1/`
- **Auth:** API key gratuite (demander via formulaire feedback)
- **Doc:** https://github.com/canlii/API_documentation/blob/master/EN.md
- **Donnees:** Jurisprudence QC (Code securite routiere C-24.2), textes de loi
- **Endpoints:**
```bash
# Lister les tribunaux/bases
GET /v1/caseBrowse/{lang}/?api_key={key}

# Chercher des cas
GET /v1/caseBrowse/{lang}/{databaseId}/?offset={n}&resultCount={n}

# Metadata d'un cas
GET /v1/caseBrowse/{lang}/{databaseId}/{caseId}/?api_key={key}

# Citateur (cas cites, cas citant, legislations citees)
GET /v1/caseCitator/en/{databaseId}/{caseId}/{metadataType}

# Lister les legislations
GET /v1/legislationBrowse/{lang}/?api_key={key}
```
- **Limites:** Max 10,000 resultats, max 10MB, HTTPS seulement
- **Libraries Python:** canliicalls (PyPI), pycanlii (GitHub), canlii-mcp (GitHub)
- **Library npm:** canlii-api

### Donnees Quebec SAAQ (CKAN API)
- **Base:** `https://www.donneesquebec.ca/recherche/api/3/action/`
- **Auth:** Aucune pour lecture
- **Datasets SAAQ disponibles (8):**

| Dataset | Description | Formats |
|---|---|---|
| Constats d'infraction (Controle routier) | Tickets emis par Controle routier Quebec | CSV, PDF |
| Rapports d'accident | Rapports police avec timing, gravite, types vehicules (2017+) | CSV, PDF |
| Vehicules en circulation | Vehicules immatricules au Quebec | CSV, PDF |
| Permis de conduire | Titulaires de permis au 1er juin/an | CSV, PDF |
| Avis de non-conformite | Non-conformites du controle routier | CSV, PDF |
| Interventions controle routier | Donnees d'interventions | CSV, PDF |
| Dossiers indemnisation | Dossiers de reclamations SAAQ | CSV, PDF |
| Blessures indemnisation | Details blessures des reclamations | CSV, PDF |

- **Exemples:**
```bash
# Chercher des datasets
GET https://www.donneesquebec.ca/recherche/api/3/action/package_search?q=infraction

# Query SQL direct sur les donnees
GET https://www.donneesquebec.ca/recherche/api/3/action/datastore_search_sql?sql={SQL}
```

### Legis Quebec — Code de la securite routiere (C-24.2)
- **URL:** https://www.legisquebec.gouv.qc.ca/fr/document/lc/c-24.2
- **PDF:** https://www.legisquebec.gouv.qc.ca/fr/pdf/cs/C-24.2.pdf
- **Acces:** PAS D'API — PDF download ou web scraping
- **Alternative:** Utiliser CanLII API qui a le meme texte

### SAAQ Points d'inaptitude
- **URL:** https://saaq.gouv.qc.ca/permis-conduire/points-inaptitude/infractions-points-inaptitude
- **Acces:** PAS D'API — PDFs a parser
- **PDFs utiles:**
  - Points & permis: https://saaq.gouv.qc.ca/blob/saaq/documents/publications/points-inaptitude-permis.pdf
  - Points & sanctions: https://saaq.gouv.qc.ca/blob/saaq/documents/publications/points-inaptitude-sanction.pdf
  - Exces vitesse & amendes: https://saaq.gouv.qc.ca/blob/saaq/documents/publications/exces-vitesse-amendes-points-inaptitude.pdf
- **Seuils de points:**
  - 25 ans et +: 15 points
  - 23-24 ans: 12 points
  - Moins de 23 ans: 8 points
  - Permis apprenti: 4 points
- **Contact donnees ouvertes:** donnees.ouvertes@saaq.gouv.qc.ca

### SOQUIJ (Societe quebecoise d'information juridique)
- **URL:** https://soquij.qc.ca
- **Acces:** Abonnement payant, PAS D'API publique
- **Donnees:** Plumitifs (dossiers judiciaires), jurisprudence complete QC
- **Note:** N'inclut PAS la Cour municipale de Montreal
- **Alternative via Certn:** https://docs.certn.co/api/guides/checks/soquij (API commerciale)

### Montreal Open Data
- **Base:** `https://data.montreal.ca/api/3/action/`
- **Datasets pertinents:**
  - Collisions routieres: https://www.donneesquebec.ca/recherche/dataset/vmtl-collisions-routieres
  - Actes criminels: https://donnees.montreal.ca/ville-de-montreal/actes-criminels
  - Stationnement (Agence mobilite durable): https://www.agencemobilitedurable.ca/en/information/open-data

### Lois federales Canada (XML)
- **GitHub:** https://github.com/justicecanada/laws-lois-xml
- **Open Canada:** https://open.canada.ca/data/en/dataset/eb0dee21-9123-4d0d-b11d-0763fa1fb403
- **Donnees:** XML complet de toutes les lois federales (Code criminel pour conduite avec facultes, etc.)

---

## 1.3 ONTARIO

### CanLII API (memes endpoints que QC ci-dessus)
- Jurisprudence Highway Traffic Act Ontario
- Texte complet du HTA

### Schedule 43 — Set Fines Ontario (558+ infractions)
- **URL:** https://www.ontariocourts.ca/ocj/provincial-offences/set-fines/set-fines-i/schedule-43/
- **Acces:** HTML table (scraping) — Clean, facilement parseable
- **Donnees:** Item, Offence, HTA Section, Set Fine
- **MAJ:** Derniere mise a jour 22 janvier 2026 (apres amendements HTA 1er jan 2026)

### Ontario Demerit Points
- **URL officiel:** https://www.ontario.ca/page/understanding-demerit-points
- **Reglement:** O. Reg. 339/94 via CanLII: https://www.canlii.org/en/on/laws/regu/o-reg-339-94/latest/

### Ontario Data Catalogue (CKAN)
- **Base:** `https://data.ontario.ca/api/3/action/`
- **Datasets:** Stats collisions ORSAR, donnees traffic (stale 2008-2012)

### A2AJ Canadian Legal Data
- **API:** https://api.a2aj.ca/docs
- **Hugging Face:** https://huggingface.co/datasets/a2aj/canadian-case-law
- **Donnees:** 17,000+ decisions Cour d'appel Ontario
- **Auth:** Aucune, gratuit

### CE QUI N'EXISTE PAS en Ontario:
- **ICON (Integrated Courts Offences Network):** Explicitement "will not be made available"
- **Ontario e-Laws API:** N'existe pas, web portal seulement (JavaScript requis)
- **POA Court Ticket Lookup API:** Pas d'API, web form seulement
- **OCPP (Ontario Courts Public Portal):** Lance oct 2025, mais PAS pour traffic/POA

---

## 1.4 SOCRATA SODA API — Notes techniques generales

Tous les datasets NYC Open Data et NYS Open Data utilisent Socrata:

- **Format URL:** `https://{domain}/resource/{dataset-id}.json`
- **Formats supportes:** JSON, CSV, XML, GeoJSON
- **Langage query:** SoQL (SQL-like) — `$where`, `$select`, `$group`, `$order`, `$limit`, `$offset`, `$having`
- **Rate limits sans token:** Throttle par IP
- **Rate limits avec token:** ~1,000 req/heure (possible d'augmenter)
- **Inscription token:** https://data.cityofnewyork.us/profile/edit/developer_settings
- **Library Python:** `pip install sodapy`
- **Doc SoQL:** https://dev.socrata.com/docs/queries/
- **Doc endpoints:** https://dev.socrata.com/docs/endpoints.html

---

# 2. APIs PAYANTES — Legal, Court Records, DMV

## 2.1 Court Records APIs

### UniCourt
- **URL:** https://unicourt.com/
- **Prix:** $49/mois (Personal) → $2,250+/mois (Enterprise)
- **Couverture:** 4,000+ tribunaux US, 140M+ records, 40+ etats — NY inclus
- **Donnees:** Dockets, parties, attorneys, judge analytics
- **API:** REST, Python SDK disponible
- **Doc:** https://unicourt.com/solutions/enterprise-api
- **QC/ON:** NON

### Trellis Law
- **URL:** https://trellis.law/
- **Prix:** $69.95/mois (Essentials) → $199.95/mois (Professional)
- **Couverture:** 45 etats US, 2,300 comtes
- **Donnees:** Analytics de juges, prediction de resultats, tendances par cour
- **Doc:** https://trellis.law/legal-data-api
- **QC/ON:** NON

### Docket Alarm
- **URL:** https://www.docketalarm.com/
- **Prix:** $39.99-$99/mois + frais per-use
- **Couverture:** Federal + state US (NY inclus)
- **API:** REST, Python client sur GitHub: https://github.com/DocketAlarm/pacer-api
- **QC/ON:** NON

### Westlaw API (Thomson Reuters)
- **URL:** Thomson Reuters Developer Portal
- **Prix:** $132-$428/mois
- **Couverture:** US + Canada (incluant QC et ON!)
- **Donnees:** Jurisprudence complete, annotations, statuts
- **Note:** Le plus complet mais le plus cher

### LexisNexis API (Protege)
- **URL:** https://dev.lexisnexis.com/
- **Prix:** $171+/mois
- **Couverture:** US + Canada
- **Donnees:** Jurisprudence, statuts, analytics
- **Note:** Comparable a Westlaw

### CoCounsel (Thomson Reuters / ex-Casetext)
- **Prix:** $225/user/mois
- **Donnees:** AI agentic + donnees Westlaw, review 10K documents
- **Note:** Lance aout 2025, enterprise seulement

### vLex / Vincent AI
- **URL:** https://vlex.com
- **Prix:** $65-$115/mois
- **Couverture:** 130+ pays (incluant Canada!)
- **Donnees:** Jurisprudence mondiale, AI search
- **Note:** Acquis par Clio en 2025

### Fastcase Legal Data API
- **URL:** https://www.fastcase.com/solutions/legal-data-api/
- **Prix:** Custom
- **Couverture:** US
- **Donnees:** Bulk case law, statuts

### CaseMine
- **URL:** https://www.casemine.com/home/casemine-api
- **Prix:** Freemium
- **Couverture:** Global
- **Donnees:** Case law search, citation analysis

### CourtListener (Free Law Project)
- **URL:** https://www.courtlistener.com/help/api/
- **Prix:** GRATUIT (5,000 queries/heure auth, 5,000/jour free)
- **Couverture:** 406+ juridictions US
- **Donnees:** Case law, PACER/RECAP (140M+ docket entries), citations
- **SDK:** `@us-legal-tools/courtlistener-sdk` (npm)

### Harvey AI
- **Prix:** $1,000-$1,200/avocat/mois
- **Note:** Le plus avance mais beaucoup trop cher pour une startup. Vise les mega-firms.
- **Valuation:** ~$8 milliards (Series F dec 2025)

### Pre/Dicta
- **URL:** https://www.pre-dicta.com/
- **Donnees:** Prediction AI de resultats judiciaires
- **Prix:** Custom

## 2.2 Driver Record / DMV APIs

### Certn (Canadian)
- **URL:** https://docs.certn.co/api/guides/checks/motor-vehicle-record-check
- **Prix:** $4.99-$10/check
- **Couverture:** Ontario — PAS Quebec, PAS Alberta
- **Donnees:** Statut permis, violations, points demerite
- **API:** REST

### Checkr
- **URL:** https://checkr.com/background-check/mvr
- **Prix:** $9.50/MVR check
- **Couverture:** US + Ontario
- **Donnees:** Driver abstracts

### SambaSafety
- **URL:** https://sambasafety.com/
- **Prix:** Enterprise
- **Couverture:** US + Canada
- **Donnees:** Monitoring continu des dossiers de conduite

### NYS DMV DIAL-IN
- **URL:** https://dmv.ny.gov/records/automated-access-for-business/dial-in
- **Prix:** $7.00/recherche
- **Couverture:** New York State
- **Donnees:** Acces direct automatise aux records DMV

### Triton Canada
- **URL:** https://www.tritoncanada.ca/
- **Prix:** Custom
- **Couverture:** Quebec + Ontario (le SEUL qui couvre QC!)
- **Donnees:** Records de conduite

### LexisNexis Risk Solutions
- **Prix:** Enterprise
- **Couverture:** US
- **Donnees:** Driver data, vehicle ownership, insurance

### Sterling
- **Prix:** Enterprise
- **Couverture:** US + Canada
- **Donnees:** Background checks + MVR

## 2.3 Vehicle & Insurance Data

### VinAudit
- **URL:** https://www.vinaudit.com/vehicle-history-api
- **Prix:** Le plus abordable US + Canada
- **Donnees:** Historique vehicule

### CARFAX
- **Acces:** Partnership formel requis
- **Donnees:** Historique vehicule complet

### IBC DASH (Insurance Bureau of Canada)
- **URL:** https://www.ibc.ca/industry-resources/insurance-data-tools/dash
- **Couverture:** Ontario (exclut explicitement Quebec!)

### NICB VINCheck
- **Prix:** Gratuit pour basic (vehicules voles)

## 2.4 Legislative Tracking APIs

### Open States API v3
- **URL:** https://v3.openstates.org/
- **Doc:** https://docs.openstates.org/api-v3/
- **Prix:** Gratuit avec API key
- **Donnees:** Bills, votes, legislateurs — 50 etats incluant NY
- **Valeur:** Tracker les changements au VTL

### LegiScan API
- **URL:** https://legiscan.com/legiscan
- **Prix:** Free tier + paid subscriptions
- **Donnees:** Bills, status, sponsors, textes, roll calls — 50 etats
- **Archives NY:** https://legiscan.com/NY/datasets
- **Doc:** https://api.legiscan.com/docs/

### SerpApi (Google Scholar Case Law)
- **URL:** https://serpapi.com/google-scholar-api
- **Prix:** $75/mois (5K searches) → $275/mois (30K)
- **Donnees:** Case law via Google Scholar avec filtres par cour
- **Valeur:** Recherche large de precedents

---

# 3. APIs SPECIALISEES — OCR, AI, Paiements

## 3.1 OCR & Data Extraction

### Mindee Traffic Ticket OCR API (GAME CHANGER)
- **URL:** https://www.mindee.com/product/traffic-ticket-ocr-api
- **Prix:** Gratuit 250 tickets/mois, puis EUR 44-584/mois ($0.01-0.10/ticket volume)
- **Ce que ca fait:** Photo/PDF du ticket → 50+ champs extraits automatiquement
- **Champs:** Plaque, type violation, montant amende, marque/modele vehicule, date, officier, departement, numero citation, date de cour, donnees vitesse
- **Precision:** >90% global, >95% sur la plupart des champs
- **Vitesse:** ~0.9 sec (images), ~1.3 sec (PDFs)
- **Couverture:** US + 50 pays (incluant Canada)
- **SDK:** Python, JavaScript
- **Valeur:** CORE du user flow "photographier ton ticket"

## 3.2 AI Analysis

### Claude API (Anthropic)
- **Doc legal:** https://docs.claude.com/en/docs/about-claude/use-case-guides/legal-summarization
- **Prix:** Haiku $1/$5, Sonnet $3/$15, Opus $5/$25 per million tokens
- **Batch API:** 50% discount
- **Context:** 200K tokens, Files API (PDF/DOCX/images), Citations API
- **Valeur:** CORE AI pour analyse ticket, matching precedents, generation arguments defense

### OpenAI GPT API
- **Doc:** https://platform.openai.com/docs/guides/structured-outputs
- **Prix:** GPT-4o ~$2.50/$10/M tokens; GPT-4o-mini ~$0.15/$0.60/M tokens
- **Valeur:** Structured Outputs = extraction JSON garantie conforme au schema

## 3.3 Paiements

### Confido Legal (MEILLEUR pour legal)
- **URL:** https://confidolegal.com/
- **Prix:** $1.50/debours, PAS de mensuel
- **API:** GraphQL, API-first design
- **Compliance:** Trust/IOLTA compliant
- **Dev center:** https://confidolegal.com/developer-center
- **Valeur:** Ideal pour platform custom avec avocats

### LawPay (standard industrie)
- **URL:** https://www.lawpay.com/
- **70+ integrations, trust/IOLTA compliant, API disponible**
- **Zapier:** Integre avec Stripe via Zapier

### Stripe (si pas d'avocats)
- **Prix:** 2.9% + $0.30/transaction
- **Features:** Subscriptions ($20/mois plan), Connect (payouts), Checkout, Tax, Webhooks
- **ATTENTION:** PAS trust/IOLTA compliant seul — utiliser Confido Legal ou LawPay en complement

### Headnote
- **URL:** https://headnote.com/
- **Note:** PAS D'API — pas adapte pour integration custom

## 3.4 Automation & Chatbots

### Insighto.ai (white-label chatbot)
- **URL:** https://insighto.ai/
- **Prix:** $0.015/query
- **Ce que ca fait:** Chatbot/voicebot AI white-label, brandable, deployable sur ton domaine
- **Valeur:** Intake client automatise

### Gavel (ex-Documate)
- **URL:** https://www.gavel.io/
- **Prix:** $350/mois (Pro) → $417/mois (API)
- **Ce que ca fait:** Document automation + portail client white-label + DocuSign
- **Valeur:** Le plus proche d'un "moteur traffic ticket" turnkey

### Docassemble (open source)
- **URL:** https://docassemble.org/
- **Prix:** ~$30 hosting
- **Ce que ca fait:** Interviews guidees → generation documents de cour automatique
- **Utilise dans:** 42+ etats US + Canada
- **Bonus:** Suffolk LIT Lab Document Assembly Line (https://assemblyline.suffolklitlab.org/) — inclut e-filing open source

### LawDroid Builder
- **URL:** https://lawdroid.com/
- **Prix:** $99/mois
- **Ce que ca fait:** Legal chatbot builder no-code, integre avec Clio

### Josef Legal
- **URL:** https://joseflegal.com/
- **Ce que ca fait:** Plateforme automation legal no-code
- **Clients:** Clifford Chance (top firm mondial)

### A2J Author
- **URL:** https://www.a2jauthor.org/
- **Prix:** Gratuit pour cours et orgs legales
- **Ce que ca fait:** Interviews guidees visuelles, deja utilise au Canada

## 3.5 Communication

### Twilio SMS
- **Prix:** ~$0.013/message vers Canada
- **Valeur:** Rappels date de cour

### SendGrid Email
- **Prix:** Gratuit 100/jour, Essentials $19.95/mois (50K emails)
- **Valeur:** Notifications, updates dossier

### Calendly
- **Prix:** $12/mois Standard
- **Ce que ca fait:** Widget booking embeddable (inline, popup), API sur plans payes
- **Valeur:** Prise de RDV consultation avocat

## 3.6 Practice Management APIs

### Clio API
- **URL:** https://docs.developers.clio.com/
- **Prix:** ~$39/mois/user
- **Ce que ca fait:** REST API complete, 250+ integrations, case management, billing, trust accounting
- **Note:** Compagnie canadienne (Burnaby, BC), a acquis vLex en 2025

### TrafficTicketCRM
- **URL:** https://www.trafficticketcrm.com/
- **Ce que ca fait:** SEUL CRM concu specifiquement pour firmes de tickets de trafic
- **Features uniques:** Auto Court Data Loader (tire les donnees de cour = leads!), docket management, direct mailers, paiements
- **Prix:** Non publie

---

# 4. COMPETITEURS — Apps & Firmes existantes

## 4.1 Apps US — Les plus avancees technologiquement

### Off The Record (le gold standard)
- **URL:** https://offtherecord.com
- **Fonde:** Octobre 2015 (Seattle)
- **Fondateurs:** Alex Guirguis (CEO), Mark Mikhail
- **Modele:** Marketplace — algo "Smart Match" connecte usagers avec avocats locaux
- **Avocats:** 1,000+ dans le reseau
- **Tickets traites:** 1,000,000+
- **Taux succes:** 97% (revendique)
- **Prix:** $59-$599/ticket (avocat fixe son prix), garantie remboursement
- **Funding:** Revolution (Steve Case) + O'Reilly AlphaTech Ventures
- **Ratings:** 4.7/5 (20,000+ reviews), 4.90 Reviews.io, 4.3-4.4 Trustpilot
- **Couverture:** Washington, NYC, Portland, expansion CA
- **CDL:** Feature speciale pour permis commercial
- **Forces:** Meilleure app du marche, matching intelligent, garantie, CDL
- **Faiblesses:** Couverture limitee, dependant des avocats

### WinIt (NYC dominant)
- **URL:** https://www.appwinit.com/
- **Fonde:** Juin 2015
- **Fondateur:** Christian Fama
- **Modele:** Contingency — usager paie 50% de la valeur du ticket SEULEMENT si dismiss
- **Revenue:** ~$14.8M (2025)
- **Users:** 1,000,000+
- **Tickets traites:** 320,000+, $6M+ en tickets dismisses
- **Couverture:** NYC (parking + traffic)
- **Equipe:** Ex-policiers retraites, juges
- **Forces:** Zero risque pour le client, massive base NYC, UX simple
- **Faiblesses:** NYC seulement, depend d'experts humains (pas scalable)

### TicketZap AI (le nouveau AI)
- **URL:** https://ticketzap.ai/
- **Modele:** AI scanne 47+ defenses legales, puis avocats verifies les resultats
- **Prix:** Analyse gratuite, paiement SEULEMENT si gain
- **Resultats:** 25,000+ tickets dismisses, $8.7M+ en amendes contestees, savings moyen $347/cas
- **Couverture:** 50 etats US + DC
- **Taux succes:** 87%
- **Forces:** AI + humain hybride, national, zero risque
- **Faiblesses:** Nouveau, position reglementaire floue

### GetDismissed (California DIY)
- **URL:** https://getdismissed.com/
- **Fonde:** 2014
- **Modele:** Automation — genere documents "Trial by Written Declaration"
- **Prix:** <$50 one-time OU $39/an (illimite!)
- **Revenue:** ~$5.4M
- **Couverture:** California seulement
- **Forces:** Ultra low cost, automatise, abonnement annuel
- **Faiblesses:** CA seulement, pas de representation

### Ticket Toro AI (Miami)
- **URL:** https://tickettoro.ai/
- **Modele:** AI scanne 50+ defauts techniques en 60 secondes
- **Prix:** $35 (ticket dismissible) / $89 (defense standard)
- **Taux succes:** 97% (revendique)
- **Couverture:** Miami-Dade County / Florida
- **Forces:** Le moins cher ($35!), AI rapide, representation incluse

### TicketFight AI (California)
- **URL:** https://www.ticketfight.ai/
- **Prix:** $49 flat, garantie remboursement
- **Couverture:** California
- **Forces:** Bas prix, rapide (10 min)

### The Ticket Clinic (le geant traditionnel)
- **URL:** https://www.theticketclinic.com/
- **Fonde:** 1987 par Mark Gold
- **Scale:** 40+ bureaux (Florida, Georgia, California), 300 affilies nationaux
- **Cas:** 5-10 millions+ depuis la fondation
- **Forces:** Le plus gros aux US, 38+ ans
- **Faiblesses:** Modele traditionnel, pas tech

### Ticket Wizard (ex-Unger & Kowitt)
- **URL:** https://ticketwizard.com/
- **Fonde:** 1995, rebrand juin 2023
- **Prix:** A partir de $49.95, garantie remboursement
- **Cas:** 1,000,000+
- **Couverture:** Toute la Florida

## 4.2 Competiteurs QUEBEC (marche direct)

### SOS Ticket
- **URL:** https://www.sosticket.ca/
- **Fonde:** 2006
- **Claim:** "Firme la plus experimentee du marche" / "Leader en contestation"
- **Prix:** $130-$550 selon points demerite, paiement en 4 versements sans interet
- **Garantie:** Remboursement complet si meilleur resultat disponible ailleurs
- **Bureau:** 485 Rue McGill, Montreal
- **Forces:** Le plus vieux au QC, marque etablie, paiement flexible
- **Faiblesses:** Firme traditionnelle, tech limitee

### SolutionTicket
- **URL:** https://www.solutionticket.com/en/
- **Prix:** A partir de $249.95 (taxes incluses) pour 0-3 points
- **Bureau:** 3221, Autoroute Laval 440 Ouest
- **Features:** Portail client en ligne 24/7 pour suivi de dossier
- **Specialisation:** Aussi camionnage/vehicules lourds
- **Forces:** Portail en ligne (seul au QC avec ca), camionnage
- **Faiblesses:** Prix plus eleve

### TicketAide
- **URL:** https://ticketaide.ca/
- **Fonde:** 2011 par Avi Levy et Jamie Benizri (ex-procureur)
- **Claim:** "Le plus abordable au Quebec"
- **Couverture:** Quebec + Ontario + New York (prix varient)
- **NOTE:** Meme fondateur (Avi Levy) que Ticket911.ca!
- **Forces:** Abordable, ex-procureurs
- **Faiblesses:** N'inclut pas la representation au proces

### MTL Ticket
- **URL:** https://www.mtlticket.ca/en/
- **Couverture:** Montreal / Quebec
- **Forces:** Focus Montreal
- **Faiblesses:** Petite operation

### Neolegal
- **URL:** https://neolegal.ca
- **Modele:** Forfait fixe, portail client virtuel
- **Note:** Le SEUL competiteur techno-forward au Quebec, mais generaliste (pas specialise tickets)

### Ticket911.ca (LE CLIENT)
- **URL:** https://aiticketinfo.com/
- **Tel:** (514)700-0303 / 1(855)444-4911
- **Email:** info@aiticketinfo.com
- **Equipe:** Avi Levy et Bernard Levy-Soussan (17 ans comme procureurs)
- **Experience:** 60 ans combines, 100,000+ cas resolus
- **Couverture:** Quebec, Ontario, Alberta, New York State
- **Services:** Tickets, preparation audience, vehicules lourds, appels, conduite avec facultes, pardons, accusations criminelles
- **Packages:** Par points demerite (0-3, 4-5, 6+) + consultation
- **Tech actuel:** Site web avec blog, soumission en ligne, mobile-friendly
- **Forces:** Ex-procureurs, multi-provinces, marque etablie, gros volume
- **Faiblesses:** Site web traditionnel (pas d'app, pas d'AI, pas de portail self-serve), pas de paiement en ligne visible

## 4.3 Competiteurs ONTARIO

### X-Copper (le dominant)
- **URL:** https://www.xcopper.com/
- **Equipe:** Ex-policiers + avocats criminalistes/paralegals
- **Clients:** 300,000+ clients satisfaits
- **Couverture:** Ontario-wide + Calgary
- **Prix:** Block Fee (devis tout-inclus upfront). Texte photo ticket a 416-926-7737
- **Services:** Tickets, vitesse, collisions, DUI, offenses criminelles
- **Forces:** Enorme base clients, ex-policiers, transparence block fee
- **Faiblesses:** Firme traditionnelle, Ontario/Alberta seulement, PAS au Quebec

### POINTTS (la franchise)
- **URL:** https://pointts.com/
- **Fonde:** Mai 1984 par Brian J. Lawrie (15 ans police veteran)
- **Modele:** FRANCHISE — premiere et plus grande firme independante de paralegals au Canada
- **Bureaux:** 17 bureaux — Ontario, Alberta, Manitoba
- **Claim:** "Traffic Tickets are the only thing they do"
- **Forces:** Le plus vieux au Canada (40+ ans), modele franchise = scalable, 100% tickets
- **Faiblesses:** Modele paralegal traditionnel, pas de tech, PAS au Quebec

### JusticeJolt
- **URL:** https://www.justicejolt.com/
- **Fondatrice:** Shelina Lalji (ex-Master Franchisee POINTTS)
- **Modele:** Plateforme virtuelle, Block Fee, matching avec paralegals licencies
- **Couverture:** Ontario + Manitoba
- **Processus:** Texte photo ticket a (289) 272-9295 ou formulaire en ligne
- **Forces:** Virtual-first, transparent, focus traffic
- **Faiblesses:** Nouveau brand (spin-off POINTTS)

### Ticket Defenders
- **URL:** https://ticketdefenders.ca/
- **Fonde:** Trademark 2002 (firme depuis 1980s comme "Streetwise Paralegal")
- **Principal:** Ex-Assistant Crown Attorney + Traffic Court Prosecutor (depuis 1989)
- **Couverture:** SW Ontario (Windsor a Toronto)
- **Forces:** Experience procureur, marque etablie, backing cabinet d'avocats

### OTT Legal Services
- **URL:** https://www.ontariotraffictickets.com/
- **Fonde:** 25+ ans par ex-policiers Toronto et OPP
- **Couverture:** Ontario-wide (10+ villes)
- **Forces:** Ex-police, representation complete, reviews Google 5 etoiles

### X-COPS
- **URL:** https://x-cops.ca/
- **Modele:** Boutique — paralegals licencies (20+ ans), avocats DUI, ex-policiers/procureurs
- **Couverture:** Toronto, Ottawa, Barrie, Ontario-wide
- **Forces:** Service personnalise

### TicketCombat
- **URL:** https://www.ticketcombat.com/
- **Modele:** Ressource educative — enseigne comment contester soi-meme (DIY)
- **Couverture:** Municipalites Ontario

## 4.4 B2B SaaS pour cabinets

| Outil | Prix | Specialisation |
|---|---|---|
| **TrafficTicketCRM** | Non publie | SEUL CRM specialise traffic tickets |
| **Clio** (canadien!) | ~$39/user/mois | General + 250 integrations |
| **MyCase** | $39-$119/user/mois | Criminal defense (traffic = subset) |
| **PracticePanther** | $49-$89/user/mois | Page dediee traffic law |
| **Smokeball** | $39-$219/user/mois | Forte automation |
| **Filevine** | Custom | Litigation/case management |

## 4.5 Marketplaces d'avocats

| Plateforme | Modele | Prix |
|---|---|---|
| **Avvo** | Bidding — avocats font des offres | Gratuit pour clients |
| **LegalMatch** | Lead gen pour avocats | $2,400-$100K/an pour avocats |
| **JustAnswer** | Abonnement Q&A | $65/mois (avis seulement, pas representation) |
| **TicketVoid** | Lead gen gratuit | Gratuit pour conducteurs |

---

# 5. APPS MORTES & LECONS CRITIQUES

| App | Annee | Ce qui s'est passe | Lecon |
|---|---|---|---|
| **TIKD** (Florida) | 2022 | Cour supreme FL: "pratique illegale du droit" (4-3) | DOIT operer via cabinet/paralegals licencies |
| **DoNotPay** | 2024-2025 | FTC: amende $193K, interdit de dire "AI lawyer" | Pas de fausses promesses sur les capacites AI |
| **Fixed** (Shark Tank) | 2016 | Acquis par Lawgix → mort. Municipalites ont bloque soumissions | Les municipalites peuvent bloquer les submissions automatisees |
| **ROSS Intelligence** | 2021 | Poursuivi par Thomson Reuters pour violation copyright → ferme | Attention aux droits d'auteur sur les donnees legales |

### Lecons cles:
1. **Toujours operer SOUS un cabinet d'avocats ou paralegals licencies** — sinon risque de "unauthorized practice of law"
2. **Ne jamais promettre que l'AI remplace un avocat** — FTC/barreaux veillent
3. **Les municipalites peuvent etre hostiles** — prevoir des canaux alternatifs
4. **Les droits d'auteur sur les donnees legales sont un champ de mines** — utiliser les sources ouvertes (CanLII, government data)

---

# 6. ANALYSE STRATEGIQUE

## 6.1 Marche en chiffres

| Metrique | Valeur |
|---|---|
| Tickets/an US | 25-50 millions |
| Revenus gouvernements US (amendes) | $12.9 milliards (2021) |
| Impact total tickets + assurance US | $7.5-15 milliards/an |
| Condamnations HTA Ontario 2022 | 559,140 |
| Legal tech global 2026 | $34.88 milliards |
| Projection 2030-2032 | $46.7-63.6 milliards (CAGR 9.4-13.5%) |
| Funding legal tech 2025 | $4.3 milliards (+54% vs 2024) |

## 6.2 Gaps au Quebec (avantage competitif)

1. **ZERO app AI au Quebec** — Tous les competiteurs QC sont des cabinets traditionnels
2. **ZERO experience mobile-first** au QC — Personne n'offre une vraie app
3. **ZERO portail self-serve avec paiement en ligne** (sauf SolutionTicket basique)
4. **X-Copper PAS au Quebec** — Le plus gros joueur canadien n'a pas touche QC
5. **POINTTS PAS au Quebec** — La plus grosse franchise canadienne non plus
6. **ZERO CRM specialise traffic au Canada** — TrafficTicketCRM est US seulement
7. **Quebec est fragmentee** — 5 petits competiteurs, aucun dominant tech

## 6.3 Modele recommande

**Hybride Off The Record + TicketZap AI:**

```
FLOW CLIENT:
1. Photo ticket → Mindee OCR (extraction donnees < 1 sec)
2. AI analyse → Claude API (47+ defenses legales checkees)
3. Smart Match → Avocat/paralegal local assigne
4. Portail client → Suivi en temps reel + documents
5. Paiement → Stripe/Confido Legal
6. Rappels → Twilio SMS avant date de cour
7. Resultat → Feedback loop pour ameliorer l'AI
```

**Pricing suggere (base sur benchmarks):**
- Analyse AI gratuite (lead gen)
- 0-3 points: $149-$199
- 4-5 points: $249-$349
- 6+ points: $399-$549
- Abonnement annuel protection: $39/an (a la GetDismissed)
- Plan B solo: $20/mois portail membre

## 6.4 Risques reglementaires

| Risque | Mitigation |
|---|---|
| Pratique illegale du droit | Toujours operer SOUS Ticket911 (cabinet licencie) |
| Fausses promesses AI | Disclaimer clair: "AI assiste, avocat decide" |
| Vie privee (Loi 25 QC) | Consentement explicite, donnees au Canada |
| IOLTA/trust compliance | Utiliser Confido Legal ou LawPay |
| Municipalites hostiles | Relations directes avec les cours, pas d'automation agressive |

---

# 7. STACK MVP RECOMMANDE

## Budget: ~$150/mois + per-transaction

| Composant | Outil | Cout mensuel |
|---|---|---|
| OCR ticket | Mindee API | Gratuit (250/mois) |
| AI analyse juridique | Claude API (Anthropic) | ~$50 |
| Documents de cour | Docassemble (open source) | ~$30 hosting |
| Chatbot intake client | Insighto.ai | ~$50 |
| Jurisprudence Canada | CanLII API | Gratuit |
| Data tickets NY | Socrata SODA API | Gratuit |
| Legislation NY | NYS Open Legislation API | Gratuit |
| Paiements | Confido Legal ou Stripe | Par transaction |
| SMS rappels | Twilio | ~$13/1000 SMS |
| Email notifications | SendGrid | Gratuit |
| Booking consultation | Calendly | $12 |
| Practice management | Clio API | ~$39/user |

**TOTAL MVP: ~$150-200/mois + ~$39/user Clio**

## Budget scale-up (~$1,300/mois a 500 users)

Ajouter:
- Certn MVR checks Ontario: ~$500 (50 checks)
- UniCourt NY: $49
- NYS DMV DIAL-IN: $700 (100 searches)
- Mindee upgrade: ~$50

## Priorites d'integration

1. **Semaine 1:** Mindee OCR + Claude API (core user flow)
2. **Semaine 2:** CanLII API + Socrata SODA (data layer)
3. **Semaine 3:** Stripe/Confido + Twilio + SendGrid (monetisation + comms)
4. **Semaine 4:** Portail client + Calendly (experience complete)

---

# SOURCES PRINCIPALES

## APIs & Donnees
- Donnees Quebec: https://www.donneesquebec.ca
- CanLII API: https://github.com/canlii/API_documentation
- NYC Open Data: https://data.cityofnewyork.us
- NYS Open Data: https://data.ny.gov
- NYS Open Legislation: https://legislation.nysenate.gov
- Socrata SODA: https://dev.socrata.com
- Mindee OCR: https://www.mindee.com/product/traffic-ticket-ocr-api
- CourtListener: https://www.courtlistener.com/help/api/
- UniCourt: https://unicourt.com
- Trellis: https://trellis.law
- Certn: https://docs.certn.co
- Confido Legal: https://confidolegal.com
- Docassemble: https://docassemble.org

## Competiteurs
- Off The Record: https://offtherecord.com
- WinIt: https://www.appwinit.com
- TicketZap AI: https://ticketzap.ai
- GetDismissed: https://getdismissed.com
- SOS Ticket: https://www.sosticket.ca
- SolutionTicket: https://www.solutionticket.com
- Ticket911: https://aiticketinfo.com
- X-Copper: https://www.xcopper.com
- POINTTS: https://pointts.com
- The Ticket Clinic: https://www.theticketclinic.com

## Industrie
- Legal tech market: https://www.globenewswire.com/news-release/2024/11/13/2980486/
- TIKD ruling: https://www.abajournal.com/news/article/florida-supreme-court-rules-ticket-fighting-startup
- DoNotPay FTC: https://www.ftc.gov/news-events/news/press-releases/2025/02/ftc-finalizes-order-donotpay
- Harvey AI: https://www.harvey.ai
- Blue J Legal: https://betakit.com/blue-j-series-d-after-doubling-revenue/

---

*Rapport genere le 8 fevrier 2026 par SeoAI pour le projet Ticket911*
