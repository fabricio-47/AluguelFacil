def calcular_multa(data_fim, data_referencia, valor_locacao, valor_diaria_equipamento, config):
    """
    Calcula dias de atraso e multa entre data_fim (planejada) e data_referencia
    (hoje, se a locação ainda estiver ativa; ou a data_fim original capturada
    antes do cancelamento, se já finalizada).

    config: dict com 'tipo', 'valor_fixo', 'percentual', 'juros_dia_percentual', 'ativo'
            (ou None se a empresa não tiver configurado nenhuma regra).

    Retorna dict: dias_atraso, valor_multa_base, valor_juros, valor_multa_total, aviso.
    """
    resultado = {
        "dias_atraso": 0,
        "valor_multa_base": 0.0,
        "valor_juros": 0.0,
        "valor_multa_total": 0.0,
        "aviso": None,
    }

    if not data_fim or not data_referencia or data_referencia <= data_fim:
        return resultado

    dias_atraso = (data_referencia - data_fim).days
    resultado["dias_atraso"] = dias_atraso

    if not config or not config.get("ativo"):
        resultado["aviso"] = "Sem regra de multa configurada para esta empresa."
        return resultado

    valor_locacao = float(valor_locacao or 0)
    tipo = config.get("tipo")

    if tipo == "fixa":
        valor_fixo = config.get("valor_fixo")
        if valor_fixo is None:
            resultado["aviso"] = "Regra de multa fixa configurada sem valor_fixo definido."
        else:
            resultado["valor_multa_base"] = float(valor_fixo) * dias_atraso

    elif tipo == "percentual":
        percentual = config.get("percentual")
        if percentual is None:
            resultado["aviso"] = "Regra de multa percentual configurada sem percentual definido."
        else:
            resultado["valor_multa_base"] = (valor_locacao * float(percentual) / 100) * dias_atraso

    elif tipo == "nova_diaria":
        if valor_diaria_equipamento is None:
            resultado["aviso"] = "Regra 'nova diária' configurada, mas o equipamento não tem valor de diária cadastrado."
        else:
            resultado["valor_multa_base"] = float(valor_diaria_equipamento) * dias_atraso

    juros_dia_percentual = config.get("juros_dia_percentual")
    if juros_dia_percentual:
        resultado["valor_juros"] = valor_locacao * (float(juros_dia_percentual) / 100) * dias_atraso

    resultado["valor_multa_total"] = resultado["valor_multa_base"] + resultado["valor_juros"]
    return resultado
