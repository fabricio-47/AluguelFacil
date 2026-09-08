-- Migration 020: campos de imovel em equipment_items
--
-- Mesma estrategia da migration 019 (veiculos): estende o motor generico
-- de locacao (equipment_items + locacoes) em vez de criar tabela/modulo
-- separado. Todos os campos opcionais (equipamento nao-imovel fica NULL).

ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS endereco_completo TEXT;
ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS metro_quadrado NUMERIC(10,2);
ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS quartos INTEGER;
ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS banheiros INTEGER;
ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS tipo_imovel VARCHAR(50);
ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS iptu NUMERIC(10,2);
ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS condominio NUMERIC(10,2);
