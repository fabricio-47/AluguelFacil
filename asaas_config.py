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
    Se a empresa não tiver config própria (ou estiver inativa), cai pra
    config global (Config.ASAAS_API_KEY/ASAAS_BASE_URL/ASAAS_WEBHOOK_SECRET).
    """
    cur.execute("SELECT * FROM config_asaas WHERE company_id=%s AND ativo=TRUE", (company_id,))
    row = cur.fetchone()
    if row and row["api_key_cifrada"]:
        return {
            "api_key": decifrar(row["api_key_cifrada"]),
            "base_url": BASE_URL_POR_AMBIENTE.get(row["ambiente"], BASE_URL_POR_AMBIENTE["sandbox"]),
            "webhook_secret": decifrar(row["webhook_secret_cifrado"]) if row["webhook_secret_cifrado"] else None,
        }
    return {
        "api_key": Config.ASAAS_API_KEY,
        "base_url": Config.ASAAS_BASE_URL,
        "webhook_secret": Config.ASAAS_WEBHOOK_SECRET,
    }


def todos_webhook_secrets_validos(cur):
    """Conjunto de todos os webhook secrets válidos (todas as empresas
    configuradas + o global), já decifrados, pra validar requests recebidos."""
    secrets = set()
    if Config.ASAAS_WEBHOOK_SECRET:
        secrets.add(Config.ASAAS_WEBHOOK_SECRET.strip())
    cur.execute(
        "SELECT webhook_secret_cifrado FROM config_asaas WHERE ativo=TRUE AND webhook_secret_cifrado IS NOT NULL"
    )
    for row in cur.fetchall():
        valor = decifrar(row["webhook_secret_cifrado"])
        if valor:
            secrets.add(valor.strip())
    return secrets
