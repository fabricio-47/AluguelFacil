from flask_login import UserMixin

from database import get_db_connection


class User(UserMixin):
    def __init__(self, id, username, email, senha, is_admin, role, company_id, eh_admin_plataforma=False):
        self.id = str(id)  # Flask-Login trabalha com string
        self.username = username
        self.email = email
        self.senha = senha  # hash, nunca texto puro
        self.is_admin = is_admin
        self.role = role
        self.company_id = company_id
        self.eh_admin_plataforma = eh_admin_plataforma

    @staticmethod
    def _from_row(row):
        if row is None:
            return None
        return User(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            senha=row["senha"],
            is_admin=row["is_admin"],
            role=row["role"],
            company_id=row["company_id"],
            eh_admin_plataforma=row.get("eh_admin_plataforma", False),
        )

    @classmethod
    def get_by_id(cls, user_id):
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM usuarios WHERE id = %s", (user_id,))
            row = cur.fetchone()
            cur.close()
            return cls._from_row(row)
        finally:
            conn.close()

    @classmethod
    def get_by_email(cls, email):
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM usuarios WHERE email = %s", (email,))
            row = cur.fetchone()
            cur.close()
            return cls._from_row(row)
        finally:
            conn.close()
