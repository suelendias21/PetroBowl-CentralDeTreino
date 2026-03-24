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

    .area-tag { text-align: center; color: #e67e22; font-size: 22px; font-weight: bold; margin-bottom: -10px; text-transform: uppercase; letter-spacing: 2px;}
    .pergunta { font-size: 40px; text-align: center; color: #111111; margin: 20px 5%; padding: 40px; background-color: #ffffff; border-radius: 12px; border-left: 8px solid #e67e22; box-shadow: 2px 2px 15px rgba(0,0,0,0.1);}
    .instrucao-blur { text-align: center; color: #666666; font-size: 14px; margin-top: 10px; font-style: italic; }
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
    """Salva/atualiza o registro da sessão atual no banco.
    Usa session_id para fazer upsert: sempre sobrescreve a sessão corrente
    em vez de criar duplicatas a cada resposta.
    """
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
        # Upsert: atualiza a sessão existente se já tiver o mesmo session_id
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
    'stats_ja_salvos': {},   # controle do que já foi salvo no banco
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
    st.markdown("<p style='text-align:center; color:#555;'>Faça login ou crie sua conta para salvar seu progresso</p>", unsafe_allow_html=True)
    st.markdown("---")

    col_l, col_r = st.columns(2)

    with col_l:
        st.subheader("🔑 Login")
        login_user = st.text_input("Usuário", key="login_user")
        login_pass = st.text_input("Senha", type="password", key="login_pass")
        if st.button("Entrar", type="primary", use_container_width=True):
            if not login_user or not login_pass:
                st.error("Preencha usuário e senha.")
            elif not usuario_existe(login_user):
                st.error("Usuário não encontrado.")
            elif not senha_correta(login_user, login_pass):
                st.error("Senha incorreta.")
            else:
                st.session_state.logado = True
                st.session_state.usuario_atual = login_user
                st.session_state.estatisticas = {}
                st.session_state.stats_ja_salvos = {}
                st.session_state.historico_erros = []
                st.session_state.pergunta_atual = None
                st.session_state.fila_areas = []
                st.session_state.indice_area = 0
                st.session_state.hora_login = datetime.now().strftime('%d/%m/%Y %H:%M')
                st.session_state.session_id = str(uuid.uuid4())
                st.rerun()

    with col_r:
        st.subheader("📝 Criar Conta")
        novo_user  = st.text_input("Escolha um usuário", key="novo_user")
        novo_pass  = st.text_input("Escolha uma senha", type="password", key="novo_pass")
        novo_pass2 = st.text_input("Confirme a senha", type="password", key="novo_pass2")
        if st.button("Criar Conta", use_container_width=True):
            if not novo_user or not novo_pass:
                st.error("Preencha todos os campos.")
            elif novo_pass != novo_pass2:
                st.error("As senhas não coincidem.")
            elif usuario_existe(novo_user):
                st.error("Esse usuário já existe.")
            elif len(novo_pass) < 4:
                st.error("Senha deve ter pelo menos 4 caracteres.")
            else:
                salvar_usuario(novo_user, {
                    'senha': hash_senha(novo_pass),
                    'historico_total': {},
                    'erros_total': []
                })
                st.success(f"Conta criada com sucesso! Faça login agora, {novo_user} 🎉")

    st.stop()

# ==========================================
# 5. HEADER PÓS-LOGIN
# ==========================================
col_titulo, col_logout = st.columns([5, 1])
with col_titulo:
    st.markdown(
        f"<h3 style='color:#e67e22; margin-bottom:0;'>🧠 PetroBowl Intelligence &nbsp;|&nbsp; "
        f"<span style='color:#27ae60;'>👤 {st.session_state.usuario_atual}</span></h3>",
        unsafe_allow_html=True
    )
with col_logout:
    if st.button("🚪 Sair", use_container_width=True):
        if st.session_state.estatisticas:
            registrar_sessao(
                st.session_state.usuario_atual,
                st.session_state.estatisticas,
                st.session_state.historico_erros
            )
        st.session_state.logado = False
        st.session_state.usuario_atual = None
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

    # Atualiza sessão
    if area not in st.session_state.estatisticas:
        st.session_state.estatisticas[area] = {'Tentativas': 0, 'Acertos': 0}
    st.session_state.estatisticas[area]['Tentativas'] += 1
    if acertou:
        st.session_state.estatisticas[area]['Acertos'] += 1
    else:
        st.session_state.historico_erros.append({
            "Área": area, "Pergunta": p['pergunta'], "Resposta": p['resposta']
        })

    # Salva o incremento no banco (só o delta desta resposta)
    delta = {area: {'Tentativas': 1, 'Acertos': 1 if acertou else 0}}
    erros_delta = [] if acertou else [{"Área": area, "Pergunta": p['pergunta'], "Resposta": p['resposta']}]
    atualizar_stats_usuario(st.session_state.usuario_atual, delta, erros_delta)
    # Atualiza o snapshot da sessão atual automaticamente
    registrar_sessao(
        st.session_state.usuario_atual,
        st.session_state.estatisticas,
        st.session_state.historico_erros,
        session_id=st.session_state.session_id
    )

def montar_fila_ciclica(areas_sel):
    """
    Monta a fila de áreas para o ciclo:
    - Áreas normais em ordem alfabética primeiro
    - Um slot '⭐ BONUS' ao final (agrupa todas as áreas com 'bonus' no nome)
    Retorna (fila, areas_bonus).
    """
    normais = sorted([a for a in areas_sel if 'bonus' not in a.lower()])
    bonus   = [a for a in areas_sel if 'bonus' in a.lower()]
    fila = normais + (['⭐ BONUS'] if bonus else [])
    return fila, set(bonus)

def sortear_pergunta_ciclica(df_f, c_area, c_perg, c_resp, areas_sel):
    if df_f.empty: return

    fila_nova, bonus_areas = montar_fila_ciclica(areas_sel)

    # Reinicia fila se as áreas mudaram
    if st.session_state.fila_areas != fila_nova:
        st.session_state.fila_areas = fila_nova
        st.session_state.indice_area = 0

    fila = st.session_state.fila_areas
    if not fila: return

    # Percorre ciclicamente até achar um slot com perguntas
    tentativas = 0
    while tentativas < len(fila):
        idx = st.session_state.indice_area % len(fila)
        slot = fila[idx]
        st.session_state.indice_area = idx + 1

        # Slot bonus: filtra todas as áreas bonus juntas
        if slot == '⭐ BONUS':
            df_slot = df_f[df_f[c_area].isin(bonus_areas)]
        else:
            df_slot = df_f[df_f[c_area] == slot]

        if not df_slot.empty:
            linha = df_slot.sample().iloc[0]
            area_real = linha[c_area]
            st.session_state.pergunta_atual = {
                "area": f"⭐ BONUS — {area_real}" if slot == '⭐ BONUS' else area_real,
                "pergunta": linha[c_perg],
                "resposta": linha[c_resp],
                "uid": str(uuid.uuid4())
            }
            return
        tentativas += 1

def acerto_callback(df_f, c_area, c_perg, c_resp, areas_sel):
    registrar_resposta_interna(True)
    sortear_pergunta_ciclica(df_f, c_area, c_perg, c_resp, areas_sel)

def erro_callback(df_f, c_area, c_perg, c_resp, areas_sel):
    registrar_resposta_interna(False)
    sortear_pergunta_ciclica(df_f, c_area, c_perg, c_resp, areas_sel)

# ==========================================
# 7. BARRA LATERAL
# ==========================================
st.sidebar.title("🧠 Central de Treino")
st.sidebar.markdown("---")

arquivo = st.sidebar.file_uploader("Carregue o Total Bank (.xlsx)", type=["xlsx"])
df_filtrado = pd.DataFrame()
areas_selecionadas = []
col_pergunta = col_resposta = col_area = None

if arquivo:
    df = carregar_planilha(arquivo)

    col_pergunta = "Question" if "Question" in df.columns else df.columns[1]
    col_resposta = "Answer"   if "Answer"   in df.columns else df.columns[2]
    col_area     = "Area"     if "Area"     in df.columns else df.columns[3]

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
            fila_atual, _ = montar_fila_ciclica(areas_selecionadas)
            idx_prox      = st.session_state.indice_area % len(fila_atual) if fila_atual else 0
            proxima       = fila_atual[idx_prox] if fila_atual else ""
            st.sidebar.success(f"📌 {len(df_filtrado)} perguntas prontas.")
            st.sidebar.info(f"🔄 Próxima área: **{proxima}**")
        else:
            st.sidebar.warning("⚠️ Marque 'Treino Geral' ou escolha áreas específicas acima.")
    else:
        df_filtrado = df
        areas_selecionadas = ["Geral"]
        st.sidebar.success(f"📌 {len(df_filtrado)} perguntas prontas.")

# ==========================================
# 8. ABAS
# ==========================================
tab_jogo, tab_sessao, tab_historico = st.tabs(["🎮 Arena de Simulação", "📊 Sessão Atual", "🏆 Histórico Total"])

# --- ABA JOGO ---
with tab_jogo:
    if arquivo and not df_filtrado.empty:
        col_sorteio, col_espaco = st.columns([1, 2])
        with col_sorteio:
            st.button(
                "🚀 Sortear Nova Pergunta",
                type="primary",
                on_click=sortear_pergunta_ciclica,
                args=(df_filtrado, col_area, col_pergunta, col_resposta, areas_selecionadas)
            )

        st.markdown("---")

        if st.session_state.pergunta_atual:
            p   = st.session_state.pergunta_atual
            uid = p['uid']

            st.markdown(f"<div class='area-tag'>📍 ÁREA: {p['area']}</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='pergunta'>{str(p['pergunta'])}</div>", unsafe_allow_html=True)

            st.components.v1.html(f"""
                <style>
                  * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: sans-serif; }}

                  #timer-display {{
                    font-size: 48px; font-weight: bold; text-align: center;
                    margin-bottom: 8px; color: #27ae60;
                  }}
                  #timer-bar-wrap {{
                    width: 100%; background: #e0e0e0;
                    border-radius: 8px; height: 14px; margin-bottom: 16px; overflow: hidden;
                  }}
                  #timer-bar {{
                    height: 14px; border-radius: 8px;
                    width: 100%; background-color: #27ae60;
                    transition: width 1s linear, background-color 0.5s;
                  }}
                  #resp {{
                    font-size: 36px; color: #1a1a1a; font-weight: bold; text-align: center;
                    padding: 20px; border: 2px dashed #e67e22; border-radius: 12px;
                    background-color: #fff8f0;
                    filter: blur(15px); transition: filter 0.4s ease;
                    cursor: pointer; user-select: none;
                    margin-bottom: 12px;
                    word-wrap: break-word;
                    word-break: break-word;
                    white-space: normal;
                  }}
                  #instrucao {{
                    text-align: center; color: #888; font-size: 13px; font-style: italic;
                    margin-bottom: 14px;
                  }}
                  #btn-pause {{
                    display: block; margin: 0 auto;
                    padding: 10px 36px; font-size: 16px; font-weight: bold;
                    background-color: #e67e22; color: white;
                    border: none; border-radius: 8px; cursor: pointer;
                    flex-shrink: 0;
                  }}
                  #btn-pause:hover {{ background-color: #cf6d17; }}
                </style>

                <div id="timer-display">⏱️ 25s</div>
                <div id="timer-bar-wrap"><div id="timer-bar"></div></div>
                <div id="resp">{str(p['resposta'])}</div>
                <div id="instrucao">A resposta será revelada automaticamente nos últimos 5 segundos (ou passe o mouse para ler agora) 🖱️</div>
                <button id="btn-pause">⏸️ Pausar</button>

                <script>
                  var TOTAL    = 25;
                  var REVEAL_AT = 5;
                  var remaining = TOTAL;
                  var paused    = false;
                  var revealed  = false;

                  var display  = document.getElementById('timer-display');
                  var bar      = document.getElementById('timer-bar');
                  var resp     = document.getElementById('resp');
                  var btnPause = document.getElementById('btn-pause');

                  // Hover revela enquanto não foi revelado automaticamente
                  resp.addEventListener('mouseover', function() {{ if (!revealed) resp.style.filter = 'blur(0px)'; }});
                  resp.addEventListener('mouseout',  function() {{ if (!revealed) resp.style.filter = 'blur(15px)'; }});

                  function getColor(rem) {{
                    if (rem > 12) return '#27ae60';
                    if (rem > 5)  return '#e67e22';
                    return '#e74c3c';
                  }}

                  function tick() {{
                    if (paused) return;
                    if (remaining <= 0) {{
                      display.textContent = '⏱️ Tempo Esgotado!';
                      display.style.color = '#e74c3c';
                      bar.style.width = '0%';
                      reveal();
                      return;
                    }}
                    var color = getColor(remaining);
                    display.textContent = '⏱️ ' + remaining + 's';
                    display.style.color = color;
                    bar.style.width = (remaining / TOTAL * 100) + '%';
                    bar.style.backgroundColor = color;

                    if (remaining <= REVEAL_AT) reveal();
                    remaining--;
                    setTimeout(tick, 1000);
                  }}

                  function reveal() {{
                    if (revealed) return;
                    revealed = true;
                    resp.style.filter = 'blur(0px)';
                    resp.style.cursor = 'default';
                  }}

                  btnPause.addEventListener('click', function() {{
                    paused = !paused;
                    btnPause.textContent = paused ? '▶️ Continuar' : '⏸️ Pausar';
                    if (!paused) tick();
                  }});

                  tick();

                  // Ajusta altura do iframe dinamicamente
                  function resizeIframe() {{
                    var h = document.body.scrollHeight + 20;
                    window.parent.document.querySelectorAll('iframe').forEach(function(f) {{
                      if (f.contentWindow === window) f.style.height = h + 'px';
                    }});
                  }}
                  window.addEventListener('load', resizeIframe);
                  new MutationObserver(resizeIframe).observe(document.body, {{childList:true, subtree:true, characterData:true}});
                </script>
            """, height=380)
            st.write("")

            col_acerto, col_erro = st.columns(2)
            with col_acerto:
                st.button(
                    "✅ Acertamos!",
                    use_container_width=True,
                    on_click=acerto_callback,
                    args=(df_filtrado, col_area, col_pergunta, col_resposta, areas_selecionadas)
                )
            with col_erro:
                st.button(
                    "❌ Erramos",
                    use_container_width=True,
                    on_click=erro_callback,
                    args=(df_filtrado, col_area, col_pergunta, col_resposta, areas_selecionadas)
                )
    else:
        if arquivo:
            st.info("👈 Escolha pelo menos uma área no menu lateral para iniciar o sorteio.")
        else:
            st.info("👈 Suba a sua planilha no menu esquerdo para iniciar o treino.")

# --- ABA SESSÃO ATUAL ---
with tab_sessao:
    st.header(f"📊 Sessão Atual — {st.session_state.usuario_atual}")

    if st.session_state.estatisticas:
        df_stats = pd.DataFrame.from_dict(st.session_state.estatisticas, orient='index')
        df_stats['Taxa de Acerto (%)'] = (df_stats['Acertos'] / df_stats['Tentativas'] * 100).round(1)

        total_tent  = df_stats['Tentativas'].sum()
        total_acert = df_stats['Acertos'].sum()
        taxa_geral  = round((total_acert / total_tent) * 100, 1) if total_tent > 0 else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Questões nesta sessão", total_tent)
        c2.metric("Acertos",               total_acert)
        c3.metric("Taxa de Acerto",         f"{taxa_geral}%")

        st.markdown("### 🔍 Por Área")
        st.dataframe(df_stats.sort_values(by='Taxa de Acerto (%)', ascending=True), use_container_width=True)
    else:
        st.info("Jogue algumas perguntas para ver as estatísticas da sessão.")

    st.markdown("---")
    st.header("📚 Erros desta Sessão")

    if st.session_state.historico_erros:
        df_erros = pd.DataFrame(st.session_state.historico_erros)
        st.dataframe(df_erros, use_container_width=True)
        csv_erros = df_erros.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Baixar Erros da Sessão (.CSV)",
            data=csv_erros,
            file_name="erros_sessao.csv",
            mime="text/csv",
            type="primary"
        )
    else:
        st.success("Nenhum erro nesta sessão ainda! 🎉")

# --- ABA HISTÓRICO TOTAL ---
with tab_historico:
    st.header(f"🏆 Histórico Total — {st.session_state.usuario_atual}")

    dados       = get_dados_usuario(st.session_state.usuario_atual)
    hist_total  = dados.get('historico_total', {})
    erros_total = dados.get('erros_total', [])
    sessoes     = dados.get('sessoes', [])

    # ---- Resumo geral acumulado ----
    if hist_total:
        df_hist = pd.DataFrame.from_dict(hist_total, orient='index')
        df_hist['Taxa de Acerto (%)'] = (df_hist['Acertos'] / df_hist['Tentativas'] * 100).round(1)

        total_tent  = df_hist['Tentativas'].sum()
        total_acert = df_hist['Acertos'].sum()
        taxa_geral  = round((total_acert / total_tent) * 100, 1) if total_tent > 0 else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("Total de Questões", total_tent)
        c2.metric("Total de Acertos",  total_acert)
        c3.metric("Taxa Global",        f"{taxa_geral}%")

        st.markdown("### 🔍 Por Área (acumulado de todas as sessões)")
        st.dataframe(df_hist.sort_values(by='Taxa de Acerto (%)', ascending=True), use_container_width=True)

        fracas = df_hist[df_hist['Taxa de Acerto (%)'] < 50]
        if not fracas.empty:
            st.warning(f"⚠️ Áreas abaixo de 50%: **{', '.join(fracas.index.tolist())}** — reforçar!")
    else:
        st.info("Nenhum histórico salvo ainda. Jogue e os dados aparecerão aqui automaticamente!")

    # ---- Log de sessões ----
    st.markdown("---")
    st.header("📅 Histórico de Sessões")

    if sessoes:
        for i, s in enumerate(reversed(sessoes)):
            num = len(sessoes) - i
            with st.expander(f"🗓️ Sessão {num} — {s['data']}  |  {s['questoes']} questões  |  {s['taxa']}% de acerto"):
                c1, c2, c3 = st.columns(3)
                c1.metric("Questões",    s['questoes'])
                c2.metric("Acertos",     s['acertos'])
                c3.metric("Taxa",        f"{s['taxa']}%")

                if s.get('por_area'):
                    df_sess = pd.DataFrame.from_dict(s['por_area'], orient='index')
                    df_sess['Taxa (%)'] = (df_sess['Acertos'] / df_sess['Tentativas'] * 100).round(1)
                    st.markdown("**Por área nesta sessão:**")
                    st.dataframe(df_sess.sort_values(by='Taxa (%)', ascending=True), use_container_width=True)

                if s.get('erros'):
                    st.markdown("**Erros desta sessão:**")
                    st.dataframe(pd.DataFrame(s['erros']), use_container_width=True)
                else:
                    st.success("Nenhum erro nesta sessão! 🎉")
    else:
        st.info("As sessões aparecerão aqui após você sair com o botão 🚪 Sair.")

    # ---- Todos os erros ----
    st.markdown("---")
    st.header("📚 Todos os Erros Registrados")

    if erros_total:
        df_erros_total = pd.DataFrame(erros_total)
        st.dataframe(df_erros_total, use_container_width=True)
        csv_total = df_erros_total.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Baixar Todos os Erros (.CSV)",
            data=csv_total,
            file_name="historico_erros_total.csv",
            mime="text/csv",
            type="primary"
        )
    else:
        st.success("Nenhum erro registrado no histórico total! 🏆")
