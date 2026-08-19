-- 1. INFRAESTRUTURA BASE
CREATE TABLE IF NOT EXISTS tenants (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. NOVOS MÓDULOS DE LOCAÇÃO (ESTRUTURA SEPARADA)
CREATE TABLE IF NOT EXISTS rentable_items (
    id SERIAL PRIMARY KEY, 
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE, 
    item_type VARCHAR(20) NOT NULL, -- 'imovel', 'equipamento', 'veiculo'
    status VARCHAR(20) NOT NULL DEFAULT 'disponivel', 
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS equipment_items (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    rentable_item_id INTEGER UNIQUE REFERENCES rentable_items(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS imoveis (
    id SERIAL PRIMARY KEY, 
    rentable_item_id INTEGER NOT NULL UNIQUE REFERENCES rentable_items(id) ON DELETE CASCADE, 
    endereco_completo TEXT NOT NULL, 
    metro_quadrado FLOAT NOT NULL, 
    quartos INTEGER NOT NULL DEFAULT 0, 
    banheiros INTEGER NOT NULL DEFAULT 0, 
    tipo_imovel VARCHAR(50) NOT NULL, -- 'apartamento', 'casa', 'comercial'
    iptu NUMERIC(10, 2) DEFAULT 0.0, 
    condominio NUMERIC(10, 2) DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS veiculos (
    id SERIAL PRIMARY KEY, 
    rentable_item_id INTEGER NOT NULL UNIQUE REFERENCES rentable_items(id) ON DELETE CASCADE, 
    placa VARCHAR(10) NOT NULL UNIQUE, 
    chassi VARCHAR(50) NOT NULL UNIQUE, 
    renavam VARCHAR(20) NOT NULL UNIQUE, 
    quilometragem INTEGER NOT NULL DEFAULT 0, 
    combustivel VARCHAR(30) NOT NULL, -- 'flex', 'gasolina', 'diesel', 'eletrico'
    cambio VARCHAR(20) NOT NULL -- 'manual', 'automatico'
);

-- 3. CONTRATOS E LOCAÇÕES centralizados no rentable_item_id
CREATE TABLE IF NOT EXISTS locacoes (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    rentable_item_id INTEGER NOT NULL REFERENCES rentable_items(id) ON DELETE RESTRICT,
    cliente_nome VARCHAR(255) NOT NULL,
    data_inicio DATE NOT NULL,
    data_fim DATE,
    valor_total NUMERIC(10, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
