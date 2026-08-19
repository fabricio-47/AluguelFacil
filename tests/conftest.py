import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app as flask_app  # noqa: E402


def make_conn(fetchone=None, fetchall=None):
    """Cria uma conexão psycopg2 falsa: cursor().fetchone()/fetchall() retornam
    os valores dados, sem tocar em banco nenhum."""
    cur = MagicMock()
    cur.fetchone.return_value = fetchone
    cur.fetchall.return_value = fetchall if fetchall is not None else []
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


@pytest.fixture
def app():
    flask_app.config.update(TESTING=True, SECRET_KEY="test-secret")
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def login_as(client, monkeypatch):
    """Loga um usuário de teste na sessão do client (sem tocar o banco de
    verdade): o carregador de usuário do Flask-Login (models.user.get_by_id)
    é mockado para sempre devolver essa linha, em qualquer request."""

    def _login(*, id=1, username="usuarioteste", email="teste@empresa.com",
               role="admin_locadora", company_id=1, senha_hash="hash-fake", is_admin=False):
        row = {
            "id": id, "username": username, "email": email,
            "senha": senha_hash, "is_admin": is_admin,
            "role": role, "company_id": company_id, "eh_admin_plataforma": False,
        }
        conn, _ = make_conn(fetchone=row)
        monkeypatch.setattr("models.user.get_db_connection", lambda: conn)

        with client.session_transaction() as sess:
            sess["_user_id"] = str(id)
            sess["_fresh"] = True

        return row

    return _login
