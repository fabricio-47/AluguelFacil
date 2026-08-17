import os

from werkzeug.security import generate_password_hash

from database import get_db_connection


def create_admin():
    username = os.environ.get("ADMIN_USERNAME", "admin")
    email = os.environ.get("ADMIN_EMAIL", "admin@admin.com")
    senha = os.environ.get("ADMIN_PASSWORD")

    if not senha:
        print("ERRO: defina a variável de ambiente ADMIN_PASSWORD com a senha do admin antes de rodar este script.")
        return

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Remove admin antigo (se já existia com esse username/email)
        cur.execute("DELETE FROM usuarios WHERE username = %s OR email = %s", (username, email))

        cur.execute(
            """
            INSERT INTO usuarios (username, email, senha, is_admin, role)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (username, email, generate_password_hash(senha), True, "super_admin")
        )
        conn.commit()
        print(f"Usuário admin criado -> username: {username} | email: {email} | role: super_admin")
    except Exception as e:
        conn.rollback()
        print(f"Erro ao criar admin: {e}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    create_admin()
