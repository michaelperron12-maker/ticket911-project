# Serveur OVH — Guide complet SeoAI

> Dernière mise à jour: 15 février 2026
> Développeur: Michael Perron (SeoAI) — michaelperron12@gmail.com — 514-609-2882

---

## 1. Informations du serveur

| Paramètre | Valeur |
|-----------|--------|
| **Nom VPS** | vps-ea59a047.vps.ovh.ca |
| **IPv4** | 148.113.194.234 |
| **IPv6** | 2607:5300:205:200::778f |
| **Utilisateur** | ubuntu |
| **OS** | Ubuntu 24.04 |
| **Python** | 3.13.7 |
| **Node.js** | v20.20.0 |
| **Disque** | 72 Go (48 Go utilisés, 24 Go libre — 67%) |
| **RAM** | 7.6 Go (~46% utilisé, swappiness=10) |
| **SSL** | Let's Encrypt (certbot, renouvellement auto) |

---

## 2. Architecture SeoAI

```
┌─────────────────────────────────────────────────────┐
│              SeoAI Platform (seoparai.com)           │
│              Serveur OVH 148.113.194.234             │
│                  Ubuntu 24.04 / 7.6GB                │
├─────────────────────────────────────────────────────┤
│                                                       │
│  🧠 62 Agents AI (SEO, audit, content, backlinks...) │
│  📊 Dashboard (seoparai.com/dashboard, NIP 8985777)  │
│  🛡️ Sécurité (Fail2ban, CrowdSec, UFW, headers)     │
│  📡 Monitoring (Uptime Kuma 6 monitors, Netdata)      │
│  💾 Backups auto (quotidien 2AM, 30j rotation)        │
│  🔍 Audits auto (Lynis hebdo, testssl mensuel)        │
│  📧 Email alerts (Postfix → michaelperron12@gmail)    │
│                                                       │
├──────────── CLIENTS (bénéficient de tout) ───────────┤
│                                                       │
│  1. jcpeintre.com          (peinture)                 │
│  2. deneigement-excellence.ca  (déneigement)          │
│  3. paysagiste-excellence.ca   (paysagement)          │
│  + facturation.deneigement-excellence.ca              │
│                                                       │
│  🎯 Objectif: 100 clients payants                     │
│                                                       │
├──────────── PRODUIT SÉPARÉ ──────────────────────────┤
│                                                       │
│  🎫 AITicketInfo (seoparai.com/scanticket/)            │
│     38 agents AI, Flask port 8912, PostgreSQL          │
│                                                       │
└─────────────────────────────────────────────────────┘
```

---

## 3. Connexion SSH

### Étape 1 — Se connecter
```bash
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234
```

### Avec le nom de domaine (alternatif)
```bash
ssh -i ~/.ssh/id_ed25519_michael ubuntu@vps-ea59a047.vps.ovh.ca
```

### Clé SSH
- Fichier local: `~/.ssh/id_ed25519_michael`
- Si la connexion coupe: attendre 5 secondes et réessayer
- Ne pas chaîner trop de commandes `sudo` (SSH instable)

### Ajouter une nouvelle clé SSH
```bash
ssh-copy-id -i ~/.ssh/ma_nouvelle_cle.pub ubuntu@148.113.194.234
```

---

## 4. Accès rapides

| Quoi | URL | Identifiants |
|------|-----|-------------|
| **SeoAI Landing** | `https://seoparai.com` | — |
| **SeoAI Dashboard** | `https://seoparai.com/dashboard` | NIP: `8985777` |
| **Dashboard Login** | `https://seoparai.com/dashboard-login` | NIP: `8985777` |
| **AITicketInfo** | `https://seoparai.com/scanticket/` | — |
| **Uptime Kuma** | `https://seoparai.com:3011` | `admin` / `SeoAI2026!` |
| **Netdata** | SSH tunnel → `localhost:19999` | — |
| **JC Peintre** | `https://jcpeintre.com` | — |
| **Déneigement** | `https://deneigement-excellence.ca` | — |
| **Paysagiste** | `https://paysagiste-excellence.ca` | — |
| **Facturation** | `https://facturation.deneigement-excellence.ca` | — |

---

## 5. Tous les sites hébergés

| # | Site | Domaine | Dossier | Port | SSL | Stack |
|---|------|---------|---------|------|-----|-------|
| 1 | **SeoAI Dashboard** | seoparai.com | `/var/www/dashboard/` | 8002, 8888, 8893, 8895 | Oui | Python + 62 agents AI |
| 2 | **AITicketInfo** | seoparai.com/scanticket/ | `/var/www/aiticketinfo/` | 8912 | Oui (via seoparai.com) | Flask + 38 agents AI + PostgreSQL |
| 3 | **Déneigement** | deneigement-excellence.ca | `/var/www/deneigement/` | — | Oui | HTML statique |
| 4 | **Paysagement** | paysagiste-excellence.ca | `/var/www/paysagement/` | 3001 | Oui | Node.js |
| 5 | **JC Peintre** | jcpeintre.com | `/var/www/jcpeintre.com/` | 3002 | Oui | Python + dashboard |
| 6 | **Facturation** | facturation.deneigement-excellence.ca | `/var/www/facturation/` | 8001 | Oui | Python |

---

## 6. Services systemd (18 actifs)

| Service | Description | Port |
|---------|-------------|------|
| `seo-api.service` | SEO AI API Server (62 agents) | 8002 |
| `seo-scanner.service` | SEO Scanner API | 8893 |
| `seo-killswitch.service` | SEO AI Killswitch Controller | 8888 |
| `seo-agent.service` | SEO Agent Scheduler | — |
| `seo-scheduler.service` | SEO AI Master Scheduler (24/7) | — |
| `seo-audit.service` | SEO AI Site Audit Agent | — |
| `chatbot.service` | SEO par AI Chatbot API | 8895 |
| `aiticketinfo.service` | AITicketInfo Flask API (38 agents AI) | 8912 |
| `facturation.service` | Facturation Multi-Services | 8001 |
| `security-status.service` | API sécurité pour dashboard | 8919 (local) |
| `ollama.service` | Ollama (LLM local) | 11434 |
| `nginx.service` | Nginx reverse proxy | 80, 443, 3011 |
| `postfix.service` | Postfix mail (SMTP) | 25 |
| `fail2ban.service` | Fail2Ban (5 jails: sshd + 4 nginx) | — |
| `crowdsec.service` | CrowdSec (protection communautaire) | 8180 (local) |
| `netdata.service` | Netdata (monitoring serveur) | 19999 (local) |
| `docker.service` | Docker (Uptime Kuma, n8n, Postgres) | — |
| `pm2-ubuntu.service` | PM2 (paysagement Node.js) | 3001 |

### Docker (3 containers)
| Container | Port | Rôle |
|-----------|------|------|
| `uptime-kuma` | 3010 → nginx 3011 (SSL) | Monitoring uptime + email alerts |
| `seo-agent-n8n` | 5678 | Automation workflows |
| `seo-agent-postgres` | 5432 | Base PostgreSQL (tickets_qc_on: 19 tables, 8K+ juris QC) |

### Commandes de base pour les services
```bash
# Voir le status d'un service
sudo systemctl status nom_du_service

# Redémarrer un service
sudo systemctl restart nom_du_service

# Voir les logs d'un service
sudo journalctl -u nom_du_service --no-pager -n 50

# Activer au démarrage
sudo systemctl enable nom_du_service
```

---

## 7. Bases de données

| Base | Emplacement | Taille | Tables | Contenu |
|------|-------------|--------|--------|---------|
| **seo_agent.db** | `/opt/seo-agent/db/` | 22M | 150 | DB principale SeoAI (agents, sites, keywords, etc.) |
| **seo_brain.db** | `/opt/seo-agent/db/` | 132K | — | AI cerveau |
| **tickets_qc_on** (PostgreSQL) | Docker `seo-agent-postgres` | ~3 Go | 19+ | 8,321 juris QC, 1.7M accidents SAAQ, 356K constats, lois, radar, SAAQ points, conditions routières |
| **facturation.db** | `/var/www/facturation/` | 252K | 12 | 7 factures |
| **jcpeintre.db** | `/var/www/jcpeintre.com/data/` | 168K | — | Données JC Peintre |
| **sessions.db** | `/var/www/dashboard/` | 36K | 5 | Sessions dashboard |
| **ChromaDB** | `/var/www/aiticketinfo/data/` | 9.3M | — | Embeddings jurisprudence |
| **Uptime Kuma** | Docker volume | — | — | 6 monitors, heartbeats |

### Vérifier l'intégrité des DBs SQLite
```bash
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "for db in /var/www/facturation/facturation.db /var/www/jcpeintre.com/data/jcpeintre.db /opt/seo-agent/db/seo_agent.db; do echo \"\$(basename \$db): \$(sqlite3 \$db 'PRAGMA integrity_check;')\"; done"
```

### Vérifier PostgreSQL (AITicketInfo)
```bash
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "docker exec seo-agent-postgres psql -U ticketdb_user -d tickets_qc_on -c \"SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;\""
```

### Stats rapides PostgreSQL
```bash
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "docker exec seo-agent-postgres psql -U ticketdb_user -d tickets_qc_on -c \"SELECT 'jurisprudence QC' as table_name, count(*) FROM jurisprudence WHERE province='QC' UNION ALL SELECT 'saaq_points', count(*) FROM saaq_points_inaptitude UNION ALL SELECT 'conditions_routieres', count(*) FROM conditions_routieres_hiver;\""
```

---

## 8. AITicketInfo — Guide complet (anciennement Ticket911)

> **Note**: Le projet a été renommé de `ticket911` à `aiticketinfo` et migré de SQLite à PostgreSQL (fév 2026).

### Architecture
```
Client → https://seoparai.com/scanticket/
         ↓ nginx (port 443, SSL)
         ↓ proxy_pass → localhost:8912
         ↓ Flask (api.py)
         ↓ 38 agents AI (Fireworks, 12 modèles)
         ↓ PostgreSQL (Docker seo-agent-postgres) + ChromaDB
         → Résultat + PDF WeasyPrint
```

### Base de données PostgreSQL
```
Container: seo-agent-postgres (Docker)
Database:  tickets_qc_on
User:      ticketdb_user
Host:      172.18.0.3:5432
Tables:    19 tables

Tables principales:
├── saaq_rapports_accident     # 1,717,407 rapports accident (2011-2022)
├── qc_constats_infraction     # 356,715 constats Contrôle routier QC
├── jurisprudence              # 8,321+ dossiers QC (CanLII, import auto quotidien 4AM)
├── lois_articles              # 4,588 lois QC + ON
├── saaq_points_inaptitude     # 22 infractions, points/amendes
├── saaq_seuils_points         # 5 seuils (probatoire, apprenti, régulier)
├── conditions_routieres_hiver # 446 segments MTQ temps réel
├── qc_radar_photo_stats       # 384 stats radar
├── qc_radar_photo_lieux       # 160 emplacements
├── mtl_collisions             # 218K+ collisions Montréal
├── road_conditions            # Conditions routières
└── speed_limits               # Limites de vitesse
```

### Fichiers serveur
```
/var/www/aiticketinfo/
├── api.py                         # API Flask principale (port 8912)
├── scanner.html                   # Frontend landing page
├── .env                           # Variables d'environnement (clés API)
├── agents/                        # 38 agents AI
│   ├── agent_canlii_updater.py    # Import auto CanLII quotidien (4AM)
│   └── ...
├── db/                            # État et metadata
├── data/                          # ChromaDB embeddings
├── logs/                          # Logs d'analyse + canlii_usage.json
├── import_canlii_traffic.py       # Import CanLII (rate limit 4700/jour, 5 tribunaux QC)
├── import_conditions_routieres.py # Import MTQ conditions routières hiver
├── import_saaq_accidents.py       # Import rapports accident SAAQ (2011-2022)
├── seed_saaq_points.py            # Seed SAAQ points d'inaptitude
├── populate_chromadb.py           # Population ChromaDB
└── setup_database.py              # Création tables PostgreSQL
```

### Fichiers locaux
```
/home/serinityvault/Desktop/projet web/aiticketinfo/
```

### GitHub
```
Repo principal: michaelperron12-maker/ticket911-project
Repo demo:      michaelperron12-maker/ticket911-demo
Vercel demo:    https://911-virid.vercel.app
```

### Services systemd
| Service | Description |
|---------|-------------|
| `aiticketinfo.service` | Flask API principale (port 8912) |
| `canlii-updater.service` | Import CanLII auto (quotidien 4AM, QC seulement) |

### Commandes AITicketInfo

#### Vérifier si ça roule
```bash
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "sudo systemctl status aiticketinfo"
```

#### Redémarrer
```bash
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "sudo systemctl restart aiticketinfo"
```

#### Voir les logs
```bash
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "sudo journalctl -u aiticketinfo --no-pager -n 100"
```

#### Tester l'API
```bash
curl -s https://seoparai.com/scanticket/api/health | python3 -m json.tool
```

#### Vérifier la DB PostgreSQL
```bash
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "docker exec seo-agent-postgres psql -U ticketdb_user -d tickets_qc_on -c \"SELECT database_id, count(*) FROM jurisprudence WHERE province='QC' GROUP BY database_id ORDER BY count(*) DESC;\""
```

#### Vérifier le quota CanLII
```bash
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "cat /var/www/aiticketinfo/logs/canlii_usage.json"
```

#### Logs import CanLII
```bash
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "tail -50 /var/www/aiticketinfo/logs/canlii_import.log"
```

#### Déployer scanner.html
```bash
scp -i ~/.ssh/id_ed25519_michael "/home/serinityvault/Desktop/projet web/aiticketinfo/scanner.html" ubuntu@148.113.194.234:/tmp/ && \
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "sudo cp /tmp/scanner.html /var/www/aiticketinfo/scanner.html && sudo chown ubuntu:ubuntu /var/www/aiticketinfo/scanner.html"
```

#### Déployer api.py + redémarrer
```bash
scp -i ~/.ssh/id_ed25519_michael "/home/serinityvault/Desktop/projet web/aiticketinfo/api.py" ubuntu@148.113.194.234:/tmp/ && \
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "sudo cp /tmp/api.py /var/www/aiticketinfo/api.py && sudo chown ubuntu:ubuntu /var/www/aiticketinfo/api.py && sudo systemctl restart aiticketinfo"
```

#### Déployer les agents
```bash
scp -i ~/.ssh/id_ed25519_michael -r "/home/serinityvault/Desktop/projet web/aiticketinfo/agents" ubuntu@148.113.194.234:/tmp/ && \
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "sudo cp -r /tmp/agents/* /var/www/aiticketinfo/agents/ && sudo chown -R ubuntu:ubuntu /var/www/aiticketinfo/agents/ && sudo systemctl restart aiticketinfo"
```

### APIs configurées
| Clé | Usage | Status |
|-----|-------|--------|
| `CANLII_API_KEY` | Jurisprudences CanLII (4700 req/jour) | **Actif** |
| `MINDEE_API_KEY` | OCR tickets (lecture automatique) | **Actif** |
| `FIREWORKS_API_KEY` | 12 modèles AI (agents) | **Actif** |
| `SMTP_PASS` | Email alert@seoparai.com | En attente |
| `TWILIO` | SMS notifications | Optionnel |
| `SENDGRID` | Email marketing | Optionnel |

### Sources de données intégrées
| Source | API | Données | Fréquence |
|--------|-----|---------|-----------|
| CanLII | REST API (clé) | Jurisprudence QC traffic (5 tribunaux: qccm, qccq, qccs, qcca, qctaq) | Auto quotidien 4AM |
| MTQ/Données Québec | WFS (gratuit) | Conditions routières hiver (446 segments) | Manuel/cron |
| SAAQ | Données hardcodées | Points d'inaptitude (22), seuils (5) | Statique (seed) |
| SAAQ/Données Québec | CSV (gratuit) | 1.7M rapports accident (2011-2022) | Importé |
| SAAQ/Données Québec | CKAN (gratuit) | 356K constats Contrôle routier | Importé |
| Données Québec | CKAN (gratuit) | Radar, collisions MTL | Importé |

---

## 9. SeoAI Dashboard (seoparai.com)

### Accès
- URL: `https://seoparai.com/dashboard`
- NIP: `8985777`
- Login: `https://seoparai.com/dashboard-login`

### Sections du dashboard
| Section | Description |
|---------|-------------|
| Dashboard | Vue d'ensemble des 4 sites clients |
| Command Center | Centre de commande des agents |
| Alertes | Alertes actives |
| Sites (4) | Déneigement, Paysagement, JC Peintre, SEO par AI |
| Mots-clés | Recherche et tracking keywords |
| Contenu | Gestion de contenu AI |
| Audit | Audit SEO des sites |
| Backlinks | Gestion des backlinks |
| Reports | Rapports SEO |
| 62 Agents | Tous les agents AI |
| Scheduler | Planificateur automatique |
| Auto-Fix | Correction SEO automatique |
| **Sécurité** | **Monitoring temps réel (NOUVEAU)** |
| Serveur | CPU, RAM, disque |

### Section Sécurité (NOUVEAU — 11 fév 2026)
- API: `/api/security-status` (port 8919, service `security-status.service`)
- Affiche en temps réel:
  - Status de tous les services (5 services + 3 containers)
  - IPs bloquées (Fail2ban + CrowdSec combinés)
  - 6 monitors Uptime avec ping en ms
  - Certificats SSL (jours restants)
  - Dernier backup (date + taille)
  - Score Lynis
  - RAM et disque en %
  - Détails des 5 jails Fail2ban

---

## 10. Nginx — Commandes

### Tester la configuration
```bash
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "sudo nginx -t"
```

### Recharger sans couper (recommandé)
```bash
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "sudo systemctl reload nginx"
```

### Voir les logs d'erreur
```bash
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "sudo tail -50 /var/log/nginx/error.log"
```

### Lister les configs actives
```bash
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "ls /etc/nginx/sites-enabled/"
```

### Configs nginx importantes
| Fichier | Rôle |
|---------|------|
| `/etc/nginx/sites-enabled/seoparai.com` | Site principal + APIs + AITicketInfo |
| `/etc/nginx/sites-enabled/uptime-kuma` | Uptime Kuma SSL (port 3011) |
| `/etc/nginx/sites-enabled/deneigement-excellence.ca` | Déneigement |
| `/etc/nginx/sites-enabled/paysagiste-excellence.ca` | Paysagement |
| `/etc/nginx/sites-enabled/jcpeintre.com` | JC Peintre |
| `/etc/nginx/sites-enabled/facturation` | Facturation |
| `/etc/nginx/conf.d/security-headers.conf` | Headers sécurité (global) |
| `/etc/nginx/conf.d/seoai-hardening.conf` | Gzip compression (global) |
| `/etc/nginx/conf.d/seoai-rate-limiting.conf` | Rate limiting (global) |
| `/etc/nginx/snippets/seoai-deny-sensitive.conf` | Block .bak/.git/.env (global) |

---

## 11. SSL — Certificats Let's Encrypt

| Domaine | Expiration | Jours restants |
|---------|------------|----------------|
| seoparai.com + www | 9 mai 2026 | 83 jours |
| jcpeintre.com + www | 4 mai 2026 | 78 jours |
| deneigement-excellence.ca + www | 4 mai 2026 | 78 jours |
| paysagiste-excellence.ca + www | 5 mai 2026 | 79 jours |
| facturation.deneigement-excellence.ca | 4 mai 2026 | 78 jours |

### Renouveler manuellement (normalement auto)
```bash
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "sudo certbot renew --dry-run"
```

### Ajouter un nouveau domaine SSL
```bash
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "sudo certbot --nginx -d nouveau-domaine.com -d www.nouveau-domaine.com"
```

---

## 12. Sécurité — Configuration complète (11 fév 2026)

### Firewall UFW
```
Ports ouverts: 22 (SSH), 80 (HTTP), 443 (HTTPS), 3011 (Uptime Kuma)
Tout le reste: fermé (deny par défaut)
```

### Nginx hardening (global, tous les sites)
| Protection | Fichier |
|-----------|---------|
| `server_tokens off` | `/etc/nginx/nginx.conf` |
| Security headers (HSTS, CSP, Referrer, Permissions) | `/etc/nginx/conf.d/security-headers.conf` |
| Gzip compression | `/etc/nginx/conf.d/seoai-hardening.conf` |
| Rate limiting (API: 10r/s, Login: 3r/s) | `/etc/nginx/conf.d/seoai-rate-limiting.conf` |
| Block .bak/.git/.env/.db/-admin | `/etc/nginx/snippets/seoai-deny-sensitive.conf` |
| HTTP/2 | Activé dans chaque site SSL |

### Outils de sécurité automatiques
| Outil | Rôle | Fréquence |
|-------|------|-----------|
| Fail2ban | Brute-force protection (5 jails: sshd, nginx-badbots, nginx-botsearch, nginx-http-auth, nginx-noscript) | Permanent 24/7 |
| CrowdSec | Protection communautaire + nginx bouncer | Permanent 24/7 |
| UFW Firewall | Bloque tout sauf 22/80/443/3011 | Permanent |
| Rate Limiting | Bloque spam API (10r/s) et login (3r/s) | Permanent |
| Security Headers | HSTS, CSP, Referrer-Policy, Permissions-Policy | Chaque requête |
| Uptime Kuma | Check 6 sites toutes les 60s + email alert si down | Permanent 24/7 |
| Netdata | Monitoring CPU/RAM/disque/réseau | Permanent 24/7 |
| Backup auto | Sites + DBs + nginx + systemd + .env | Quotidien 2AM (rotation 30j) |
| Lynis | Audit sécurité système complet | Lundi 3AM |
| testssl.sh | Audit SSL tous les domaines | 1er du mois 4AM |
| Logrotate | Rotation des logs tous services | Automatique |

### Fichiers de sécurité
```
/opt/seo-agent/security/
├── backup.sh              # Script backup quotidien
├── lynis-audit.sh         # Script audit Lynis hebdomadaire
├── ssl-audit.sh           # Script audit SSL mensuel
├── security_status.py     # API status sécurité (port 8919)
├── last-audit.json        # Résultat dernier audit Lynis
└── last-backup.json       # Résultat dernier backup
```

### Crons automatiques
```
/etc/cron.d/seoai-backup      → 0 2 * * *   (quotidien 2AM)
/etc/cron.d/seoai-lynis-audit  → 0 3 * * 1   (lundi 3AM)
/etc/cron.d/seoai-ssl-audit    → 0 4 1 * *   (1er du mois 4AM)
```

### Fail2ban config
```
/etc/fail2ban/jail.d/seoai-nginx.conf  → 4 jails nginx
```

### CrowdSec config
```
/etc/crowdsec/acquis.d/nginx.yaml      → Acquisition logs nginx
Port API: 8180 (localhost seulement)
Collections: nginx, sshd, postfix
```

---

## 13. Monitoring et diagnostic

### Commandes rapides
```bash
# Espace disque
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "df -h /"

# Mémoire RAM
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "free -h"

# Processus gourmands
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "ps aux --sort=-%mem | head -15"

# Uptime et charge
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "uptime"

# Tous les ports en écoute
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "sudo ss -tlnp | grep LISTEN"

# Tous les services actifs
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "systemctl list-units --type=service --state=active | grep -E 'seo|ticket|chatbot|facturation|nginx|fail2ban|crowdsec|netdata'"

# Docker containers
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "docker ps"
```

### Vérifier la sécurité
```bash
# Fail2ban status
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "sudo fail2ban-client status"

# CrowdSec décisions
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "sudo cscli decisions list"

# API sécurité (tout en un)
curl -s https://seoparai.com/api/security-status | python3 -m json.tool

# Dernier audit Lynis
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "cat /opt/seo-agent/security/last-audit.json"

# Dernier backup
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "cat /opt/seo-agent/security/last-backup.json"
```

### Uptime Kuma (monitoring web)
- URL: `https://seoparai.com:3011`
- Username: `admin`
- Password: `SeoAI2026!`
- 6 monitors (check 60s): seoparai.com, jcpeintre.com, deneigement, paysagiste, aiticketinfo, facturation
- Email alerts: `michaelperron12@gmail.com` (via Postfix localhost)

### Netdata (dashboard serveur via SSH tunnel)
```bash
ssh -i ~/.ssh/id_ed25519_michael -L 19999:localhost:19999 ubuntu@148.113.194.234
# Puis ouvrir http://localhost:19999 dans le navigateur
```

---

## 14. Déploiement — Sites statiques

### Copier un fichier
```bash
scp -i ~/.ssh/id_ed25519_michael fichier.html ubuntu@148.113.194.234:/var/www/deneigement/
```

### Copier un dossier
```bash
scp -i ~/.ssh/id_ed25519_michael -r dossier/ ubuntu@148.113.194.234:/var/www/deneigement/
```

### Permissions des fichiers web
```bash
# Sites statiques (nginx sert directement)
sudo chown -R www-data:www-data /var/www/deneigement/
sudo chmod -R 755 /var/www/deneigement/

# AITicketInfo (Flask tourne sous ubuntu)
sudo chown -R ubuntu:ubuntu /var/www/aiticketinfo/
sudo chmod -R 755 /var/www/aiticketinfo/
```

---

## 15. Docker (Uptime Kuma + n8n + Postgres)

```bash
# Voir les containers Docker
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "docker ps"

# Logs Uptime Kuma
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "docker logs --tail 50 uptime-kuma"

# Logs n8n
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "docker logs --tail 50 seo-agent-n8n"

# Redémarrer Uptime Kuma
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "docker restart uptime-kuma"
```

---

## 16. Backups

### Backup automatique (quotidien 2AM)
```
Script: /opt/seo-agent/security/backup.sh
Contenu: sites + DBs + nginx + systemd + .env
Stockage: /opt/seo-agent/backups/
Rotation: 30 jours
Dernier: 621M (11 fév 2026)
```

### Vérifier le dernier backup
```bash
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "cat /opt/seo-agent/security/last-backup.json && ls -lh /opt/seo-agent/backups/"
```

### Backup PostgreSQL (AITicketInfo)
```bash
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "docker exec seo-agent-postgres pg_dump -U ticketdb_user tickets_qc_on > /tmp/tickets_qc_on-\$(date +%Y%m%d).sql"
```

### Télécharger le dump PostgreSQL en local
```bash
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "docker exec seo-agent-postgres pg_dump -U ticketdb_user tickets_qc_on" > "/home/serinityvault/Desktop/projet web/aiticketinfo/db/tickets_qc_on-backup-$(date +%Y%m%d).sql"
```

---

## Demarrage Rapide — Toujours Partir sur le Bon Pied

### Etape 0 — Aller dans le dossier de scripts
```bash
cd ~/Desktop/projet\ web/sync-serveur/
```

### Etape 1 — Health check (tout va bien ?)
```bash
./seo-agents.sh health
```
> Verifie: APIs, services, Docker, DBs. Si tout est vert → on peut travailler.

### Etape 2 — Backup avant de toucher a quoi que ce soit
```bash
./seo-agents.sh db-backup
```
> Telecharge seo_agent.db, ticket911.db, facturation.db en local dans ~/Desktop/projet web/backups/

### Etape 3 — Coder en local, puis sync
```bash
# Simuler d'abord (voir ce qui changerait)
./sync.sh deneigement --dry-run

# Si OK, sync pour vrai
./sync.sh deneigement

# Ou sync tout d'un coup
./sync.sh all
```

### Etape 4 — Verifier apres deploiement
```bash
./seo-agents.sh health
```

---

## Scripts SeoAI (dossier sync-serveur/)

### sync.sh — Synchronisation intelligente

| Commande | Description |
|----------|-------------|
| `./sync.sh` | Affiche l'aide et les sites disponibles |
| `./sync.sh deneigement` | Sync deneigement local → serveur |
| `./sync.sh seo-ai` | Sync les agents SEO local → serveur |
| `./sync.sh aiticketinfo` | Sync AITicketInfo local → serveur |
| `./sync.sh all` | Sync tous les 7 sites |
| `./sync.sh all --dry-run` | Simuler sans copier |
| `./sync.sh seo-ai --reverse` | Telecharger du serveur → local |
| `./sync.sh deneigement --watch` | Sync auto a chaque modification |
| `./sync.sh seo-ai --force` | Inclure les fichiers .db |

Sites disponibles: `deneigement`, `paysagement`, `jcpeintre`, `facturation`, `seo-ai`, `aiticketinfo`, `dashboard`

### seo-agents.sh — Controle des 62 Agents SEO

#### Monitoring
| Commande | Description |
|----------|-------------|
| `./seo-agents.sh health` | Health check complet (APIs + services + DBs) |
| `./seo-agents.sh status` | Status de tous les services SEO |
| `./seo-agents.sh agents` | Lister les 62 agents et leur etat |
| `./seo-agents.sh server` | Infos serveur (CPU, RAM, disque) |
| `./seo-agents.sh security` | Fail2ban, CrowdSec, SSL |

#### Taches SEO (site_id: 1=deneigement, 2=paysagement, 3=jcpeintre, 4=seoparai)
| Commande | Description |
|----------|-------------|
| `./seo-agents.sh audit 1` | Audit SEO de deneigement |
| `./seo-agents.sh content 3 "peintre montreal"` | Generer un article SEO |
| `./seo-agents.sh keywords 2` | Recherche de mots-cles paysagement |
| `./seo-agents.sh report 1` | Rapport SEO hebdomadaire |
| `./seo-agents.sh positions` | Positions Google de tous les sites |

#### Services
| Commande | Description |
|----------|-------------|
| `./seo-agents.sh logs seo-api` | Logs d'un service (50 dernieres lignes) |
| `./seo-agents.sh restart aiticketinfo` | Redemarrer un service |
| `./seo-agents.sh restart-all` | Redemarrer tous les services SEO |

#### Bases de donnees
| Commande | Description |
|----------|-------------|
| `./seo-agents.sh db-status` | Taille, tables, integrite de toutes les DBs |
| `./seo-agents.sh db-query "SELECT COUNT(*) FROM keywords"` | Requete SQL directe |
| `./seo-agents.sh db-backup` | Backup de toutes les DBs en local |

---

## Claude Agent Teams — Templates

Templates prets a l'emploi dans `~/Documents/prompts-agent-teams/` :

| Fichier | Usage |
|---------|-------|
| `01-quand-utiliser.md` | Quand utiliser Agent Teams vs Solo vs Subagent |
| `02-template-code-review.md` | Code review multi-angle (securite, perf, tests) |
| `03-template-feature-build.md` | Construire une feature full-stack en parallele |
| `04-template-refactoring.md` | Refactoring avec tests continus |
| `05-template-debug.md` | Investigation de bugs multi-hypotheses |
| `06-template-qa.md` | QA / tests d'une app |
| `07-bonnes-pratiques.md` | Regles et optimisations Agent Teams |
| `08-template-seoai-audit.md` | **Audit SEO des 4 sites clients en parallele** |
| `09-template-seoai-content.md` | **Generation contenu + keywords + backlinks** |
| `10-template-seoai-maintenance.md` | **Maintenance hebdo/mensuelle serveur** |

### Utiliser dans Claude Code
```bash
claude --model claude-opus-4-6
# Puis copier-coller un template et adapter les parametres
```

---

## Checklist Hebdomadaire

```
[ ] ./seo-agents.sh health              → Tout est vert ?
[ ] ./seo-agents.sh db-backup           → Backup des DBs
[ ] ./seo-agents.sh security            → Pas de breche ?
[ ] ./seo-agents.sh audit 1             → Audit deneigement
[ ] ./seo-agents.sh audit 2             → Audit paysagement
[ ] ./seo-agents.sh audit 3             → Audit jcpeintre
[ ] ./seo-agents.sh positions           → Positions Google OK ?
[ ] ./seo-agents.sh report 1            → Rapport deneigement
[ ] ./seo-agents.sh report 2            → Rapport paysagement
[ ] ./seo-agents.sh report 3            → Rapport jcpeintre
[ ] ./sync.sh all --dry-run             → Des changements a sync ?
```

---

## Aide-memoire rapide

```bash
# Alias recommandes a ajouter dans ~/.bashrc local:
alias ovh='ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234'
alias ovh-ati='ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "sudo systemctl status aiticketinfo"'
alias ovh-logs='ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234 "sudo journalctl -u aiticketinfo -f"'
alias ovh-sec='curl -s https://seoparai.com/api/security-status | python3 -m json.tool'

# Nouveaux alias pour les scripts:
alias seo-sync='cd ~/Desktop/projet\ web/sync-serveur/ && ./sync.sh'
alias seo-agents='cd ~/Desktop/projet\ web/sync-serveur/ && ./seo-agents.sh'
alias seo-health='cd ~/Desktop/projet\ web/sync-serveur/ && ./seo-agents.sh health'
alias seo-backup='cd ~/Desktop/projet\ web/sync-serveur/ && ./seo-agents.sh db-backup'
```

### Installer les alias
```bash
# Copier-coller dans le terminal:
cat >> ~/.bashrc << 'EOF'

# === SeoAI Shortcuts ===
alias ovh='ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234'
alias seo-sync='cd ~/Desktop/projet\ web/sync-serveur/ && ./sync.sh'
alias seo-agents='cd ~/Desktop/projet\ web/sync-serveur/ && ./seo-agents.sh'
alias seo-health='cd ~/Desktop/projet\ web/sync-serveur/ && ./seo-agents.sh health'
alias seo-backup='cd ~/Desktop/projet\ web/sync-serveur/ && ./seo-agents.sh db-backup'
EOF
source ~/.bashrc
```

Apres ca, depuis n'importe ou dans le terminal:
```bash
seo-health                              # Health check
seo-sync deneigement                    # Sync un site
seo-agents audit 1                      # Audit SEO
seo-backup # Backup DBs
```
https://keepersecurity.ca/vault/share/#PHcvlI3Mm1E19CH_8rfSQBoCUwEMO3tcg6K2aI201qg/lang/fr_FR
---
9yC9kEpzDu4DLkhrkFtwmavjLi9RBqxm5Vp7wTxP api canlii
*Document maintenu par SeoAI — Michael Perron*
*Derniere mise a jour: 15 fevrier 2026*
