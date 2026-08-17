from functools import wraps

from flask import session, flash, redirect, url_for

from database import get_db_connection

SESSION_KEY = "cliente_id"


def login_cliente(cliente_id):
    session[SESSION_KEY] = cliente_id


def logout_cliente():
    session.pop(SESSION_KEY, None)


def cliente_atual():
    """Retorna o dict do cliente logado no portal, ou None. Não tem relação
    nenhuma com o current_user do Flask-Login (funcionários) — chave de
    sessão própria, checagem própria."""
    cliente_id = session.get(SESSION_KEY)
    if not cliente_id:
        return None
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM clientes WHERE id=%s", (cliente_id,))
        return cur.fetchone()
    finally:
        conn.close()


def requer_login_cliente(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get(SESSION_KEY):
            flash("Faça login para acessar o portal.", "info")
            return redirect(url_for("portal.login"))
        return f(*args, **kwargs)
    return wrapped
