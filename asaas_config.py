from cryptography.fernet import Fernet

from config import Config

BASE_URL_POR_AMBIENTE = {
    "sandbox": "https://sandbox.asaas.com/api/v3",
    "producao": "https://api.asaas.com/v3",
}


def _fernet():
    if not Config.APP_ENCRYPTION_KEY:
        raise RuntimeError("APP_ENCRYPTION_KEY ausente — infraestrutura de criptografia não configurada.")
    return Fernet(Config.APP_ENCRYPTION_KEY.encode())


def cifrar(texto):
    if not texto:
        return None
    return _fernet().encrypt(texto.encode()).decode()


def decifrar(texto_cifrado):
    if not texto_cifrado:
        return None
    return _fernet().decrypt(texto_cifrado.encode()).decode()


def obter_config_asaas(cur, company_id):
    """
    Retorna as credenciais Asaas da empresa: {api_key, base_url, webhook_secret}.
    Se a empresa não tiver config própria (ou estiver inativa, ou o valor
    cifrado não puder ser decifrado), cai pra config global
    (Config.ASAAS_API_KEY/ASAAS_BASE_URL/ASAAS_WEBHOOK_SECRET).
    """
    cur.execute("SELECT * FROM config_asaas WHERE company_id=%s AND ativo=TRUE", (company_id,))
    row = cur.fetchone()
    if row and row["api_key_cifrada"]:
        try:
            return {
                "api_key": decifrar(row["api_key_cifrada"]),
                "base_url": BASE_URL_POR_AMBIENTE.get(row["ambiente"], BASE_URL_POR_AMBIENTE["sandbox"]),
                "webhook_secret": decifrar(row["webhook_secret_cifrado"]) if row["webhook_secret_cifrado"] else None,
            }
        except Exception:
            pass  # cai pro fallback global abaixo
    return {
        "api_key": Config.ASAAS_API_KEY,
        "base_url": Config.ASAAS_BASE_URL,
        "webhook_secret": Config.ASAAS_WEBHOOK_SECRET,
    }


def todos_webhook_secrets_validos(cur):
    """Mapa de secret válido -> company_id que o configurou (None pro secret
    global, sem escopo), já decifrados, pra validar e escopar requests
    recebidos no webhook. Uma linha com secret corrompido/não-decifrável é
    ignorada em vez de derrubar a função inteira."""
    secrets = {}
    if Config.ASAAS_WEBHOOK_SECRET:
        secrets[Config.ASAAS_WEBHOOK_SECRET.strip()] = None
    cur.execute(
        "SELECT company_id, webhook_secret_cifrado FROM config_asaas WHERE ativo=TRUE AND webhook_secret_cifrado IS NOT NULL"
    )
    for row in cur.fetchall():
        try:
            valor = decifrar(row["webhook_secret_cifrado"])
        except Exception:
            continue
        if valor:
            secrets[valor.strip()] = row["company_id"]
    return secrets
