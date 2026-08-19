from werkzeug.security import check_password_hash, generate_password_hash

from conftest import make_conn

SENHA_ATUAL = "SenhaAtual123!"


def test_troca_senha_com_sucesso(client, login_as, monkeypatch):
    login_as(username="joana", email="joana@empresa.com", senha_hash=generate_password_hash(SENHA_ATUAL))
    conn, cur = make_conn()
    monkeypatch.setattr("routes.configuracoes_routes.get_db_connection", lambda: conn)

    res = client.post("/configuracoes/senha", data={
        "senha_atual": SENHA_ATUAL,
        "nova_senha": "NovaSenhaForte!456",
        "confirmacao_senha": "NovaSenhaForte!456",
    }, follow_redirects=True)

    assert res.status_code == 200
    assert "Senha alterada com sucesso" in res.get_data(as_text=True)

    cur.execute.assert_called_once()
    sql, params = cur.execute.call_args[0]
    assert "UPDATE usuarios SET senha" in sql
    assert check_password_hash(params[0], "NovaSenhaForte!456")
    conn.commit.assert_called_once()


def test_rejeita_senha_atual_incorreta(client, login_as, monkeypatch):
    login_as(senha_hash=generate_password_hash(SENHA_ATUAL))
    conn, cur = make_conn()
    monkeypatch.setattr("routes.configuracoes_routes.get_db_connection", lambda: conn)

    res = client.post("/configuracoes/senha", data={
        "senha_atual": "SenhaErrada",
        "nova_senha": "NovaSenhaForte!456",
        "confirmacao_senha": "NovaSenhaForte!456",
    }, follow_redirects=True)

    assert "Senha atual incorreta" in res.get_data(as_text=True)
    cur.execute.assert_not_called()


def test_rejeita_confirmacao_diferente(client, login_as, monkeypatch):
    login_as(senha_hash=generate_password_hash(SENHA_ATUAL))
    conn, cur = make_conn()
    monkeypatch.setattr("routes.configuracoes_routes.get_db_connection", lambda: conn)

    res = client.post("/configuracoes/senha", data={
        "senha_atual": SENHA_ATUAL,
        "nova_senha": "NovaSenhaForte!456",
        "confirmacao_senha": "OutraCoisa!456",
    }, follow_redirects=True)

    assert "não coincidem" in res.get_data(as_text=True)
    cur.execute.assert_not_called()


def test_rejeita_senha_fraca(client, login_as, monkeypatch):
    login_as(username="joana", email="joana@empresa.com", senha_hash=generate_password_hash(SENHA_ATUAL))
    conn, cur = make_conn()
    monkeypatch.setattr("routes.configuracoes_routes.get_db_connection", lambda: conn)

    res = client.post("/configuracoes/senha", data={
        "senha_atual": SENHA_ATUAL,
        "nova_senha": "1234567",
        "confirmacao_senha": "1234567",
    }, follow_redirects=True)

    assert "8 caracteres" in res.get_data(as_text=True)
    cur.execute.assert_not_called()


def test_rejeita_senha_igual_ao_username(client, login_as, monkeypatch):
    login_as(username="joana_admin", email="joana@empresa.com", senha_hash=generate_password_hash(SENHA_ATUAL))
    conn, cur = make_conn()
    monkeypatch.setattr("routes.configuracoes_routes.get_db_connection", lambda: conn)

    res = client.post("/configuracoes/senha", data={
        "senha_atual": SENHA_ATUAL,
        "nova_senha": "joana_admin",
        "confirmacao_senha": "joana_admin",
    }, follow_redirects=True)

    assert "não pode conter" in res.get_data(as_text=True)
    cur.execute.assert_not_called()


def test_exige_login(client):
    res = client.post("/configuracoes/senha", data={
        "senha_atual": "x", "nova_senha": "y", "confirmacao_senha": "y",
    })
    assert res.status_code == 302
    assert "/auth/login" in res.headers["Location"]
