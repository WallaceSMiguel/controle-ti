"""Sessões, permissões, CSRF, bloqueio de login e auditoria."""
import secrets
import threading
import time
from functools import wraps

from flask import abort, current_app, g, request, session

from . import db

# ---------------------------------------------------------------- sessões ---
# A chave de dados (DEK) de cada sessão fica apenas na memória do servidor.
_sessoes: dict[str, dict] = {}
_lock = threading.Lock()


def _timeout() -> int:
    return int(current_app.config["TIMEOUT_MIN"]) * 60


def criar_sessao(usuario_id: int, dek: bytes | None):
    sid = secrets.token_urlsafe(32)
    with _lock:
        _sessoes[sid] = {"uid": usuario_id, "dek": dek, "ultimo": time.time()}
    session.clear()
    session["sid"] = sid
    session["csrf"] = secrets.token_urlsafe(32)


def obter_sessao() -> dict | None:
    sid = session.get("sid")
    if not sid:
        return None
    agora = time.time()
    limite = _timeout()
    with _lock:
        # limpeza das expiradas
        for k in [k for k, v in _sessoes.items() if agora - v["ultimo"] > limite]:
            del _sessoes[k]
        s = _sessoes.get(sid)
        if s:
            s["ultimo"] = agora
        return s


def encerrar_sessao():
    sid = session.get("sid")
    with _lock:
        _sessoes.pop(sid, None)
    session.clear()


def encerrar_sessoes_usuario(uid: int):
    with _lock:
        for k in [k for k, v in _sessoes.items() if v["uid"] == uid]:
            del _sessoes[k]


def encerrar_todas_sessoes():
    with _lock:
        _sessoes.clear()


def atualizar_dek_sessao(dek: bytes | None):
    sid = session.get("sid")
    with _lock:
        if sid in _sessoes:
            _sessoes[sid]["dek"] = dek


# ---------------------------------------------------------------- usuário ---
PERFIS = {
    "admin": "Administrador",
    "tecnico": "Técnico",
    "consulta": "Consulta",
}


class Usuario:
    def __init__(self, row, unidades_ids):
        self.id = row["id"]
        self.usuario = row["usuario"]
        self.nome = row["nome"]
        self.perfil = row["perfil"]
        self.acesso_cofre = bool(row["acesso_cofre"])
        self.todas_unidades = bool(row["todas_unidades"]) or row["perfil"] == "admin"
        self.trocar_senha = bool(row["trocar_senha"])
        self.tem_dek = bool(row["dek_envolvida"])
        self.unidades_ids = unidades_ids

    @property
    def perfil_nome(self):
        return PERFIS.get(self.perfil, self.perfil)

    @property
    def e_admin(self):
        return self.perfil == "admin"

    @property
    def pode_editar_estoque(self):
        return self.perfil in ("admin", "tecnico")

    @property
    def pode_senhas_pc(self):
        return self.perfil in ("admin", "tecnico")

    @property
    def pode_cofre(self):
        return self.perfil == "admin" or self.acesso_cofre

    @property
    def iniciais(self):
        partes = [p for p in self.nome.split() if p]
        return (partes[0][0] + (partes[-1][0] if len(partes) > 1 else "")).upper()

    def acessa_unidade(self, unidade_id) -> bool:
        if unidade_id is None:  # registros "Geral" do cofre
            return True
        return self.todas_unidades or int(unidade_id) in self.unidades_ids

    def filtro_unidade(self, coluna: str, incluir_geral=False):
        """Retorna (sql, params) para restringir consultas às unidades do usuário."""
        if self.todas_unidades:
            return "1=1", []
        ids = self.unidades_ids or [-1]
        sql = f"{coluna} IN ({','.join('?' * len(ids))})"
        if incluir_geral:
            sql = f"({sql} OR {coluna} IS NULL)"
        return sql, list(ids)


def precisa_dek(perfil: str, acesso_cofre: bool) -> bool:
    return perfil in ("admin", "tecnico") or bool(acesso_cofre)


def carregar_usuario(uid: int) -> Usuario | None:
    con = db.get_db()
    row = con.execute("SELECT * FROM usuarios WHERE id = ? AND ativo = 1", (uid,)).fetchone()
    if not row:
        return None
    ids = [r[0] for r in con.execute(
        "SELECT unidade_id FROM usuario_unidades WHERE usuario_id = ?", (uid,))]
    return Usuario(row, ids)


# ------------------------------------------------------------- decorators ---
def requer(condicao):
    def deco(f):
        @wraps(f)
        def inner(*a, **kw):
            if not condicao(g.usuario):
                abort(403)
            return f(*a, **kw)
        return inner
    return deco


requer_admin = requer(lambda u: u.e_admin)
requer_editor = requer(lambda u: u.pode_editar_estoque)
requer_senhas_pc = requer(lambda u: u.pode_senhas_pc)
requer_cofre = requer(lambda u: u.pode_cofre)


def dek_atual() -> bytes:
    dek = g.get("dek")
    if not dek:
        abort(403, "Seu usuário ainda não tem a chave de acesso às senhas. "
                   "Peça ao administrador para redefinir sua senha.")
    return dek


# ------------------------------------------------------------------- CSRF ---
def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def validar_csrf():
    esperado = session.get("csrf")
    enviado = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
    if not esperado or not enviado or not secrets.compare_digest(esperado, enviado):
        abort(400, "Formulário expirado. Recarregue a página e tente novamente.")


# ------------------------------------------------------- bloqueio de login ---
_falhas: dict[str, tuple[int, float]] = {}
MAX_FALHAS = 5
BLOQUEIO_SEG = 5 * 60


def login_bloqueado(usuario: str) -> int:
    """Segundos restantes de bloqueio (0 = liberado)."""
    n, ate = _falhas.get(usuario.lower(), (0, 0))
    resto = int(ate - time.time())
    return resto if resto > 0 else 0


def registrar_falha(usuario: str):
    chave = usuario.lower()
    n, ate = _falhas.get(chave, (0, 0))
    if ate and ate < time.time():
        n = 0
    n += 1
    _falhas[chave] = (n, time.time() + BLOQUEIO_SEG if n >= MAX_FALHAS else 0)


def limpar_falhas(usuario: str):
    _falhas.pop(usuario.lower(), None)


# -------------------------------------------------------------- auditoria ---
def auditar(acao: str, detalhe: str = "", usuario: str | None = None):
    if usuario is None:
        u = g.get("usuario")
        usuario = u.usuario if u else None
    con = db.get_db()
    con.execute(
        "INSERT INTO auditoria (data, usuario, acao, detalhe, ip) VALUES (?, ?, ?, ?, ?)",
        (db.agora(), usuario, acao, detalhe, request.remote_addr if request else None),
    )
    con.commit()
