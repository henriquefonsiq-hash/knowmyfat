import streamlit as st
import pandas as pd
import json
import os
import sys
from google import genai
from PIL import Image
import socket
import PyPDF2

# ===== CONSTANTES & CONFIGURAÇÕES =====
def get_base_path():
    if getattr(sys, 'frozen', False):
        # Se for executável, usa a pasta do .exe
        return os.path.dirname(sys.executable)
    # Se for script, usa a pasta do app.py
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_path()
BOOKS_DIR = os.path.join(BASE_DIR, "books")
DATA_DIR = os.path.join(BASE_DIR, "data")
MODEL_NAME = "gemini-flash-latest" # Corrigido após teste de conectividade

# Lógica de API Key (Prioriza st.secrets para Nuvem, fallback para local)
if "GEMINI_API_KEY" in st.secrets:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
else:
    # Caso queira usar localmente sem segredos, coloque sua chave aqui:
    GEMINI_API_KEY = 'AIzaSyAIeIhGw_exzkQLl5Pq9J8wCoBT_k1Yblk'

def ensure_books_dir():
    os.makedirs(BOOKS_DIR, exist_ok=True)

def extract_text_from_pdfs():
    text = ""
    ensure_books_dir()
    for filename in os.listdir(BOOKS_DIR):
        if filename.endswith(".pdf"):
            path = os.path.join(BOOKS_DIR, filename)
            try:
                with open(path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
            except Exception as e:
                print(f"Erro ao ler {filename}: {e}")
    return text

def is_online():
    try:
        # Tenta conectar ao DNS do Google para verificar internet
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        return True
    except OSError:
        return False

# Configuração da Página
st.set_page_config(
    page_title="NutriPlan & Gordura Corporal",
    page_icon="💪",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ===== CONSTANTES & DADOS INICIAIS =====
DEFAULT_ING = [
    {"id": 1, "name": "Frango (Peito Grelhado)", "protein": 31.0, "carbs": 0.0, "fat": 3.6, "category": "Prot", "micro": "Rico em Selênio e B6"},
    {"id": 2, "name": "Arroz Branco Cozido", "protein": 2.5, "carbs": 28.0, "fat": 0.2, "category": "Carb", "micro": "Fonte de energia"},
    {"id": 3, "name": "Ovo Cozido", "protein": 13.0, "carbs": 1.1, "fat": 11.0, "category": "Prot/Gord", "micro": "Vitamina D e Colina"},
    {"id": 4, "name": "Azeite de Oliva", "protein": 0.0, "carbs": 0.0, "fat": 100.0, "category": "Gord", "micro": "Gorduras Saudáveis"},
    {"id": 5, "name": "Feijão Cozido", "protein": 4.8, "carbs": 13.6, "fat": 0.5, "category": "Prot/Carb", "micro": "Fibras e Ferro"}
]

# Caminhos de arquivos para persistência local simples
DATA_DIR = "data"
ING_FILE = os.path.join(DATA_DIR, "ingredients.json")
HIST_FILE = os.path.join(DATA_DIR, "history.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

from typing import List, Dict, Any, TypedDict, cast

class MacroDict(TypedDict):
    p: float
    c: float
    f: float

class MealItem(TypedDict):
    name: str
    g: int

class MealDict(TypedDict):
    name: str
    items: List[MealItem]
    macros: MacroDict

# ===== INICIALIZAÇÃO DE ESTADO =====
def init_state():
    ensure_data_dir()
    
    # Ingressos
    if 'ingredients' not in st.session_state:
        if os.path.exists(ING_FILE):
            with open(ING_FILE, "r", encoding="utf-8") as f:
                st.session_state['ingredients'] = json.load(f)
        else:
            st.session_state['ingredients'] = DEFAULT_ING
            
    # Histórico de Peso
    if 'weight_history' not in st.session_state:
        if os.path.exists(HIST_FILE):
            with open(HIST_FILE, "r", encoding="utf-8") as f:
                st.session_state['weight_history'] = json.load(f)
        else:
            st.session_state['weight_history'] = []
            
    # Configurações TDEE
    if 'settings' not in st.session_state:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                st.session_state['settings'] = json.load(f)
        else:
            st.session_state['settings'] = {"target_cals": 0}

def save_data(key, filename):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(st.session_state[key], f, ensure_ascii=False, indent=4)

init_state()

# ===== TELA PRINCIPAL =====
st.title("💪 NutriPlan & Avaliação Física")
st.markdown("Gerador de dietas inteligente e monitor de gordura corporal por IA.")

tab_diet, tab_foods, tab_progress, tab_bf, tab_chat = st.tabs(["🍽️ Dieta", "🍎 Alimentos", "📈 Progresso", "🔬 Gordura Corporal", "💬 Chat Nutricional"])

with tab_diet:
    st.header("Gerador de Dieta")
    
    # --- CALCULADORA TDEE ---
    with st.expander("⚙️ Configuração & Calculadora de Macros", expanded=st.session_state['settings']['target_cals'] == 0):
        c_col1, c_col2 = st.columns(2)
        with c_col1:
            peso_atual = st.number_input("Seu Peso Atual (KG)", value=100.0, step=0.1, key="diet_peso")
            idade = st.number_input("Idade", value=25, step=1)
            altura_calc = st.number_input("Altura (cm)", value=175.0, step=0.1, key="diet_altura")
            genero_calc = st.selectbox("Gênero", ["Masculino", "Feminino"], key="diet_genero")
            
        with c_col2:
            atividade = st.selectbox("Nível de Atividade", [
                "Sedentário (Pouco/Nenhum)", 
                "Leve (1-3 dias/semana)", 
                "Moderado (3-5 dias/semana)", 
                "Intenso (6-7 dias/semana)"
            ])
            objetivo = st.selectbox("Objetivo", [
                "Perda de Peso (-500 kcal)", 
                "Manutenção", 
                "Ganho de Massa (+300 kcal)"
            ])
            
            # Map factors
            act_map = {"Sedentário (Pouco/Nenhum)": 1.2, "Leve (1-3 dias/semana)": 1.375, "Moderado (3-5 dias/semana)": 1.55, "Intenso (6-7 dias/semana)": 1.725}
            
            if st.button("Calcular e Aplicar Macros", width="stretch"):
                # Mifflin-St Jeor
                bmr = (10 * peso_atual) + (6.25 * altura_calc) - (5 * idade)
                bmr = bmr + 5 if genero_calc == "Masculino" else bmr - 161
                
                tdee = bmr * act_map[atividade]
                if "Perda de Peso" in objetivo: tdee -= 500
                elif "Ganho" in objetivo: tdee += 300
                
                st.session_state['settings']['target_cals'] = tdee
                
                # Split: 30% Prot, 45% Carb, 25% Fat
                p_kg = (tdee * 0.3) / 4 / peso_atual
                c_kg = (tdee * 0.45) / 4 / peso_atual
                f_kg = (tdee * 0.25) / 9 / peso_atual
                
                st.session_state['settings']['p_kg'] = p_kg
                st.session_state['settings']['c_kg'] = c_kg
                st.session_state['settings']['f_kg'] = f_kg
                save_data('settings', SETTINGS_FILE)
                st.success(f"Meta aplicada: **{tdee:.0f} kcal**")
                st.rerun()

    # --- INPUTS DA DIETA ---
    target_cals = st.session_state['settings'].get('target_cals', 0)
    if target_cals > 0:
        st.info(f"🎯 Sua meta calórica atual: **{target_cals:.0f} kcal**")
        
    m_col1, m_col2, m_col3 = st.columns(3)
    p_kg = st.session_state['settings'].get('p_kg', 2.0)
    c_kg = st.session_state['settings'].get('c_kg', 4.0)
    f_kg = st.session_state['settings'].get('f_kg', 1.0)
    
    with m_col1: p_input = st.number_input("Proteínas (g/kg)", value=float(f"{p_kg:.1f}"), step=0.1)
    with m_col2: c_input = st.number_input("Carboidratos (g/kg)", value=float(f"{c_kg:.1f}"), step=0.1)
    with m_col3: f_input = st.number_input("Gorduras (g/kg)", value=float(f"{f_kg:.1f}"), step=0.1)
    peso_input = st.number_input("Peso Atual p/ Cálculo (KG)", value=100.0, step=0.1)
    
    # --- SELEÇÃO DE ALIMENTOS ---
    st.subheader("🛒 Selecionar Alimentos Base")
    opcoes_ing = {ing['name']: ing for ing in st.session_state['ingredients']}
    ingredientes_selecionados = st.multiselect(
        "Escolha os ingredientes que deseja incluir na dieta",
        options=list(opcoes_ing.keys()),
        default=list(opcoes_ing.keys())[:5]
    )
    
    # --- GERAÇÃO DA DIETA ---
    if st.button("🚀 Gerar Dieta Completa", type="primary", width="stretch"):
        if not ingredientes_selecionados:
            st.warning("Selecione pelo menos um alimento.")
        else:
            p_total = peso_input * p_input
            c_total = peso_input * c_input
            f_total = peso_input * f_input
            
            pool = [opcoes_ing[nome] for nome in ingredientes_selecionados]
            import random
            
            meals: List[MealDict] = []
            target_macros = {'p': p_total, 'c': c_total, 'f': f_total}
            
            for i in range(1, 5): # 4 refeições
                tar = {'p': p_total / 4, 'c': c_total / 4, 'f': f_total / 4}
                meal: MealDict = {'name': f"Refeição {i}", 'items': [], 'macros': {'p': 0.0, 'c': 0.0, 'f': 0.0}}
                
                def add_item(m: MealDict, ing: dict, g_amount: float):
                    if g_amount < 3: return
                    add_p = (ing['protein'] * g_amount) / 100
                    add_c = (ing['carbs'] * g_amount) / 100
                    add_f = (ing['fat'] * g_amount) / 100
                    
                    m['items'].append({'name': str(ing['name']), 'g': int(g_amount)})
                    
                    m['macros']['p'] += add_p
                    m['macros']['c'] += add_c
                    m['macros']['f'] += add_f
                    
                    target_macros['p'] -= add_p
                    target_macros['c'] -= add_c
                    target_macros['f'] -= add_f

                prots = [x for x in pool if 'Prot' in x['category']]
                p_src = random.choice(prots) if prots else pool[0]
                amount = (tar['p'] / p_src['protein']) * 100 if p_src['protein'] > 0 else 0
                add_item(meal, p_src, amount)

                carbs = [x for x in pool if 'Carb' in x['category']]
                if tar['c'] > 5:
                    c_src = random.choice(carbs) if carbs else pool[0]
                    amount = (tar['c'] / c_src['carbs']) * 100 if c_src['carbs'] > 0 else 0
                    add_item(meal, c_src, amount)
                    
                fats = [x for x in pool if 'Gord' in x['category']]
                if tar['f'] > 2:
                    f_src = random.choice(fats) if fats else (pool[0])
                    amount = (tar['f'] / f_src['fat']) * 100 if f_src['fat'] > 0 else 0
                    add_item(meal, f_src, amount)
                    
                meals.append(meal)
                
            # Exibir Dieta
            st.divider()
            st.subheader("📋 Sua Dieta Gerada")
            
            total_kcal = (p_total * 4) + (c_total * 4) + (f_total * 9)
            st.info(f"**Total Diário:** {p_total:.0f}g Proteínas | {c_total:.0f}g Carboidratos | {f_total:.0f}g Gorduras | **{total_kcal:.0f} kcal**")
            
            for m in meals:
                meal_kcal = (m['macros']['p'] * 4.0) + (m['macros']['c'] * 4.0) + (m['macros']['f'] * 9.0)
                with st.container(border=True):
                    st.markdown(f"#### {m['name']} - **{meal_kcal:.0f} kcal**")
                    st.caption(f"{m['macros']['p']:.0f}P | {m['macros']['c']:.0f}C | {m['macros']['f']:.0f}G")
                    for item in m['items']:
                        st.markdown(f"- **{item['g']}g** {item['name']}")

with tab_foods:
    st.header("Gerenciamento de Alimentos")
    st.markdown("Adicione, edite ou remova ingredientes da sua base de dados.")
    
    # Exibir banco de dados atual
    df = pd.DataFrame(st.session_state['ingredients'])
    
    # Interface para adicionar novo alimento
    with st.expander("➕ Adicionar Novo Alimento", expanded=False):
        with st.form("form_novo_alimento", clear_on_submit=True):
            cols = st.columns([2, 1, 1, 1])
            new_name = cols[0].text_input("Nome do Alimento")
            new_p = cols[1].number_input("Proteínas (g/100g)", min_value=0.0, step=0.1)
            new_c = cols[2].number_input("Carboidratos (g/100g)", min_value=0.0, step=0.1)
            new_f = cols[3].number_input("Gorduras (g/100g)", min_value=0.0, step=0.1)
            
            cols2 = st.columns([1, 2])
            new_cat = cols2[0].selectbox("Categoria Predominante", ["Proteínas", "Carboidratos", "Gorduras", "Proteínas/Carboidratos", "Proteínas/Gorduras"])
            new_micro = cols2[1].text_input("Micronutrientes (Opcional)")
            
            if st.form_submit_button("Salvar Alimento"):
                if new_name:
                    new_id = max([i.get('id', 0) for i in st.session_state['ingredients']] + [0]) + 1
                    novo_ingrediente = {
                        "id": new_id,
                        "name": new_name,
                        "protein": new_p,
                        "carbs": new_c,
                        "fat": new_f,
                        "category": new_cat,
                        "micro": new_micro
                    }
                    st.session_state['ingredients'].append(novo_ingrediente)
                    save_data('ingredients', ING_FILE)
                    st.success(f"Alimento '{new_name}' adicionado com sucesso!")
                    st.rerun()
                else:
                    st.error("O nome do alimento é obrigatório.")

    # Tabela editável
    st.subheader("Base de Dados")
    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        column_config={
            "id": st.column_config.NumberColumn(disabled=True),
        },
        key="data_editor_ingredients"
    )

    if st.button("💾 Salvar Alterações da Tabela"):
        st.session_state['ingredients'] = edited_df.to_dict('records')
        save_data('ingredients', ING_FILE)
        st.success("Base de dados atualizada.")

with tab_progress:
    st.header("Histórico de Progresso 📈")
    
    # Form to add entry
    with st.form("form_peso", clear_on_submit=True):
        col_data, col_peso = st.columns(2)
        import datetime
        data_registro = col_data.date_input("Data do Registro", datetime.date.today())
        peso_registro = col_peso.number_input("Peso (KG)", value=80.0, step=0.1)
        
        if st.form_submit_button("Registrar Peso", type="primary"):
            nova_entrada = {
                "date": data_registro.strftime("%Y-%m-%d"),
                "weight": peso_registro
            }
            st.session_state['weight_history'].append(nova_entrada)
            # Ordenar por data
            st.session_state['weight_history'] = sorted(st.session_state['weight_history'], key=lambda x: x['date'])
            save_data('weight_history', HIST_FILE)
            st.success("Registro adicionado!")
            st.rerun()
            
    if st.session_state['weight_history']:
        df_hist = pd.DataFrame(st.session_state['weight_history'])
        df_hist['date'] = pd.to_datetime(df_hist['date'])
        df_hist = df_hist.set_index('date')
        
        st.line_chart(df_hist['weight'])
        
        # Display as table
        with st.expander("Ver Todos os Registros"):
            st.dataframe(df_hist.sort_index(ascending=False))
            
        if st.button("🗑️ Limpar Histórico"):
            st.session_state['weight_history'] = []
            save_data('weight_history', HIST_FILE)
            st.rerun()
    else:
        st.info("Nenhum registro de peso encontrado. Adicione para ver o gráfico.")

with tab_bf:
    st.header("Monitor de Gordura Corporal")
    st.markdown("Estimativa precisa pelo Método da Marinha Americana")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("📏 Suas Medidas")
        gender = st.radio("Gênero", ["Masculino", "Feminino"], horizontal=True)
        altura = st.number_input("Altura (cm)", min_value=100.0, max_value=250.0, value=175.0, step=0.1)
        pescoco = st.number_input("Pescoço (cm) - Abaixo do pomo de adão", min_value=20.0, max_value=80.0, value=38.0, step=0.1)
        
        abdomen_label = "Abdômen (cm) - Altura do umbigo" if gender == "Masculino" else "Cintura (cm) - Parte mais estreita"
        abdomen = st.number_input(abdomen_label, min_value=40.0, max_value=150.0, value=85.0, step=0.1)
        
        quadril = 0.0
        if gender == "Feminino":
            quadril = st.number_input("Quadril (cm) - Parte mais larga", min_value=50.0, max_value=150.0, value=95.0, step=0.1)
            
        btn_calc = st.button("🔬 Calcular Percentual de Gordura", width="stretch", type="primary")

    with col2:
        st.subheader("📊 Seu Resultado")
        if btn_calc:
            import math
            bf = 0.0
            valido = True
            
            if gender == "Masculino":
                if abdomen <= pescoco:
                    st.error("O abdômen deve ser maior que o pescoço.")
                    valido = False
                else:
                    bf = 86.010 * math.log10(abdomen - pescoco) - 70.041 * math.log10(altura) + 36.76
            else:
                bf = 163.205 * math.log10(abdomen + quadril - pescoco) - 97.684 * math.log10(altura) - 78.387
            
            if valido:
                bf = max(2.0, min(bf, 70.0)) # Clamping
                st.metric(label="Gordura Corporal", value=f"{bf:.1f}%")
                
                # Categoria
                categoria = ""
                if gender == "Masculino":
                    if bf < 6: categoria = "Gordura Essencial ⚠️"
                    elif bf <= 14: categoria = "Atleta 🏆"
                    elif bf <= 18: categoria = "Fitness 💪"
                    elif bf <= 25: categoria = "Médio 👍"
                    else: categoria = "Obeso ⚠️"
                else:
                    if bf < 14: categoria = "Gordura Essencial ⚠️"
                    elif bf <= 21: categoria = "Atleta 🏆"
                    elif bf <= 25: categoria = "Fitness 💪"
                    elif bf <= 32: categoria = "Médio 👍"
                    else: categoria = "Obeso ⚠️"
                    
                st.success(f"Categoria: **{categoria}**")
                st.progress(min(int((bf / 50) * 100), 100))
                st.caption("*Método da Marinha Americana (US Navy Method)")
                
    st.divider()
    st.subheader("🤖 Análise por IA + Foto")
    
    online = is_online()
    
    if not online:
        st.warning("⚠️ **Modo Offline:** A análise por IA requer conexão com a internet. Os cálculos matemáticos acima continuam funcionando normalmente.")
    else:
        st.info("Envie uma foto e a Inteligência Artificial (Gemini) analisará visualmente sua composição corporal, combinando com suas medidas.")
    
    upload_img = st.file_uploader("Enviar Foto", type=['jpg', 'jpeg', 'png'], label_visibility="collapsed", disabled=not online)
    
    if upload_img:
        st.image(upload_img, caption="Sua Foto", width=200)
        
        if st.button("Analisar com Inteligência Artificial", type="primary", width="stretch", disabled=not online):
            with st.spinner("Analisando com IA..."):
                try:
                    # Configurando Gemini (Novo SDK)
                    client = genai.Client(api_key=GEMINI_API_KEY)
                    
                    img_pil = Image.open(upload_img)
                    
                    medidas_texto = f"Gênero: {gender}\nAltura: {altura} cm\nPescoço: {pescoco} cm\nAbdômen/Cintura: {abdomen} cm"
                    if gender == "Feminino": medidas_texto += f"\nQuadril: {quadril} cm"
                    
                    prompt = f"""Você é um especialista em composição corporal. Analise esta foto de uma pessoa e combine com as medidas fornecidas para estimar o percentual de gordura corporal.
                    
                    MEDIDAS INFORMADAS:
                    {medidas_texto}
                    
                    INSTRUÇÕES:
                    1. Analise visualmente a composição corporal na foto.
                    2. Considere as medidas fornecidas junto com a análise visual.
                    3. Forneça uma estimativa do percentual de gordura corporal.
                    4. Responda EXATAMENTE neste formato JSON:
                    {{"percentual": 18.5, "analise": "Descrição breve sobre o que observou..."}}
                    """
                    
                    response = client.models.generate_content(
                        model=MODEL_NAME,
                        contents=[prompt, img_pil]
                    )
                    texto = response.text
                    
                    import re
                    # Tentar parsear a resposta para extrair percentual e análise
                    match = re.search(r'\{.*\}', texto, re.DOTALL)
                    if match:
                        dados = json.loads(match.group(0))
                        perc_ia = dados.get("percentual", "--")
                        analise_ia = dados.get("analise", texto)
                    else:
                        perc_ia = "N/A"
                        analise_ia = texto
                        
                    st.success("🤖 Análise por IA (Gemini Vision) concluída")
                    st.metric("Estimativa IA de Gordura Corporal", f"{perc_ia}%" if isinstance(perc_ia, (int, float)) else perc_ia)
                    st.write(analise_ia)
                    st.caption("⚠️ Estimativa visual — use como referência complementar ao cálculo matemático.")
                    
                except Exception as e:
                    print(f"DEBUG: Erro na análise por IA: {e}")
                    st.error(f"Erro ao analisar com IA: {e}. Verifique sua conexão e chave de API.")

with tab_chat:
    st.header("💬 Chat Nutricional Especializado")
    st.markdown("Tire suas dúvidas com base em livros e artigos de nutrição.")
    
    if not online:
        st.warning("⚠️ **Modo Offline:** O ChatBot requer conexão com a internet para processar as dúvidas via Gemini.")
    else:
        # Carregar conhecimento dos PDFs
        with st.spinner("Carregando base de conhecimento..."):
            conhecimento = extract_text_from_pdfs()
            num_livros = len([f for f in os.listdir(BOOKS_DIR) if f.endswith(".pdf")])
            
        if num_livros == 0:
            st.info(f"📚 Nenhuns livros encontrados na pasta `{BOOKS_DIR}`. Coloque seus PDFs lá para 'treinar' o ChatBot.")
            st.caption("Dica: Você pode colocar manuais de nutrição, tabelas de alimentos ou artigos científicos.")
            
        # Chat Interface
        if "messages" not in st.session_state:
            st.session_state.messages = []

        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        if prompt_user := st.chat_input("Como posso te ajudar hoje?"):
            st.session_state.messages.append({"role": "user", "content": prompt_user})
            with st.chat_message("user"):
                st.markdown(prompt_user)

            with st.chat_message("assistant"):
                try:
                    client = genai.Client(api_key=GEMINI_API_KEY)
                    
                    # Limitar o contexto para não exceder o limite de tokens (pegando os primeiros 15000 chars como exemplo simples)
                    contexto_limitado = conhecimento[:15000] if conhecimento else "Nenhum livro disponível no momento."
                    
                    full_prompt = f"""Você é um assistente de nutrição especializado e amigável. Use o CONTEXTO abaixo para responder à PERGUNTA do usuário.
                    
                    CONTEXTO DOS LIVROS:
                    {contexto_limitado}
                    
                    INSTRUÇÕES:
                    1. Se a resposta estiver no contexto, responda de forma clara e objetiva.
                    2. Se a resposta não estiver clara no contexto, use seu conhecimento geral mas mencione que não encontrou especificamente nos livros.
                    3. Seja profissional e encorajador.
                    
                    PERGUNTA: {prompt_user}
                    """
                    
                    response = client.models.generate_content(
                        model=MODEL_NAME,
                        contents=full_prompt
                    )
                    answer = response.text
                    st.markdown(answer)
                    st.session_state.messages.append({"role": "assistant", "content": answer})
                except Exception as e:
                    print(f"DEBUG: Erro no ChatBot: {e}")
                    st.error(f"Erro no ChatBot: {e}")
