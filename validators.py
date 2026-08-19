SENHAS_PROIBIDAS = {"12345678", "123456", "password", "mudar123", "senha123"}


def validar_forca_senha(senha, dados_pessoais=None):
    """Retorna (True, None) se válida, ou (False, "Mensagem de erro") se inválida.

    dados_pessoais: lista opcional de strings (username, email, nome...) que a
    senha não pode conter nem estar contida em.
    """
    if len(senha) < 8:
        return False, "A senha deve ter pelo menos 8 caracteres."

    senha_lower = senha.lower()

    for dado in dados_pessoais or ():
        dado_lower = (dado or "").strip().lower()
        if dado_lower and (dado_lower in senha_lower or senha_lower in dado_lower):
            return False, "A senha não pode conter seu nome, usuário ou e-mail."

    if senha_lower in SENHAS_PROIBIDAS:
        return False, "Escolha uma senha mais segura. Evite sequências óbvias."

    return True, None
