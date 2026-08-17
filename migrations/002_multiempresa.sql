-- Migration 002: banco genérico (equipamentos) + multi-tenant (companies)
--
-- Só estrutura (DDL). Idempotente e re-executável com segurança, no mesmo
-- estilo de schema.sql (IF NOT EXISTS / DO $$ ... IF NOT EXISTS).
--
-- Não altera nenhuma rota/consulta do app: a tabela "motos" é renomeada para
-- "motos_legado" e uma view chamada "motos" é criada em cima dela, para que
-- todo o SQL cru existente em routes/*.py continue funcionando sem mudança
-- de código (view simples de uma tabela só é automaticamente atualizável no
-- Postgres — aceita INSERT/UPDATE/DELETE).
--
-- Seed de dados (company padrão, migração de motos_legado -> equipment_items,
-- backfill de company_id, SET NOT NULL) fica no migrate_multiempresa.py, não
-- aqui, porque depende de valores gerados em runtime (IDs via RETURNING).

-- ======================
-- companies (raiz do multi-tenant)
-- ======================
CREATE TABLE IF NOT EXISTS companies (
    id SERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    cnpj VARCHAR(20) UNIQUE,
    plano VARCHAR(50) DEFAULT 'padrao',
    ativo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ======================
-- branches (filiais de uma company)
-- ======================
CREATE TABLE IF NOT EXISTS branches (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    nome TEXT NOT NULL,
    endereco TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ======================
-- equipment_categories (com subcategorias via categoria_pai_id)
-- ======================
CREATE TABLE IF NOT EXISTS equipment_categories (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    nome TEXT NOT NULL,
    categoria_pai_id INTEGER REFERENCES equipment_categories(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ======================
-- equipment_items (substitui o conceito de "motos", genérico)
-- ======================
CREATE TABLE IF NOT EXISTS equipment_items (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    branch_id INTEGER NOT NULL REFERENCES branches(id),
    categoria_id INTEGER REFERENCES equipment_categories(id) ON DELETE SET NULL,

    codigo_interno VARCHAR(50),
    sku VARCHAR(100),
    codigo_barras VARCHAR(100),

    nome TEXT NOT NULL,
    marca TEXT,
    modelo TEXT,
    numero_serie VARCHAR(100),
    descricao TEXT,
    foto VARCHAR(255),

    valor_compra NUMERIC(12,2),
    valor_diaria NUMERIC(12,2),
    valor_semanal NUMERIC(12,2),
    valor_quinzenal NUMERIC(12,2),
    valor_mensal NUMERIC(12,2),
    valor_hora NUMERIC(12,2),
    caucao NUMERIC(12,2),

    status VARCHAR(20) NOT NULL DEFAULT 'disponivel',
    quantidade_disponivel INTEGER NOT NULL DEFAULT 0,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_equipment_items_status CHECK (status IN (
        'disponivel', 'reservado', 'alugado', 'manutencao', 'danificado', 'perdido', 'inativo'
    )),
    CONSTRAINT chk_equipment_items_quantidade CHECK (quantidade_disponivel >= 0),
    CONSTRAINT uq_equipment_items_company_codigo UNIQUE (company_id, codigo_interno)
);

-- ======================
-- equipment_kits / equipment_kit_items (N:N com quantidade)
-- ======================
CREATE TABLE IF NOT EXISTS equipment_kits (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    nome TEXT NOT NULL,
    descricao TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS equipment_kit_items (
    id SERIAL PRIMARY KEY,
    kit_id INTEGER NOT NULL REFERENCES equipment_kits(id) ON DELETE CASCADE,
    equipment_item_id INTEGER NOT NULL REFERENCES equipment_items(id) ON DELETE CASCADE,
    quantidade INTEGER NOT NULL DEFAULT 1,

    CONSTRAINT chk_equipment_kit_items_quantidade CHECK (quantidade > 0),
    CONSTRAINT uq_equipment_kit_items UNIQUE (kit_id, equipment_item_id)
);

-- ======================
-- company_id nas tabelas existentes (sem NOT NULL ainda — o script Python
-- faz o backfill e só então aperta a constraint)
-- ======================
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id);
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id);
ALTER TABLE locacoes ADD COLUMN IF NOT EXISTS company_id INTEGER REFERENCES companies(id);

-- Coluna de compatibilidade: locacoes.moto_id continua existindo e funcionando
-- (nada é removido). equipment_item_id é a nova FK que o código vai passar a
-- usar numa fase futura. ON DELETE RESTRICT de propósito (diferente do
-- ON DELETE CASCADE que moto_id tem hoje — ver observação no plano).
ALTER TABLE locacoes ADD COLUMN IF NOT EXISTS equipment_item_id INTEGER REFERENCES equipment_items(id) ON DELETE RESTRICT;

-- ======================
-- motos -> motos_legado + view de compatibilidade "motos"
-- ======================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'motos' AND table_type = 'BASE TABLE'
    ) THEN
        ALTER TABLE motos RENAME TO motos_legado;
    END IF;
END$$;

CREATE OR REPLACE VIEW motos AS SELECT * FROM motos_legado;

-- ======================
-- Índices
-- ======================
CREATE INDEX IF NOT EXISTS idx_branches_company_id ON branches(company_id);
CREATE INDEX IF NOT EXISTS idx_equipment_categories_company_id ON equipment_categories(company_id);
CREATE INDEX IF NOT EXISTS idx_equipment_categories_pai_id ON equipment_categories(categoria_pai_id);
CREATE INDEX IF NOT EXISTS idx_equipment_items_company_id ON equipment_items(company_id);
CREATE INDEX IF NOT EXISTS idx_equipment_items_branch_id ON equipment_items(branch_id);
CREATE INDEX IF NOT EXISTS idx_equipment_items_categoria_id ON equipment_items(categoria_id);
CREATE INDEX IF NOT EXISTS idx_equipment_items_status ON equipment_items(status);
CREATE INDEX IF NOT EXISTS idx_equipment_kits_company_id ON equipment_kits(company_id);
CREATE INDEX IF NOT EXISTS idx_equipment_kit_items_kit_id ON equipment_kit_items(kit_id);
CREATE INDEX IF NOT EXISTS idx_equipment_kit_items_item_id ON equipment_kit_items(equipment_item_id);
CREATE INDEX IF NOT EXISTS idx_usuarios_company_id ON usuarios(company_id);
CREATE INDEX IF NOT EXISTS idx_clientes_company_id ON clientes(company_id);
CREATE INDEX IF NOT EXISTS idx_locacoes_company_id ON locacoes(company_id);
CREATE INDEX IF NOT EXISTS idx_locacoes_equipment_item_id ON locacoes(equipment_item_id);

-- ======================
-- Triggers de updated_at (reaproveita set_updated_at(), já criada em schema.sql)
-- ======================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_branches_updated') THEN
        CREATE TRIGGER trg_branches_updated
        BEFORE UPDATE ON branches
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_equipment_categories_updated') THEN
        CREATE TRIGGER trg_equipment_categories_updated
        BEFORE UPDATE ON equipment_categories
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_equipment_items_updated') THEN
        CREATE TRIGGER trg_equipment_items_updated
        BEFORE UPDATE ON equipment_items
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_equipment_kits_updated') THEN
        CREATE TRIGGER trg_equipment_kits_updated
        BEFORE UPDATE ON equipment_kits
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END$$;
