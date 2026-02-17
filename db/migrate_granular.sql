-- ══════════════════════════════════════════════════════════════
--  MIGRATION: Analyse Granulaire — Blitz + OCR Metadata
--  Date: 2026-02-17
--  Usage: docker exec seo-agent-postgres psql -U ticketdb_user -d tickets_qc_on -f /tmp/migrate_granular.sql
-- ══════════════════════════════════════════════════════════════

-- ── Table: tickets_scannes_meta ──
-- Stocke les métadonnées extraites par OCR des tickets scannés par les clients.
-- C'est la SEULE source de matricule policier, rue exacte, etc.
-- Se remplit au fil du temps via le pipeline OCR (Mindee).
CREATE TABLE IF NOT EXISTS tickets_scannes_meta (
    id SERIAL PRIMARY KEY,
    dossier_uuid UUID NOT NULL,
    -- Infos extraites du ticket par OCR
    matricule_policier VARCHAR(50),
    corps_policier VARCHAR(100),       -- SPVM, SQ, police municipale, etc.
    poste_police VARCHAR(100),
    rue_exacte VARCHAR(500),
    ville VARCHAR(200),
    code_postal VARCHAR(10),
    numero_constat VARCHAR(50),
    -- Infos infraction
    article VARCHAR(50),
    loi VARCHAR(200),
    date_infraction DATE,
    heure_infraction TIME,
    -- Appareil de mesure
    appareil_type VARCHAR(100),        -- cinémomètre, laser, radar photo, etc.
    appareil_serie VARCHAR(100),       -- numéro de série
    -- Véhicule
    plaque VARCHAR(20),
    type_vehicule VARCHAR(100),
    -- Montant
    montant_amende NUMERIC(10,2),
    points_inaptitude INTEGER,
    -- Vitesse (si applicable)
    vitesse_captee INTEGER,
    vitesse_permise INTEGER,
    -- Métadonnées
    zone_scolaire BOOLEAN DEFAULT FALSE,
    zone_construction BOOLEAN DEFAULT FALSE,
    conditions_meteo VARCHAR(200),
    -- Tracking
    confiance_ocr NUMERIC(5,2),        -- score de confiance Mindee 0-100
    champs_extraits JSONB,             -- tous les champs bruts OCR
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tsm_dossier ON tickets_scannes_meta(dossier_uuid);
CREATE INDEX IF NOT EXISTS idx_tsm_matricule ON tickets_scannes_meta(matricule_policier);
CREATE INDEX IF NOT EXISTS idx_tsm_rue ON tickets_scannes_meta(rue_exacte);
CREATE INDEX IF NOT EXISTS idx_tsm_ville ON tickets_scannes_meta(ville);
CREATE INDEX IF NOT EXISTS idx_tsm_corps ON tickets_scannes_meta(corps_policier);
CREATE INDEX IF NOT EXISTS idx_tsm_appareil ON tickets_scannes_meta(appareil_type);
CREATE INDEX IF NOT EXISTS idx_tsm_date ON tickets_scannes_meta(date_infraction);
CREATE INDEX IF NOT EXISTS idx_tsm_constat ON tickets_scannes_meta(numero_constat);

-- ── Mise à jour header du runner ──
-- Les 2 nouveaux détecteurs (blitz_daily, pattern_jour_semaine) écrivent dans
-- recensement_stats existant — pas besoin de nouvelle table pour eux.

-- ══════════════════════════════════════════════════════════════
-- Vérification
-- ══════════════════════════════════════════════════════════════
DO $$
BEGIN
    RAISE NOTICE 'Migration granulaire terminée: tickets_scannes_meta créée';
END $$;
