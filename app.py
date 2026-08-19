import os
import psycopg2
from flask import Flask, flash, redirect, render_template, request, url_for

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'chave-secreta-provisoria-aluguelfacil')

def get_db_connection():
    """Estabelece a conexão com o banco de dados local ou produção."""
    # Se houver DATABASE_URL configurada (Render), usa ela. Caso contrário, conecta local.
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        return psycopg2.connect(database_url)
    
    # Configuração padrão do seu ambiente local
    return psycopg2.connect(
        host="localhost",
        database="postgres",
        user="postgres",
        password="password" # Substitua pela sua senha local se houver
    )

@app.route('/')
def index():
    """Página inicial do sistema."""
    return "<h1>SaaS AluguelFácil Rodando com Sucesso!</h1><p>Acesse <a href='/imoveis/cadastrar'>/imoveis/cadastrar</a> ou <a href='/veiculos/cadastrar'>/veiculos/cadastrar</a></p>"

# ==========================================
# 🏢 MÓDULO DE IMÓVEIS (ROTAS)
# ==========================================

@app.route('/imoveis/cadastrar', methods=['GET'])
def tela_cadastro_imovel():
    """Exibe o formulário HTML de cadastro de imóvel."""
    return render_template('imoveis/cadastrar.html')

@app.route('/imoveis/salvar', methods=['POST'])
def salvar_imovel():
    """Recebe os dados do formulário e grava nas tabelas unificadas."""
    endereco = request.form.get('endereco_completo')
    m2 = request.form.get('metro_quadrado')
    quartos = request.form.get('quartos', 0)
    banheiros = request.form.get('banheiros', 0)
    tipo = request.form.get('tipo_imovel')
    iptu = request.form.get('iptu', 0.0)
    condominio = request.form.get('condominio', 0.0)
    
    tenant_id = 1 

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. Insere o item na tabela central unificada pai
        cursor.execute(
            "INSERT INTO rentable_items (tenant_id, item_type, status) VALUES (%s, %s, %s) RETURNING id;",
            (tenant_id, 'imovel', 'disponivel')
        )
        rentable_item_id = cursor.fetchone()[0]

        # 2. Insere os campos específicos na tabela filha de imóveis
        cursor.execute(
            """INSERT INTO imoveis (rentable_item_id, endereco_completo, metro_quadrado, quartos, banheiros, tipo_imovel, iptu, condominio)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s);""",
            (rentable_item_id, endereco, m2, quartos, banheiros, tipo, iptu, condominio)
        )
        conn.commit()
        flash("Imóvel cadastrado com sucesso!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao salvar imóvel: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('tela_cadastro_imovel'))


# ==========================================
# 🚗 MÓDULO DE VEÍCULOS (ROTAS)
# ==========================================

@app.route('/veiculos/cadastrar', methods=['GET'])
def tela_cadastro_veiculo():
    """Exibe o formulário HTML de cadastro de veículo."""
    return render_template('veiculos/cadastrar.html')

@app.route('/veiculos/salvar', methods=['POST'])
def salvar_veiculo():
    """Recebe os dados do formulário e grava nas tabelas unificadas."""
    placa = request.form.get('placa')
    chassi = request.form.get('chassi')
    renavam = request.form.get('renavam')
    km = request.form.get('quilometragem', 0)
    combustivel = request.form.get('combustivel')
    cambio = request.form.get('cambio')
    
    tenant_id = 1

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # 1. Insere o item na tabela central unificada pai
        cursor.execute(
            "INSERT INTO rentable_items (tenant_id, item_type, status) VALUES (%s, %s, %s) RETURNING id;",
            (tenant_id, 'veiculo', 'disponivel')
        )
        rentable_item_id = cursor.fetchone()[0]

        # 2. Insere os campos específicos na tabela filha de veículos
        cursor.execute(
            """INSERT INTO veiculos (rentable_item_id, placa, chassi, renavam, quilometragem, combustivel, cambio)
               VALUES (%s, %s, %s, %s, %s, %s, %s);""",
            (rentable_item_id, placa, chassi, renavam, km, combustivel, cambio)
        )
        conn.commit()
        flash("Veículo cadastrado com sucesso!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao salvar veículo: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('tela_cadastro_veiculo'))
