from validators import validar_forca_senha


def test_rejeita_senha_curta():
    valido, erro = validar_forca_senha("Ab1!23")
    assert valido is False
    assert "8 caracteres" in erro


def test_aceita_senha_forte():
    valido, erro = validar_forca_senha("SenhaForte!2024")
    assert valido is True
    assert erro is None


def test_funciona_sem_dados_pessoais():
    valido, erro = validar_forca_senha("SenhaForte!2024", None)
    assert valido is True
    assert erro is None


def test_rejeita_senha_igual_ao_username():
    valido, erro = validar_forca_senha("testuser_senha", ["testuser_senha", "test@senha.com"])
    assert valido is False
    assert "não pode conter" in erro


def test_rejeita_senha_contendo_email():
    valido, erro = validar_forca_senha("test@senha.com123", ["testuser_senha", "test@senha.com"])
    assert valido is False


def test_rejeita_senha_contida_em_dado_pessoal(): # senha curta demais, mas contida no dado
    valido, erro = validar_forca_senha("senha123", ["senha1234567"])
    assert valido is False


def test_comparacao_com_dados_pessoais_ignora_maiusculas_e_espacos():
    valido, erro = validar_forca_senha("JoaoSilva99!", [" JOAOSILVA99! "])
    assert valido is False


def test_rejeita_senha_da_lista_proibida():
    valido, erro = validar_forca_senha("12345678")
    assert valido is False
    assert "sequências óbvias" in erro


def test_ignora_dados_pessoais_vazios():
    valido, erro = validar_forca_senha("SenhaForte!2024", ["", None, "   "])
    assert valido is True
