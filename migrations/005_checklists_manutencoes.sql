-- Migration 005: checklist de entrega/devolução + manutenção.
--
-- Só estrutura (DDL). Idempotente. Aditiva: não toca em locacoes/boletos/
-- equipment_items além de referenciá-las via FK.
--
-- DEFAULT de company_id fica no migrate_checklists_manutencoes.py (depende
-- do id gerado em runtime pela Fase 1), mesmo padrão das migrations anteriores.

CREATE TABLE IF NOT EXISTS checklists (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    locacao_id INTEGER NOT NULL REFERENCES locacoes(id) ON DELETE CASCADE,

    tipo VARCHAR(20) NOT NULL,
    estado_geral VARCHAR(20) NOT NULL,
    acessorios_enviados TEXT,
    observacoes TEXT,
    criado_por INTEGER REFERENCES usuarios(id),
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    confirmado_pelo_cliente BOOLEAN DEFAULT FALSE,

    CONSTRAINT chk_checklists_tipo CHECK (tipo IN ('entrega', 'devolucao')),
    CONSTRAINT chk_checklists_estado CHECK (estado_geral IN ('novo', 'bom', 'regular', 'danificado')),
    CONSTRAINT uq_checklists_locacao_tipo UNIQUE (locacao_id, tipo)
);

CREATE TABLE IF NOT EXISTS checklist_fotos (
    id SERIAL PRIMARY KEY,
    checklist_id INTEGER NOT NULL REFERENCES checklists(id) ON DELETE CASCADE,
    arquivo TEXT NOT NULL,
    data_upload TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS manutencoes (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    equipment_item_id INTEGER NOT NULL REFERENCES equipment_items(id),

    tipo VARCHAR(20) NOT NULL,
    problema TEXT NOT NULL,
    tecnico_id INTEGER REFERENCES usuarios(id),
    data_abertura DATE NOT NULL DEFAULT CURRENT_DATE,
    data_conclusao_prevista DATE,
    data_conclusao_real DATE,
    pecas_utilizadas TEXT,
    valor NUMERIC(12,2),
    fornecedor TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'aberta',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_manutencoes_tipo CHECK (tipo IN ('preventiva', 'corretiva', 'emergencial')),
    CONSTRAINT chk_manutencoes_status CHECK (status IN ('aberta', 'em_andamento', 'concluida')),
    CONSTRAINT chk_manutencoes_valor CHECK (valor IS NULL OR valor >= 0)
);

CREATE INDEX IF NOT EXISTS idx_checklists_company_id ON checklists(company_id);
CREATE INDEX IF NOT EXISTS idx_checklists_locacao_id ON checklists(locacao_id);
CREATE INDEX IF NOT EXISTS idx_checklist_fotos_checklist_id ON checklist_fotos(checklist_id);

CREATE INDEX IF NOT EXISTS idx_manutencoes_company_id ON manutencoes(company_id);
CREATE INDEX IF NOT EXISTS idx_manutencoes_equipment_item_id ON manutencoes(equipment_item_id);
CREATE INDEX IF NOT EXISTS idx_manutencoes_status ON manutencoes(status);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_manutencoes_updated') THEN
        CREATE TRIGGER trg_manutencoes_updated
        BEFORE UPDATE ON manutencoes
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END$$;
