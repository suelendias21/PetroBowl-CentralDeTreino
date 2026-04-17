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
    .stApp { background-color: #ffffff; color: #111111; }
    [data-testid="stSidebar"] { background-color: #f5f5f5; }
    .area-tag { text-align: center; color: #e67e22; font-size: 22px; font-weight: bold; margin-bottom: 20px; text-transform: uppercase; letter-spacing: 2px;}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. SISTEMA DE USUÁRIOS
# ==========================================
DB_PATH = "petrobowl_users"

def hash_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()

def usuario_existe(usuario):
    with shelve.open(DB_PATH) as db:
        return usuario in db

def senha_correta(usuario, senha):
    with shelve.open(DB_PATH) as db:
        if usuario not in db: return False
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
            if area not in hist: hist[area] = {'Tentativas': 0, 'Acertos': 0}
            hist[area]['Tentativas'] += vals.get('Tentativas', 0)
            hist[area]['Acertos']    += vals.get('Acertos', 0)
        dados['historico_total'] = hist
        erros = dados.get('erros_total', [])
        erros.extend(erros_novos)
        dados['erros_total'] = erros[-500:] 
        db[usuario] = dados

def registrar_sessao(usuario, estatisticas_sessao, erros_sessao, session_id, num_sessao):
    if not estatisticas_sessao: return
    with shelve.open(DB_PATH) as db:
        dados = db.get(usuario, {'senha': '', 'historico_total': {}, 'erros_total': [], 'sessoes': []})
        sessoes = dados.get('sessoes', [])
        total_tent  = sum(v['Tentativas'] for v in estatisticas_sessao.values())
        total_acert = sum(v['Acertos']    for v in estatisticas_sessao.values())
        registro = {
            'session_id': session_id,
            'numero': num_sessao,
            'data': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'questoes': total_tent,
            'acertos': total_acert,
            'taxa': round((total_acert / total_tent * 100), 1) if total_tent > 0 else 0,
            'por_area': dict(estatisticas_sessao),
            'erros': list(erros_sessao)
        }
        for i, s in enumerate(sessoes):
            if s.get('session_id') == session_id:
                sessoes[i] = registro
                break
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
    'numero_sessao': 1,
    'pergunta_atual': None,
    'historico_erros': [],
    'estatisticas': {},
    'fila_areas': [],
    'indice_area': 0,
    'session_id': None,
    'aguardando_navegacao': False,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ==========================================
# 4. LOGIN / CADASTRO
# ==========================================
if not st.session_state.logado:
    st.markdown("<h1 style='text-align:center; color:#e67e22;'>🧠 PetroBowl Intelligence</h1>", unsafe_allow_html=True)
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("🔑 Login")
        u = st.text_input("Usuário", key="l_u")
        s = st.text_input("Senha", type="password", key="l_s")
        if st.button("Entrar", use_container_width=True):
            if usuario_existe(u) and senha_correta(u, s):
                dados_db = get_dados_usuario(u)
                st.session_state.logado = True
                st.session_state.usuario_atual = u
                st.session_state.numero_sessao = len(dados_db.get('sessoes', [])) + 1
                st.session_state.session_id = str(uuid.uuid4())
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")
    with col_r:
        st.subheader("📝 Criar Conta")
        nu = st.text_input("Novo usuário", key="n_u")
        ns = st.text_input("Nova senha", type="password", key="n_s")
        if st.button("Criar Conta", use_container_width=True):
            if not nu or not ns:
                st.error("Preencha todos os campos.")
            elif not usuario_existe(nu):
                salvar_usuario(nu, {'senha': hash_senha(ns), 'historico_total': {}, 'erros_total': [], 'sessoes': []})
                st.success("Conta criada com sucesso!")
            else:
                st.error("Este usuário já existe.")
    st.stop()

# ==========================================
# 5. HEADER
# ==========================================
c_t, c_l = st.columns([5, 1])
c_t.markdown(f"### 🧠 PetroBowl Intelligence | Sessão {st.session_state.numero_sessao} | <span style='color:#27ae60;'>👤 {st.session_state.usuario_atual}</span>", unsafe_allow_html=True)
if c_l.button("🚪 Sair", use_container_width=True):
    registrar_sessao(st.session_state.usuario_atual, st.session_state.estatisticas, st.session_state.historico_erros, st.session_state.session_id, st.session_state.numero_sessao)
    st.session_state.logado = False
    st.rerun()

# ==========================================
# 6. LÓGICA DO JOGO
# ==========================================
@st.cache_data
def carregar_planilha(file):
    df = pd.read_excel(file, sheet_name="Total Bank")
    df.columns = df.columns.astype(str).str.strip()
    return df

def sortear_pergunta_ciclica(df_f, areas_sel):
    if df_f.empty: return
    c_area, c_perg, c_resp = "Area", "Question", "Answer"
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
        st.session_state.aguardando_navegacao = False

def processar_resposta(acertou):
    p = st.session_state.pergunta_atual
    if not p: return
    
    area = p['area']
    if area not in st.session_state.estatisticas: st.session_state.estatisticas[area] = {'Tentativas': 0, 'Acertos': 0}
    st.session_state.estatisticas[area]['Tentativas'] += 1
    if acertou: st.session_state.estatisticas[area]['Acertos'] += 1
    else: 
        st.session_state.historico_erros.append({
            "Sessão": st.session_state.numero_sessao,
            "Hora": datetime.now().strftime("%H:%M"), 
            "Área": area, 
            "Pergunta": p['pergunta'], 
            "Resposta": p['resposta']
        })
    
    atualizar_stats_usuario(st.session_state.usuario_atual, {area: {'Tentativas': 1, 'Acertos': 1 if acertou else 0}}, [] if acertou else [{"Sessão": st.session_state.numero_sessao, "Área": area, "Pergunta": p['pergunta'], "Resposta": p['resposta']}])
    
    st.session_state.aguardando_navegacao = True

def finalizar_sessao_callback():
    registrar_sessao(st.session_state.usuario_atual, st.session_state.estatisticas, st.session_state.historico_erros, st.session_state.session_id, st.session_state.numero_sessao)
    st.session_state.logado = False
    st.rerun()

# ==========================================
# 7. BARRA LATERAL
# ==========================================
arquivo = st.sidebar.file_uploader("Carregue o Total Bank (.xlsx)", type=["xlsx"])
voz_ativa = st.sidebar.checkbox("🔊 Narrar Automaticamente", value=True)
df_filtrado = pd.DataFrame()
areas_selecionadas = []

if arquivo:
    df = carregar_planilha(arquivo)
    areas_disponiveis = sorted(list(df["Area"].dropna().unique()))
    areas_selecionadas = st.sidebar.multiselect("Áreas de Treino:", options=areas_disponiveis, default=areas_disponiveis)
    if areas_selecionadas:
        df_filtrado = df[df["Area"].isin(areas_selecionadas)]

# ==========================================
# 8. INTERFACE DE TREINO
# ==========================================
tab_jogo, tab_sessao, tab_hist = st.tabs(["🎮 Arena de Simulação", "📊 Sessão Atual", "🏆 Histórico Total"])

with tab_jogo:
    if not df_filtrado.empty:
        if not st.session_state.pergunta_atual and not st.session_state.aguardando_navegacao:
            if st.button("🚀 Iniciar Treino / Sortear Pergunta", type="primary"):
                sortear_pergunta_ciclica(df_filtrado, areas_selecionadas)
                st.rerun()
        
        if st.session_state.pergunta_atual:
            p = st.session_state.pergunta_atual
            pergunta_js = str(p['pergunta']).replace('"', '\\"').replace('\n', ' ')

            st.markdown(f"<div class='area-tag'>📍 ÁREA: {p['area']}</div>", unsafe_allow_html=True)

            if not st.session_state.aguardando_navegacao:
                components.html(f"""
                    <style>
                        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: sans-serif; }}
                        body {{ background: white; text-align: center; overflow: hidden; }}
                        #timer-display {{ font-size: 50px; font-weight: bold; color: #7f8c8d; margin: 10px 0; }}
                        #timer-bar-wrap {{ width: 100%; background: #eee; height: 12px; border-radius: 10px; overflow: hidden; margin-bottom: 20px; }}
                        #timer-bar {{ height: 100%; width: 100%; background: #bdc3c7; transition: width 1s linear; }}
                        .box {{ background: #f9f9f9; border: 2px solid #e67e22; border-radius: 12px; padding: 20px; margin: 10px 0; display: none; font-size: 22px; color: #2c3e50; font-weight: 500; }}
                        .btn-action {{ background: #e67e22; color: white; border: none; padding: 12px; border-radius: 8px; font-size: 15px; font-weight: bold; cursor: pointer; margin: 5px; width: 45%; }}
                        #btn-pause {{ width: 92%; background: #95a5a6; }}
                    </style>

                    <div id="timer-display">⏱️ Preparando...</div>
                    <div id="timer-bar-wrap"><div id="timer-bar"></div></div>

                    <button class="btn-action" id="btn-reveal-q">👁️ Revelar Pergunta</button>
                    <button class="btn-action" id="btn-reveal-a">👁️ Revelar Resposta</button>
                    
                    <div class="box" id="q-box">{p['pergunta']}</div>
                    <div class="box" id="a-box">{p['resposta']}</div>

                    <button class="btn-action" id="btn-pause">⏸️ Pausar Narração</button>

                    <script>
                        var TOTAL = 15;
                        var remaining = TOTAL;
                        var paused = false;
                        var timerStarted = false;
                        var vozAtiva = {str(voz_ativa).lower()};
                        var perguntaTxt = "{pergunta_js}";

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

                        window.onload = function() {{
                            if (vozAtiva) {{
                                window.speechSynthesis.cancel();
                                var msg = new SpeechSynthesisUtterance(perguntaTxt);
                                msg.lang = 'en-US';
                                msg.onstart = () => {{ display.textContent = "📢 Lendo..."; }};
                                msg.onend = () => {{ 
                                    // Só inicia o tempo se não estiver pausado manualmente durante a leitura
                                    if (!paused) {{
                                        timerStarted = true;
                                        btnPause.textContent = "⏸️ Pausar Cronômetro";
                                        tick();
                                    }} else {{
                                        // Se estava pausado na leitura, marca que ao despausar deve iniciar o timer
                                        timerStarted = true;
                                    }}
                                }};
                                window.speechSynthesis.speak(msg);
                            }} else {{
                                timerStarted = true;
                                btnPause.textContent = "⏸️ Pausar Cronômetro";
                                tick();
                            }}
                        }};

                        document.getElementById('btn-reveal-q').onclick = () => {{ qBox.style.display = "block"; }};
                        document.getElementById('btn-reveal-a').onclick = () => {{ aBox.style.display = "block"; }};
                        
                        btnPause.onclick = function() {{
                            paused = !paused;
                            
                            if (paused) {{
                                // Lógica de PAUSAR
                                if (!timerStarted && vozAtiva) {{
                                    window.speechSynthesis.pause();
                                    this.textContent = "▶️ Continuar Narração";
                                }} else {{
                                    this.textContent = "▶️ Continuar Cronômetro";
                                }}
                            }} else {{
                                // Lógica de CONTINUAR
                                if (!timerStarted && vozAtiva) {{
                                    window.speechSynthesis.resume();
                                    this.textContent = "⏸️ Pausar Narração";
                                }} else {{
                                    this.textContent = "⏸️ Pausar Cronômetro";
                                    tick();
                                }}
                            }}
                        }};
                    </script>
                """, height=400)

                c1, c2 = st.columns(2)
                c1.button("✅ Acertamos!", use_container_width=True, on_click=processar_resposta, args=(True,))
                c2.button("❌ Erramos", use_container_width=True, on_click=processar_resposta, args=(False,))
            
            else:
                st.info("Resultado registrado! Como deseja prosseguir?")
                nav_c1, nav_c2 = st.columns(2)
                with nav_c1:
                    st.button("⏭️ Próxima Pergunta", use_container_width=True, type="primary", 
                              on_click=sortear_pergunta_ciclica, args=(df_filtrado, areas_selecionadas))
                with nav_c2:
                    st.button("⏹️ Encerrar Sessão", use_container_width=True, on_click=finalizar_sessao_callback)

    else:
        st.info("👈 Selecione áreas na barra lateral para começar.")

# --- ESTATÍSTICAS ---
with tab_sessao:
    st.header(f"📊 Sessão #{st.session_state.numero_sessao}")
    if st.session_state.estatisticas:
        df_s = pd.DataFrame.from_dict(st.session_state.estatisticas, orient='index')
        df_s['Taxa de Acerto (%)'] = (df_s['Acertos'] / df_s['Tentativas'] * 100).round(1)
        t_tent = df_s['Tentativas'].sum()
        t_acer = df_s['Acertos'].sum()
        t_taxa = round((t_acer / t_tent * 100), 1) if t_tent > 0 else 0
        m1, m2, m3 = st.columns(3)
        m1.metric("Respondidas", t_tent)
        m2.metric("Acertos", t_acer)
        m3.metric("Taxa", f"{t_taxa}%")
        st.dataframe(df_s.sort_values(by='Taxa de Acerto (%)'), use_container_width=True)
        if st.session_state.historico_erros:
            st.subheader(f"📚 Erros da Sessão")
            df_err = pd.DataFrame(st.session_state.historico_erros)
            st.dataframe(df_err, use_container_width=True)
            csv = df_err.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Baixar Erros da Sessão (.CSV)", data=csv, file_name=f"erros_Sessao_{st.session_state.numero_sessao}_{st.session_state.usuario_atual}.csv", mime="text/csv")
    else:
        st.info("Nenhuma pergunta respondida nesta sessão.")

with tab_hist:
    st.header("🏆 Histórico Acumulado")
    dados_db = get_dados_usuario(st.session_state.usuario_atual)
    h_total = dados_db.get('historico_total', {})
    h_sessoes = dados_db.get('sessoes', [])
    if h_total:
        df_h = pd.DataFrame.from_dict(h_total, orient='index')
        df_h['Taxa de Acerto (%)'] = (df_h['Acertos'] / df_h['Tentativas'] * 100).round(1)
        th_tent = df_h['Tentativas'].sum()
        th_acer = df_h['Acertos'].sum()
        th_taxa = round((th_acer / th_tent * 100), 1) if th_tent > 0 else 0
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Geral", th_tent)
        c2.metric("Acertos Totais", th_acer)
        c3.metric("Taxa Global", f"{th_taxa}%")
        st.dataframe(df_h.sort_values(by='Taxa de Acerto (%)'), use_container_width=True)
        if h_sessoes:
            st.subheader("📅 Log de Sessões")
            df_raw = pd.DataFrame(h_sessoes)
            cols_desejadas = ['numero', 'data', 'questoes', 'acertos', 'taxa']
            cols_validas = [c for c in cols_desejadas if c in df_raw.columns]
            df_log = df_raw[cols_validas].rename(columns={'numero': 'Sessão', 'data': 'Data/Hora', 'questoes': 'Perguntas', 'acertos': 'Acertos', 'taxa': 'Taxa (%)'})
            st.dataframe(df_log.sort_values(by=df_log.columns[0], ascending=False), use_container_width=True)
            todos_erros = dados_db.get('erros_total', [])
            if todos_erros:
                csv_total = pd.DataFrame(todos_erros).to_csv(index=False).encode('utf-8')
                st.download_button("📊 Baixar Todos os Erros (.CSV)", data=csv_total, file_name=f"historico_erros_geral_{st.session_state.usuario_atual}.csv", mime="text/csv")
    else:
        st.info("Sem dados no histórico ainda.")
