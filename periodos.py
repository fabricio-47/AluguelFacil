import datetime as dt


def parse_date(s):
    if not s:
        return None
    try:
        return dt.datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def limites_mes(referencia):
    primeiro_dia = referencia.replace(day=1)
    proximo_mes = (primeiro_dia.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return primeiro_dia, proximo_mes


def intervalo_periodo(periodo, inicio_str, fim_str):
    """Retorna (data_inicio, data_fim) inclusivas conforme o filtro escolhido
    (hoje/semana/mes/ano/custom)."""
    hoje = dt.date.today()
    if periodo == "hoje":
        return hoje, hoje
    if periodo == "semana":
        inicio = hoje - dt.timedelta(days=hoje.weekday())
        return inicio, hoje
    if periodo == "ano":
        return hoje.replace(month=1, day=1), hoje
    if periodo == "custom":
        inicio = parse_date(inicio_str) or hoje.replace(day=1)
        fim = parse_date(fim_str) or hoje
        return inicio, fim
    # "mes" (padrão)
    return hoje.replace(day=1), hoje
