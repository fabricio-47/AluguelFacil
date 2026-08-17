-- Migration 014: 4º slot de imagem do cliente — foto/retrato (separado dos
-- 3 documentos da migration 013).
--
-- Só estrutura (DDL). Idempotente. Aditiva.

ALTER TABLE clientes ADD COLUMN IF NOT EXISTS foto_cliente_arquivo VARCHAR(255);
