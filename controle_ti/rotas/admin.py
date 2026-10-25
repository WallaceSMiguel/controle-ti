from datetime import datetime
from pathlib import Path

from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template,
                   request, send_file, url_for)
from werkzeug.security import generate_password_hash

from .. import backup, cripto, db
from .. import seguranca as seg
from . import txt
from .auth import validar_nova_senha

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.before_request
def so_admin():
    if not g.usuario or not g.usuario.e_admin:
        abort(403)


# ---------------------------------------------------------------- usuários ---
@bp.route("/usuarios")
def usuarios():
    con = db.get_db()
    lista = con.execute("SELECT * FROM usuarios ORDER BY ativo DESC, nome").fetchall()
    unidades: dict[int, list] = {}
    for r in con.execute("SELECT uu.usuario_id, un.nome FROM usuario_unidades uu "
                         "JOIN unidades un ON un.id = uu.unidade_id ORDER BY un.nome"):
        unidades.setdefault(r["usuario_id"], []).append(r["nome"])
    return render_template("usuarios_lista.html", lista=lista, unidades=unidades,
                           perfis=seg.PERFIS)


def _salvar_unidades(con, uid, ids):
    con.execute("DELETE FROM usuario_unidades WHERE usuario_id = ?", (uid,))
    for i in ids:
        con.execute("INSERT INTO usuario_unidades (usuario_id, unidade_id) VALUES (?, ?)",
                    (uid, i))


@bp.route("/usuarios/novo", methods=["GET", "POST"])
@bp.route("/usuarios/<int:uid>", methods=["GET", "POST"], endpoint="usuario_editar")
def usuario_novo(uid=None):
    con = db.get_db()
    alvo = con.execute("SELECT * FROM usuarios WHERE id = ?", (uid,)).fetchone() if uid else None
    if uid and not alvo:
        abort(404)
    todas_un = con.execute("SELECT id, nome, ativa FROM unidades ORDER BY nome").fetchall()
    erros = []
    if alvo:
        dados = dict(alvo)
        dados["unidades"] = [r[0] for r in con.execute(
            "SELECT unidade_id FROM usuario_unidades WHERE usuario_id = ?", (uid,))]
    else:
        dados = {"perfil": "tecnico", "ativo": 1, "unidades": [], "acesso_cofre": 0,
                 "todas_unidades": 0}

    if request.method == "POST":
        f = request.form
        dados = {
            "usuario": txt(f, "usuario", 50),
            "nome": txt(f, "nome", 100),
            "perfil": f.get("perfil"),
            "acesso_cofre": 1 if f.get("acesso_cofre") else 0,
            "todas_unidades": 1 if f.get("todas_unidades") else 0,
            "ativo": 1 if f.get("ativo") else 0,
            "unidades": [int(x) for x in f.getlist("unidades") if x.isdigit()],
        }
        senha = f.get("senha", "")
        if dados["perfil"] not in seg.PERFIS:
            erros.append("Perfil inválido.")
        if not dados["usuario"] or not dados["nome"]:
            erros.append("Preencha usuário e nome.")
        dup = con.execute("SELECT id FROM usuarios WHERE usuario = ? AND id != ?",
                          (dados["usuario"], uid or 0)).fetchone()
        if dup:
            erros.append("Esse nome de usuário já existe.")
        if dados["perfil"] != "admin" and not dados["todas_unidades"] and not dados["unidades"]:
            erros.append("Selecione ao menos uma unidade (ou marque “todas as unidades”).")
        if senha or not alvo:
            e = validar_nova_senha(senha, f.get("confirmacao", ""))
            if e:
                erros.append(e)
        if alvo and alvo["id"] == g.usuario.id and (dados["perfil"] != "admin" or not dados["ativo"]):
            erros.append("Você não pode remover seu próprio acesso de administrador.")

        precisa = seg.precisa_dek(dados["perfil"], dados["acesso_cofre"])
        tem = bool(alvo and alvo["dek_envolvida"])
        if precisa and not tem and not senha:
            erros.append("Para liberar acesso às senhas, defina uma senha temporária "
                         "para o usuário (ela será trocada no primeiro login).")

        if not erros:
            salt = alvo["kek_salt"] if alvo else None
            envolvida = alvo["dek_envolvida"] if alvo else None
            if not precisa:
                salt = envolvida = None
            elif senha:
                salt, envolvida = cripto.envolver_dek(g.dek, senha)
            hash_ = generate_password_hash(senha) if senha else alvo["senha_hash"]
            if alvo:
                con.execute(
                    "UPDATE usuarios SET usuario = ?, nome = ?, perfil = ?, acesso_cofre = ?, "
                    "todas_unidades = ?, ativo = ?, senha_hash = ?, kek_salt = ?, "
                    "dek_envolvida = ?, trocar_senha = CASE WHEN ? THEN 1 ELSE trocar_senha END "
                    "WHERE id = ?",
                    (dados["usuario"], dados["nome"], dados["perfil"], dados["acesso_cofre"],
                     dados["todas_unidades"], dados["ativo"], hash_, salt, envolvida,
                     1 if senha else 0, uid))
                acao = "usuario_editado" + (" (senha redefinida)" if senha else "")
            else:
                cur = con.execute(
                    "INSERT INTO usuarios (usuario, nome, senha_hash, perfil, acesso_cofre, "
                    "todas_unidades, ativo, trocar_senha, kek_salt, dek_envolvida, criado_em) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)",
                    (dados["usuario"], dados["nome"], hash_, dados["perfil"],
                     dados["acesso_cofre"], dados["todas_unidades"], dados["ativo"],
                     salt, envolvida, db.agora()))
                uid = cur.lastrowid
                acao = "usuario_criado"
            _salvar_unidades(con, uid, dados["unidades"])
            con.commit()
            if alvo and alvo["id"] != g.usuario.id:
                seg.encerrar_sessoes_usuario(uid)  # aplica as novas permissões
            seg.auditar(acao, f"{dados['usuario']} — perfil {seg.PERFIS[dados['perfil']]}"
                              f"{', cofre' if dados['acesso_cofre'] else ''}"
                              f"{'' if dados['ativo'] else ', INATIVO'}")
            flash("Usuário salvo." + (" Informe a senha temporária ao usuário." if senha else ""),
                  "ok")
            return redirect(url_for("admin.usuarios"))
    return render_template("usuario_form.html", u=dados, alvo=alvo, erros=erros,
                           unidades=todas_un, perfis=seg.PERFIS)


# ---------------------------------------------------------------- unidades ---
@bp.route("/unidades", methods=["GET", "POST"])
def unidades():
    con = db.get_db()
    if request.method == "POST":
        acao = request.form.get("acao")
        nome = txt(request.form, "nome", 80)
        uid = request.form.get("id", type=int)
        try:
            if acao == "nova" and nome:
                con.execute("INSERT INTO unidades (nome) VALUES (?)", (nome,))
                seg.auditar("unidade_criada", nome)
            elif acao == "renomear" and uid and nome:
                con.execute("UPDATE unidades SET nome = ? WHERE id = ?", (nome, uid))
                seg.auditar("unidade_renomeada", f"#{uid} → {nome}")
            elif acao == "alternar" and uid:
                con.execute("UPDATE unidades SET ativa = 1 - ativa WHERE id = ?", (uid,))
                seg.auditar("unidade_ativacao", f"#{uid}")
            con.commit()
            flash("Unidades atualizadas.", "ok")
        except db.sqlite3.IntegrityError:
            flash("Já existe uma unidade com esse nome.", "erro")
        return redirect(url_for("admin.unidades"))
    lista = con.execute("""
        SELECT un.*, (SELECT COUNT(*) FROM equipamentos e WHERE e.unidade_id = un.id) equipamentos,
               (SELECT COUNT(*) FROM cofre c WHERE c.unidade_id = un.id) cofre
        FROM unidades un ORDER BY un.nome""").fetchall()
    return render_template("unidades.html", lista=lista)


# --------------------------------------------------------------- auditoria ---
@bp.route("/auditoria")
def auditoria():
    a = request.args
    where, params = ["1=1"], []
    if a.get("usuario"):
        where.append("usuario = ?")
        params.append(a.get("usuario"))
    if a.get("acao"):
        where.append("acao LIKE ?")
        params.append(f"{a.get('acao')}%")
    if a.get("de"):
        where.append("data >= ?")
        params.append(a.get("de"))
    if a.get("ate"):
        where.append("data <= ?")
        params.append(a.get("ate") + " 23:59:59")
    con = db.get_db()
    registros = con.execute("SELECT * FROM auditoria WHERE " + " AND ".join(where) +
                            " ORDER BY id DESC LIMIT 1000", params).fetchall()
    usuarios = [r[0] for r in con.execute(
        "SELECT DISTINCT usuario FROM auditoria WHERE usuario IS NOT NULL ORDER BY usuario")]
    return render_template("auditoria.html", registros=registros, usuarios=usuarios, f=a)


# ------------------------------------------------------------------ backup ---
def _pasta_backups() -> Path:
    return Path(current_app.config["PASTA_DADOS"]) / "backups"


def _arquivo_backup(nome) -> Path:
    pasta = _pasta_backups().resolve()
    arq = (pasta / nome).resolve()
    if arq.parent != pasta or not arq.name.startswith("controle_ti_") or arq.suffix != ".db" or not arq.exists():
        abort(404)
    return arq


def _mesma_instalacao(verificador) -> bool | None:
    if not verificador or not g.dek:
        return None
    try:
        return cripto.decifrar(g.dek, verificador, "verificador") == "controle-ti-ok"
    except cripto.ErroCripto:
        return False


@bp.route("/backup", methods=["GET", "POST"])
def backups():
    pasta = _pasta_backups()
    if request.method == "POST":
        arq = backup.fazer_backup(current_app.config["DB_PATH"], str(pasta),
                                  current_app.config["BACKUP_MANTER"])
        seg.auditar("backup_manual", arq.name)
        flash(f"Backup criado: {arq.name}", "ok")
        return redirect(url_for("admin.backups"))
    lista = []
    for a in sorted(pasta.glob("controle_ti_*.db"), reverse=True) if pasta.exists() else []:
        item = {"nome": a.name, "tamanho": a.stat().st_size,
                "data": datetime.fromtimestamp(a.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "tipo": "antes" if "antes_da_restauracao" in a.name else "enviado" if "enviado" in a.name else ""}
        try:
            info = backup.inspecionar(a)
            item.update(info, valido=True, mesma=_mesma_instalacao(info["verificador"]))
        except backup.ErroBackup as e:
            item.update(valido=False, erro=str(e))
        lista.append(item)
    return render_template("backup.html", lista=lista, pasta=str(pasta))


@bp.route("/backup/<nome>")
def backup_baixar(nome):
    arq = _arquivo_backup(nome)
    seg.auditar("backup_baixado", nome)
    return send_file(arq, as_attachment=True, download_name=nome)


def _executar_restauracao(arq: Path):
    """Restaura, registra na auditoria do banco restaurado e encerra todas as sessões."""
    try:
        info = backup.inspecionar(arq)
    except backup.ErroBackup as e:
        flash(str(e), "erro")
        return redirect(url_for("admin.backups"))
    if request.form.get("confirmacao", "").strip().upper() != "RESTAURAR":
        flash("Para confirmar, digite RESTAURAR no campo de confirmação.", "erro")
        return redirect(url_for("admin.backups"))
    quem = g.usuario.usuario
    mesma = _mesma_instalacao(info["verificador"])
    db.fechar_db()  # libera a conexão desta requisição
    try:
        antes, info = backup.restaurar(current_app.config["DB_PATH"], arq, str(_pasta_backups()))
    except (backup.ErroBackup, OSError, db.sqlite3.Error) as e:
        flash(f"A restauração não foi feita: {e}", "erro")
        return redirect(url_for("admin.backups"))
    db.inicializar(current_app.config["DB_PATH"])  # cria tabelas novas que o backup antigo não tinha
    seg.auditar("backup_restaurado",
                f"{arq.name} restaurado por {quem}. Estado anterior guardado em {antes.name}", usuario=quem)
    seg.encerrar_todas_sessoes()
    seg.encerrar_sessao()
    flash(f"Backup {arq.name} restaurado: {info['equipamentos']} equipamentos, {info['cofre']} senhas no cofre "
          f"e {info['usuarios']} usuários. Entre novamente com a senha que valia na data do backup. "
          f"O estado anterior foi guardado em {antes.name}.", "ok")
    if mesma is False:
        flash("Este backup é de outra instalação: use os usuários e o código de recuperação dela.", "aviso")
    return redirect(url_for("auth.login"))


@bp.route("/backup/<nome>/restaurar", methods=["POST"])
def backup_restaurar(nome):
    return _executar_restauracao(_arquivo_backup(nome))


@bp.route("/backup/enviar", methods=["POST"])
def backup_enviar():
    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        flash("Escolha o arquivo de backup (.db).", "erro")
        return redirect(url_for("admin.backups"))
    pasta = _pasta_backups()
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"controle_ti_{datetime.now():%Y-%m-%d_%H%M%S}_enviado.db"
    arquivo.save(destino)
    try:
        backup.inspecionar(destino)
    except backup.ErroBackup as e:
        destino.unlink(missing_ok=True)
        flash(f"{arquivo.filename}: {e}", "erro")
        return redirect(url_for("admin.backups"))
    seg.auditar("backup_enviado", f"{arquivo.filename} → {destino.name}")
    return _executar_restauracao(destino)
