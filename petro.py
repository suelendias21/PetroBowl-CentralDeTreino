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
    .next-area-info { color: #7f8c8d; font-size: 14px; margin-bottom: 5px; font-weight: bold; }
    .pergunta-num { color: #2c3e50; font-size: 18px; font-weight: bold; text-align: center; }
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
# FUNÇÃO PARA RENDERIZAR TABELA HTML COM ÁUDIO
# ==========================================
def render_tabela_erros_html(erros_list, height=420):
    if not erros_list:
        return
    rows = ""
    for err in erros_list:
        sess = err.get('Sessão', '?')
        num = err.get('Nº', '-')
        hora = err.get('Hora', '-')
        area = err.get('Área', '-')
        perg = str(err.get('Pergunta', '-'))
        resp = str(err.get('Resposta', '-'))
        
        # Escapar caracteres para o JavaScript
        perg_js = perg.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'").replace('\n', ' ')
        
        rows += f"""
        <tr>
            <td>#{sess}</td>
            <td>{num}</td>
            <td>{hora}</td>
            <td>{area}</td>
            <td>{perg}</td>
            <td>{resp}</td>
            <td style="text-align: center;">
                <button class="btn-play" onclick="speak('{perg_js}')" title="Ouvir Pergunta">▶️</button>
            </td>
        </tr>
        """
        
    html_code = f"""
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; color: #333; }}
        .table-container {{ width: 100%; height: {height-20}px; overflow-y: auto; border: 1px solid #eee; border-radius: 8px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; background-color: #fff; }}
        th, td {{ padding: 12px 10px; text-align: left; border-bottom: 1px solid #f0f0f0; }}
        th {{ background-color: #f8f9fa; font-weight: 600; color: #2c3e50; position: sticky; top: 0; z-index: 1; border-bottom: 2px solid #e67e22; box-shadow: 0 2px 2px -1px rgba(0,0,0,0.1); }}
        tr:hover {{ background-color: #fafafa; }}
        .btn-play {{ background-color: #e67e22; color: white; border: none; border-radius: 5px; padding: 6px 12px; cursor: pointer; font-size: 14px; transition: 0.2s; }}
        .btn-play:hover {{ background-color: #cf6d17; transform: scale(1.05); }}
    </style>
    <div class="table-container">
        <table>
            <thead>
                <tr>
                    <th width="8%">Sess.</th>
                    <th width="8%">Nº</th>
                    <th width="10%">Hora</th>
                    <th width="15%">Área</th>
                    <th width="35%">Pergunta</th>
                    <th width="16%">Resposta</th>
                    <th width="8%" style="text-align: center;">Ouvir</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
    </div>
    <script>
        function speak(text) {{
            window.speechSynthesis.cancel();
            var msg = new SpeechSynthesisUtterance(text);
            msg.lang = 'en-US';
            msg.rate = 0.85;
            window.speechSynthesis.speak(msg);
        }}
    </script>
    """
    components.html(html_code, height=height)

# ==========================================
# 3. SESSION STATE INICIAL
# ==========================================
defaults = {
    'logado': False,
    'usuario_atual': None,
    'numero_sessao': 1,
    'contagem_perguntas_sessao': 0, 
    'pergunta_atual': None,
    'historico_erros': [],
    'estatisticas': {},
    'fila_areas': [],
    'indice_area': 0,
    'session_id': None,
    'aguardando_navegacao': False
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
if c_l.button("🚪 Encerrar e Sair", use_container_width=True):
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

def montar_fila_ciclica(areas_sel):
    if not areas_sel: return [], set()
    normais = sorted([a for a in areas_sel if 'bonus' not in a.lower()])
    bonus   = [a for a in areas_sel if 'bonus' in a.lower()]
    fila = normais + (['⭐ BONUS'] if bonus else [])
    return fila, set(bonus)

def sortear_pergunta_ciclica(df_f, areas_sel):
    if df_f.empty: return
    c_area, c_perg, c_resp = "Area", "Question", "Answer"
    fila, bonus_set = montar_fila_ciclica(areas_sel)
    idx = st.session_state.indice_area % len(fila)
    slot = fila[idx]
    st.session_state.indice_area += 1
    df_slot = df_f[df_f[c_area].isin(bonus_set)] if slot == '⭐ BONUS' else df_f[df_f[c_area] == slot]
    if not df_slot.empty:
        linha = df_slot.sample().iloc[0]
        st.session_state.contagem_perguntas_sessao += 1 
        st.session_state.pergunta_atual = {
            "num": st.session_state.contagem_perguntas_sessao,
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
            "Nº": p.get('num', '?'), "Hora": datetime.now().strftime("%H:%M"), 
            "Área": area, "Pergunta": p['pergunta'], "Resposta": p['resposta']
        })
    atualizar_stats_usuario(st.session_state.usuario_atual, {area: {'Tentativas': 1, 'Acertos': 1 if acertou else 0}}, [] if acertou else [{"Sessão": st.session_state.numero_sessao, "Nº": p.get('num', '?'), "Área": area, "Pergunta": p['pergunta'], "Resposta": p['resposta']}])
    st.session_state.aguardando_navegacao = True

def finalizar_sessao_callback():
    registrar_sessao(st.session_state.usuario_atual, st.session_state.estatisticas, st.session_state.historico_erros, st.session_state.session_id, st.session_state.numero_sessao)
    st.session_state.logado = False
    st.rerun()

# ==========================================
# 7. BARRA LATERAL (CONFIGS)
# ==========================================
arquivo = st.sidebar.file_uploader("Carregue o Total Bank (.xlsx)", type=["xlsx"])
voz_ativa = st.sidebar.checkbox("🔊 Narrar no Sorteio", value=True)
df_filtrado = pd.DataFrame()
areas_selecionadas = []

if arquivo:
    df = carregar_planilha(arquivo)
    areas_disponiveis = sorted(list(df["Area"].dropna().unique()))
    areas_selecionadas = st.sidebar.multiselect("Áreas de Treino:", options=areas_disponiveis, default=areas_disponiveis)
    if areas_selecionadas:
        df_filtrado = df[df["Area"].isin(areas_selecionadas)]

# ==========================================
# 8. ABAS: ARENA / SESSÃO / HISTÓRICO
# ==========================================
tab_jogo, tab_sessao, tab_hist = st.tabs(["🎮 Arena de Simulação", "📊 Sessão Atual", "🏆 Histórico Total"])

# --- ARENA ---
with tab_jogo:
    if not df_filtrado.empty:
        fila, _ = montar_fila_ciclica(areas_selecionadas)
        idx_prox = st.session_state.indice_area % len(fila) if fila else 0
        area_seguinte = fila[idx_prox] if fila else "---"

        if not st.session_state.pergunta_atual and not st.session_state.aguardando_navegacao:
            st.markdown(f"<div class='next-area-info'>🎯 PRÓXIMA MATÉRIA: {area_seguinte}</div>", unsafe_allow_html=True)
            if st.button("🚀 Sortear Pergunta", type="primary"):
                sortear_pergunta_ciclica(df_filtrado, areas_selecionadas)
                st.rerun()
        
        if st.session_state.pergunta_atual:
            p = st.session_state.pergunta_atual
            pergunta_js = str(p['pergunta']).replace('"', '\\"').replace('\n', ' ')

            st.markdown(f"<div class='pergunta-num'>Pergunta {p.get('num', '?')}</div>", unsafe_allow_html=True)
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
                        var TOTAL = 15; var remaining = TOTAL; var paused = false; var timerStarted = false;
                        var vozAtiva = {str(voz_ativa).lower()}; var perguntaTxt = "{pergunta_js}";
                        var display = document.getElementById('timer-display'); var bar = document.getElementById('timer-bar');
                        var qBox = document.getElementById('q-box'); var aBox = document.getElementById('a-box'); var btnPause = document.getElementById('btn-pause');

                        function tick() {{
                            if (paused || !timerStarted) return;
                            if (remaining <= 0) {{ display.textContent = "⏱️ FIM!"; bar.style.width = "0%"; aBox.style.display = "block"; return; }}
                            display.textContent = "⏱️ " + remaining + "s";
                            display.style.color = remaining <= 5 ? "#e74c3c" : "#27ae60";
                            bar.style.width = (remaining / TOTAL * 100) + "%";
                            bar.style.background = remaining <= 5 ? "#e74c3c" : "#27ae60";
                            remaining--; setTimeout(tick, 1000);
                        }}

                        window.onload = function() {{
                            if (vozAtiva) {{
                                window.speechSynthesis.cancel();
                                var msg = new SpeechSynthesisUtterance(perguntaTxt); msg.lang = 'en-US'; msg.rate = 0.85;
                                msg.onstart = () => {{ display.textContent = "📢 Lendo..."; }};
                                msg.onend = () => {{ if (!paused) {{ timerStarted = true; btnPause.textContent = "⏸️ Pausar Cronômetro"; tick(); }} else {{ timerStarted = true; }} }};
                                window.speechSynthesis.speak(msg);
                            }} else {{ timerStarted = true; btnPause.textContent = "⏸️ Pausar Cronômetro"; tick(); }}
                        }};

                        document.getElementById('btn-reveal-q').onclick = () => {{ qBox.style.display = "block"; }};
                        document.getElementById('btn-reveal-a').onclick = () => {{ aBox.style.display = "block"; }};
                        btnPause.onclick = function() {{
                            paused = !paused;
                            if (paused) {{
                                if (!timerStarted && vozAtiva) {{ window.speechSynthesis.pause(); this.textContent = "▶️ Continuar Narração"; }} 
                                else {{ this.textContent = "▶️ Continuar Cronômetro"; }}
                            }} else {{
                                if (!timerStarted && vozAtiva) {{ window.speechSynthesis.resume(); this.textContent = "⏸️ Pausar Narração"; }} 
                                else {{ this.textContent = "⏸️ Pausar Cronômetro"; tick(); }}
                            }}
                        }};
                    </script>
                """, height=400)

                c1, c2 = st.columns(2)
                c1.button("✅ Acertamos!", use_container_width=True, on_click=processar_resposta, args=(True,))
                c2.button("❌ Erramos", use_container_width=True, on_click=processar_resposta, args=(False,))
            else:
                st.info("Resultado registrado! Como deseja prosseguir?")
                st.markdown(f"<div class='next-area-info'>🎯 PRÓXIMA MATÉRIA: {area_seguinte}</div>", unsafe_allow_html=True)
                nav_c1, nav_c2 = st.columns(2)
                with nav_c1:
                    st.button("⏭️ Próxima Pergunta", use_container_width=True, type="primary", on_click=sortear_pergunta_ciclica, args=(df_filtrado, areas_selecionadas))
                with nav_c2:
                    st.button("⏹️ Encerrar Sessão", use_container_width=True, on_click=finalizar_sessao_callback)
    else:
        st.info("👈 Selecione áreas na barra lateral para começar.")

# --- SESSÃO ATUAL ---
with tab_sessao:
    st.header(f"📊 Desempenho da Sessão #{st.session_state.numero_sessao}")
    if st.session_state.estatisticas:
        df_s = pd.DataFrame.from_dict(st.session_state.estatisticas, orient='index')
        df_s['Taxa (%)'] = (df_s['Acertos'] / df_s['Tentativas'] * 100).round(1)
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Perguntas", st.session_state.contagem_perguntas_sessao)
        m2.metric("Acertos", df_s['Acertos'].sum())
        m3.metric("Taxa Global", f"{round((df_s['Acertos'].sum()/df_s['Tentativas'].sum()*100),1)}%" if not df_s.empty else "0%")
        st.dataframe(df_s, use_container_width=True)
        
        if st.session_state.historico_erros:
            st.subheader("📚 Revisão de Erros da Sessão")
            # Renderiza a tabela HTML com JS embutido
            render_tabela_erros_html(st.session_state.historico_erros, height=450)
            
            csv = pd.DataFrame(st.session_state.historico_erros).to_csv(index=False).encode('utf-8')
            st.download_button("📥 Baixar Erros (.CSV)", data=csv, file_name=f"erros_Sessao_{st.session_state.numero_sessao}.csv", mime="text/csv")
    else:
        st.info("Nenhuma pergunta respondida ainda.")

# --- HISTÓRICO TOTAL ---
with tab_hist:
    st.header("🏆 Histórico Acumulado")
    dados_db = get_dados_usuario(st.session_state.usuario_atual)
    h_total = dados_db.get('historico_total', {})
    
    if h_total:
        df_h = pd.DataFrame.from_dict(h_total, orient='index')
        df_h['Taxa (%)'] = (df_h['Acertos'] / df_h['Tentativas'] * 100).round(1)
        st.dataframe(df_h, use_container_width=True)
        
        todos_erros = dados_db.get('erros_total', [])
        if todos_erros:
            st.subheader("📚 Banco de Erros Histórico")
            
            # Pegamos os últimos 40 erros para não gerar um HTML gigantesco
            erros_recentes = list(reversed(todos_erros[-40:]))
            render_tabela_erros_html(erros_recentes, height=500)

            csv_t = pd.DataFrame(todos_erros).to_csv(index=False).encode('utf-8')
            st.download_button("📊 Baixar Todos os Erros (.CSV)", data=csv_t, file_name=f"historico_erros_total.csv", mime="text/csv")
    else:
        st.info("Sem dados no histórico ainda.")
