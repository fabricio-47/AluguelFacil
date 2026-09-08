-- Migration 021: remove tabelas mortas de uma arquitetura abandonada
-- (veiculos, imoveis, rentable_items).
--
-- Nenhuma rota do sistema le ou escreve nessas tabelas -- confirmado por
-- grep no codigo inteiro antes desta migration. O modulo real de
-- veiculos/imoveis usa equipment_items (migrations 019 e 020).
--
-- Ordem de DROP respeita FK: veiculos e imoveis referenciam rentable_items.

DROP TABLE IF EXISTS veiculos;
DROP TABLE IF EXISTS imoveis;
DROP TABLE IF EXISTS rentable_items;
