-- Permite personalizar o acesso de UM usuário específico, além do padrão
-- por cargo já existente (permissoes_customizadas). Quando existe uma linha
-- aqui para o usuário, ela substitui totalmente o que o cargo dele daria;
-- quando não existe, o usuário continua usando o cargo normalmente.

CREATE TABLE IF NOT EXISTS permissoes_customizadas_usuario (
    usuario_id INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
    permissoes JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
