from unittest.mock import ANY

from conftest import make_conn


def test_atendente_nao_pode_resetar_senha(client, login_as, monkeypatch):
    login_as(role="atendente", company_id=1)

    # atendente/vendedor não têm GERENCIAR_USUARIOS: tem_permissao() consulta
    # permissoes_customizadas antes de cair no default de PERMISSOES_POR_ROLE.
    perm_conn, _ = make_conn(fetchone=None)
    monkeypatch.setattr("permissions.get_db_connection", lambda: perm_conn)

    route_conn, route_cur = make_conn()
    monkeypatch.setattr("routes.usuarios_routes.get_db_connection", lambda: route_conn)

    res = client.post("/usuarios/42/resetar-senha")

    assert res.status_code == 302
    route_cur.execute.assert_not_called()

    with client.session_transaction() as sess:
        flashes = sess.get("_flashes", [])
    assert any("permiss" in msg for _, msg in flashes)


def test_admin_pode_resetar_senha(client, login_as, monkeypatch):
    login_as(role="admin_locadora", company_id=1)  # acesso total, sem consulta extra ao banco

    alvo = {"id": 42, "username": "func_alvo", "company_id": 1}
    route_conn, route_cur = make_conn(fetchone=alvo)
    monkeypatch.setattr("routes.usuarios_routes.get_db_connection", lambda: route_conn)

    res = client.post("/usuarios/42/resetar-senha", follow_redirects=True)

    assert res.status_code == 200
    route_cur.execute.assert_any_call("UPDATE usuarios SET senha=%s WHERE id=%s", (ANY, 42))
    route_conn.commit.assert_called_once()

    corpo = res.get_data(as_text=True)
    assert "func_alvo" in corpo
    assert "só será exibida desta vez" in corpo or "não será exibida novamente" in corpo


def test_nao_reseta_senha_de_usuario_de_outra_empresa(client, login_as, monkeypatch):
    login_as(role="admin_locadora", company_id=1)

    alvo_de_outra_empresa = {"id": 99, "username": "outro", "company_id": 2}
    route_conn, route_cur = make_conn(fetchone=alvo_de_outra_empresa)
    monkeypatch.setattr("routes.usuarios_routes.get_db_connection", lambda: route_conn)

    res = client.post("/usuarios/99/resetar-senha")

    assert res.status_code == 302
    route_cur.execute.assert_called_once()  # só o SELECT, sem UPDATE

    with client.session_transaction() as sess:
        flashes = sess.get("_flashes", [])
    assert any("não encontrado" in msg for _, msg in flashes)


def test_senha_resetada_so_aparece_uma_vez(client, login_as, monkeypatch):
    login_as(role="admin_locadora", company_id=1)

    alvo = {"id": 42, "username": "func_alvo", "company_id": 1}
    route_conn, _ = make_conn(fetchone=alvo)
    monkeypatch.setattr("routes.usuarios_routes.get_db_connection", lambda: route_conn)

    client.post("/usuarios/42/resetar-senha")

    primeira = client.get("/usuarios/senha-resetada")
    assert "func_alvo" in primeira.get_data(as_text=True)

    segunda = client.get("/usuarios/senha-resetada", follow_redirects=True)
    assert "func_alvo" not in segunda.get_data(as_text=True)
