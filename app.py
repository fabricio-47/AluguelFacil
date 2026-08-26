Para integrar o SDK atualizado da Google (`google-genai`) no seu aplicativo Flask e remover o uso do modelo legado, você precisa fazer as seguintes atualizações no `app.py`:

1. Instalar a nova biblioteca no seu ambiente terminal:
```bash
pip install google-genai

```


2. Atualizar o arquivo **`app.py`** com a nova inicialização e o modelo `gemini-2.5-flash` ou `gemini-2.5-pro` (o modelo `gemini-3.6-flash` ainda não existe oficialmente no SDK; o padrão recomendado da família 2.5 é o `gemini-2.5-flash`).

Código atualizado com a integração da IA:

```python
import os
import psycopg2
from flask import Flask, flash, redirect, render_template, request, url_for
from google import genai  # Novo SDK oficial do Gemini

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'chave-secreta-provisoria-aluguelfacil')

# Configuração do Cliente Gemini com o novo SDK
# Certifique-se de ter a variável GEMINI_API_KEY no seu ambiente (.env ou SO)
ai_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
AI_MODEL_NAME = "gemini-2.5-flash"


def get_db_connection():
    """Estabelece a conexão com o banco de dados local ou produção."""
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        return psycopg2.connect(database_url)
    
    return psycopg2.connect(
        host="localhost",
        database="postgres",
        user="postgres",
        password="password"
    )

@app.route('/')
def index():
    """Página inicial do sistema."""
    return "<h1>SaaS AluguelFácil Rodando com Sucesso!</h1><p>Acesse o painel geral em: <a href='/inventario'>/inventario</a></p>"


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
        cursor.execute(
            "INSERT INTO rentable_items (tenant_id, item_type, status) VALUES (%s, %s, %s) RETURNING id;",
            (tenant_id, 'imovel', 'disponivel')
        )
        rentable_item_id = cursor.fetchone()[0]

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
        cursor.execute(
            "INSERT INTO rentable_items (tenant_id, item_type, status) VALUES (%s, %s, %s) RETURNING id;",
            (tenant_id, 'veiculo', 'disponivel')
        )
        rentable_item_id = cursor.fetchone()[0]

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


# ==========================================
# 📊 MÓDULO DE INVENTÁRIO (ROTA)
# ==========================================

@app.route('/inventario', methods=['GET'])
def inventario_geral():
    """Busca todos os imóveis e veículos do banco de dados e exibe na tela."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, endereco_completo, metro_quadrado, tipo_imovel FROM imoveis;")
        lista_imoveis = cursor.fetchall()

        cursor.execute("SELECT id, placa, quilometragem, combustivel FROM veiculos;")
        lista_veiculos = cursor.fetchall()
    except Exception as e:
        lista_imoveis = []
        lista_veiculos = []
        flash(f"Erro ao carregar inventário: {str(e)}", "danger")
    finally:
        cursor.close()
        conn.close()

    return render_template('inventario.html', imoveis=lista_imoveis, veiculos=lista_veiculos)


# Exemplo de como chamar o modelo no backend, caso vá adicionar alguma rota com IA
def gerar_descricao_com_ia(prompt_texto):
    response = ai_client.models.generate_content(
        model=AI_MODEL_NAME,
        contents=prompt_texto,
    )
    return response.text

if __name__ == '__main__':
    app.run(debug=True)

```