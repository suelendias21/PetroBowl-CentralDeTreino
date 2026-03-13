import sys
import warnings
import uuid
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
    .area-tag { text-align: center; color: #f39c12; font-size: 22px; font-weight: bold; margin-bottom: -10px; text-transform: uppercase; letter-spacing: 2px;}
    .pergunta { font-size: 40px; text-align: center; margin: 20px 5%; padding: 40px; background-color: #1e1e2e; border-radius: 12px; border-left: 8px solid #f39c12; box-shadow: 2px 2px 15px rgba(0,0,0,0.4);}
    .instrucao-blur { text-align: center; color: #888888; font-size: 14px; margin-top: 10px; font-style: italic; }
    
    /* BLINDAGEM VISUAL: A caixa já nasce borrada, impossível vazar a resposta */
    .resposta-box {
        font-size: 38px; color: #00fa9a; font-weight: bold; text-align: center; 
        margin-top: 10px; padding: 20px; border: 2px dashed #00fa9a; border-radius: 12px; 
        background-color: rgba(0, 250, 154, 0.05);
        filter: blur(15px); /* O borrão fica aqui como regra absoluta de fábrica */
        cursor: pointer;
    }
    
    /* O hover tira o blur com prioridade máxima */
    .resposta-box:hover { filter: blur(0px) !important; }
    
    @keyframes removerBlur {
        to { filter: blur(0px); }
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. BANCO DE MEMÓRIA E FUNÇÕES BLINDADAS
# ==========================================
if 'pergunta_atual' not in st.session_state: st.session_state.pergunta_atual = None
if 'historico_erros' not in st.session_state: st.session_state.historico_erros = []
if 'estatisticas' not in st.session_state: st.session_state.estatisticas = {}

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
        st.session_state.historico_erros.append({
            "Área": area, "Pergunta": p['pergunta'], "Resposta": p['resposta']
        })

def sortear_pergunta_callback(df_f, c_area, c_perg, c_resp):
    if not df_f.empty:
        linha = df_f.sample().iloc[0]
        st.session_state.pergunta_atual = {
            "area": linha[c_area] if c_area in df_f.columns else "Geral",
            "pergunta": linha[c_perg],
            "resposta": linha[c_resp],
            "uid": str(uuid.uuid4())
        }

def acerto_callback(df_f, c_area, c_perg, c_resp):
    registrar_resposta_interna(True)
    sortear_pergunta_callback(df_f, c_area, c_perg, c_resp)

def erro_callback(df_f, c_area, c_perg, c_resp):
    registrar_resposta_interna(False)
    sortear_pergunta_callback(df_f, c_area, c_perg, c_resp)

# ==========================================
# 3. BARRA LATERAL (Upload e Filtros)
# ==========================================
st.sidebar.title("🧠 Central de Treino")
st.sidebar.markdown("---")

arquivo = st.sidebar.file_uploader("Carregue o Total Bank (.xlsx)", type=["xlsx"])
df_filtrado = pd.DataFrame()

if arquivo:
    df = carregar_planilha(arquivo)
    
    col_pergunta = "Question" if "Question" in df.columns else df.columns[1]
    col_resposta = "Answer" if "Answer" in df.columns else df.columns[2]
    col_area = "Area" if "Area" in df.columns else df.columns[3]
    
    df = df.dropna(subset=[col_pergunta])
    
    if col_area in df.columns:
        areas_disponiveis = sorted(list(df[col_area].dropna().unique()))
        treino_geral = st.sidebar.checkbox("🌍 Treino Geral (Selecionar Todas as Áreas)", value=False)
        areas_selecionadas = st.sidebar.multiselect(
            "Ou selecione áreas específicas:",
            options=areas_disponiveis,
            default=areas_disponiveis if treino_geral else []
        )
        if areas_selecionadas:
            df_filtrado = df[df[col_area].isin(areas_selecionadas)]
            st.sidebar.success(f"📌 {len(df_filtrado)} perguntas prontas para o sorteio.")
        else:
            st.sidebar.warning("⚠️ Marque 'Treino Geral' ou escolha áreas específicas acima.")
    else:
        df_filtrado = df
        st.sidebar.success(f"📌 {len(df_filtrado)} perguntas prontas.")

# ==========================================
# 4. ABAS DO APLICATIVO E LÓGICA DO JOGO
# ==========================================
tab_jogo, tab_analytics = st.tabs(["🎮 Arena de Simulação", "📊 Analytics & Revisão"])

with tab_jogo:
    if arquivo and not df_filtrado.empty:
        col_sorteio, col_espaco = st.columns([1, 2])
        
        with col_sorteio:
            st.button(
                "🚀 Sortear Nova Pergunta",
                type="primary",
                on_click=sortear_pergunta_callback,
                args=(df_filtrado, col_area, col_pergunta, col_resposta)
            )
        
        st.markdown("---")
        
        if st.session_state.pergunta_atual:
            p = st.session_state.pergunta_atual
            uid = p['uid']
            
            st.markdown(f"""
                <style>
                /* O blur some após 15s (quando o timer atinge 5s) */
                .anim-blur-{uid} {{
                    animation: removerBlur 0.5s ease-in-out 15s forwards; 
                }}
                
                .timer-bar-{uid} {{
                    height: 12px; width: 100%; border-radius: 8px; margin: 5px 0 20px 0;
                    animation: shrinkTimer 20s linear forwards; 
                }}
                
                @keyframes shrinkTimer {{
                    0% {{ width: 100%; background-color: #00fa9a; }}
                    33% {{ width: 66%; background-color: #f39c12; }}
                    66% {{ width: 33%; background-color: #e74c3c; }}
                    100% {{ width: 0%; background-color: #e74c3c; }}
                }}
                
                @keyframes countdown-{uid} {{
                    0%    {{ content: "⏱️ 20s"; color: #00fa9a; }}
                    5%    {{ content: "⏱️ 19s"; color: #00fa9a; }}
                    10%   {{ content: "⏱️ 18s"; color: #00fa9a; }}
                    15%   {{ content: "⏱️ 17s"; color: #00fa9a; }}
                    20%   {{ content: "⏱️ 16s"; color: #00fa9a; }}
                    25%   {{ content: "⏱️ 15s"; color: #00fa9a; }}
                    30%   {{ content: "⏱️ 14s"; color: #00fa9a; }}
                    35%   {{ content: "⏱️ 13s"; color: #f39c12; }}
                    40%   {{ content: "⏱️ 12s"; color: #f39c12; }}
                    45%   {{ content: "⏱️ 11s"; color: #f39c12; }}
                    50%   {{ content: "⏱️ 10s"; color: #f39c12; }}
                    55%   {{ content: "⏱️ 9s";  color: #f39c12; }}
                    60%   {{ content: "⏱️ 8s";  color: #f39c12; }}
                    65%   {{ content: "⏱️ 7s";  color: #f39c12; }}
                    70%   {{ content: "⏱️ 6s";  color: #e74c3c; }}
                    75%   {{ content: "⏱️ 5s";  color: #e74c3c; }}
                    80%   {{ content: "⏱️ 4s";  color: #e74c3c; }}
                    85%   {{ content: "⏱️ 3s";  color: #e74c3c; }}
                    90%   {{ content: "⏱️ 2s";  color: #e74c3c; }}
                    95%   {{ content: "⏱️ 1s";  color: #e74c3c; }}
                    99.9% {{ content: "⏱️ 0s";  color: #e74c3c; }}
                    100%  {{ content: "⏱️ Tempo Esgotado!"; color: #e74c3c; }}
                }}
                .timer-text-{uid}::after {{
                    content: "⏱️ 20s";
                    animation: countdown-{uid} 20s forwards;
                    font-size: 45px;
                    font-weight: bold;
                    display: block;
                    text-align: center;
                    margin-top: 15px;
                }}
                </style>
            """, unsafe_allow_html=True)
            
            st.markdown(f"<div class='area-tag'>📍 ÁREA: {p['area']}</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='pergunta'>{str(p['pergunta'])}</div>", unsafe_allow_html=True)
            
            st.markdown(f"<div class='timer-text-{uid}'></div>", unsafe_allow_html=True)
            st.markdown(f"<div class='timer-bar-{uid}'></div>", unsafe_allow_html=True)
            
            resposta_escaped = str(p['resposta']).replace("'", "\\'").replace('"', '&quot;')
            st.components.v1.html(f"""
                <style>
                  #resp {{
                    font-size: 38px; color: #00fa9a; font-weight: bold; text-align: center;
                    padding: 20px; border: 2px dashed #00fa9a; border-radius: 12px;
                    background-color: rgba(0,250,154,0.05);
                    filter: blur(15px);
                    transition: filter 0.4s ease;
                    cursor: pointer;
                    user-select: none;
                  }}
                </style>
                <div id="resp">{str(p['resposta'])}</div>
                <script>
                  var el = document.getElementById('resp');
                  var revealed = false;

                  // Hover: revela enquanto não foi revelado automaticamente
                  el.addEventListener('mouseover', function() {{
                    if (!revealed) el.style.filter = 'blur(0px)';
                  }});
                  el.addEventListener('mouseout', function() {{
                    if (!revealed) el.style.filter = 'blur(15px)';
                  }});

                  // Após 15s: revela permanentemente e desativa hover
                  setTimeout(function() {{
                    revealed = true;
                    el.style.filter = 'blur(0px)';
                    el.style.cursor = 'default';
                  }}, 15000);
                </script>
            """, height=120)
            st.markdown("<div class='instrucao-blur'>A resposta será revelada automaticamente nos últimos 5 segundos (ou passe o mouse para ler agora) 🖱️</div>", unsafe_allow_html=True)

            st.write("")
            col_acerto, col_erro = st.columns(2)
            
            with col_acerto:
                st.button(
                    "✅ Acertamos!",
                    use_container_width=True,
                    on_click=acerto_callback,
                    args=(df_filtrado, col_area, col_pergunta, col_resposta)
                )
                    
            with col_erro:
                st.button(
                    "❌ Erramos",
                    use_container_width=True,
                    on_click=erro_callback,
                    args=(df_filtrado, col_area, col_pergunta, col_resposta)
                )
                    
    else:
        if arquivo:
            st.info("👈 Escolha pelo menos uma área no menu lateral para iniciar o sorteio.")
        else:
            st.info("👈 Suba a sua planilha no menu esquerdo para iniciar o treino.")

with tab_analytics:
    st.header("📈 Desempenho da Equipe")
    
    if st.session_state.estatisticas:
        df_stats = pd.DataFrame.from_dict(st.session_state.estatisticas, orient='index')
        df_stats['Taxa de Acerto (%)'] = (df_stats['Acertos'] / df_stats['Tentativas'] * 100).round(1)
        
        total_tentativas = df_stats['Tentativas'].sum()
        total_acertos = df_stats['Acertos'].sum()
        taxa_geral = round((total_acertos / total_tentativas) * 100, 1) if total_tentativas > 0 else 0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Questões Treinadas", total_tentativas)
        c2.metric("Acertos Totais", total_acertos)
        c3.metric("Taxa de Conversão Global", f"{taxa_geral}%")
        
        st.markdown("### 🔍 Análise por Área")
        st.dataframe(df_stats.sort_values(by='Taxa de Acerto (%)', ascending=True), use_container_width=True)
        
    else:
        st.markdown("<p style='color:gray;'>As estatísticas vão aparecer aqui conforme vocês jogam.</p>", unsafe_allow_html=True)
        
    st.markdown("---")
    st.header("📚 Lista Negra (Erros do Dia)")
    
    if st.session_state.historico_erros:
        df_erros = pd.DataFrame(st.session_state.historico_erros)
        st.dataframe(df_erros, use_container_width=True)
        
        csv_erros = df_erros.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Baixar Perguntas Erradas (.CSV)",
            data=csv_erros,
            file_name="revisao_petrobowl.csv",
            mime="text/csv",
            type="primary"
        )
    else:
        st.success("Vocês ainda não erraram nenhuma questão!")