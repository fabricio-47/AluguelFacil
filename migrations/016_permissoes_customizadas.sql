-- Migration 016: permissões customizadas por cargo, por empresa.
--
-- Só estrutura (DDL). Idempotente. Aditiva.
-- Uma linha por (empresa, cargo) — diferente de config_multas/config_asaas
-- (uma linha por empresa), aqui é por empresa E cargo, já que uma empresa
-- pode customizar vários cargos independentemente.
--
-- A coluna `permissoes` é um array JSON de strings (os valores de
-- permissions.py, ex: ["ver_locacoes", "criar_locacao"]). A PRESENÇA da
-- linha (mesmo com array vazio) significa "este cargo foi customizado";
-- a AUSÊNCIA de linha significa "usa o padrão fixo do código".

CREATE TABLE IF NOT EXISTS permissoes_customizadas (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    role VARCHAR(20) NOT NULL,
    permissoes JSONB NOT NULL DEFAULT '[]'::jsonb,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(company_id, role),
    CONSTRAINT chk_permissoes_customizadas_role CHECK (role IN (
        'financeiro', 'atendente', 'vendedor', 'tecnico', 'estoquista', 'entregador'
    ))
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_permissoes_customizadas_updated') THEN
        CREATE TRIGGER trg_permissoes_customizadas_updated
        BEFORE UPDATE ON permissoes_customizadas
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END$$;
