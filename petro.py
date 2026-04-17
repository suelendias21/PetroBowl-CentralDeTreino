import sys
import warnings
import uuid
import hashlib
import shelve
from datetime import datetime
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

if 'warnings' not in sys.modules:
    sys.modules['warnings'] = warnings
warnings.filterwarnings("ignore")

# ==========================================
# 1. CONFIGURAÇÕES E ESTILOS GERAIS
# ==========================================
st.set_page_config(page_title="PetroBowl Intelligence", page_icon="🧠", layout="wide")

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}

    /* Fundo branco geral */
    .stApp { background-color: #ffffff; color: #111111; }
    [data-testid="stSidebar"] { background-color: #f5f5f5; }

    .area-tag { text-align: center; color: #e67e22; font-size: 22px; font-weight: bold; margin-bottom: 20px; text-transform: uppercase; letter-spacing: 2px;}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. SISTEMA DE USUÁRIOS (shelve = banco local)
# ==========================================
DB_PATH = "petrobowl_users"

def hash_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()

def usuario_existe(usuario):
    with shelve.open(DB_PATH) as db:
        return usuario in db

def senha_correta(usuario, senha):
    with shelve.open(DB_PATH) as db:
        if usuario not in db:
            return False
        return db[usuario]['senha'] == hash_senha(senha)

def salvar_usuario(usuario, dados):
    with shelve.open(DB_PATH) as db:
        db[usuario] = dados

def get_dados_usuario(usuario):
    with shelve.open(DB_PATH) as db:
        return dict(db.get(usuario, {}))

def atualizar_stats_usuario(usuario, stats_delta, erros_novos):
    with shelve.open(DB_PATH) as db:
        dados = db.get(usuario, {'senha': '', 'historico_total': {}, 'erros_total': []})
        hist = dados.get('historico_total', {})
        for area, vals in stats_delta.items():
            if area not in hist:
                hist[area] = {'Tentativas': 0, 'Acertos': 0}
            hist[area]['Tentativas'] += vals.get('Tentativas', 0)
            hist[area]['Acertos']    += vals.get('Acertos', 0)
        dados['historico_total'] = hist
        erros = dados.get('erros_total', [])
        erros.extend(erros_novos)
        dados['erros_total'] = erros[-200:]
        db[usuario] = dados

def registrar_sessao(usuario, estatisticas_sessao, erros_sessao, session_id=None):
    if not estatisticas_sessao:
        return
    with shelve.open(DB_PATH) as db:
        dados = db.get(usuario, {'senha': '', 'historico_total': {}, 'erros_total': [], 'sessoes': []})
        sessoes = dados.get('sessoes', [])
        total_tent  = sum(v['Tentativas'] for v in estatisticas_sessao.values())
        total_acert = sum(v['Acertos']    for v in estatisticas_sessao.values())
        registro = {
            'session_id': session_id,
            'data': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'questoes': total_tent,
            'acertos': total_acert,
            'taxa': round((total_acert / total_tent * 100), 1) if total_tent > 0 else 0,
            'por_area': dict(estatisticas_sessao),
            'erros': list(erros_sessao)
        }
        if session_id:
            for i, s in enumerate(sessoes):
                if s.get('session_id') == session_id:
                    sessoes[i] = registro
                    break
            else:
                sessoes.append(registro)
        else:
            sessoes.append(registro)
        dados['sessoes'] = sessoes[-100:]
        db[usuario] = dados

# ==========================================
# 3. SESSION STATE INICIAL
# ==========================================
defaults = {
    'logado': False,
    'usuario_atual': None,
    'pergunta_atual': None,
    'historico_erros': [],
    'estatisticas': {},
    'stats_ja_salvos': {},
    'fila_areas': [],
    'indice_area': 0,
    'session_id': None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ==========================================
# 4. TELA DE LOGIN / CADASTRO
# ==========================================
if not st.session_state.logado:
    st.markdown("<h1 style='text-align:center; color:#e67e22;'>🧠 PetroBowl Intelligence</h1>", unsafe_allow_html=True)
    st.markdown("---")
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("🔑 Login")
        login_user = st.text_input("Usuário", key="login_user")
        login_pass = st.text_input("Senha", type="password", key="login_pass")
        if st.button("Entrar", type="primary", use_container_width=True):
            if usuario_existe(login_user) and senha_correta(login_user, login_pass):
                st.session_state.logado = True
                st.session_state.usuario_atual = login_user
                st.session_state.session_id = str(uuid.uuid4())
                st.rerun()
            else:
                st.error("Credenciais inválidas.")
    with col_r:
        st.subheader("📝 Criar Conta")
        novo_user  = st.text_input("Novo usuário", key="novo_user")
        novo_pass  = st.text_input("Nova senha", type="password", key="novo_pass")
        if st.button("Criar Conta", use_container_width=True):
            if not usuario_existe(novo_user):
                salvar_usuario(novo_user, {'senha': hash_senha(novo_pass), 'historico_total': {}, 'erros_total': []})
                st.success("Conta criada!")
            else:
                st.error("Usuário já existe.")
    st.stop()

# ==========================================
# 5. HEADER
# ==========================================
col_titulo, col_logout = st.columns([5, 1])
with col_titulo:
    st.markdown(f"### 🧠 PetroBowl Intelligence | <span style='color:#27ae60;'>👤 {st.session_state.usuario_atual}</span>", unsafe_allow_html=True)
with col_logout:
    if st.button("🚪 Sair", use_container_width=True):
        if st.session_state.estatisticas:
            registrar_sessao(st.session_state.usuario_atual, st.session_state.estatisticas, st.session_state.historico_erros, st.session_state.session_id)
        st.session_state.logado = False
        st.rerun()

# ==========================================
# 6. FUNÇÕES DO JOGO
# ==========================================
@st.cache_data
def carregar_planilha(file):
    df = pd.read_excel(file, sheet_name="Total Bank")
    df.columns = df.columns.astype(str).str.strip()
    return df

def registrar_resposta_interna(acertou):
    p = st.session_state.pergunta_atual
    if not p: return
    area = p['area']
    if area not in st.session_state.estatisticas:
        st.session_state.estatisticas[area] = {'Tentativas': 0, 'Acertos': 0}
    st.session_state.estatisticas[area]['Tentativas'] += 1
    if acertou:
        st.session_state.estatisticas[area]['Acertos'] += 1
    else:
        st.session_state.historico_erros.append({"Área": area, "Pergunta": p['pergunta'], "Resposta": p['resposta']})
    
    atualizar_stats_usuario(st.session_state.usuario_atual, {area: {'Tentativas': 1, 'Acertos': 1 if acertou else 0}}, [] if acertou else [{"Área": area, "Pergunta": p['pergunta'], "Resposta": p['resposta']}])
    registrar_sessao(st.session_state.usuario_atual, st.session_state.estatisticas, st.session_state.historico_erros, st.session_state.session_id)

def sortear_pergunta_ciclica(df_f, c_area, c_perg, c_resp, areas_sel):
    normais = sorted([a for a in areas_sel if 'bonus' not in a.lower()])
    bonus   = [a for a in areas_sel if 'bonus' in a.lower()]
    fila = normais + (['⭐ BONUS'] if bonus else [])
    
    idx = st.session_state.indice_area % len(fila)
    slot = fila[idx]
    st.session_state.indice_area += 1
    
    df_slot = df_f[df_f[c_area].isin(bonus)] if slot == '⭐ BONUS' else df_f[df_f[c_area] == slot]
    if not df_slot.empty:
        linha = df_slot.sample().iloc[0]
        st.session_state.pergunta_atual = {
            "area": linha[c_area], "pergunta": linha[c_perg], "resposta": linha[c_resp], "uid": str(uuid.uuid4())
        }

# ==========================================
# 7. BARRA LATERAL
# ==========================================
arquivo = st.sidebar.file_uploader("Carregue o Total Bank (.xlsx)", type=["xlsx"])
voz_ativa = st.sidebar.checkbox("🔊 Narrar Pergunta", value=True)
areas_selecionadas = []
df_filtrado = pd.DataFrame()

if arquivo:
    df = carregar_planilha(arquivo)
    c_perg, c_resp, c_area = "Question", "Answer", "Area"
    areas_disponiveis = sorted(list(df[c_area].dropna().unique()))
    areas_selecionadas = st.sidebar.multiselect("Áreas:", options=areas_disponiveis, default=areas_disponiveis)
    if areas_selecionadas:
        df_filtrado = df[df[c_area].isin(areas_selecionadas)]

# ==========================================
# 8. ABA JOGO
# ==========================================
tab_jogo, tab_sessao, tab_hist = st.tabs(["🎮 Arena", "📊 Sessão", "🏆 Histórico"])

with tab_jogo:
    if not df_filtrado.empty:
        if st.button("🚀 Sortear Nova Pergunta", type="primary"):
            sortear_pergunta_ciclica(df_filtrado, "Area", "Question", "Answer", areas_selecionadas)
        
        if st.session_state.pergunta_atual:
            p = st.session_state.pergunta_atual
            pergunta_limpa = str(p['pergunta']).replace('"', '\\"').replace('\n', ' ')
            resposta_limpa = str(p['resposta']).replace('"', '\\"').replace('\n', ' ')

            st.markdown(f"<div class='area-tag'>📍 ÁREA: {p['area']}</div>", unsafe_allow_html=True)

            components.html(f"""
                <style>
                    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', sans-serif; }}
                    body {{ background: white; text-align: center; }}
                    #timer-display {{ font-size: 50px; font-weight: bold; color: #7f8c8d; margin: 10px 0; }}
                    #timer-bar-wrap {{ width: 100%; background: #eee; height: 12px; border-radius: 10px; overflow: hidden; margin-bottom: 20px; }}
                    #timer-bar {{ height: 100%; width: 100%; background: #bdc3c7; transition: width 1s linear; }}
                    
                    .box {{ 
                        background: #f9f9f9; border: 2px solid #e67e22; border-radius: 12px; 
                        padding: 20px; margin: 10px 0; min-height: 60px; display: none;
                        font-size: 24px; color: #2c3e50; font-weight: 500;
                    }}
                    
                    .btn-action {{
                        background: #e67e22; color: white; border: none; padding: 12px 24px;
                        border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer;
                        margin: 5px; transition: 0.3s; width: 45%;
                    }}
                    .btn-action:hover {{ background: #cf6d17; }}
                    #btn-pause {{ width: 92%; background: #95a5a6; }}
                </style>

                <div id="timer-display">⏱️ Pronto</div>
                <div id="timer-bar-wrap"><div id="timer-bar"></div></div>

                <button class="btn-action" id="btn-reveal-q">👁️ Revelar Pergunta</button>
                <button class="btn-action" id="btn-reveal-a">👁️ Revelar Resposta</button>
                
                <div class="box" id="q-box">{p['pergunta']}</div>
                <div class="box" id="a-box">{p['resposta']}</div>

                <button class="btn-action" id="btn-pause">⏸️ Pausar Cronômetro</button>

                <script>
                    var TOTAL = 25;
                    var remaining = TOTAL;
                    var paused = false;
                    var timerStarted = false;
                    var vozAtiva = {str(voz_ativa).lower()};
                    var perguntaTxt = "{pergunta_limpa}";

                    var display = document.getElementById('timer-display');
                    var bar = document.getElementById('timer-bar');
                    var qBox = document.getElementById('q-box');
                    var aBox = document.getElementById('a-box');
                    var btnPause = document.getElementById('btn-pause');

                    function tick() {{
                        if (paused || !timerStarted) return;
                        if (remaining <= 0) {{
                            display.textContent = "⏱️ FIM!";
                            bar.style.width = "0%";
                            aBox.style.display = "block";
                            return;
                        }}
                        display.textContent = "⏱️ " + remaining + "s";
                        display.style.color = remaining <= 5 ? "#e74c3c" : "#27ae60";
                        bar.style.width = (remaining / TOTAL * 100) + "%";
                        bar.style.background = remaining <= 5 ? "#e74c3c" : "#27ae60";
                        remaining--;
                        setTimeout(tick, 1000);
                    }}

                    document.getElementById('btn-reveal-q').onclick = function() {{
                        qBox.style.display = "block";
                        if (!timerStarted) {{
                            if (vozAtiva) {{
                                window.speechSynthesis.cancel();
                                var msg = new SpeechSynthesisUtterance(perguntaTxt);
                                msg.lang = 'en-US';
                                msg.onstart = () => {{ display.textContent = "📢 Lendo..."; }};
                                msg.onend = () => {{ timerStarted = true; tick(); }};
                                window.speechSynthesis.speak(msg);
                            }} else {{
                                timerStarted = true; tick();
                            }}
                        }}
                    }};

                    document.getElementById('btn-reveal-a').onclick = function() {{
                        aBox.style.display = "block";
                    }};

                    btnPause.onclick = function() {{
                        paused = !paused;
                        this.textContent = paused ? "▶️ Continuar" : "⏸️ Pausar Cronômetro";
                        if (!paused) tick();
                    }};
                </script>
            """, height=450)

            c1, c2 = st.columns(2)
            c1.button("✅ Acertamos!", use_container_width=True, on_click=registrar_resposta_interna, args=(True,))
            c2.button("❌ Erramos", use_container_width=True, on_click=registrar_resposta_interna, args=(False,))
    else:
        st.info("Suba a planilha para começar.")

# --- ABAS ESTATÍSTICAS (Resumidas para manter o foco) ---
with tab_sessao:
    if st.session_state.estatisticas:
        st.dataframe(pd.DataFrame.from_dict(st.session_state.estatisticas, orient='index'), use_container_width=True)
with tab_hist:
    dados = get_dados_usuario(st.session_state.usuario_atual)
    if dados.get('historico_total'):
        st.dataframe(pd.DataFrame.from_dict(dados['historico_total'], orient='index'), use_container_width=True)
