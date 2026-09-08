-- Migration 024: cadastro publico de empresas (self-signup) + rate limit por IP.
CREATE TABLE IF NOT EXISTS signup_attempts (
    id SERIAL PRIMARY KEY,
    ip VARCHAR(64) NOT NULL,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_signup_attempts_ip_data ON signup_attempts (ip, criado_em);
