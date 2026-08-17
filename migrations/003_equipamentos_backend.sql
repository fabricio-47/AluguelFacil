-- Migration 003: completa equipment_items para o backend de motos_routes.py
-- poder trocar de vez a view "motos" por equipment_items, sem quebrar
-- documento/galeria de fotos nem o campo "ano" do formulário.
--
-- Só estrutura (DDL). Idempotente e re-executável com segurança, mesmo
-- estilo de schema.sql e migrations/002_multiempresa.sql.
--
-- DEFAULT de company_id/branch_id/categoria_id em equipment_items e o
-- backfill de dados que já vieram da Fase 1 (motos_legado -> equipment_items)
-- ficam no migrate_equipamentos_backend.py, porque dependem de IDs gerados
-- em runtime.

ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS documento_arquivo VARCHAR(255);
ALTER TABLE equipment_items ADD COLUMN IF NOT EXISTS ano INTEGER;

CREATE TABLE IF NOT EXISTS equipment_item_imagens (
    id SERIAL PRIMARY KEY,
    equipment_item_id INTEGER NOT NULL REFERENCES equipment_items(id) ON DELETE CASCADE,
    arquivo TEXT NOT NULL,
    data_upload TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_equipment_item_imagens_item_id ON equipment_item_imagens(equipment_item_id);

-- locacoes.moto_id não pode mais ser NOT NULL: locações novas (criadas depois
-- desta fase) vão referenciar equipamentos que só existem em equipment_items,
-- não na view "motos" (que só mostra motos_legado) — então moto_id fica NULL
-- para elas. Locações antigas continuam com moto_id preenchido, intacto.
ALTER TABLE locacoes ALTER COLUMN moto_id DROP NOT NULL;
