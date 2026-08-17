-- Migration 007: entregas + auditoria de movimentação de estoque.
--
-- Só estrutura (DDL). Idempotente. Aditiva: branches não muda (já tem tudo
-- que a tela de gestão precisa desde a Fase 1).
--
-- DEFAULT de company_id fica no migrate_entregas_estoque.py (depende do id
-- gerado em runtime pela Fase 1), mesmo padrão das migrations anteriores.

CREATE TABLE IF NOT EXISTS entregas (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    locacao_id INTEGER NOT NULL REFERENCES locacoes(id) ON DELETE CASCADE,

    endereco TEXT NOT NULL,
    entregador_id INTEGER REFERENCES usuarios(id),
    veiculo TEXT,
    horario_previsto TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT 'aguardando',
    observacoes TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_entregas_status CHECK (status IN (
        'aguardando', 'em_separacao', 'saiu_para_entrega', 'entregue', 'retirada_agendada', 'finalizada'
    ))
);

-- Sem ON DELETE CASCADE de propósito: um equipamento com movimentação
-- registrada não deve poder ser excluído silenciosamente (o tratamento de
-- ForeignKeyViolation em excluir_equipamento, da Fase 2, já cobre isso).
CREATE TABLE IF NOT EXISTS movimentacoes_estoque (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    equipment_item_id INTEGER NOT NULL REFERENCES equipment_items(id),

    tipo VARCHAR(20) NOT NULL,
    quantidade INTEGER NOT NULL DEFAULT 1,
    motivo TEXT,
    usuario_id INTEGER REFERENCES usuarios(id),
    data TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_movimentacoes_tipo CHECK (tipo IN (
        'entrada', 'saida', 'transferencia', 'manutencao', 'perda', 'ajuste'
    ))
);

CREATE INDEX IF NOT EXISTS idx_entregas_company_id ON entregas(company_id);
CREATE INDEX IF NOT EXISTS idx_entregas_locacao_id ON entregas(locacao_id);
CREATE INDEX IF NOT EXISTS idx_entregas_entregador_id ON entregas(entregador_id);
CREATE INDEX IF NOT EXISTS idx_entregas_status ON entregas(status);

CREATE INDEX IF NOT EXISTS idx_movimentacoes_company_id ON movimentacoes_estoque(company_id);
CREATE INDEX IF NOT EXISTS idx_movimentacoes_equipment_item_id ON movimentacoes_estoque(equipment_item_id);
CREATE INDEX IF NOT EXISTS idx_movimentacoes_tipo ON movimentacoes_estoque(tipo);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_entregas_updated') THEN
        CREATE TRIGGER trg_entregas_updated
        BEFORE UPDATE ON entregas
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END$$;
