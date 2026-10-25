from flask import (Blueprint, abort, flash, g, jsonify, redirect, render_template,
                   request, url_for)

from .. import cripto, db
from .. import seguranca as seg
from . import dias_desde, txt
from .estoque import unidades_do_usuario

bp = Blueprint("cofre", __name__)

CATEGORIAS = ["Sistema contábil/fiscal", "Portal do governo", "Prefeitura", "E-mail",
              "Banco", "Rede/Infraestrutura", "Servidor", "Fornecedor", "Certificado digital",
              "Outro"]


def obter_item(iid):
    row = db.get_db().execute(
        "SELECT c.*, un.nome unidade FROM cofre c LEFT JOIN unidades un "
        "ON un.id = c.unidade_id WHERE c.id = ?", (iid,)).fetchone()
    if not row or not g.usuario.acessa_unidade(row["unidade_id"]):
        abort(404)
    return row


@bp.route("/cofre")
@seg.requer_cofre
def lista():
    a = request.args
    filtro, params = g.usuario.filtro_unidade("c.unidade_id", incluir_geral=True)
    where = [filtro]
    if a.get("unidade") == "geral":
        where.append("c.unidade_id IS NULL")
    elif a.get("unidade"):
        where.append("c.unidade_id = ?")
        params.append(a.get("unidade"))
    if a.get("categoria"):
        where.append("c.categoria = ?")
        params.append(a.get("categoria"))
    if a.get("q"):
        termo = f"%{a.get('q').strip()}%"
        where.append("(c.sistema LIKE ? OR c.usuario LIKE ? OR c.url LIKE ?)")
        params += [termo] * 3
    itens = db.get_db().execute(
        "SELECT c.id, c.sistema, c.categoria, c.url, c.usuario, c.unidade_id, "
        "c.senha_alterada_em, c.atualizado_por, un.nome unidade FROM cofre c "
        "LEFT JOIN unidades un ON un.id = c.unidade_id WHERE " + " AND ".join(where) +
        " ORDER BY c.sistema COLLATE NOCASE", params).fetchall()
    itens = [dict(i, idade=dias_desde(i["senha_alterada_em"])) for i in itens]
    return render_template("cofre_lista.html", itens=itens, categorias=CATEGORIAS,
                           unidades=unidades_do_usuario(False), f=a)


@bp.route("/cofre/novo", methods=["GET", "POST"])
@bp.route("/cofre/<int:iid>/editar", methods=["GET", "POST"], endpoint="editar")
@seg.requer_cofre
def novo(iid=None):
    dek = seg.dek_atual()
    item = obter_item(iid) if iid else None
    erros = []
    if item:
        dados = dict(item)
        dados["notas"] = cripto.decifrar(dek, item["notas_enc"], "cofre-notas")
    else:
        dados = {"unidade_id": None}
    if request.method == "POST":
        f = request.form
        dados = {"sistema": txt(f, "sistema", 150), "categoria": txt(f, "categoria", 80),
                 "url": txt(f, "url", 300), "usuario": txt(f, "usuario", 150),
                 "notas": txt(f, "notas", 3000)}
        un = f.get("unidade_id") or ""
        dados["unidade_id"] = int(un) if un.isdigit() else None
        senha = f.get("senha", "")
        if not dados["sistema"]:
            erros.append("Informe o nome do sistema.")
        if dados["unidade_id"] is not None and not g.usuario.acessa_unidade(dados["unidade_id"]):
            erros.append("Unidade inválida.")
        if not item and not senha:
            erros.append("Informe a senha.")
        if dados["url"] and not dados["url"].lower().startswith(("http://", "https://")):
            dados["url"] = "https://" + dados["url"]
        if not erros:
            con = db.get_db()
            agora = db.agora()
            notas_enc = cripto.cifrar(dek, dados["notas"], "cofre-notas") if dados["notas"] else None
            if item:
                senha_enc = cripto.cifrar(dek, senha, "cofre") if senha else item["senha_enc"]
                alterada = agora if senha else item["senha_alterada_em"]
                con.execute("UPDATE cofre SET unidade_id = ?, categoria = ?, sistema = ?, url = ?, "
                            "usuario = ?, senha_enc = ?, notas_enc = ?, atualizado_em = ?, "
                            "atualizado_por = ?, senha_alterada_em = ? WHERE id = ?",
                            (dados["unidade_id"], dados["categoria"], dados["sistema"],
                             dados["url"], dados["usuario"], senha_enc, notas_enc, agora,
                             g.usuario.nome, alterada, iid))
                seg.auditar("cofre_senha_alterada" if senha else "cofre_editado",
                            f"#{iid} {dados['sistema']}")
            else:
                cur = con.execute(
                    "INSERT INTO cofre (unidade_id, categoria, sistema, url, usuario, senha_enc, "
                    "notas_enc, criado_em, atualizado_em, atualizado_por, senha_alterada_em) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (dados["unidade_id"], dados["categoria"], dados["sistema"], dados["url"],
                     dados["usuario"], cripto.cifrar(dek, senha, "cofre"), notas_enc,
                     agora, agora, g.usuario.nome, agora))
                iid = cur.lastrowid
                seg.auditar("cofre_criado", f"#{iid} {dados['sistema']}")
            con.commit()
            flash("Registro do cofre salvo.", "ok")
            return redirect(url_for("cofre.lista"))
    elif item:
        seg.auditar("cofre_aberto_edicao", f"#{iid} {item['sistema']}")
    return render_template("cofre_form.html", c=dados, item=item, erros=erros,
                           categorias=CATEGORIAS, unidades=unidades_do_usuario())


@bp.route("/cofre/<int:iid>/excluir", methods=["POST"])
@seg.requer_admin
def excluir(iid):
    item = obter_item(iid)
    con = db.get_db()
    con.execute("DELETE FROM cofre WHERE id = ?", (iid,))
    con.commit()
    seg.auditar("cofre_excluido", f"#{iid} {item['sistema']}")
    flash("Registro excluído do cofre.", "ok")
    return redirect(url_for("cofre.lista"))


@bp.route("/api/revelar/cofre/<int:iid>", methods=["POST"])
@seg.requer_cofre
def revelar(iid):
    item = obter_item(iid)
    senha = cripto.decifrar(seg.dek_atual(), item["senha_enc"], "cofre")
    acao = "cofre_senha_copiada" if request.args.get("acao") == "copiar" else "cofre_senha_visualizada"
    seg.auditar(acao, f"#{iid} {item['sistema']}")
    return jsonify({"senha": senha})
