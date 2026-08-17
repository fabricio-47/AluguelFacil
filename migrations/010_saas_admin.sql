-- Migration 010: super admin da plataforma + planos SaaS.
--
-- Só estrutura (DDL) + backfills determinísticos (sem lógica por linha —
-- esses ficam em UPDATE puro; o que precisa de runtime, como zerar limites
-- da company padrão ou marcar o admin bootstrap, fica no
-- migrate_saas_admin.py, mesmo padrão das migrations anteriores).

ALTER TABLE companies ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'ativo';
ALTER TABLE companies ADD COLUMN IF NOT EXISTS status_atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS limite_usuarios INTEGER;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS limite_equipamentos INTEGER;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS limite_filiais INTEGER;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS data_inicio_trial DATE;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS data_bloqueio DATE;

-- Backfill de status a partir do boolean "ativo" já existente (Fase 1).
UPDATE companies SET status = 'ativo' WHERE status IS NULL AND ativo = TRUE;
UPDATE companies SET status = 'bloqueado' WHERE status IS NULL AND ativo = FALSE;
UPDATE companies SET status = 'ativo' WHERE status IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_companies_status') THEN
        ALTER TABLE companies ADD CONSTRAINT chk_companies_status CHECK (status IN ('ativo', 'bloqueado', 'trial'));
    END IF;
END$$;

-- "plano" já existe desde a Fase 1 (default 'padrao'); normaliza pros 3
-- planos novos antes de restringir com CHECK.
UPDATE companies SET plano = 'basico' WHERE plano IS NULL OR plano NOT IN ('basico', 'profissional', 'enterprise');

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_companies_plano') THEN
        ALTER TABLE companies ADD CONSTRAINT chk_companies_plano CHECK (plano IN ('basico', 'profissional', 'enterprise'));
    END IF;
END$$;

ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS eh_admin_plataforma BOOLEAN NOT NULL DEFAULT FALSE;
