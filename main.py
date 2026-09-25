# ferramentas do proprio Py
from flask import Flask, jsonify, request, render_template, session
import calendar
from datetime import date, datetime, timedelta

# O motor de conexão com a Nuvem
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = "iris_cyberpunk_secret_2026" 

# ----------------- COLOQUE SUAS CHAVES AQUI -----------------
SUPABASE_URL = "https://dbtbwqgxirlegjwtpdoa.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRidGJ3cWd4aXJsZWdqd3RwZG9hIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc5MDIyNzg4NiwiZXhwIjoyMTA1ODAzODg2fQ.rkJ9cxiruOxyBGbWsjAjncdfs6GuDbzhpcdKLlkKsa4"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ----------------- SISTEMA DE LOGIN NA NUVEM -----------------
@app.route('/api/sessao', methods=['GET', 'POST', 'DELETE'])
def gerenciar_sessao():
    if request.method == 'GET':
        return jsonify({"usuario": session.get('usuario')})
    
    elif request.method == 'POST':
        pacote = request.json
        nome = pacote.get("usuario", "").strip().lower()
        senha = pacote.get("senha", "").strip()
        
        if not nome or not senha:
            return jsonify({"erro": "Nome e senha são obrigatórios"}), 400
            
        # Puxa o usuário do Supabase
        resposta = supabase.table('usuarios').select("*").eq("nome", nome).execute()
        usuarios_encontrados = resposta.data
        
        if len(usuarios_encontrados) > 0:
            # Usuário existe, checa a senha
            senha_salva = usuarios_encontrados[0]['senha']
            if senha_salva != senha:
                return jsonify({"erro": "Senha incorreta. Acesso negado."}), 401
        else:
            # Usuário novo, cadastra direto no Supabase
            supabase.table('usuarios').insert({"nome": nome, "senha": senha}).execute()
            
        session['usuario'] = nome
        return jsonify({"status": "sucesso"})
        
    elif request.method == 'DELETE':
        session.pop('usuario', None)
        return jsonify({"status": "sucesso"})

@app.route('/')
def home():
    return render_template("index.html")

# ----------------- TAREFAS NA NUVEM POR USUÁRIO -----------------
@app.route('/api/tarefas', methods=['GET'])
def listar_tarefas():
    if 'usuario' not in session: return jsonify([])
    
    usuario = session['usuario']
    
    # Busca SÓ as tarefas deste usuário
    resposta = supabase.table('tarefas').select("*").eq("usuario", usuario).execute()
    tarefas = resposta.data
    
    agora = datetime.now()
    limite_futuro = agora + timedelta(days=40)
    
    precisa_verificar = True
    houve_mudanca = False

    while precisa_verificar:
        precisa_verificar = False
        for tarefa in tarefas:
            if tarefa.get("tipo") == "recorrente" and not tarefa.get("clone_gerado", False):
                try:
                    data_alvo = datetime.strptime(tarefa["data_alvo"], "%d/%m/%Y %H:%M")
                except:
                    continue
                    
                if data_alvo <= limite_futuro:
                    nova_data_calculo = None
                    if tarefa["recorrencia"] == "diaria":
                        nova_data_calculo = data_alvo + timedelta(days=1)
                    elif tarefa["recorrencia"] == "semanal":
                        nova_data_calculo = data_alvo + timedelta(days=7)
                    elif tarefa["recorrencia"] == "mensal":
                        mes_atual = data_alvo.month; ano_atual = data_alvo.year
                        if mes_atual == 12: novo_mes = 1; novo_ano = ano_atual + 1
                        else: novo_mes = mes_atual + 1; novo_ano = ano_atual
                        ultimo_dia = calendar.monthrange(novo_ano, novo_mes)[1]
                        novo_dia = min(data_alvo.day, ultimo_dia)
                        nova_data_calculo = data_alvo.replace(year=novo_ano, month=novo_mes, day=novo_dia)
                    elif tarefa["recorrencia"] == "customizada":
                        if tarefa["custom_unidade"] == "horas": nova_data_calculo = data_alvo + timedelta(hours=tarefa.get("custom_valor", 0))
                        elif tarefa["custom_unidade"] == "dias": nova_data_calculo = data_alvo + timedelta(days=tarefa.get("custom_valor", 0))

                    if nova_data_calculo != None:
                        nova_data_texto = nova_data_calculo.strftime("%d/%m/%Y %H:%M")
                        
                        # Atualiza a tarefa original (marca que já gerou clone)
                        supabase.table('tarefas').update({"clone_gerado": True}).eq("id", tarefa['id']).execute()
                        
                        # Injeta o clone
                        novo_clone = {
                            "usuario": usuario,
                            "titulo": tarefa["titulo"],
                            "tipo": tarefa["tipo"],
                            "data_alvo": nova_data_texto,
                            "concluida": False,
                            "recorrencia": tarefa["recorrencia"],
                            "custom_valor": tarefa.get("custom_valor"),
                            "custom_unidade": tarefa.get("custom_unidade"),
                            "clone_gerado": False
                        }
                        supabase.table('tarefas').insert(novo_clone).execute()
                        
                        houve_mudanca = True
                        precisa_verificar = True
                        
                        # Recarrega da nuvem para o loop ver o novo clone
                        resposta = supabase.table('tarefas').select("*").eq("usuario", usuario).execute()
                        tarefas = resposta.data
                        break 
                        
    if houve_mudanca:
        resposta = supabase.table('tarefas').select("*").eq("usuario", usuario).execute()
        tarefas = resposta.data

    return jsonify(tarefas)

@app.route('/api/tarefas', methods=['POST'])
def receber_nova_tarefas():
    if 'usuario' not in session: return jsonify({"erro": "Acesso negado"}), 401
    usuario = session['usuario']
    dados = request.json

    nova_tarefa = {
        "usuario": usuario,
        "titulo": dados['titulo'],
        "tipo": dados['tipo'],
        "data_alvo": dados['data_alvo'],
        "concluida": False,
        "recorrencia": dados.get('recorrencia'),
        "custom_valor": dados.get('custom_valor'),
        "custom_unidade": dados.get('custom_unidade'),
        "clone_gerado": False
    }
    
    supabase.table('tarefas').insert(nova_tarefa).execute()
    return jsonify({"status": "sucesso"}), 201

@app.route('/api/tarefas/<int:id_tarefa>/toggle', methods=['POST'])
def api_concluir_tarefa(id_tarefa):
    if 'usuario' not in session: return jsonify({"erro": "Acesso negado"}), 401
    usuario = session['usuario']
    
    # Garante que só altera se a tarefa pertencer a este usuário
    resposta = supabase.table('tarefas').select("concluida").eq("id", id_tarefa).eq("usuario", usuario).execute()
    if resposta.data:
        estado_atual = resposta.data[0]['concluida']
        supabase.table('tarefas').update({"concluida": not estado_atual}).eq("id", id_tarefa).execute()
        return jsonify({"status": "sucesso"})

    return jsonify({"erro": "Tarefa não encontrada"}), 404

@app.route('/api/tarefas/<int:id_tarefa>', methods=['DELETE'])
def deletar_tarefa(id_tarefa):
    if 'usuario' not in session: return jsonify({"erro": "Acesso negado"}), 401
    usuario = session['usuario']
    
    # Deleta só se pertencer a este usuário
    supabase.table('tarefas').delete().eq("id", id_tarefa).eq("usuario", usuario).execute()
    return jsonify({"status": "sucesso"})

@app.route('/manifest.json')
def manifest():
    return app.send_static_file('manifest.json')

@app.route('/sw.js')
def service_worker():
    resposta = app.send_static_file('sw.js')
    resposta.headers['Content-Type'] = 'application/javascript'
    return resposta

if __name__ == '__main__':
    print("A iniciar o servidor Iris Multi-usuario na Nuvem...")
    app.run(debug=True, host='0.0.0.0')