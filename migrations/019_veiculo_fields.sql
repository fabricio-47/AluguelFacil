-- Migration 019: campos de veiculo em equipment_items
--
-- Em vez de criar uma tabela/modulo separado para "veiculos", estende o
-- motor de locacao generico que ja existe (equipment_items + locacoes),
-- reaproveitando contrato, assinatura digital, multa, financeiro e
-- permissoes ja testados em producao. As tabelas "veiculos"/"imoveis"/
-- "rentable_items" que existem no banco sao de uma tentativa de
-- arquitetura anterior, abandonada, sem nenhuma rota usando-as -- nao sao
-- tocadas por esta migration.
--
-- Todos os campos sao opcionais (equipamento nao-veiculo continua com eles
-- NULL). Idempotente e re-executavel com seguranca.

ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS placa VARCHAR(10);
ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS chassi VARCHAR(50);
ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS renavam VARCHAR(20);
ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS quilometragem INTEGER;
ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS combustivel VARCHAR(30);
ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS cambio VARCHAR(20);

-- Unicidade so entre os que tem valor preenchido (varios equipment_items
-- nao-veiculo com placa/chassi/renavam NULL nao devem colidir entre si).
CREATE UNIQUE INDEX IF NOT EXISTS uq_equipment_items_placa
    ON equipment_items (company_id, placa) WHERE placa IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_equipment_items_chassi
    ON equipment_items (company_id, chassi) WHERE chassi IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_equipment_items_renavam
    ON equipment_items (company_id, renavam) WHERE renavam IS NOT NULL;
