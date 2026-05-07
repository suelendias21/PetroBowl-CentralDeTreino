import sys
import warnings
import uuid
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
st.set_page_config(page_title="PetroBowl Intelligence - Amistoso", page_icon="🏆", layout="wide")

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
# FUNÇÃO PARA RENDERIZAR TABELA HTML (SEM DB)
# ==========================================
def render_tabela_erros_html(erros_list, height=420):
    if not erros_list:
        return
    rows = ""
    for err in erros_list:
        num = err.get('Nº', '-')
        hora = err.get('Hora', '-')
        area = err.get('Área', '-')
        perg = str(err.get('Pergunta', '-'))
        resp = str(err.get('Resposta', '-'))
        
        perg_js = perg.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'").replace('\n', ' ')
        
        rows += f"""
        <tr>
            <td>{num}</td>
            <td>{hora}</td>
            <td>{area}</td>
            <td>{perg}</td>
            <td>
                <span class="resp-hidden" onclick="this.classList.toggle('revealed')" title="Clique para revelar a resposta">{resp}</span>
            </td>
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
        th, td {{ padding: 12px 10px; text-align: left; border-bottom: 1px solid #f0f0f0; vertical-align: middle; }}
        th {{ background-color: #f8f9fa; font-weight: 600; color: #2c3e50; position: sticky; top: 0; z-index: 1; border-bottom: 2px solid #e67e22; box-shadow: 0 2px 2px -1px rgba(0,0,0,0.1); }}
        tr:hover {{ background-color: #fafafa; }}
        
        .resp-hidden {{
            color: transparent; 
            background-color: #ffffff; 
            cursor: pointer;
            transition: color 0.1s ease-in-out; 
            user-select: none; 
            display: inline-block;
            padding: 4px 10px;
            border-radius: 4px;
            min-width: 80px; 
            min-height: 1.2em;
        }}
        .resp-hidden:hover {{ background-color: #f5f5f5; }}
        .resp-hidden.revealed {{ color: #333; background-color: transparent; user-select: text; }}

        .btn-play {{ background-color: #e67e22; color: white; border: none; border-radius: 5px; padding: 6px 12px; cursor: pointer; font-size: 14px; transition: 0.2s; }}
        .btn-play:hover {{ background-color: #cf6d17; transform: scale(1.05); }}
    </style>
    <div class="table-container">
        <table>
            <thead>
                <tr>
                    <th width="8%">Nº</th>
                    <th width="10%">Hora</th>
                    <th width="15%">Área</th>
                    <th width="40%">Pergunta</th>
                    <th width="19%">Resposta (Clique)</th>
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
# 2. SESSION STATE INICIAL (STATELESS)
# ==========================================
defaults = {
    'contagem_perguntas_sessao': 0, 
    'pergunta_atual': None,
    'historico_erros': [],
    'estatisticas': {},
    'fila_areas': [],
    'indice_area': 0,
    'aguardando_navegacao': False
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ==========================================
# 3. HEADER DA COMPETIÇÃO
# ==========================================
c_t, c_l = st.columns([5, 1])
c_t.markdown(f"### 🏆 PetroBowl Intelligence | Modo Competição Rápida", unsafe_allow_html=True)
if c_l.button("🔄 Zerar Sessão", use_container_width=True):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# ==========================================
# 4. LÓGICA DO JOGO (SEM BANCO DE DADOS)
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
            "Nº": p.get('num', '?'), "Hora": datetime.now().strftime("%H:%M"), 
            "Área": area, "Pergunta": p['pergunta'], "Resposta": p['resposta']
        })
    st.session_state.aguardando_navegacao = True

# ==========================================
# 5. BARRA LATERAL (CONFIGS)
# ==========================================
st.sidebar.title("Configurações do Jogo")
arquivo = st.sidebar.file_uploader("Carregue o Total Bank (.xlsx)", type=["xlsx"])
voz_ativa = st.sidebar.checkbox("🔊 Narrar no Sorteio", value=True)
df_filtrado = pd.DataFrame()
areas_selecionadas = []

if arquivo:
    df = carregar_planilha(arquivo)
    areas_disponiveis = sorted(list(df["Area"].dropna().unique()))
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📚 Áreas de Treino")
    
    selecionar_todas = st.sidebar.checkbox("🌍 Selecionar Todas as Áreas", value=False)
    st.sidebar.caption("Ou escolha matérias específicas:")
    
    if selecionar_todas:
        areas_selecionadas = areas_disponiveis.copy()
        
    for area in areas_disponiveis:
        marcado = st.sidebar.checkbox(area, value=selecionar_todas, disabled=selecionar_todas, key=f"chk_{area}")
        if marcado and not selecionar_todas:
            areas_selecionadas.append(area)

    if areas_selecionadas:
        areas_selecionadas = list(set(areas_selecionadas))
        df_filtrado = df[df["Area"].isin(areas_selecionadas)]

# ==========================================
# 6. ABAS: ARENA / SESSÃO ATUAL
# ==========================================
tab_jogo, tab_sessao = st.tabs(["🎮 Arena de Simulação", "📊 Sessão Atual"])

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
                st.button("⏭️ Próxima Pergunta", use_container_width=True, type="primary", on_click=sortear_pergunta_ciclica, args=(df_filtrado, areas_selecionadas))
    else:
        st.info("👈 Selecione pelo menos uma área na barra lateral para começar.")

# --- SESSÃO ATUAL ---
with tab_sessao:
    st.header(f"📊 Desempenho do Amistoso")
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
            render_tabela_erros_html(st.session_state.historico_erros, height=450)
            
            # Botão de salvar a sessão
            csv = pd.DataFrame(st.session_state.historico_erros).to_csv(index=False).encode('utf-8')
            st.download_button("📥 Baixar Planilha de Erros (.CSV) para Revisão", data=csv, file_name=f"erros_amistoso_{datetime.now().strftime('%d_%m')}.csv", mime="text/csv")
    else:
        st.info("Nenhuma pergunta respondida ainda.")
