from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .. import cripto, db
from .. import seguranca as seg
from . import txt

bp = Blueprint("auth", __name__)

UNIDADES_PADRAO = ["Del Castilho (Matriz)", "Caxias", "Barra"]
SENHA_MIN = 8


def validar_nova_senha(senha, confirmacao):
    if len(senha) < SENHA_MIN:
        return f"A senha precisa ter pelo menos {SENHA_MIN} caracteres."
    if senha != confirmacao:
        return "A confirmação não confere com a senha."
    return None


@bp.route("/instalacao", methods=["GET", "POST"])
def setup():
    if db.existe_usuario():
        return redirect(url_for("auth.login"))
    erro = None
    if request.method == "POST":
        nome = txt(request.form, "nome", 100)
        usuario = txt(request.form, "usuario", 50)
        senha = request.form.get("senha", "")
        erro = validar_nova_senha(senha, request.form.get("confirmacao", ""))
        if not nome or not usuario:
            erro = "Preencha nome e usuário."
        if not erro:
            con = db.get_db()
            dek = cripto.nova_dek()
            salt, envolvida = cripto.envolver_dek(dek, senha)
            codigo = cripto.gerar_codigo_recuperacao()
            r_salt, r_env = cripto.envolver_dek(dek, codigo)
            db.config_set("recuperacao_salt", r_salt)
            db.config_set("recuperacao_dek", r_env)
            db.config_set("verificador", cripto.cifrar(dek, "controle-ti-ok", "verificador"))
            for nome_un in UNIDADES_PADRAO:
                con.execute("INSERT OR IGNORE INTO unidades (nome) VALUES (?)", (nome_un,))
            con.execute(
                "INSERT INTO usuarios (usuario, nome, senha_hash, perfil, acesso_cofre, "
                "todas_unidades, kek_salt, dek_envolvida, criado_em) "
                "VALUES (?, ?, ?, 'admin', 1, 1, ?, ?, ?)",
                (usuario, nome, generate_password_hash(senha), salt, envolvida, db.agora()),
            )
            con.commit()
            seg.auditar("instalacao", f"Administrador inicial: {usuario}", usuario=usuario)
            return render_template("recuperacao.html", codigo=codigo)
    return render_template("setup.html", erro=erro)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if not db.existe_usuario():
        return redirect(url_for("auth.setup"))
    erro = None
    usuario_txt = ""
    if request.method == "POST":
        usuario_txt = txt(request.form, "usuario", 50)
        senha = request.form.get("senha", "")
        espera = seg.login_bloqueado(usuario_txt)
        if espera:
            erro = f"Muitas tentativas. Aguarde {espera // 60 + 1} minuto(s)."
        else:
            con = db.get_db()
            row = con.execute("SELECT * FROM usuarios WHERE usuario = ? AND ativo = 1",
                              (usuario_txt,)).fetchone()
            if row and check_password_hash(row["senha_hash"], senha):
                dek = None
                if row["dek_envolvida"]:
                    try:
                        dek = cripto.abrir_dek(row["kek_salt"], row["dek_envolvida"], senha)
                    except cripto.ErroCripto:
                        dek = None
                seg.limpar_falhas(usuario_txt)
                seg.criar_sessao(row["id"], dek)
                con.execute("UPDATE usuarios SET ultimo_login = ? WHERE id = ?",
                            (db.agora(), row["id"]))
                con.commit()
                seg.auditar("login", "", usuario=row["usuario"])
                destino = request.args.get("proximo", "")
                if not destino.startswith("/") or destino.startswith("//"):
                    destino = url_for("painel.inicio")
                return redirect(destino)
            seg.registrar_falha(usuario_txt)
            seg.auditar("login_falhou", f"Usuário informado: {usuario_txt}", usuario=None)
            erro = "Usuário ou senha inválidos."
    return render_template("login.html", erro=erro, usuario_txt=usuario_txt,
                           expirou="proximo" in request.args)


@bp.route("/logout")
def logout():
    if g.get("usuario"):
        seg.auditar("logout")
    seg.encerrar_sessao()
    return redirect(url_for("auth.login"))


@bp.route("/conta/senha", methods=["GET", "POST"])
def trocar_senha():
    erro = None
    if request.method == "POST":
        con = db.get_db()
        row = con.execute("SELECT * FROM usuarios WHERE id = ?", (g.usuario.id,)).fetchone()
        atual = request.form.get("atual", "")
        nova = request.form.get("nova", "")
        erro = validar_nova_senha(nova, request.form.get("confirmacao", ""))
        if not check_password_hash(row["senha_hash"], atual):
            erro = "Senha atual incorreta."
        elif not erro and nova == atual:
            erro = "A nova senha precisa ser diferente da atual."
        if not erro:
            salt, envolvida = row["kek_salt"], row["dek_envolvida"]
            if g.dek:
                salt, envolvida = cripto.envolver_dek(g.dek, nova)
            con.execute(
                "UPDATE usuarios SET senha_hash = ?, kek_salt = ?, dek_envolvida = ?, "
                "trocar_senha = 0 WHERE id = ?",
                (generate_password_hash(nova), salt, envolvida, g.usuario.id))
            con.commit()
            seg.auditar("senha_alterada", "Alterou a própria senha")
            flash("Senha alterada com sucesso.", "ok")
            return redirect(url_for("painel.inicio"))
    return render_template("trocar_senha.html", erro=erro)
