# PLAN & RESUME — Session 8 fevrier 2026
## Projet Ticket911 + NotaryWallet | Par: SeoAI (Michael Perron)

---

# 1. ETAT DES PROJETS

## NotaryWallet — Crypto Inheritance Platform
| Element | Status |
|---------|--------|
| App frontend | https://notarywallet-app.vercel.app (en ligne) |
| Mobile PWA | https://notarywallet-lite.vercel.app (en ligne, minimal) |
| Presentation | https://notarywallet-presentation.vercel.app (en ligne, 18 slides) |
| GitHub | https://github.com/michaelperron12-maker/NotaryWallet.git (a jour) |
| Blockchain | Diamond 0x3fc1d204788FD6C079eC37aD1A608c3fc1700983 (Sepolia) |
| PDF | NotaryWallet-Presentation.pdf (local + GitHub) |
| Completion | 92% — Phase 4 (Launch) en cours |

## Ticket911.ca — Defense de contraventions
| Element | Status |
|---------|--------|
| Demo site | https://911-virid.vercel.app (19 pages) |
| Proposition client | proposition-client-ticket911.pdf (envoyee le 7 fev) |
| Email pitch | Envoye a info@ticket911.ca le 7 fev 2026 |
| Recherche API | RECHERCHE-COMPLETE-APIs-ET-COMPETITEURS.md (complet) |
| Plan B | Lancer solo a 20$/mois si Ticket911 refuse |

---

# 2. ANALYSE CoCounsel (ex-Casetext / Thomson Reuters)

## C'est quoi
- AI juridique "agentic" pour avocats
- Acces a Westlaw (plus grosse base de donnees juridique US)
- Review automatique de 10K+ documents
- Prix: $225/utilisateur/mois
- Couverture: USA seulement

## Pour Quebec (Ticket911)
- **PAS un competiteur** — marche different, droit different
- **PAS un outil utile** — Westlaw = droit americain, pas quebecois
- Common law US vs Code civil du Quebec
- Trop cher pour ce qu'on en ferait

## Pour New York (expansion future)
- **OUTIL potentiel** pour les avocats qui travaillent sur nos dossiers NY
- **PAS un competiteur direct** — CoCounsel = outil pour avocats, Ticket911 = service pour consommateurs
- Pourrait etre utilise par des avocats partenaires pour recherche juridique

### Difference de marche
| | CoCounsel | Ticket911 (NY) |
|---|-----------|----------------|
| Client | Avocat dans son bureau | Conducteur avec un ticket |
| Prix | $225/mois/avocat | ~$20/mois ou pay-per-ticket |
| But | Recherche juridique generale | Contester un ticket specifique |
| Interface | Complexe, professionnel | Simple, grand public |
| Data | Westlaw (tout le droit US) | NYC Open Data + VTL codes |

---

# 3. COMPETITEURS DIRECTS A NEW YORK

| App | Modele | Forces | Faiblesses |
|-----|--------|--------|------------|
| **WinIt** | Pay-per-ticket (~$99-199) | NYC focused, forte presence | NYC seulement, cher |
| **Off The Record** | Connecte avec avocats | Gold standard US, 50 etats | Pas de AI, juste matching |
| **Tikd** | Garantie "on gagne ou gratuit" | Aucun risque pour client | Floride seulement |
| **TicketZap AI** | AI analysis | Tech-forward | Nouveau, pas prouve |
| **GetDismissed** | Self-serve defense | Pas besoin d'avocat | Californie seulement |

## Gap a New York
- WinIt domine mais ZERO AI analysis
- Aucun ne fait OCR + AI auto-analysis du ticket
- Aucun portail self-serve avec AI au Quebec
- NY Open Data = gratuit, 85M+ rows de violations

---

# 4. STACK MVP RECOMMANDE

## Quebec — ~$150/mois
| Service | Role | Cout |
|---------|------|------|
| Mindee OCR | Photo du ticket -> extraction data | ~$50/mois |
| Claude API | Analyse AI, recommandation defense | ~$50/mois |
| Docassemble | Generation de documents juridiques | Gratuit (open source) |
| CanLII | Jurisprudence canadienne/quebecoise | Gratuit |
| Stripe | Paiements abonnement | 2.9% + 0.30$ |
| Twilio | SMS notifications | ~$20/mois |
| Vercel | Hosting frontend | Gratuit (hobby) |

## New York (additionnel)
| Service | Role | Cout |
|---------|------|------|
| Socrata/SODA API | NYC violations data (85M+ rows) | Gratuit (app token) |
| NY VTL codes | Code des infractions routieres NY | Gratuit (public) |
| CoCounsel (optionnel) | Pour avocats partenaires NY | $225/user/mois |

---

# 5. STRATEGIE D'EXPANSION

## Phase 1 — Quebec (maintenant)
- Lancer MVP pour contraventions routieres au Quebec
- Portail self-serve + abonnement $20/mois
- CanLII + OCR + Claude AI
- ZERO competiteur AI au Quebec

## Phase 2 — New York (6-12 mois)
- NYC Open Data = jackpot (tout est ouvert et gratuit)
- 8M+ conducteurs, millions de tickets/annee
- Competiteurs: WinIt mais aucun avec AI
- Pay-per-ticket model ($49-149/ticket)

## Phase 3 — Ontario + autres US (12-24 mois)
- X-Copper et POINTTS dominent ON mais ZERO app
- Expansion vers autres etats US avec Open Data

---

# 6. ACTIONS COMPLETEES AUJOURD'HUI (8 fev)

- [x] Vercel links NotaryWallet verifies (app + lite + presentation)
- [x] Presentation HTML deployee sur Vercel
- [x] PDF presentation genere (Chromium headless, 18 pages)
- [x] Push GitHub NotaryWallet a jour
- [x] Nettoyage ~2.2 Go (backups NotaryWallet + SafeGen)
- [x] Recherche API complete savee dans MEMORY
- [x] Analyse CoCounsel / competiteurs NY
- [x] Ce document de plan

---

# 7. PROCHAINES ETAPES

### Si Ticket911.ca accepte
- Developper la plateforme complete ($40K + $3,950/mois)
- 8 semaines de delivery

### Si Ticket911.ca refuse (Plan B solo)
1. Stripe integration (paiement $20/mois)
2. Portail membre (login/inscription)
3. Nom de domaine propre
4. OCR integration (Mindee - photo du ticket)
5. Claude AI analysis (recommandation de defense)
6. MVP launch Quebec
7. Phase NY avec Open Data

### NotaryWallet
1. Audit de securite externe
2. Deploy Base L2 mainnet
3. Backend + notifications
4. Google Play Store
5. Marketing + landing page

---

*Document genere le 8 fevrier 2026 — SeoAI*
