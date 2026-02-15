"""
Configuration pour le systeme d'import tickets_qc_on.
Deploye sur le serveur OVH (148.113.194.234) avec le PostgreSQL Docker existant.
100% PostgreSQL.
"""
import os

# PostgreSQL - Docker container seo-agent-postgres sur le serveur OVH
DB_CONFIG = {
    'host': os.environ.get('TICKETS_DB_HOST', '172.18.0.3'),
    'port': int(os.environ.get('TICKETS_DB_PORT', 5432)),
    'dbname': os.environ.get('TICKETS_DB_NAME', 'tickets_qc_on'),
    'user': os.environ.get('TICKETS_DB_USER', 'ticketdb_user'),
    'password': os.environ.get('TICKETS_DB_PASS', 'Tk911PgSecure2026'),
}

# CanLII API - cle gratuite via https://www.canlii.org/en/feedback/feedback.html
CANLII_API_KEY = os.environ.get('CANLII_API_KEY', '9yC9kEpzDu4DLkhrkFtwmavjLi9RBqxm5Vp7wTxP')

# Fireworks AI - pour enrichissement futur
FIREWORKS_API_KEY = os.environ.get('FIREWORKS_API_KEY', '')

# URLs de base des APIs
DONNEES_QC_BASE = 'https://www.donneesquebec.ca/recherche/api/3/action'
MONTREAL_BASE = 'https://data.montreal.ca/api/3/action'
CANLII_BASE = 'https://api.canlii.org/v1'

# Rate limiting
REQUEST_DELAY = 0.5       # secondes entre requetes (CKAN)
CANLII_DELAY = 1.0        # secondes entre requetes CanLII (respecter leurs limites)
MAX_RETRIES = 3

# Limites d'import
CKAN_BATCH_SIZE = 32000   # records par requete CKAN
CANLII_BATCH_SIZE = 100   # decisions par requete CanLII
CANLII_MAX_PER_DB = 50000 # max decisions par tribunal (qccq et oncj en ont 20K-40K+)

# Logging
LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'import.log')
