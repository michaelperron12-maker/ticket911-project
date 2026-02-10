# Memory Notes

## Project: Ticket911.ca (Client: traffic ticket defense law firm)
- Developer: Michael Perron (SeoAI), email: michaelperron12@gmail.com, tel: 514-609-2882
- GitHub: michaelperron12-maker, repos: ticket911-project, ticket911-demo
- Vercel: 911-virid.vercel.app (demo site only)
- VPS PROD: https://seoparai.com/scanticket/ (26-agent AI backend)
- Local: /home/serinityvault/Desktop/projet web/911/
- Colors: #1e3a5f, #e63946, #d4a843, font Inter
- Proposal: $40K dev + $3,950/month, email sent Feb 7, 2026

### Backend (Feb 10, 2026) — ~80% complet
- 26 agents AI: Fireworks 12 modèles, pipeline 4 phases, FONCTIONNEL
- DB: 24,770 juris (97 QC, 895 ON), 4,280 lois (4082 QC, 198 ON)
- ChromaDB: 992 embeddings, FTS5: 24,770 entrées
- Email: SMTP localhost Postfix OK, HTML pro template
- PDF: WeasyPrint 9 pages, systemd: ticket911.service enabled
- Dotenv: .env propre, load_dotenv() dans api.py + base_agent.py

### Frontend Scanner (Feb 10, 2026) — LANDING PAGE COMPLÈTE DÉPLOYÉE
- scanner.html: landing page complète + scanner intégré
- Navbar fixe: logo, liens, CTA rouge "Analyser mon ticket"
- Hero plein écran: badge vert live, titre gradient, stats (24770/4280/26/45s)
- Comment ça marche: 3 step cards avec scroll reveal
- Pourquoi Ticket911: 6 feature cards (juris, lois, double verif, PDF, QC+ON, Vision)
- Scanner: formulaire + pipeline 26 agents + résultats
- Prix: 3 plans (Gratuit $0, Pro $19.99, Abo $9.99/mois) — boutons placeholder
- FAQ: 6 questions accordéon
- Footer: SeoAI branding, legal disclaimer
- Mode DEMO: /api/demo, bouton "Tester sans ticket", min 8s animation
- Noms de modèles AI CACHÉS (user veut pas les montrer)
- Section "Moteurs AI" RETIRÉE des résultats
- Cache-busting headers sur route index, responsive mobile
- IntersectionObserver scroll reveal animations

### OVH Server
- SSH: `ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234`
- SSH instable: retry après 5s, ne pas chaîner trop de sudo
- Flask: port 8912, nginx proxy seoparai.com/scanticket/
- DB: /var/www/ticket911/db/ticket911.db

### APIs en attente (user doit fournir)
- SMTP_PASS (alert@seoparai.com), MINDEE_API_KEY (OCR, prioritaire)
- CANLII_API_KEY, TWILIO, SENDGRID (optionnels)

### Prochaines étapes
- Stripe placeholder (frontend seulement, pas fonctionnel)
- Portail membre login/inscription
- Rate limiting, log rotation

## Project: NotaryWallet (Crypto Inheritance Platform)
- Local: /home/serinityvault/Desktop/projet web/NotaryWallet/
- GitHub: https://github.com/michaelperron12-maker/NotaryWallet.git
- Vercel links:
  - App frontend: https://notarywallet-app.vercel.app
  - Lite (mobile PWA): https://notarywallet-lite.vercel.app
  - Presentation: https://notarywallet-presentation.vercel.app
- Blockchain: Diamond contract on Sepolia: 0x3fc1d204788FD6C079eC37aD1A608c3fc1700983
- Domaine prévu: app.notarywallet.com (pas encore actif)
- Stack: React 19, Vite, TypeScript, TailwindCSS, wagmi v2, Solidity 0.8.24, ERC-2535 Diamond
- Mobile: Capacitor PWA + APK Android (v2.3.1), 9 versions APK
- 3 produits: Site Web (B2C), NotaryWallet Lite (mobile), NotaryPro (B2B SaaS $499-1499/mois)
- Presentation: 18 slides HTML interactif + PDF local (NotaryWallet-Presentation.pdf)
- Status: 92% complet, Phase 4 (Launch) en cours

## System optimization (Feb 7, 2026)
- Swappiness réduit à 10 (était 60) — sudo sysctl vm.swappiness=10
- ClamAV désactivé (économise ~1 Go RAM)
- Pour rendre permanent: echo "vm.swappiness=10" | sudo tee -a /etc/sysctl.conf

## User preferences
- Language: French (Quebecois), writes in casual/phonetic French
- Prefers quick execution over discussion
- Wants everything saved locally + GitHub + Vercel always in sync
- Company name: SeoAI (not Croige - Croige is an alias/brand used in documents)
