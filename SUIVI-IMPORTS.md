# SUIVI IMPORTS — AITicketInfo / Ticket911

## Sources de donnees actives

| # | Source | Script | Cron | Volume | Status |
|---|--------|--------|------|--------|--------|
| 1 | CanLII API (jurisprudence) | `import_canlii_traffic.py` | 4AM quotidien | 8,254+ jugements | ACTIF |
| 2 | Donnees ouvertes QC (constats CRQ) | `import_donnees_qc.py --source constats` | hebdo dimanche 2AM | ~356K constats (2012-2022) | A DEPLOYER |
| 3 | Donnees ouvertes QC (radar stats) | `import_donnees_qc.py --source radars` | mensuel 1er 3AM | ~384/mois cumulatif | A DEPLOYER |
| 4 | Donnees ouvertes QC (radar lieux) | `import_donnees_qc.py --source lieux` | mensuel 1er 3:15AM | ~160 emplacements | A DEPLOYER |
| 5 | Donnees ouvertes QC (collisions SAAQ) | `import_donnees_qc.py --source collisions` | hebdo dimanche 2:30AM | ~12 ans CSV S3 | A DEPLOYER |
| 6 | Donnees ouvertes MTL (collisions) | `import_donnees_mtl.py --source collisions` | hebdo dimanche 3AM | ~218K collisions | A DEPLOYER |
| 7 | Donnees ouvertes MTL (escouade) | `import_donnees_mtl.py --source escouade` | hebdo dimanche 3:30AM | ~53K interventions | A DEPLOYER |
| 8 | SOQUIJ RSS (decisions vedettes) | `import_soquij_rss.py` | quotidien 5AM | ~2/semaine (faible) | A DEPLOYER |
| 9 | Google Scholar (case law) | `import_scholar_cases.py` | hebdo samedi 1AM | variable | A DEPLOYER |


## Deploiement VPS OVH

### Etape 1 — Copier les scripts
```bash
# Depuis le poste local
scp -i ~/.ssh/id_ed25519_michael \
  import_donnees_qc.py import_donnees_mtl.py import_soquij_rss.py import_scholar_cases.py \
  ubuntu@148.113.194.234:/var/www/aiticketinfo/
```

### Etape 2 — Cron sur le serveur
```bash
ssh -i ~/.ssh/id_ed25519_michael ubuntu@148.113.194.234

# Editer crontab
crontab -e

# Ajouter ces lignes :
# --- AITicketInfo imports ---
# CanLII (deja en place)
0 4 * * * cd /var/www/aiticketinfo && python3 import_canlii_traffic.py --max-requests 4700 --qc-only >> logs/canlii_import.log 2>&1

# Donnees QC — constats + collisions (dimanche 2AM)
0 2 * * 0 cd /var/www/aiticketinfo && python3 import_donnees_qc.py --source constats >> logs/donnees_qc.log 2>&1
30 2 * * 0 cd /var/www/aiticketinfo && python3 import_donnees_qc.py --source collisions >> logs/donnees_qc.log 2>&1

# Donnees QC — radars (1er du mois 3AM)
0 3 1 * * cd /var/www/aiticketinfo && python3 import_donnees_qc.py --source radars >> logs/donnees_qc.log 2>&1
15 3 1 * * cd /var/www/aiticketinfo && python3 import_donnees_qc.py --source lieux >> logs/donnees_qc.log 2>&1

# Donnees MTL (dimanche 3AM)
0 3 * * 0 cd /var/www/aiticketinfo && python3 import_donnees_mtl.py >> logs/donnees_mtl.log 2>&1

# SOQUIJ RSS (quotidien 5AM)
0 5 * * * cd /var/www/aiticketinfo && python3 import_soquij_rss.py >> logs/soquij_rss.log 2>&1

# Google Scholar (samedi 1AM)
0 1 * * 6 cd /var/www/aiticketinfo && python3 import_scholar_cases.py --max-pages 3 >> logs/scholar.log 2>&1

# Embeddings (apres tous les imports, 6AM)
0 6 * * * cd /var/www/aiticketinfo && python3 embedding_service.py >> logs/embeddings.log 2>&1
```

### Etape 3 — Test dry-run
```bash
# Tester chaque script en dry-run
python3 import_donnees_qc.py --dry-run --source constats
python3 import_donnees_mtl.py --dry-run
python3 import_soquij_rss.py --dry-run
python3 import_scholar_cases.py --dry-run --max-pages 1
```

### Etape 4 — Premier import reel
```bash
# Import initial (peut prendre 30-60 min pour les gros datasets)
python3 import_donnees_qc.py 2>&1 | tee logs/donnees_qc_initial.log
python3 import_donnees_mtl.py 2>&1 | tee logs/donnees_mtl_initial.log
python3 import_soquij_rss.py 2>&1 | tee logs/soquij_rss_initial.log
python3 import_scholar_cases.py --max-pages 5 2>&1 | tee logs/scholar_initial.log
```


## Verification rapide

```bash
# Compter les records par table
psql -h 172.18.0.3 -U ticketdb_user -d tickets_qc_on -c "
SELECT 'jurisprudence' AS t, COUNT(*) FROM jurisprudence
UNION ALL SELECT 'qc_constats', COUNT(*) FROM qc_constats_infraction
UNION ALL SELECT 'qc_radar_stats', COUNT(*) FROM qc_radar_photo_stats
UNION ALL SELECT 'qc_radar_lieux', COUNT(*) FROM qc_radar_photo_lieux
UNION ALL SELECT 'qc_collisions', COUNT(*) FROM qc_collisions_saaq
UNION ALL SELECT 'mtl_collisions', COUNT(*) FROM mtl_collisions
UNION ALL SELECT 'mtl_escouade', COUNT(*) FROM mtl_escouade_mobilite
ORDER BY 1;
"

# Verifier les derniers imports
psql -h 172.18.0.3 -U ticketdb_user -d tickets_qc_on -c "
SELECT source_name, records_inserted, completed_at, status
FROM data_source_log ORDER BY id DESC LIMIT 10;
"

# Verifier jurisprudence par source
psql -h 172.18.0.3 -U ticketdb_user -d tickets_qc_on -c "
SELECT source, COUNT(*) FROM jurisprudence GROUP BY source ORDER BY COUNT(*) DESC;
"
```


## Volumes estimes apres import complet

| Table | Volume estime | Notes |
|-------|--------------|-------|
| `jurisprudence` | ~8,500+ | CanLII + SOQUIJ RSS + Scholar |
| `qc_constats_infraction` | ~356,000 | 11 annees CRQ |
| `qc_radar_photo_stats` | ~384 | Cumulatif derniere periode |
| `qc_radar_photo_lieux` | ~160 | Emplacements actifs |
| `qc_collisions_saaq` | ~500,000+ | 12 annees SAAQ |
| `mtl_collisions` | ~218,000 | 2012-2021 |
| `mtl_escouade_mobilite` | ~53,000 | Interventions |
| **TOTAL** | **~1,135,000+** | |


## APIs et acces

| Source | Type acces | Cle API | Limite |
|--------|-----------|---------|--------|
| CanLII | REST API | CANLII_API_KEY (.env) | 5000 req/jour |
| Donnees QC | CKAN Datastore | Aucune (gratuit) | Illimite |
| Donnees MTL | CKAN Datastore | Aucune (gratuit) | Illimite |
| MTQ WFS | OGC WFS | Aucune (gratuit) | Illimite |
| SAAQ S3 | Download CSV | Aucune (gratuit) | Illimite |
| SOQUIJ RSS | RSS XML | Aucune (gratuit) | ~20 items/feed |
| Google Scholar | Scraping | Aucune | Rate limit ~100/jour |


## Fichiers crees

| Fichier | Lignes | Description |
|---------|--------|-------------|
| `import_donnees_qc.py` | ~350 | Constats, radars, collisions SAAQ |
| `import_donnees_mtl.py` | ~220 | Collisions MTL, escouade mobilite |
| `import_soquij_rss.py` | ~280 | RSS decisions vedettes SOQUIJ |
| `import_scholar_cases.py` | ~380 | Scraper Google Scholar case law |
| `SUIVI-IMPORTS.md` | ce fichier | Documentation et suivi |
