from database import get_db_connection

def migrar():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS password_resets (
                id SERIAL PRIMARY KEY,
                usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
                token VARCHAR(255) NOT NULL UNIQUE,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expira_em TIMESTAMP NOT NULL,
                usado BOOLEAN NOT NULL DEFAULT FALSE
            );
        """)
        conn.commit()
        print("Tabela password_resets criada com sucesso!")
    except Exception as e:
        conn.rollback()
        print(f"Erro ao criar tabela: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    migrar()
