"""Frontend Streamlit do assistente da Órbita.

Uso: streamlit run src/agentic_rag/app.py
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Any

import streamlit as st
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from agentic_rag.agent.agent import get_agent, rollback_turn
from agentic_rag.config import get_settings, setup_langsmith
from agentic_rag.guardrails.middleware import PROMPT_PROTECTION_NODE
from agentic_rag.ingestion.pipeline import run_ingestion
from agentic_rag.ingestion.uploads import (
    SUPPORTED_EXTENSIONS,
    UploadCheck,
    check_upload,
    save_upload,
)
from agentic_rag.memory.conversations import (
    ConversationSummary,
    StoredMessage,
    delete_conversation,
    list_conversations,
    load_conversation,
    save_turn,
    to_agent_messages,
)
from agentic_rag.memory.store import UserContext

logger = logging.getLogger(__name__)

ERROR_ANSWER = (
    "Não consegui responder agora por uma falha interna. Tente de novo em instantes; "
    "se o problema continuar, avise o time responsável pelo assistente."
)

st.set_page_config(page_title="Assistente Órbita", page_icon=":material/orbit:", layout="wide")

USER_NAME = "Usuário"

SUGGESTIONS = [
    "Qual é a política de reembolso de 2026?",
    "Quantos dias de férias eu tenho?",
    "Quanto está o dólar hoje?",
]

CSS = """
<style>
:root {
    --bg: #0a0a0b; --side: #111112; --card: #1c1c1e; --card-2: #232326;
    --border: #262629; --text: #ececee; --muted: #8b8b93;
    --accent: #d8b45a; --accent-soft: rgba(216,180,90,.12);
}
#MainMenu, footer, [data-testid="stToolbarActions"], [data-testid="stMainMenu"],
[data-testid="stAppDeployButton"], [data-testid="stDecoration"] { display: none; }
header[data-testid="stHeader"] { background: transparent; }
[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarCollapseButton"] { color: var(--muted); }
[data-testid="stExpandSidebarButton"]:hover, [data-testid="stSidebarCollapsedControl"]:hover,
[data-testid="stSidebarCollapseButton"]:hover { color: var(--accent); }
html, body, .stApp { font-family: "Inter", "Segoe UI", system-ui, sans-serif; }
.stApp { background:
    radial-gradient(800px 480px at 92% -8%, rgba(216,180,90,.08), transparent 62%),
    radial-gradient(circle, rgba(255,255,255,.045) 1px, transparent 1.2px) 0 0 / 22px 22px,
    var(--bg); }
.block-container { max-width: 800px; padding-top: 2rem; padding-bottom: 9rem; }

/* Sidebar */
section[data-testid="stSidebar"] { background: var(--side); border-right: 1px solid var(--border); }
section[data-testid="stSidebar"] > div { padding-top: 0; }
/* Tira o cabeçalho do fluxo: o botão de recolher fica na mesma linha do título */
[data-testid="stSidebarHeader"] { position:absolute; top:.85rem; right:.6rem; z-index:10;
    height:auto; padding:0; margin:0; }
[data-testid="stSidebarUserContent"] { padding-top:0; }
section[data-testid="stSidebar"] .block-container { padding: 0 1rem 1rem; }
.side-title { font-size:1.05rem; font-weight:600; padding:1.1rem 3rem 1rem .2rem;
    border-bottom:1px solid var(--border); margin:0 -1rem 1rem; padding-left:1.2rem; }
.side-label { color: var(--muted); font-size:.7rem; text-transform:uppercase;
    letter-spacing:.1em; margin:1.4rem 0 .5rem; font-weight:600; padding-left:.2rem; }
section[data-testid="stSidebar"] [class*="st-key-conv-"] button { border-color: transparent;
    font-size:.84rem; font-weight:400; padding:.4rem .6rem; }
section[data-testid="stSidebar"] [class*="st-key-conv-"] button p { overflow:hidden;
    text-overflow:ellipsis; white-space:nowrap; }
section[data-testid="stSidebar"] [class*="st-key-conv-active-"] button {
    background: var(--accent-soft); border-color: rgba(216,180,90,.28); }
/* Linha da conversa: título (estica) + lixeira (fixa); min-width:0 deixa o título truncar */
section[data-testid="stSidebar"] [class*="st-key-row-"] { gap:.15rem; flex-wrap:nowrap; }
section[data-testid="stSidebar"] [class*="st-key-row-"] > div { min-width:0; }
section[data-testid="stSidebar"] [class*="st-key-del-"] { flex:0 0 auto; width:auto; }
section[data-testid="stSidebar"] [class*="st-key-del-"] button { width:1.9rem; height:1.9rem;
    min-height:0; padding:0; justify-content:center; border-color: transparent;
    color: var(--muted); opacity:.35; }
section[data-testid="stSidebar"] [class*="st-key-row-"]:hover [class*="st-key-del-"] button,
section[data-testid="stSidebar"] [class*="st-key-del-"] button:focus-visible { opacity:1; }
section[data-testid="stSidebar"] [class*="st-key-del-"] button:hover { color:#e57373;
    border-color: transparent; background: rgba(229,115,115,.1); }
.file-row { display:flex; align-items:center; gap:.55rem; font-size:.8rem; color:#b8b8c0;
    padding:.25rem .2rem; }
.file-ext { font-size:.6rem; font-weight:700; padding:.08rem .38rem; border-radius:4px;
    background: var(--card); border:1px solid var(--border); color: var(--accent);
    min-width:2.1rem; text-align:center; }
.file-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
/* Lista de arquivos aguardando envio */
.file-info { display:flex; flex-direction:column; min-width:0; gap:.05rem; }
.file-status { font-size:.7rem; color: var(--muted); }
.file-status.warn { color: var(--accent); }
.file-status.bad { color:#e57373; }
[class*="st-key-pending-"] { flex-wrap:nowrap; }
[class*="st-key-pending-"] > div { min-width:0; }
[class*="st-key-rm-"] { flex:0 0 auto; width:auto; }
[class*="st-key-rm-"] button { width:1.9rem; height:1.9rem; min-height:0; padding:0;
    justify-content:center; border-color: transparent; color: var(--muted); }
[class*="st-key-rm-"] button:hover { color:#e57373; border-color: transparent;
    background: rgba(229,115,115,.1); }
[data-testid="stFileUploaderDropzone"] { background: var(--card);
    border:1px dashed var(--border); border-radius:12px; }
.side-meta { color: var(--muted); font-size:.75rem; line-height:1.6; padding-left:.2rem; }

/* Botões */
.stButton > button { width:100%; justify-content:flex-start; border-radius:9px;
    border:1px solid var(--border); background: transparent; color: var(--text);
    font-weight:500; font-size:.88rem; padding:.5rem .8rem; transition:.15s; }
.stButton > button:hover { border-color: var(--accent); color: var(--accent);
    background: var(--accent-soft); }
.stButton > button[kind="primary"] { background: var(--accent); border-color: var(--accent);
    color:#17130a; font-weight:600; }
.stButton > button[kind="primary"]:hover { background:#e4c26d; color:#17130a; }
.stButton > button:disabled { opacity:.4; }

/* Boas-vindas */
.hero { padding:5.5rem 0 2rem; }
.hero .hi { font-size:1.9rem; color: var(--accent); font-weight:400; line-height:1.2; }
.hero .ask { font-size:2.8rem; color: var(--accent); font-weight:500; line-height:1.15;
    letter-spacing:-.01em; }
.topbar { position:fixed; top:.9rem; right:4.2rem; z-index:5; font-size:.75rem;
    color: var(--muted); display:flex; gap:.5rem; align-items:center; }
.chip { padding:.22rem .65rem; border:1px solid var(--border); border-radius:999px;
    background: var(--side); }
.chip b { color: var(--accent); font-weight:500; }
/* Engrenagem fixa no canto superior direito */
/* z-index acima do stHeader (fixo, transparente), que cobre o topo e captura os cliques */
.st-key-settings { position:fixed; top:.65rem; right:1.4rem; z-index:1000000; width:auto; }
.st-key-settings button { width:2.2rem; height:2.2rem; min-height:0; padding:0;
    justify-content:center; border-radius:999px; background: var(--side); color: var(--muted); }

/* Modal */
[data-testid="stDialog"] [role="dialog"] { background: var(--side);
    border:1px solid var(--border); border-radius:14px; }
.dialog-hint { color: var(--muted); font-size:.82rem; margin-bottom:.8rem; }

/* Sugestões */
.main .stButton > button { justify-content:center; text-align:center; background: var(--card);
    border-color: var(--border); color:#cfcfd5; font-size:.82rem; font-weight:400;
    height:100%; min-height:3.2rem; border-radius:12px; }

/* Mensagens */
[data-testid="stChatMessageAvatarUser"], [data-testid="stChatMessageAvatarAssistant"],
[data-testid="stChatMessage"] > div:first-child:has(img, span[data-testid]) { display:none; }
[data-testid="stChatMessage"] { background: transparent; padding:.6rem 0; gap:0; }
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background: var(--card); border:1px solid var(--border); border-radius:14px;
    padding:.8rem 1.1rem; margin-left:auto; max-width:85%; }
[data-testid="stExpander"], [data-testid="stStatus"] { border:1px solid var(--border);
    border-radius:10px; background: var(--side); }
.tool-chip { font-family: ui-monospace, Consolas, monospace; font-size:.78rem;
    color: var(--accent); }

/* Ferramentas usadas: um bloco recolhível com a lista, e cada ferramenta recolhível dentro */
.tools { display:inline-block; max-width:100%; margin:0 0 .7rem; font-size:.8rem; }
.tools summary { list-style:none; cursor:pointer; user-select:none; }
.tools summary::-webkit-details-marker { display:none; }
.tools > summary { display:inline-flex; align-items:center; gap:.45rem; color: var(--muted);
    padding:.28rem .75rem; border:1px solid var(--border); border-radius:999px;
    background: var(--side); transition:.15s; }
.tools > summary:hover, .tools[open] > summary { color: var(--accent);
    border-color: rgba(216,180,90,.35); }
.tools > summary b { color: var(--accent); font-weight:600; }
.tools summary::before { content:"›"; display:inline-block; transition:transform .15s;
    font-size:.95rem; line-height:1; }
.tools details[open] > summary::before, .tools[open] > summary::before { transform:rotate(90deg); }
.tools-list { margin-top:.4rem; width:min(560px, 100%); border:1px solid var(--border);
    border-radius:10px; background: var(--side); padding:.25rem; }
.tool-item > summary { display:flex; align-items:center; gap:.5rem; padding:.4rem .55rem;
    border-radius:7px; color: var(--text); }
.tool-item > summary:hover { background: var(--card); }
.tool-item > summary::before { color: var(--muted); }
.tool-name { font-family: ui-monospace, Consolas, monospace; color: var(--accent);
    font-size:.78rem; flex:0 0 auto; }
.tool-preview { color: var(--muted); overflow:hidden; text-overflow:ellipsis;
    white-space:nowrap; min-width:0; }
.tool-args { margin:.15rem .4rem .45rem 1.4rem; padding:.55rem .7rem; max-height:180px;
    overflow:auto; background: var(--bg); border:1px solid var(--border); border-radius:7px;
    font-family: ui-monospace, Consolas, monospace; font-size:.74rem; color:#cfcfd5;
    white-space:pre-wrap; word-break:break-word; }

/* Input */
[data-testid="stBottom"] > div { background: transparent; }
[data-testid="stBottom"] [data-testid="stBottomBlockContainer"] { max-width:800px;
    padding-bottom:2.2rem; position:relative; }
[data-testid="stBottom"] [data-testid="stBottomBlockContainer"]::after {
    content:"As respostas podem apresentar imprecisões. Considere revisar em fontes confiáveis.";
    position:absolute; bottom:.6rem; left:0; right:0; text-align:center;
    font-size:.7rem; color: var(--muted); }
[data-testid="stChatInput"] { border-radius:18px; border:1px solid var(--border);
    background: var(--card); padding:.35rem; }
[data-testid="stChatInput"]:focus-within { border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft); }
[data-testid="stChatInput"] textarea { background: transparent; color: var(--text); }
[data-testid="stChatInputSubmitButton"] { background: var(--card-2); color: var(--muted); }
[data-testid="stChatInputSubmitButton"]:hover { background: var(--accent); color:#17130a; }
</style>
"""


@st.cache_resource(show_spinner="Iniciando o agente…")
def load_agent() -> tuple[Any, bool]:
    """Cria o agente uma única vez por processo (reaproveita as conexões SQLite entre reruns)."""
    tracing = setup_langsmith()
    return get_agent(), tracing


def new_conversation() -> None:
    """Zera a conversa atual e abre um novo thread_id (só é gravada ao enviar a 1ª mensagem)."""
    st.session_state.messages = []
    st.session_state.thread_id = str(uuid.uuid4())


def open_conversation(conversation_id: str) -> None:
    """Carrega do SQLite uma conversa antiga e continua nela (mesmo thread_id)."""
    stored = load_conversation(get_settings().user_id, conversation_id)
    st.session_state.messages = [
        {"role": m.role, "content": m.content, "tools": m.tools} for m in stored
    ]
    st.session_state.thread_id = conversation_id


def list_data_files() -> list[Path]:
    """Arquivos que serão indexados (pasta data/raw)."""
    data_dir = get_settings().data_dir
    if not data_dir.exists():
        return []
    return sorted(p for p in data_dir.iterdir() if p.is_file())


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def remove_conversation(conversation_id: str) -> None:
    """Apaga a conversa do SQLite e do checkpointer; se era a ativa, abre uma nova."""
    delete_conversation(get_settings().user_id, conversation_id)
    agent, _ = load_agent()
    agent.checkpointer.delete_thread(conversation_id)
    if conversation_id == st.session_state.thread_id:
        new_conversation()


def ask_delete(conversation_id: str, title: str) -> None:
    """Marca a conversa para apagar; o modal de confirmação abre no rerun."""
    st.session_state.delete_target = (conversation_id, title)


def clear_delete_target() -> None:
    """Esquece a conversa marcada para apagar (fecha a confirmação)."""
    st.session_state.pop("delete_target", None)


# A conversa a apagar fica no session_state (e não só no clique da lixeira) para o modal
# continuar aberto nos reruns; fechar pelo X/ESC/clique fora limpa o alvo via on_dismiss.
@st.dialog(
    "Apagar conversa?", icon=":material/delete:", width="small", on_dismiss=clear_delete_target
)
def confirm_delete_dialog(conversation_id: str, title: str) -> None:
    """Confirmação antes de apagar uma conversa do histórico."""
    st.markdown(
        f'<div class="dialog-hint">A conversa <b>{_esc(title)}</b> e todas as mensagens dela '
        "serão apagadas. Essa ação não pode ser desfeita.</div>",
        unsafe_allow_html=True,
    )
    cancel, confirm = st.columns(2)
    if cancel.button("Cancelar", key="confirm-cancel"):
        clear_delete_target()
        st.rerun()
    if confirm.button("Apagar", key="confirm-delete", type="primary", icon=":material/delete:"):
        clear_delete_target()
        remove_conversation(conversation_id)
        st.rerun()


def render_conversation_item(conv: ConversationSummary) -> None:
    """Linha do histórico: botão que abre a conversa + lixeira discreta."""
    active = conv.id == st.session_state.thread_id
    prefix = "conv-active" if active else "conv"
    with st.container(key=f"row-{conv.id}", horizontal=True, vertical_alignment="center", gap=None):
        if st.button(
            conv.title,
            key=f"{prefix}-{conv.id}",
            help=f"{conv.updated_at.astimezone():%d/%m/%Y %H:%M}",
            width="stretch",
        ):
            open_conversation(conv.id)
            st.rerun()
        st.button(
            "",
            key=f"del-{conv.id}",
            icon=":material/delete:",
            help="Apagar conversa",
            on_click=ask_delete,
            args=(conv.id, conv.title),
        )


def render_sidebar(tracing: bool) -> None:
    with st.sidebar:
        st.markdown('<div class="side-title">Assistente Órbita</div>', unsafe_allow_html=True)
        if st.button("Nova conversa", type="primary", icon=":material/add_circle:"):
            new_conversation()
            st.rerun()

        # Histórico de conversas do usuário (SQLite)
        st.markdown('<div class="side-label">Conversas recentes</div>', unsafe_allow_html=True)
        conversations = list_conversations(get_settings().user_id)
        if not conversations:
            st.caption("Nenhuma conversa ainda.")
        for conv in conversations:
            render_conversation_item(conv)
        if target := st.session_state.get("delete_target"):
            confirm_delete_dialog(*target)

        st.markdown(
            f'<div class="side-label">Sessão</div><div class="side-meta">'
            f"Usuário: {_esc(get_settings().user_id)}<br>"
            f"LangSmith: {'ligado' if tracing else 'desligado'}</div>",
            unsafe_allow_html=True,
        )


def _ext_badge(name: str) -> str:
    return f'<span class="file-ext">{_esc(Path(name).suffix.lstrip(".").upper() or "—")}</span>'


def _format_size(size: int) -> str:
    return f"{size / 1024:.0f} KB" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} MB"


def _ingest() -> tuple[str, str]:
    """Roda a ingestão e devolve (tipo, mensagem) para mostrar no modal."""
    try:
        result = run_ingestion()
    except Exception as exc:  # noqa: BLE001 - mostrar qualquer falha ao usuário
        logger.exception("Falha na ingestão")
        return "error", f"Falha na ingestão: {exc}"
    return "success", (
        f"{result.total} chunks na base: {result.added} novo(s) ou alterado(s), "
        f"{result.deleted} removido(s)."
    )


def _show_feedback(key: str) -> None:
    """Mostra (uma vez) as mensagens guardadas antes do último rerun do modal."""
    for kind, text in st.session_state.pop(key, []):
        getattr(st, kind)(text)


def render_knowledge_tab() -> None:
    """Aba com os arquivos de data/raw e o botão para gerar os embeddings."""
    files = list_data_files()
    st.markdown(
        '<div class="dialog-hint">Arquivos de <code>data/raw</code> indexados no Astra DB. '
        "Gere os embeddings de novo sempre que os documentos mudarem.</div>",
        unsafe_allow_html=True,
    )
    if files:
        rows = "".join(
            f'<div class="file-row">{_ext_badge(p.name)}'
            f'<span class="file-name">{_esc(p.name)}</span></div>'
            for p in files
        )
        st.markdown(rows, unsafe_allow_html=True)
    else:
        st.caption("Nenhum arquivo em data/raw.")

    st.write("")
    if st.button(
        "Gerar embeddings", type="primary", disabled=not files, icon=":material/database:"
    ):
        with st.spinner(f"Indexando {len(files)} arquivo(s)…"):
            kind, text = _ingest()
        getattr(st, kind)(text)


# Arquivos adicionados e ainda não enviados: {nome: (conteúdo, validação)}. Ficam no
# session_state (e não no file_uploader) para a lista ter remoção e status por arquivo.
PendingUploads = dict[str, tuple[bytes, UploadCheck]]


def _pending_uploads() -> PendingUploads:
    if "pending_uploads" not in st.session_state:
        st.session_state.pending_uploads = {}
    pending: PendingUploads = st.session_state.pending_uploads
    return pending


def _uploader_key() -> str:
    return f"uploader-{st.session_state.get('uploader_version', 0)}"


def _on_files_added() -> None:
    """Move os arquivos do uploader para a lista de pendentes e esvazia o uploader."""
    pending = _pending_uploads()
    for file in st.session_state.get(_uploader_key()) or []:
        data = file.getvalue()
        check = check_upload(file.name, data)
        pending[check.name or file.name] = (data, check)  # mesmo nome: o último vale
    # Chave nova = uploader vazio, pronto para receber mais arquivos
    st.session_state.uploader_version = st.session_state.get("uploader_version", 0) + 1


def _remove_pending(name: str) -> None:
    _pending_uploads().pop(name, None)


def _upload_status(check: UploadCheck) -> str:
    if not check.ok:
        return f'<span class="file-status bad">Recusado: {_esc(check.error or "")}</span>'
    if check.injection_signals:
        return (
            '<span class="file-status warn">Contém texto com cara de instrução; '
            "o agente vai tratá-lo só como dado</span>"
        )
    if check.replaces:
        return '<span class="file-status warn">Substitui o arquivo existente</span>'
    return '<span class="file-status">Pronto para enviar</span>'


def _send_pending() -> None:
    """Salva os arquivos válidos em data/raw e indexa a base."""
    pending = _pending_uploads()
    feedback: list[tuple[str, str]] = []
    saved: list[str] = []
    with st.spinner("Salvando e indexando…"):
        for name in [n for n, (_, check) in pending.items() if check.ok]:
            data, _ = pending[name]
            try:
                save_upload(name, data)
            except (ValueError, OSError) as exc:
                logger.exception("Falha ao salvar %s", name)
                feedback.append(("error", f"Não foi possível salvar {name}: {exc}"))
                continue
            saved.append(name)
            del pending[name]
        if saved:
            feedback.append(("success", f"{len(saved)} arquivo(s) salvo(s) em data/raw."))
            kind, text = _ingest()
            if kind == "error":
                text += " Os arquivos foram salvos: tente de novo em Gerar embeddings."
            feedback.append((kind, text))
    st.session_state.upload_feedback = feedback


def render_upload_tab() -> None:
    """Aba para adicionar documentos novos: escolhe, revisa a lista e envia."""
    _show_feedback("upload_feedback")
    settings = get_settings()
    extensions = sorted(ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS)
    st.markdown(
        '<div class="dialog-hint">Os arquivos ficam na lista abaixo até você enviar. Ao '
        "enviar, eles são salvos em <code>data/raw</code> e a base é indexada de novo. "
        f"Formatos: {', '.join(extensions).upper()}; até {settings.upload_max_mb} MB cada."
        "</div>",
        unsafe_allow_html=True,
    )
    st.file_uploader(
        "Adicionar arquivos",
        type=extensions,
        accept_multiple_files=True,
        key=_uploader_key(),
        on_change=_on_files_added,
        label_visibility="collapsed",
    )

    pending = _pending_uploads()
    if not pending:
        st.caption("Nenhum arquivo aguardando envio.")
        return

    st.markdown('<div class="side-label">Aguardando envio</div>', unsafe_allow_html=True)
    for index, (name, (_, check)) in enumerate(pending.items()):
        with st.container(
            key=f"pending-{index}", horizontal=True, vertical_alignment="center", gap=None
        ):
            st.markdown(
                f'<div class="file-row">{_ext_badge(name)}<div class="file-info">'
                f'<span class="file-name">{_esc(name)} · {_format_size(check.size)}</span>'
                f"{_upload_status(check)}</div></div>",
                unsafe_allow_html=True,
                width="stretch",
            )
            st.button(
                "",
                key=f"rm-{index}",
                icon=":material/close:",
                help="Tirar da lista",
                on_click=_remove_pending,
                args=(name,),
            )

    valid = sum(check.ok for _, check in pending.values())
    if valid < len(pending):
        st.caption(
            "Arquivos recusados não são enviados: tire-os da lista ou corrija e adicione de novo."
        )
    if st.button(
        f"Enviar {valid} arquivo(s)",
        type="primary",
        disabled=not valid,
        icon=":material/upload:",
        key="send-uploads",
    ):
        _send_pending()
        st.rerun(scope="fragment")  # atualiza as duas abas sem fechar o modal


@st.dialog("Configurações", icon=":material/settings:", width="medium")
def settings_dialog() -> None:
    """Modal da engrenagem: base de conhecimento e upload de documentos novos."""
    knowledge_tab, upload_tab = st.tabs(["Base de conhecimento", "Adicionar arquivos"])
    with knowledge_tab:
        render_knowledge_tab()
    with upload_tab:
        render_upload_tab()


def render_topbar() -> None:
    st.markdown(
        f'<div class="topbar"><span class="chip">Modelo <b>{_esc(get_settings().llm_model)}</b>'
        "</span></div>",
        unsafe_allow_html=True,
    )
    if st.button("", key="settings", icon=":material/settings:", help="Configurações"):
        settings_dialog()


def _html_text(text: str) -> str:
    """Escapa para HTML dentro do st.markdown: sem quebra de linha (uma linha em branco
    encerraria o bloco HTML) e sem `$` (o Streamlit leria como fórmula LaTeX)."""
    return _esc(text).replace("\n", "&#10;").replace("$", "&#36;")


def _args_preview(args: dict[str, Any]) -> str:
    """Resumo de uma linha dos argumentos (ex.: a query), mostrado ao lado do nome."""
    return " · ".join(str(v) for v in args.values())


def tools_html(tools: list[dict[str, Any]]) -> str:
    """Bloco recolhível "N ferramentas usadas"; dentro, cada ferramenta abre os argumentos.

    Usa <details> em vez de st.expander porque o Streamlit não permite expander aninhado,
    e assim abrir e fechar não causa rerun.
    """
    items = "".join(
        '<details class="tool-item"><summary>'
        f'<span class="tool-name">{_html_text(call["name"])}</span>'
        f'<span class="tool-preview">{_html_text(_args_preview(call["args"]))}</span>'
        "</summary>"
        f'<pre class="tool-args">'
        f"{_html_text(json.dumps(call['args'], ensure_ascii=False, indent=2))}</pre>"
        "</details>"
        for call in tools
    )
    label = "ferramenta usada" if len(tools) == 1 else "ferramentas usadas"
    return (
        f'<details class="tools"><summary><b>{len(tools)}</b> {label}</summary>'
        f'<div class="tools-list">{items}</div></details>'
    )


def render_message(msg: dict[str, Any]) -> None:
    with st.chat_message(msg["role"]):
        if tools := msg.get("tools"):
            st.markdown(tools_html(tools), unsafe_allow_html=True)
        st.markdown(msg["content"])


def run_agent(question: str) -> None:
    """Executa o agente em streaming e mostra tools + resposta em tempo real."""
    agent, _ = load_agent()
    settings = get_settings()
    context = UserContext(user_id=settings.user_id)
    thread_id = st.session_state.thread_id
    config: RunnableConfig = {
        "configurable": {"thread_id": thread_id},
        "metadata": {
            "thread_id": thread_id,
            "user_id": context.user_id,
            "llm_model": settings.llm_model,
        },
        "tags": ["streamlit", "memoria-sqlite"],
    }

    # Estado antes do turno: usado para desfazê-lo se falhar no meio
    before = agent.get_state(config)

    # Conversa sem checkpoint (ex.: gravada antes do checkpointer em SQLite): reconstrói o
    # contexto a partir do histórico, ignorando turnos que falharam
    history: list[Any] = []
    if not before.values:
        stored = [
            StoredMessage(m["role"], m["content"])
            for m in st.session_state.messages[:-1]
            if not m.get("error")
        ]
        history = to_agent_messages(stored)

    tools: list[dict[str, Any]] = []
    answer = ""
    failed = False
    with st.chat_message("assistant"):
        status = st.status("Pensando…", expanded=False)
        placeholder = st.empty()
        streamed = ""  # texto da resposta chegando token a token
        try:
            # "messages" entrega os tokens do LLM conforme são gerados (efeito de digitação);
            # "updates" entrega cada passo completo (chamadas de tool e a resposta final)
            for mode, data in agent.stream(
                {"messages": [*history, HumanMessage(question)]},
                config,
                context=context,
                stream_mode=["messages", "updates"],
            ):
                if mode == "messages":
                    chunk, meta = data
                    # Só tokens do nó "model": o resumo (SummarizationMiddleware) também
                    # chama o LLM, e o texto dele não é a resposta ao colaborador
                    if (
                        meta.get("langgraph_node") == "model"
                        and isinstance(chunk, AIMessageChunk)
                        and (text := chunk.text)
                    ):
                        streamed += text
                        placeholder.markdown(streamed + "▌")
                    continue

                for node, step in data.items():
                    # Só o nó "model" (LLM) e o guardrail de prompt (resposta fixa, sem
                    # LLM) trazem mensagens novas. O resumo (SummarizationMiddleware)
                    # devolve as mensagens antigas preservadas, que seriam mostradas de
                    # novo como se fossem deste turno.
                    if node not in ("model", PROMPT_PROTECTION_NODE) or not isinstance(step, dict):
                        continue
                    for message in step.get("messages", []):
                        if isinstance(message, AIMessage) and message.tool_calls:
                            # Texto que veio antes de uma chamada de tool não é a resposta
                            streamed = ""
                            placeholder.empty()
                            for call in message.tool_calls:
                                tools.append({"name": call["name"], "args": call["args"]})
                                status.update(label=f"Usando {call['name']}…")
                                # Ao vivo, só o nome; os argumentos ficam no bloco
                                # recolhível que aparece com a resposta (render_message)
                                with status:
                                    st.markdown(
                                        f'<span class="tool-chip">{_esc(call["name"])}</span>',
                                        unsafe_allow_html=True,
                                    )
                        elif isinstance(message, ToolMessage):
                            continue
                        elif isinstance(message, AIMessage):
                            answer = message.text
                            placeholder.markdown(answer)
            status.update(
                label=f"{len(tools)} ferramenta(s) usada(s)" if tools else "Resposta pronta",
                state="complete",
            )
        except Exception:  # noqa: BLE001 - qualquer falha vira mensagem amigável ao usuário
            # Detalhes técnicos só no log (e no trace do LangSmith), não na tela
            logger.exception("Falha ao executar o agente (thread %s)", thread_id)
            failed = True
            status.update(label="Erro", state="error")
            answer = ERROR_ANSWER
            placeholder.markdown(answer)
            try:
                rollback_turn(agent, config, before)
            except Exception:  # noqa: BLE001 - o turno já falhou; só registra
                logger.exception("Falha ao desfazer o turno (thread %s)", thread_id)

    if failed:
        # O turno com falha fica só na tela: não vai para o histórico nem para o contexto
        st.session_state.messages[-1]["error"] = True
        st.session_state.messages.append({"role": "assistant", "content": answer, "error": True})
        return

    st.session_state.messages.append({"role": "assistant", "content": answer, "tools": tools})
    save_turn(context.user_id, thread_id, question, answer, tools)


def main() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    if "messages" not in st.session_state:
        new_conversation()
    _, tracing = load_agent()
    render_sidebar(tracing)
    render_topbar()

    pending: str | None = None

    if not st.session_state.messages:
        st.markdown(
            f'<div class="hero"><div class="hi">Saudações, {USER_NAME}.</div>'
            '<div class="ask">Qual sua dúvida hoje?</div></div>',
            unsafe_allow_html=True,
        )
        cols = st.columns(len(SUGGESTIONS))
        for col, text in zip(cols, SUGGESTIONS, strict=True):
            if col.button(text, key=f"sug-{text}"):
                pending = text

    for msg in st.session_state.messages:
        render_message(msg)

    typed = st.chat_input("Pergunte alguma coisa...")
    question = typed or pending
    if question:
        # Pergunta e resposta são gravadas juntas no SQLite ao final do turno (save_turn)
        st.session_state.messages.append({"role": "user", "content": question})
        render_message(st.session_state.messages[-1])
        run_agent(question)
        st.rerun()


main()
