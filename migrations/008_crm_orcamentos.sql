-- Migration 008: CRM (orçamentos, pipeline de vendas, tarefas).
--
-- Só estrutura (DDL). Idempotente. Aditiva: nenhuma tabela existente muda.
--
-- DEFAULT de company_id fica no migrate_crm_orcamentos.py (depende do id
-- gerado em runtime pela Fase 1), mesmo padrão das migrations anteriores.

CREATE TABLE IF NOT EXISTS orcamentos (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    cliente_id INTEGER NOT NULL REFERENCES clientes(id),
    criado_por INTEGER REFERENCES usuarios(id),

    frete NUMERIC(10,2) NOT NULL DEFAULT 0,
    valor_total NUMERIC(10,2) NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'criado',
    validade DATE,
    observacoes TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_orcamentos_status CHECK (status IN (
        'criado', 'enviado', 'visualizado', 'aprovado', 'recusado'
    ))
);

-- Um orçamento pode ter vários equipamentos; cada item vira, na conversão,
-- uma locação independente (1 equipamento = 1 assinatura Asaas). locacao_id
-- marca qual item já foi convertido, permitindo retry só dos que falharam.
CREATE TABLE IF NOT EXISTS orcamento_itens (
    id SERIAL PRIMARY KEY,
    orcamento_id INTEGER NOT NULL REFERENCES orcamentos(id) ON DELETE CASCADE,
    equipment_item_id INTEGER NOT NULL REFERENCES equipment_items(id),

    quantidade INTEGER NOT NULL DEFAULT 1,
    periodo_dias INTEGER,
    frequencia_pagamento VARCHAR(20),
    valor_unitario NUMERIC(10,2) NOT NULL,
    desconto NUMERIC(10,2) NOT NULL DEFAULT 0,

    locacao_id INTEGER REFERENCES locacoes(id),

    CONSTRAINT chk_orcamento_itens_frequencia CHECK (
        frequencia_pagamento IS NULL OR frequencia_pagamento IN ('WEEKLY', 'MONTHLY')
    )
);

-- Um cliente sempre tem uma etapa atual: uma linha só por cliente (estado
-- atual, não histórico — diferente de movimentacoes_estoque).
CREATE TABLE IF NOT EXISTS pipeline_clientes (
    id SERIAL PRIMARY KEY,
    cliente_id INTEGER NOT NULL UNIQUE REFERENCES clientes(id) ON DELETE CASCADE,

    etapa VARCHAR(30) NOT NULL DEFAULT 'novo_cliente',
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_responsavel INTEGER REFERENCES usuarios(id),

    CONSTRAINT chk_pipeline_clientes_etapa CHECK (etapa IN (
        'novo_cliente', 'contato_realizado', 'orcamento_enviado',
        'negociacao', 'reserva', 'locacao', 'cliente_recorrente'
    ))
);

CREATE TABLE IF NOT EXISTS tarefas_crm (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    cliente_id INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,

    tipo VARCHAR(20) NOT NULL,
    descricao TEXT,
    data_prevista DATE,
    concluida BOOLEAN NOT NULL DEFAULT FALSE,
    usuario_responsavel INTEGER REFERENCES usuarios(id),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_tarefas_crm_tipo CHECK (tipo IN (
        'ligar', 'whatsapp', 'enviar_orcamento', 'follow_up'
    ))
);

CREATE INDEX IF NOT EXISTS idx_orcamentos_company_id ON orcamentos(company_id);
CREATE INDEX IF NOT EXISTS idx_orcamentos_cliente_id ON orcamentos(cliente_id);
CREATE INDEX IF NOT EXISTS idx_orcamentos_criado_por ON orcamentos(criado_por);
CREATE INDEX IF NOT EXISTS idx_orcamentos_status ON orcamentos(status);

CREATE INDEX IF NOT EXISTS idx_orcamento_itens_orcamento_id ON orcamento_itens(orcamento_id);
CREATE INDEX IF NOT EXISTS idx_orcamento_itens_equipment_item_id ON orcamento_itens(equipment_item_id);

CREATE INDEX IF NOT EXISTS idx_pipeline_clientes_etapa ON pipeline_clientes(etapa);
CREATE INDEX IF NOT EXISTS idx_pipeline_clientes_usuario_responsavel ON pipeline_clientes(usuario_responsavel);

CREATE INDEX IF NOT EXISTS idx_tarefas_crm_company_id ON tarefas_crm(company_id);
CREATE INDEX IF NOT EXISTS idx_tarefas_crm_cliente_id ON tarefas_crm(cliente_id);
CREATE INDEX IF NOT EXISTS idx_tarefas_crm_usuario_responsavel ON tarefas_crm(usuario_responsavel);
CREATE INDEX IF NOT EXISTS idx_tarefas_crm_concluida ON tarefas_crm(concluida);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_orcamentos_updated') THEN
        CREATE TRIGGER trg_orcamentos_updated
        BEFORE UPDATE ON orcamentos
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_tarefas_crm_updated') THEN
        CREATE TRIGGER trg_tarefas_crm_updated
        BEFORE UPDATE ON tarefas_crm
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END$$;
