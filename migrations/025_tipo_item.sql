-- Discrimina equipment_items por tipo (equipamento/veiculo/imovel), necessario
-- pra gating por modulo (Fase 4) ja que os 3 dividem a mesma tabela/tela.
ALTER TABLE equipment_items
    ADD COLUMN IF NOT EXISTS tipo_item VARCHAR(20) NOT NULL DEFAULT 'equipamento';

ALTER TABLE equipment_items
    DROP CONSTRAINT IF EXISTS chk_equipment_items_tipo_item;

ALTER TABLE equipment_items
    ADD CONSTRAINT chk_equipment_items_tipo_item CHECK (tipo_item IN ('equipamento', 'veiculo', 'imovel'));

-- Backfill de itens ja existentes (heuristica pelos campos preenchidos).
UPDATE equipment_items
SET tipo_item = 'veiculo'
WHERE tipo_item = 'equipamento' AND (placa IS NOT NULL OR chassi IS NOT NULL OR renavam IS NOT NULL);

UPDATE equipment_items
SET tipo_item = 'imovel'
WHERE tipo_item = 'equipamento' AND (endereco_completo IS NOT NULL OR quartos IS NOT NULL OR tipo_imovel IS NOT NULL);
