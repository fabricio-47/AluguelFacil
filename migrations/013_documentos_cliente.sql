-- Migration 013: 3 slots de imagem por cliente (documento frente/verso +
-- comprovante de residência), substituindo o campo solto habilitacao_arquivo
-- que nunca teve rota de upload funcional.
--
-- Só estrutura (DDL). Idempotente. Aditiva na prática — o DROP COLUMN é de
-- uma coluna que nunca foi preenchida por nenhuma rota em produção.

ALTER TABLE clientes ADD COLUMN IF NOT EXISTS doc_frente_arquivo VARCHAR(255);
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS doc_verso_arquivo VARCHAR(255);
ALTER TABLE clientes ADD COLUMN IF NOT EXISTS comprovante_residencia_arquivo VARCHAR(255);

ALTER TABLE clientes DROP COLUMN IF EXISTS habilitacao_arquivo;
