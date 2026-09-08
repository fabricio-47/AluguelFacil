-- Migration 023: bairro e cidade separados do endereco_completo em equipment_items.
ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS bairro VARCHAR(100);
ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS cidade VARCHAR(100);
