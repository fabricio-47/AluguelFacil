-- Corrige um bug: o gate por modulo usa slugs no plural (equipamentos/veiculos/
-- imoveis, mesmos nomes de company_modulos.modulo), mas a coluna tipo_item
-- tinha sido criada com valores no singular. Alinha tudo no plural.
ALTER TABLE equipment_items
    DROP CONSTRAINT IF EXISTS chk_equipment_items_tipo_item;

UPDATE equipment_items SET tipo_item = 'equipamentos' WHERE tipo_item = 'equipamento';
UPDATE equipment_items SET tipo_item = 'veiculos' WHERE tipo_item = 'veiculo';
UPDATE equipment_items SET tipo_item = 'imoveis' WHERE tipo_item = 'imovel';

ALTER TABLE equipment_items
    ALTER COLUMN tipo_item SET DEFAULT 'equipamentos';

ALTER TABLE equipment_items
    ADD CONSTRAINT chk_equipment_items_tipo_item CHECK (tipo_item IN ('equipamentos', 'veiculos', 'imoveis'));
