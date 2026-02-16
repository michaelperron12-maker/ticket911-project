-- ============================================================
-- BASE DE DONNEES : tickets_qc_on
-- Agregation donnees publiques tickets QC + ON
-- PostgreSQL avec tsvector + GIN pour recherche plein texte
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- LOG DES IMPORTS
-- ============================================================
CREATE TABLE IF NOT EXISTS data_source_log (
    id SERIAL PRIMARY KEY,
    source_name VARCHAR(100) NOT NULL,
    source_url TEXT,
    module_name VARCHAR(50),
    records_fetched INTEGER DEFAULT 0,
    records_inserted INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'running',
    error_message TEXT,
    metadata JSONB
);

-- ============================================================
-- QUEBEC : CONSTATS D'INFRACTION (Controle routier QC)
-- Source : donneesquebec.ca - SAAQ
-- Dataset ID : 6b794b52-c074-4064-bfb4-61a9e1fc2d6f
-- ============================================================
CREATE TABLE IF NOT EXISTS qc_constats_infraction (
    id SERIAL PRIMARY KEY,
    annee_donnees INTEGER,
    date_infraction DATE,
    heure_infraction TIME,
    region VARCHAR(100),
    lieu_infraction TEXT,
    type_intervention VARCHAR(100),
    loi VARCHAR(200),
    reglement VARCHAR(200),
    article VARCHAR(50),
    description_infraction TEXT,
    vitesse_permise INTEGER,
    vitesse_constatee INTEGER,
    montant_amende NUMERIC(10,2),
    points_inaptitude INTEGER,
    categorie_vehicule VARCHAR(100),
    raw_data JSONB,
    source_resource_id VARCHAR(100),
    imported_at TIMESTAMP DEFAULT NOW(),
    -- tsvector pour recherche plein texte
    tsv tsvector GENERATED ALWAYS AS (
        to_tsvector('french', COALESCE(description_infraction,'') || ' ' || COALESCE(lieu_infraction,'') || ' ' || COALESCE(region,''))
    ) STORED
);

CREATE INDEX IF NOT EXISTS idx_qc_constats_date ON qc_constats_infraction(date_infraction);
CREATE INDEX IF NOT EXISTS idx_qc_constats_article ON qc_constats_infraction(article);
CREATE INDEX IF NOT EXISTS idx_qc_constats_region ON qc_constats_infraction(region);
CREATE INDEX IF NOT EXISTS idx_qc_constats_annee ON qc_constats_infraction(annee_donnees);
CREATE INDEX IF NOT EXISTS idx_qc_constats_vitesse ON qc_constats_infraction(vitesse_permise, vitesse_constatee);
CREATE INDEX IF NOT EXISTS idx_qc_constats_tsv ON qc_constats_infraction USING GIN(tsv);

-- ============================================================
-- QUEBEC : STATISTIQUES RADAR PHOTO
-- Source : donneesquebec.ca
-- ============================================================
CREATE TABLE IF NOT EXISTS qc_radar_photo_stats (
    id SERIAL PRIMARY KEY,
    date_rapport DATE,
    type_appareil VARCHAR(100),
    localisation TEXT,
    municipalite VARCHAR(100),
    route VARCHAR(200),
    direction VARCHAR(50),
    vitesse_limite INTEGER,
    nombre_constats INTEGER,
    periode VARCHAR(50),
    raw_data JSONB,
    source_resource_id VARCHAR(100),
    imported_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_qc_radar_muni ON qc_radar_photo_stats(municipalite);
CREATE INDEX IF NOT EXISTS idx_qc_radar_type ON qc_radar_photo_stats(type_appareil);

-- ============================================================
-- QUEBEC : LOCALISATION DES RADARS PHOTO (GPS)
-- Source : donneesquebec.ca
-- ============================================================
CREATE TABLE IF NOT EXISTS qc_radar_photo_lieux (
    id SERIAL PRIMARY KEY,
    type_appareil VARCHAR(100),
    municipalite VARCHAR(100),
    route VARCHAR(200),
    emplacement TEXT,
    direction VARCHAR(50),
    vitesse_limite INTEGER,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    date_mise_service DATE,
    actif BOOLEAN DEFAULT TRUE,
    raw_data JSONB,
    imported_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_qc_radar_lieux_muni ON qc_radar_photo_lieux(municipalite);
CREATE INDEX IF NOT EXISTS idx_qc_radar_lieux_coords ON qc_radar_photo_lieux(latitude, longitude);

-- ============================================================
-- QUEBEC : COLLISIONS SAAQ
-- Source : donneesquebec.ca / ouvert.canada.ca
-- ============================================================
CREATE TABLE IF NOT EXISTS qc_collisions_saaq (
    id SERIAL PRIMARY KEY,
    annee INTEGER,
    date_collision DATE,
    heure_collision TIME,
    region_admin VARCHAR(100),
    municipalite VARCHAR(100),
    route VARCHAR(200),
    type_route VARCHAR(50),
    gravite VARCHAR(50),
    nombre_vehicules INTEGER,
    nombre_victimes INTEGER,
    nombre_deces INTEGER,
    nombre_blesses_graves INTEGER,
    nombre_blesses_legers INTEGER,
    conditions_meteo VARCHAR(100),
    etat_surface VARCHAR(100),
    eclairage VARCHAR(100),
    raw_data JSONB,
    source_resource_id VARCHAR(100),
    imported_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_qc_collisions_date ON qc_collisions_saaq(date_collision);
CREATE INDEX IF NOT EXISTS idx_qc_collisions_muni ON qc_collisions_saaq(municipalite);
CREATE INDEX IF NOT EXISTS idx_qc_collisions_gravite ON qc_collisions_saaq(gravite);

-- ============================================================
-- QUEBEC : VEHICULES EN CIRCULATION (SAAQ)
-- ============================================================
CREATE TABLE IF NOT EXISTS qc_vehicules_circulation (
    id SERIAL PRIMARY KEY,
    annee INTEGER,
    region VARCHAR(100),
    type_vehicule VARCHAR(100),
    nombre_vehicules INTEGER,
    raw_data JSONB,
    imported_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- MONTREAL : COLLISIONS ROUTIERES (depuis 2012)
-- Source : donnees.montreal.ca
-- Resource ID : 05deae93-d9fc-4acb-9779-e0942b5e962f
-- ============================================================
CREATE TABLE IF NOT EXISTS mtl_collisions (
    id SERIAL PRIMARY KEY,
    no_collision VARCHAR(100) UNIQUE,
    date_collision DATE,
    heure_collision TIME,
    arrondissement VARCHAR(200),
    rue1 VARCHAR(500),
    rue2 VARCHAR(500),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    gravite VARCHAR(200),
    nombre_deces INTEGER DEFAULT 0,
    nombre_blesses_graves INTEGER DEFAULT 0,
    nombre_blesses_legers INTEGER DEFAULT 0,
    type_collision VARCHAR(200),
    conditions_meteo VARCHAR(200),
    etat_surface VARCHAR(200),
    eclairage VARCHAR(200),
    raw_data JSONB,
    imported_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mtl_collisions_date ON mtl_collisions(date_collision);
CREATE INDEX IF NOT EXISTS idx_mtl_collisions_arr ON mtl_collisions(arrondissement);
CREATE INDEX IF NOT EXISTS idx_mtl_collisions_coords ON mtl_collisions(latitude, longitude);

-- ============================================================
-- MONTREAL : ACTES CRIMINELS (SPVM)
-- ============================================================
CREATE TABLE IF NOT EXISTS mtl_actes_criminels (
    id SERIAL PRIMARY KEY,
    categorie VARCHAR(100),
    date_evenement DATE,
    quart VARCHAR(20),
    pdq INTEGER,
    arrondissement VARCHAR(100),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    raw_data JSONB,
    imported_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mtl_crimes_cat ON mtl_actes_criminels(categorie);
CREATE INDEX IF NOT EXISTS idx_mtl_crimes_date ON mtl_actes_criminels(date_evenement);

-- ============================================================
-- MONTREAL : SIGNALISATION STATIONNEMENT
-- ============================================================
CREATE TABLE IF NOT EXISTS mtl_signalisation_stationnement (
    id SERIAL PRIMARY KEY,
    panneau_id VARCHAR(50),
    code_rpa VARCHAR(50),
    description_rpa TEXT,
    fleche VARCHAR(20),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    rue VARCHAR(200),
    arrondissement VARCHAR(100),
    raw_data JSONB,
    imported_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mtl_signal_code ON mtl_signalisation_stationnement(code_rpa);

-- ============================================================
-- MONTREAL : INTERVENTIONS ESCOUADE MOBILITE
-- ============================================================
CREATE TABLE IF NOT EXISTS mtl_escouade_mobilite (
    id SERIAL PRIMARY KEY,
    date_intervention DATE,
    type_intervention VARCHAR(100),
    arrondissement VARCHAR(100),
    lieu TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    raw_data JSONB,
    imported_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- JURISPRUDENCE (fusionnee : CanLII + A2AJ + curated)
-- Table principale unifiee
-- ============================================================
CREATE TABLE IF NOT EXISTS jurisprudence (
    id SERIAL PRIMARY KEY,
    canlii_id VARCHAR(100) UNIQUE,
    database_id VARCHAR(20),
    province VARCHAR(5),
    titre TEXT,
    citation VARCHAR(200),
    numero_dossier VARCHAR(100),
    date_decision DATE,
    url_canlii TEXT,
    tribunal VARCHAR(200),
    langue VARCHAR(5),
    mots_cles TEXT[],
    lois_pertinentes TEXT[],
    resume TEXT,
    texte_complet TEXT,
    resultat VARCHAR(50),
    est_ticket_related BOOLEAN DEFAULT FALSE,
    source VARCHAR(50),
    raw_metadata JSONB,
    imported_at TIMESTAMP DEFAULT NOW(),
    -- tsvector pour recherche plein texte (francais + anglais)
    tsv_fr tsvector GENERATED ALWAYS AS (
        to_tsvector('french',
            COALESCE(titre,'') || ' ' ||
            COALESCE(citation,'') || ' ' ||
            COALESCE(resume,'') || ' ' ||
            COALESCE(texte_complet,'')
        )
    ) STORED,
    tsv_en tsvector GENERATED ALWAYS AS (
        to_tsvector('english',
            COALESCE(titre,'') || ' ' ||
            COALESCE(citation,'') || ' ' ||
            COALESCE(resume,'') || ' ' ||
            COALESCE(texte_complet,'')
        )
    ) STORED
);

CREATE INDEX IF NOT EXISTS idx_juris_date ON jurisprudence(date_decision);
CREATE INDEX IF NOT EXISTS idx_juris_province ON jurisprudence(province);
CREATE INDEX IF NOT EXISTS idx_juris_db ON jurisprudence(database_id);
CREATE INDEX IF NOT EXISTS idx_juris_ticket ON jurisprudence(est_ticket_related);
CREATE INDEX IF NOT EXISTS idx_juris_resultat ON jurisprudence(resultat);
CREATE INDEX IF NOT EXISTS idx_juris_source ON jurisprudence(source);
CREATE INDEX IF NOT EXISTS idx_juris_mots_cles ON jurisprudence USING GIN(mots_cles);
CREATE INDEX IF NOT EXISTS idx_juris_lois ON jurisprudence USING GIN(lois_pertinentes);
CREATE INDEX IF NOT EXISTS idx_juris_tsv_fr ON jurisprudence USING GIN(tsv_fr);
CREATE INDEX IF NOT EXISTS idx_juris_tsv_en ON jurisprudence USING GIN(tsv_en);

-- ============================================================
-- CITATIONS (cas cites / citants)
-- ============================================================
CREATE TABLE IF NOT EXISTS jurisprudence_citations (
    id SERIAL PRIMARY KEY,
    source_canlii_id VARCHAR(100),
    target_canlii_id VARCHAR(100),
    target_titre TEXT,
    target_citation VARCHAR(200),
    target_database_id VARCHAR(20),
    type_citation VARCHAR(20),
    raw_data JSONB,
    imported_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(source_canlii_id, target_canlii_id, type_citation)
);

CREATE INDEX IF NOT EXISTS idx_citations_source ON jurisprudence_citations(source_canlii_id);
CREATE INDEX IF NOT EXISTS idx_citations_target ON jurisprudence_citations(target_canlii_id);

-- ============================================================
-- LEGISLATION CITEE DANS LES CAS
-- ============================================================
CREATE TABLE IF NOT EXISTS jurisprudence_legislation (
    id SERIAL PRIMARY KEY,
    case_canlii_id VARCHAR(100),
    legislation_id VARCHAR(100),
    titre_legislation TEXT,
    database_id VARCHAR(20),
    type_legislation VARCHAR(50),
    url_canlii TEXT,
    raw_data JSONB,
    imported_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_legis_case ON jurisprudence_legislation(case_canlii_id);

-- ============================================================
-- LOIS ET ARTICLES (CSR + HTA + Code criminel)
-- Texte complet des articles
-- ============================================================
CREATE TABLE IF NOT EXISTS lois_articles (
    id SERIAL PRIMARY KEY,
    province VARCHAR(5) NOT NULL,
    loi VARCHAR(200) NOT NULL,
    code_loi VARCHAR(20),
    article VARCHAR(50) NOT NULL,
    titre_article TEXT,
    texte_complet TEXT,
    categorie VARCHAR(50),
    amende_min NUMERIC(10,2),
    amende_max NUMERIC(10,2),
    points_inaptitude_min INTEGER,
    points_inaptitude_max INTEGER,
    type_responsabilite VARCHAR(30),
    url_source TEXT,
    imported_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(province, code_loi, article),
    -- tsvector
    tsv tsvector GENERATED ALWAYS AS (
        to_tsvector('french',
            COALESCE(article,'') || ' ' ||
            COALESCE(titre_article,'') || ' ' ||
            COALESCE(texte_complet,'') || ' ' ||
            COALESCE(categorie,'')
        )
    ) STORED
);

CREATE INDEX IF NOT EXISTS idx_lois_province ON lois_articles(province);
CREATE INDEX IF NOT EXISTS idx_lois_article ON lois_articles(article);
CREATE INDEX IF NOT EXISTS idx_lois_categorie ON lois_articles(categorie);
CREATE INDEX IF NOT EXISTS idx_lois_tsv ON lois_articles USING GIN(tsv);

-- ============================================================
-- ONTARIO : TRAFFIC OFFENCES (OPP)
-- ============================================================
CREATE TABLE IF NOT EXISTS on_traffic_offences (
    id SERIAL PRIMARY KEY,
    annee INTEGER,
    type_infraction VARCHAR(200),
    nombre_infractions INTEGER,
    variation_annuelle NUMERIC(5,2),
    source_dataset VARCHAR(100),
    raw_data JSONB,
    imported_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_on_offences_annee ON on_traffic_offences(annee);

-- ============================================================
-- ONTARIO : SET FINES (bareme amendes)
-- ============================================================
CREATE TABLE IF NOT EXISTS on_set_fines (
    id SERIAL PRIMARY KEY,
    loi VARCHAR(200),
    article VARCHAR(50),
    description_infraction TEXT,
    amende_fixe NUMERIC(10,2),
    suramende NUMERIC(10,2),
    frais_cour NUMERIC(10,2),
    total_payable NUMERIC(10,2),
    points_inaptitude INTEGER,
    date_mise_a_jour DATE,
    raw_data JSONB,
    imported_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_on_fines_article ON on_set_fines(article);

-- ============================================================
-- JURISPRUDENCE CLE (cas de reference manuels)
-- ============================================================
CREATE TABLE IF NOT EXISTS ref_jurisprudence_cle (
    id SERIAL PRIMARY KEY,
    province VARCHAR(5) NOT NULL,
    nom_cas TEXT NOT NULL,
    citation VARCHAR(200),
    annee INTEGER,
    tribunal VARCHAR(100),
    loi_applicable VARCHAR(200),
    article_applicable VARCHAR(50),
    principe_juridique TEXT NOT NULL,
    type_infraction VARCHAR(100),
    resultat VARCHAR(50),
    url_canlii TEXT,
    notes TEXT,
    imported_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ref_juris_province ON ref_jurisprudence_cle(province);
CREATE INDEX IF NOT EXISTS idx_ref_juris_type ON ref_jurisprudence_cle(type_infraction);

-- ============================================================
-- ANALYSES TICKET911 (resultats des analyses)
-- ============================================================
CREATE TABLE IF NOT EXISTS analyses_completes (
    id SERIAL PRIMARY KEY,
    dossier_uuid VARCHAR(20) NOT NULL,
    ticket_json JSONB,
    lois_json JSONB,
    precedents_json JSONB,
    analyse_json JSONB,
    verification_json JSONB,
    cross_verification_json JSONB,
    rapport_client_json JSONB,
    rapport_avocat_json JSONB,
    procedure_json JSONB,
    points_json JSONB,
    supervision_json JSONB,
    score_final INTEGER,
    confiance INTEGER,
    recommandation TEXT,
    juridiction VARCHAR(5),
    temps_total REAL,
    tokens_total INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analyses_uuid ON analyses_completes(dossier_uuid);
CREATE INDEX IF NOT EXISTS idx_analyses_date ON analyses_completes(created_at);

-- ============================================================
-- AGENT RUNS (telemetrie des agents)
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_runs (
    id SERIAL PRIMARY KEY,
    agent_name VARCHAR(100),
    action TEXT,
    input_summary TEXT,
    output_summary TEXT,
    tokens_used INTEGER DEFAULT 0,
    duration_seconds REAL DEFAULT 0,
    success BOOLEAN DEFAULT TRUE,
    error TEXT,
    dossier_uuid VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_runs_agent ON agent_runs(agent_name);
CREATE INDEX IF NOT EXISTS idx_runs_dossier ON agent_runs(dossier_uuid);

-- ============================================================
-- VUES UTILES
-- ============================================================

-- Vue : infractions QC avec details loi
CREATE OR REPLACE VIEW v_qc_infractions_complet AS
SELECT
    ci.date_infraction,
    ci.region,
    ci.description_infraction,
    ci.article,
    ci.vitesse_permise,
    ci.vitesse_constatee,
    (ci.vitesse_constatee - ci.vitesse_permise) AS exces_vitesse,
    ci.montant_amende,
    ci.points_inaptitude,
    la.type_responsabilite,
    la.amende_min,
    la.amende_max
FROM qc_constats_infraction ci
LEFT JOIN lois_articles la ON la.article = ci.article AND la.province = 'QC';

-- Vue : jurisprudence tickets seulement
CREATE OR REPLACE VIEW v_jurisprudence_tickets AS
SELECT
    j.province,
    j.titre,
    j.citation,
    j.date_decision,
    j.tribunal,
    j.url_canlii,
    j.mots_cles,
    j.resume,
    j.resultat,
    j.source
FROM jurisprudence j
WHERE j.est_ticket_related = TRUE
ORDER BY j.date_decision DESC;

-- Vue : stats par province et resultat
CREATE OR REPLACE VIEW v_jurisprudence_stats AS
SELECT
    province,
    resultat,
    COUNT(*) AS total,
    MIN(date_decision) AS plus_ancien,
    MAX(date_decision) AS plus_recent
FROM jurisprudence
WHERE est_ticket_related = TRUE
GROUP BY province, resultat
ORDER BY province, total DESC;

-- Vue : stats collisions Montreal par arrondissement
CREATE OR REPLACE VIEW v_mtl_collisions_stats AS
SELECT
    arrondissement,
    COUNT(*) AS total_collisions,
    SUM(nombre_deces) AS total_deces,
    SUM(nombre_blesses_graves) AS total_blesses_graves,
    SUM(nombre_blesses_legers) AS total_blesses_legers,
    MIN(date_collision) AS premiere_collision,
    MAX(date_collision) AS derniere_collision
FROM mtl_collisions
GROUP BY arrondissement
ORDER BY total_collisions DESC;

-- ============================================================
-- RECENSEMENT DES STATS (anomalies pre-calculees)
-- Detecte quotas, speed traps, radars disproportionnes, etc.
-- Recalcule chaque dimanche 5:30AM
-- ============================================================
CREATE TABLE IF NOT EXISTS recensement_stats (
    id SERIAL PRIMARY KEY,
    batch_id UUID NOT NULL,
    anomaly_type VARCHAR(50) NOT NULL,
    -- champs de matching ticket
    region VARCHAR(100),
    article VARCHAR(50),
    radar_site_id INTEGER,
    radar_site_name TEXT,
    -- metriques statistiques
    observed_value NUMERIC(12,2),
    expected_value NUMERIC(12,2),
    deviation_pct NUMERIC(8,2),
    z_score NUMERIC(6,2),
    confidence_level VARCHAR(10) DEFAULT 'medium'
        CHECK (confidence_level IN ('high','medium','low')),
    severity VARCHAR(10) DEFAULT 'medium'
        CHECK (severity IN ('high','medium','low')),
    -- textes defense prets a injecter
    defense_text_fr TEXT NOT NULL,
    legal_reference TEXT,
    -- details calcul
    computation_details JSONB,
    period_start DATE,
    period_end DATE,
    sample_size INTEGER,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recens_type ON recensement_stats(anomaly_type);
CREATE INDEX IF NOT EXISTS idx_recens_region ON recensement_stats(region);
CREATE INDEX IF NOT EXISTS idx_recens_article ON recensement_stats(article);
CREATE INDEX IF NOT EXISTS idx_recens_severity ON recensement_stats(severity);
CREATE INDEX IF NOT EXISTS idx_recens_active ON recensement_stats(is_active);
CREATE INDEX IF NOT EXISTS idx_recens_batch ON recensement_stats(batch_id);
-- index composite pour matching rapide ticket -> anomalies
CREATE INDEX IF NOT EXISTS idx_recens_match ON recensement_stats(is_active, region, article);

-- ============================================================
-- RECENSEMENT RUNS (log des executions hebdomadaires)
-- ============================================================
CREATE TABLE IF NOT EXISTS recensement_runs (
    id SERIAL PRIMARY KEY,
    batch_id UUID NOT NULL UNIQUE,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    anomalies_computed INTEGER DEFAULT 0,
    anomalies_high INTEGER DEFAULT 0,
    anomalies_medium INTEGER DEFAULT 0,
    anomalies_low INTEGER DEFAULT 0,
    duration_seconds REAL,
    status VARCHAR(20) DEFAULT 'running',
    details JSONB
);

-- Vue : radars les plus actifs
CREATE OR REPLACE VIEW v_radars_top AS
SELECT
    r.municipalite,
    r.route,
    r.vitesse_limite,
    r.type_appareil,
    COALESCE(s.total_constats, 0) AS total_constats
FROM qc_radar_photo_lieux r
LEFT JOIN (
    SELECT municipalite, route, SUM(nombre_constats) AS total_constats
    FROM qc_radar_photo_stats
    GROUP BY municipalite, route
) s ON s.municipalite = r.municipalite AND s.route = r.route
ORDER BY total_constats DESC;
