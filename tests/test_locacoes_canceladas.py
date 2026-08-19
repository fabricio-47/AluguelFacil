import datetime as dt

from conftest import make_conn


def test_pagina_de_canceladas_exibe_as_locacoes_canceladas(client, login_as, monkeypatch):
    login_as(role="admin_locadora", company_id=1)

    locacao_cancelada = {
        "id": 321,
        "data_inicio": dt.date(2026, 1, 10),
        "data_fim": None,
        "valor": 1500.0,
        "frequencia_pagamento": "monthly",
        "pagamento_status": "RECEIVED",
        "valor_pago": 1500.0,
        "asaas_subscription_id": None,
        "asaas_payment_id": None,
        "boleto_url": None,
        "contrato_arquivo": None,
        "cliente_nome": "Cliente Teste Cancelamento",
        "moto_modelo": "CG 160",
        "moto_placa": "ABC-1234",
    }
    conn, cur = make_conn(fetchall=[locacao_cancelada])
    monkeypatch.setattr("routes.locacoes_routes.get_db_connection", lambda: conn)

    res = client.get("/locacoes/canceladas")

    assert res.status_code == 200
    corpo = res.get_data(as_text=True)
    assert "Cliente Teste Cancelamento" in corpo
    assert "CG 160" in corpo

    (sql,) = cur.execute.call_args[0]
    assert "l.cancelado = TRUE" in sql


def test_pagina_renderiza_com_contrato_e_boleto_avulso(client, login_as, monkeypatch):
    login_as(role="admin_locadora", company_id=1)

    locacao_cancelada = {
        "id": 322,
        "data_inicio": dt.date(2026, 2, 1),
        "data_fim": dt.date(2026, 2, 20),
        "valor": 800.0,
        "frequencia_pagamento": "weekly",
        "pagamento_status": "PENDING",
        "valor_pago": 0,
        "asaas_subscription_id": None,
        "asaas_payment_id": "pay_123456789",
        "boleto_url": "https://asaas.com/boleto/xyz",
        "contrato_arquivo": "contrato-322.pdf",
        "cliente_nome": "Outro Cliente",
        "moto_modelo": "Biz 125",
        "moto_placa": "XYZ-9876",
    }
    conn, _cur = make_conn(fetchall=[locacao_cancelada])
    monkeypatch.setattr("routes.locacoes_routes.get_db_connection", lambda: conn)

    res = client.get("/locacoes/canceladas")

    assert res.status_code == 200
    corpo = res.get_data(as_text=True)
    assert "Outro Cliente" in corpo
    assert "/locacoes/contrato/322/pdf" in corpo
    assert "https://asaas.com/boleto/xyz" in corpo
    assert "Pagamento Único" in corpo
