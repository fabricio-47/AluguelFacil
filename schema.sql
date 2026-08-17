-- Schema MotoRental Atualizado
-- Frequência de pagamento apenas WEEKLY e MONTHLY

-- Extensão para textos case-insensitive (emails, usernames)
CREATE EXTENSION IF NOT EXISTS citext;

-- Função para atualizar updated_at automaticamente
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = CURRENT_TIMESTAMP;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ====
-- Usuários (para Flask-Login)
-- ====
CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    username citext NOT NULL UNIQUE,
    email citext NOT NULL UNIQUE,
    senha TEXT NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,
    role VARCHAR(20) NOT NULL DEFAULT 'atendente',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Migração idempotente: garante a coluna "role" em bancos que já tinham a tabela usuarios
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'atendente';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_usuarios_role'
    ) THEN
        ALTER TABLE usuarios ADD CONSTRAINT chk_usuarios_role CHECK (role IN (
            'super_admin','admin_locadora','gerente','atendente',
            'financeiro','estoquista','tecnico','entregador','vendedor'
        ));
    END IF;
END$$;

-- ====
-- Clientes
-- ====
CREATE TABLE IF NOT EXISTS clientes (
    id SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    email citext NOT NULL UNIQUE,
    telefone TEXT NOT NULL,
    cpf VARCHAR(20) UNIQUE,
    endereco TEXT,
    data_nascimento DATE,
    observacoes TEXT,
    doc_frente_arquivo VARCHAR(255),
    doc_verso_arquivo VARCHAR(255),
    comprovante_residencia_arquivo VARCHAR(255),
    foto_cliente_arquivo VARCHAR(255),
    asaas_id VARCHAR(255) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ====
-- Motos
-- ====
CREATE TABLE IF NOT EXISTS motos (
    id SERIAL PRIMARY KEY,
    placa VARCHAR(20) NOT NULL UNIQUE,
    modelo TEXT NOT NULL,
    ano INTEGER,
    disponivel BOOLEAN DEFAULT TRUE,
    imagem VARCHAR(255),
    documento_arquivo VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ====
-- Locações
-- ====
CREATE TABLE IF NOT EXISTS locacoes (
    id SERIAL PRIMARY KEY,
    cliente_id INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    moto_id INTEGER NOT NULL REFERENCES motos(id) ON DELETE CASCADE,
    data_inicio DATE NOT NULL,
    data_fim DATE,
    cancelado BOOLEAN DEFAULT FALSE,
    observacoes TEXT,

    -- Contrato único em PDF
    contrato_arquivo VARCHAR(255),

    -- Assinatura Asaas
    asaas_subscription_id VARCHAR(255) UNIQUE,

    -- Campos financeiros
    valor NUMERIC(12,2),
    boleto_url TEXT,
    pagamento_status VARCHAR(50) DEFAULT 'PENDING',
    valor_pago NUMERIC(12,2) DEFAULT 0,
    data_pagamento DATE,
    asaas_payment_id VARCHAR(255),

    -- Frequência de pagamento (apenas WEEKLY ou MONTHLY)
    frequencia_pagamento VARCHAR(20) NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_locacoes_datas CHECK (data_fim IS NULL OR data_fim >= data_inicio),
    CONSTRAINT chk_locacoes_valor CHECK (valor IS NULL OR valor >= 0),
    CONSTRAINT chk_locacoes_valor_pago CHECK (valor_pago IS NULL OR valor_pago >= 0),
    CONSTRAINT chk_locacoes_freq CHECK (frequencia_pagamento IN ('WEEKLY','MONTHLY')),
    CONSTRAINT chk_locacoes_status CHECK (pagamento_status IN (
        'PENDING','RECEIVED','CONFIRMED','OVERDUE','CANCELED','REFUNDED','CHARGEBACK','RECEIVED_IN_CASH'
    ))
);

-- ====
-- Histórico de Boletos (Payments Asaas)
-- ====
CREATE TABLE IF NOT EXISTS boletos (
    id SERIAL PRIMARY KEY,
    locacao_id INTEGER NOT NULL REFERENCES locacoes(id) ON DELETE CASCADE,
    asaas_payment_id VARCHAR(255) UNIQUE NOT NULL,
    status VARCHAR(50) DEFAULT 'PENDING',
    valor NUMERIC(12,2),
    valor_pago NUMERIC(12,2) DEFAULT 0,
    boleto_url TEXT,
    descricao TEXT,
    data_vencimento DATE,
    data_pagamento DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_boletos_valor CHECK (valor IS NULL OR valor >= 0),
    CONSTRAINT chk_boletos_valor_pago CHECK (valor_pago IS NULL OR valor_pago >= 0),
    CONSTRAINT chk_boletos_status CHECK (status IN (
        'PENDING','RECEIVED','CONFIRMED','OVERDUE','CANCELED','REFUNDED','CHARGEBACK','RECEIVED_IN_CASH'
    ))
);

-- ====
-- Imagens das Motos
-- ====
CREATE TABLE IF NOT EXISTS moto_imagens (
    id SERIAL PRIMARY KEY,
    moto_id INTEGER NOT NULL REFERENCES motos(id) ON DELETE CASCADE,
    arquivo TEXT NOT NULL,
    data_upload TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ====
-- Serviços Extras nas Locações
-- ====
CREATE TABLE IF NOT EXISTS servicos_locacao (
    id SERIAL PRIMARY KEY,
    locacao_id INTEGER NOT NULL REFERENCES locacoes(id) ON DELETE CASCADE,
    descricao TEXT NOT NULL,
    valor NUMERIC(12,2),
    data_servico DATE DEFAULT CURRENT_DATE,
    quilometragem INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_servicos_valor CHECK (valor IS NULL OR valor >= 0),
    CONSTRAINT chk_servicos_km CHECK (quilometragem IS NULL OR quilometragem >= 0)
);

-- ====
-- Índices
-- ====
CREATE INDEX IF NOT EXISTS idx_clientes_cpf ON clientes(cpf);
CREATE INDEX IF NOT EXISTS idx_clientes_email ON clientes(email);
CREATE INDEX IF NOT EXISTS idx_clientes_asaas ON clientes(asaas_id);

CREATE INDEX IF NOT EXISTS idx_motos_placa ON motos(placa);
CREATE INDEX IF NOT EXISTS idx_motos_modelo ON motos(modelo);

CREATE INDEX IF NOT EXISTS idx_locacoes_cliente_id ON locacoes(cliente_id);
CREATE INDEX IF NOT EXISTS idx_locacoes_moto_id ON locacoes(moto_id);
CREATE INDEX IF NOT EXISTS idx_locacoes_subscription ON locacoes(asaas_subscription_id);
CREATE INDEX IF NOT EXISTS idx_locacoes_payment_id ON locacoes(asaas_payment_id);
CREATE INDEX IF NOT EXISTS idx_locacoes_status ON locacoes(pagamento_status);

CREATE INDEX IF NOT EXISTS idx_boletos_locacao_id ON boletos(locacao_id);
CREATE INDEX IF NOT EXISTS idx_boletos_status ON boletos(status);
CREATE INDEX IF NOT EXISTS idx_boletos_due_date ON boletos(data_vencimento);

CREATE INDEX IF NOT EXISTS idx_servicos_locacao_id ON servicos_locacao(locacao_id);

-- ====
-- Triggers de updated_at
-- ====
DO $$
BEGIN
    IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'trg_usuarios_updated'
    ) THEN
    CREATE TRIGGER trg_usuarios_updated 
    BEFORE UPDATE ON usuarios
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;

    IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'trg_clientes_updated'
    ) THEN
    CREATE TRIGGER trg_clientes_updated 
    BEFORE UPDATE ON clientes
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;

    IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'trg_motos_updated'
    ) THEN
    CREATE TRIGGER trg_motos_updated 
    BEFORE UPDATE ON motos
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;

    IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'trg_locacoes_updated'
    ) THEN
    CREATE TRIGGER trg_locacoes_updated 
    BEFORE UPDATE ON locacoes
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;

    IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'trg_boletos_updated'
    ) THEN
    CREATE TRIGGER trg_boletos_updated 
    BEFORE UPDATE ON boletos
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;

    IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'trg_servicos_updated'
    ) THEN
    CREATE TRIGGER trg_servicos_updated 
    BEFORE UPDATE ON servicos_locacao
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END$$;