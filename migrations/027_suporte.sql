-- Sistema de suporte (chat/ticket) entre clientes do portal e a locadora.

CREATE TABLE IF NOT EXISTS suporte_tickets (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    cliente_id INTEGER NOT NULL REFERENCES clientes(id),
    assunto VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'aberto',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

ALTER TABLE suporte_tickets DROP CONSTRAINT IF EXISTS suporte_tickets_status_check;
ALTER TABLE suporte_tickets ADD CONSTRAINT suporte_tickets_status_check
    CHECK (status IN ('aberto', 'respondido', 'fechado'));

CREATE INDEX IF NOT EXISTS idx_suporte_tickets_company_id ON suporte_tickets(company_id);
CREATE INDEX IF NOT EXISTS idx_suporte_tickets_cliente_id ON suporte_tickets(cliente_id);
CREATE INDEX IF NOT EXISTS idx_suporte_tickets_status ON suporte_tickets(status);

CREATE TABLE IF NOT EXISTS suporte_mensagens (
    id SERIAL PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES suporte_tickets(id) ON DELETE CASCADE,
    autor_tipo VARCHAR(20) NOT NULL,
    autor_cliente_id INTEGER REFERENCES clientes(id),
    autor_usuario_id INTEGER REFERENCES usuarios(id),
    mensagem TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

ALTER TABLE suporte_mensagens DROP CONSTRAINT IF EXISTS suporte_mensagens_autor_tipo_check;
ALTER TABLE suporte_mensagens ADD CONSTRAINT suporte_mensagens_autor_tipo_check
    CHECK (autor_tipo IN ('cliente', 'funcionario'));

CREATE INDEX IF NOT EXISTS idx_suporte_mensagens_ticket_id ON suporte_mensagens(ticket_id);
