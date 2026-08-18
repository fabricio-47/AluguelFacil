-- Migration 018: rastreia quando o comprovante de residência do cliente foi
-- atualizado pela última vez, para a regra de atualização cadastral
-- obrigatória (cliente parado há mais de 90 dias que volta a alugar).
-- Ver docs/superpowers/specs/2026-08-18-atualizacao-cadastral-comprovante-design.md

ALTER TABLE clientes ADD COLUMN IF NOT EXISTS comprovante_residencia_atualizado_em TIMESTAMP;

-- Backfill: clientes que já têm um comprovante de residência arquivado
-- recebem uma data aproximada (não sabemos a data exata do upload
-- original, já que a coluna não existia). Usamos updated_at como melhor
-- proxy disponível, caindo para created_at se updated_at for nulo.
-- Clientes sem comprovante arquivado ficam com a coluna NULL — e isso é
-- correto: eles não têm comprovante nenhum, então já deveriam ser
-- bloqueados na próxima locação até enviarem um.
UPDATE clientes
SET comprovante_residencia_atualizado_em = COALESCE(updated_at, created_at)
WHERE comprovante_residencia_arquivo IS NOT NULL
  AND comprovante_residencia_atualizado_em IS NULL;
