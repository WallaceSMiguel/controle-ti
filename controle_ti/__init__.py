import configparser
import os
import secrets
from datetime import date, datetime
from pathlib import Path

from flask import Flask, g, redirect, render_template, request, url_for

from . import db, seguranca

PADROES = {
    "host": "0.0.0.0",
    "porta": "8443",
    "https": "sim",
    "timeout_minutos": "15",
    "backup_manter": "30",
}

PUBLICOS = {"static", "auth.login", "auth.setup"}


def ler_config(pasta_dados: Path) -> configparser.SectionProxy:
    cfg = configparser.ConfigParser()
    arquivo = pasta_dados / "config.ini"
    if arquivo.exists():
        cfg.read(arquivo, encoding="utf-8")
    if "servidor" not in cfg:
        cfg["servidor"] = {}
    alterou = False
    for k, v in PADROES.items():
        if k not in cfg["servidor"]:
            cfg["servidor"][k] = v
            alterou = True
    if alterou:
        with open(arquivo, "w", encoding="utf-8") as f:
            cfg.write(f)
    return cfg["servidor"]


def _chave_secreta(pasta: Path) -> str:
    arq = pasta / "chave_sessao.txt"
    if not arq.exists():
        arq.write_text(secrets.token_hex(32), encoding="utf-8")
        try:
            os.chmod(arq, 0o600)
        except OSError:
            pass
    return arq.read_text(encoding="utf-8").strip()


def create_app(pasta_dados: str | None = None) -> Flask:
    base = Path(__file__).resolve().parent.parent
    pasta = Path(pasta_dados or os.environ.get("CONTROLE_TI_DADOS") or base / "dados")
    pasta.mkdir(parents=True, exist_ok=True)
    cfg = ler_config(pasta)

    app = Flask(__name__)
    usa_https = cfg.get("https", "sim").lower() in ("sim", "s", "true", "1")
    app.config.update(
        SECRET_KEY=_chave_secreta(pasta),
        PASTA_DADOS=str(pasta),
        DB_PATH=str(pasta / "controle_ti.db"),
        TIMEOUT_MIN=int(cfg.get("timeout_minutos", "15")),
        BACKUP_MANTER=int(cfg.get("backup_manter", "30")),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=usa_https,
        SESSION_COOKIE_NAME="controle_ti",
        MAX_CONTENT_LENGTH=150 * 1024 * 1024,  # importação em lote do msinfo32
    )
    db.inicializar(app.config["DB_PATH"])
    app.teardown_appcontext(db.fechar_db)

    from .rotas import admin, auth, cofre, estoque, painel
    for bp in (auth.bp, painel.bp, estoque.bp, cofre.bp, admin.bp):
        app.register_blueprint(bp)

    @app.before_request
    def antes():
        g.usuario = None
        g.dek = None
        if request.method == "POST":
            seguranca.validar_csrf()
        if request.endpoint in PUBLICOS:
            return None
        if not db.existe_usuario():
            return redirect(url_for("auth.setup"))
        s = seguranca.obter_sessao()
        if not s:
            seguranca.encerrar_sessao()
            if request.path.startswith("/api/"):
                return {"erro": "Sessão expirada"}, 401
            return redirect(url_for("auth.login", proximo=request.full_path))
        u = seguranca.carregar_usuario(s["uid"])
        if not u:
            seguranca.encerrar_sessao()
            return redirect(url_for("auth.login"))
        g.usuario = u
        g.dek = s["dek"]
        if u.trocar_senha and request.endpoint not in ("auth.trocar_senha", "auth.logout"):
            return redirect(url_for("auth.trocar_senha"))
        return None

    @app.after_request
    def cabecalhos(resp):
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; frame-ancestors 'none'")
        if request.endpoint != "static":
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.context_processor
    def contexto():
        return {
            "usuario": g.get("usuario"),
            "csrf_token": seguranca.csrf_token,
            "timeout_min": app.config["TIMEOUT_MIN"],
            "hoje": date.today().isoformat(),
        }

    from . import msinfo

    def hw_resumo(row):
        try:
            return msinfo.resumo_curto({k: row[k] for k in ("processador", "memoria_gb", "armazenamento")})
        except (KeyError, IndexError, TypeError):
            return ""

    app.jinja_env.globals.update(
        hw_resumo=hw_resumo, memoria_txt=msinfo.memoria_txt, capacidade=msinfo.capacidade,
        gb_legivel=msinfo.gb_legivel, processador_curto=msinfo.processador_curto)

    @app.template_filter("databr")
    def databr(valor, com_hora=False):
        if not valor:
            return "—"
        try:
            if len(valor) > 10:
                d = datetime.strptime(valor[:19], "%Y-%m-%d %H:%M:%S")
                return d.strftime("%d/%m/%Y %H:%M") if com_hora else d.strftime("%d/%m/%Y")
            return datetime.strptime(valor, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            return valor

    def erro(codigo, titulo):
        def handler(e):
            msg = getattr(e, "description", "") or ""
            if msg == getattr(type(e), "description", None):
                msg = ""  # mensagem padrão (em inglês) do Werkzeug
            return render_template("erro.html", codigo=codigo, titulo=titulo, msg=msg), codigo
        return handler

    app.register_error_handler(400, erro(400, "Requisição inválida"))
    app.register_error_handler(403, erro(403, "Acesso negado"))
    app.register_error_handler(404, erro(404, "Página não encontrada"))
    return app
