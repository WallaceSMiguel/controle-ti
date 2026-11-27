"""Termos de responsabilidade: geração, consulta, impressão e devolução.

Integra com o estoque (itens vêm dos equipamentos cadastrados, com a configuração do
msinfo32) e com o cofre de senhas (acessos podem vir do cofre, com a senha).
"""
import base64
import json

from flask import (Blueprint, abort, flash, g, jsonify, redirect, render_template, request,
                   url_for)

from .. import cripto, db, hardware
from .. import seguranca as seg
from .. import termos as T
from . import data_form, txt
from .estoque import obter_equipamento, registrar_mov, unidades_do_usuario

bp = Blueprint("termos", __name__)

CAMPOS_TEXTO = {"nome": 150, "cpf": 20, "rg": 30, "endereco": 300, "email": 150, "cargo": 100,
                "setor": 100, "local": 100, "recNome": 150, "recCargo": 100, "obs": 2000}


def pode_ver_senhas() -> bool:
    u = g.usuario
    return bool(g.get("dek")) and (u.pode_cofre or u.pode_senhas_pc)


def obter_termo(tid):
    row = db.get_db().execute("SELECT * FROM termos WHERE id = ?", (tid,)).fetchone()
    if not row or not g.usuario.acessa_unidade(row["unidade_id"]):
        abort(404)
    t = dict(row)
    try:
        t["dados"] = json.loads(row["dados"] or "{}")
    except ValueError:
        t["dados"] = {}
    return t


def equipamentos_disponiveis():
    filtro, params = g.usuario.filtro_unidade("e.unidade_id")
    rows = db.get_db().execute(
        "SELECT e.*, un.nome unidade, h.processador, h.memoria_gb, h.armazenamento "
        "FROM equipamentos e JOIN unidades un ON un.id = e.unidade_id "
        "LEFT JOIN hardware h ON h.equipamento_id = e.id "
        f"WHERE {filtro} AND e.status != 'Baixado' ORDER BY un.nome, e.tipo, e.patrimonio",
        params).fetchall()
    out = []
    for e in rows:
        hw = {k: e[k] for k in ("processador", "memoria_gb", "armazenamento")}
        item, serie = T.descricao_equipamento(e, hw if any(hw.values()) else None)
        rotulo = " · ".join(x for x in (f"{e['tipo']} {e['marca'] or ''} {e['modelo'] or ''}".strip(),
                                        e["patrimonio"], e["hostname"], e["responsavel"]) if x)
        out.append({"id": e["id"], "unidade": e["unidade"], "rotulo": rotulo, "item": item,
                    "serie": serie, "unidade_id": e["unidade_id"], "setor": e["setor"] or ""})
    return out


def cofre_disponivel():
    if not g.usuario.pode_cofre:
        return []
    filtro, params = g.usuario.filtro_unidade("c.unidade_id", incluir_geral=True)
    return db.get_db().execute(
        "SELECT c.id, c.sistema, c.usuario, c.url, un.nome unidade FROM cofre c "
        f"LEFT JOIN unidades un ON un.id = c.unidade_id WHERE {filtro} "
        "ORDER BY c.sistema COLLATE NOCASE", params).fetchall()


def _txt(v, limite):
    return str(v if v is not None else "").strip()[:limite]


def ler_json(body: dict, original: dict | None):
    """Monta o termo a partir do JSON enviado pelo editor. Devolve (dados, unidade_id, erros)."""
    d = (body or {}).get("dados") or {}
    if not isinstance(d, dict):
        abort(400)
    orig = original or {}
    dados = {k: _txt(d.get(k), lim) for k, lim in CAMPOS_TEXTO.items()}
    dados["tipo"] = d.get("tipo") if d.get("tipo") in T.TIPOS else "equipamentos"
    dados["data"] = data_form(d.get("data")) or ""
    dados["empresaSnapshot"] = orig.get("empresaSnapshot") or T.snapshot_empresa()
    erros = []

    unidade_id, unidade_nome = None, ""
    try:
        unidade_id = int(d.get("unidade_id") or 0) or None
    except (TypeError, ValueError):
        unidade_id = None
    if unidade_id:
        r = db.get_db().execute("SELECT nome FROM unidades WHERE id = ?", (unidade_id,)).fetchone()
        if not r or not g.usuario.acessa_unidade(unidade_id):
            erros.append("Unidade inválida.")
            unidade_id = None
        else:
            unidade_nome = r["nome"]
    elif not g.usuario.todas_unidades:
        erros.append("Selecione a unidade.")
    dados["unidade"] = unidade_nome

    # ---- itens
    equip = {e["id"]: e for e in equipamentos_disponiveis()}
    itens = []
    for it_in in (d.get("itens") or []) if dados["tipo"] != "acessos" else []:
        if not isinstance(it_in, dict):
            continue
        it = {"item": _txt(it_in.get("item"), 200), "serie": _txt(it_in.get("serie"), 200),
              "qtd": _txt(it_in.get("qtd"), 5) or "1", "estado": _txt(it_in.get("estado"), 40) or "Novo",
              "obs": _txt(it_in.get("obs"), 300)}
        try:
            eid = int(it_in.get("equipamento_id") or 0)
        except (TypeError, ValueError):
            eid = 0
        if eid:
            antes = eid in T.ids_equipamentos(orig)
            if eid not in equip and not antes:
                erros.append("Equipamento inválido em um dos itens.")
                continue
            it["equipamento_id"] = eid
            if eid in equip:
                it["item"] = it["item"] or equip[eid]["item"]
                it["serie"] = it["serie"] or equip[eid]["serie"]
        if it["item"] or it["serie"] or it["obs"]:
            itens.append(it)
    dados["itens"] = itens

    # ---- acessos
    acessos_orig = orig.get("acessos") or []
    acessos, dek = [], None
    for a_in in (d.get("acessos") or []) if dados["tipo"] != "equipamentos" else []:
        if not isinstance(a_in, dict):
            continue
        a = {"sid": _txt(a_in.get("sid"), 20), "sistema": _txt(a_in.get("sistema"), 150),
             "usuario": _txt(a_in.get("usuario"), 150), "detalhe": _txt(a_in.get("detalhe"), 300)}
        if not a["sid"]:
            a.pop("sid")
        try:
            idx = int(a_in.get("orig")) if a_in.get("orig") is not None else -1
        except (TypeError, ValueError):
            idx = -1
        anterior = acessos_orig[idx] if 0 <= idx < len(acessos_orig) else {}
        try:
            cofre_id = int(a_in.get("cofre_id") or 0)
        except (TypeError, ValueError):
            cofre_id = 0
        item_cofre = None
        if cofre_id and not g.usuario.pode_cofre:
            # quem não acessa o cofre pode editar o termo, mas só mantém o vínculo que já existia
            if anterior.get("cofre_id") != cofre_id:
                abort(403)
            a["cofre_id"] = cofre_id
        elif cofre_id:
            item_cofre = db.get_db().execute("SELECT * FROM cofre WHERE id = ?", (cofre_id,)).fetchone()
            if not item_cofre or not g.usuario.acessa_unidade(item_cofre["unidade_id"]):
                erros.append("Registro do cofre inválido em um dos acessos.")
                continue
            a["cofre_id"] = cofre_id
            a["sistema"] = a["sistema"] or item_cofre["sistema"]
        if not (a["sistema"] or a["usuario"]):
            continue
        senha = str(a_in.get("senha") or "")[:200]
        if a_in.get("usar_cofre") and item_cofre:
            dek = dek or seg.dek_atual()
            a["senha_enc"] = T.cifrar_senha(dek, cripto.decifrar(dek, item_cofre["senha_enc"], "cofre"))
            seg.auditar("cofre_senha_no_termo", f"#{item_cofre['id']} {item_cofre['sistema']}")
        elif senha:
            dek = dek or seg.dek_atual()
            a["senha_enc"] = T.cifrar_senha(dek, senha)
        elif anterior.get("senha_enc") and not a_in.get("limpar"):
            a["senha_enc"] = anterior["senha_enc"]  # mantém a senha já gravada
        acessos.append(a)
    dados["acessos"] = acessos

    if not dados["nome"]:
        erros.append("Informe o nome do colaborador.")
    if dados["tipo"] != "acessos" and not dados["itens"]:
        erros.append("Adicione pelo menos um item.")
    if dados["tipo"] != "equipamentos" and not dados["acessos"]:
        erros.append("Adicione pelo menos um acesso.")
    return dados, unidade_id, erros


def _json(dados: dict) -> str:
    return json.dumps({k: v for k, v in dados.items() if k != "unidade_id"}, ensure_ascii=False)


def _entregar_equipamentos(con, ids, nome, setor, numero):
    for eid in ids:
        if setor:
            con.execute("UPDATE equipamentos SET responsavel = ?, setor = ?, atualizado_em = ? "
                        "WHERE id = ?", (nome, setor, db.agora(), eid))
        else:
            con.execute("UPDATE equipamentos SET responsavel = ?, atualizado_em = ? WHERE id = ?",
                        (nome, db.agora(), eid))
        con.execute("UPDATE equipamentos SET status = 'Em uso' WHERE id = ? AND status = 'Em estoque'",
                    (eid,))
        registrar_mov(con, eid, f"Entregue a {nome} pelo termo {numero}")


def _editor(t, dados):
    """Tela do editor (formulário + pré-visualização ao vivo, igual ao sistema de termos)."""
    acessos = []
    for i, a in enumerate(dados.get("acessos") or []):
        a = {k: v for k, v in a.items() if k not in ("senha", "senha_enc")}
        a["tem_senha"] = bool((dados.get("acessos") or [])[i].get("senha_enc"))
        a["orig"] = i
        acessos.append(a)
    equip = equipamentos_disponiveis()
    cofre = [{"id": c["id"], "sistema": c["sistema"], "usuario": c["usuario"] or "", "url": c["url"] or "",
              "unidade": c["unidade"] or ""} for c in cofre_disponivel()]
    emp = T.empresa()
    cfg = {
        "modo": "editar" if t else "novo",
        "numero": t["numero"] if t else None,
        "url_salvar": url_for("termos.editar", tid=t["id"]) if t else url_for("termos.novo"),
        "url_voltar": url_for("termos.detalhe", tid=t["id"]) if t else url_for("termos.lista"),
        "csrf": seg.csrf_token(),
        "empresa": emp,
        "logo_padrao": url_for("static", filename="logo-termo.jpg"),
        "usuario_nome": g.usuario.nome,
        "unidades": [{"id": u["id"], "nome": u["nome"]} for u in unidades_do_usuario()],
        "equipamentos": equip,
        "cofre": cofre,
        "dados": dict(dados, acessos=acessos),
        "dados_vindos": bool(t) or bool(dados.get("itens")),
    }
    return render_template("termo_editor.html", t=t, cfg=cfg)


def _resposta_erros(erros):
    return jsonify(erro=" ".join(erros)), 400


# ------------------------------------------------------------------- rotas ---
@bp.route("/termos")
def lista():
    a = request.args
    filtro, params = g.usuario.filtro_unidade("t.unidade_id", incluir_geral=True)
    where = [filtro]
    if a.get("status") in T.STATUS:
        where.append("t.status = ?")
        params.append(a["status"])
    if a.get("tipo") in T.TIPOS:
        where.append("t.tipo = ?")
        params.append(a["tipo"])
    if a.get("unidade", "").isdigit():
        where.append("t.unidade_id = ?")
        params.append(int(a["unidade"]))
    if a.get("q"):
        termo = f"%{a['q'].strip()}%"
        where.append("(t.colaborador LIKE ? OR t.cpf LIKE ? OR t.numero LIKE ? OR t.dados LIKE ?)")
        params += [termo] * 4
    con = db.get_db()
    itens = con.execute("SELECT t.* FROM termos t WHERE " + " AND ".join(where) +
                        " ORDER BY t.criado_em DESC, t.id DESC LIMIT 500", params).fetchall()
    filtro_c, params_c = g.usuario.filtro_unidade("unidade_id", incluir_geral=True)
    contagem = {r["status"]: r["n"] for r in con.execute(
        f"SELECT status, COUNT(*) n FROM termos WHERE {filtro_c} GROUP BY status", params_c)}
    return render_template("termos_lista.html", itens=itens, f=a, status=T.STATUS, tipos=T.TIPOS,
                           unidades=unidades_do_usuario(False), contagem=contagem)


@bp.route("/termos/novo", methods=["GET", "POST"])
@seg.requer_editor
def novo():
    if request.method == "POST":
        dados, unidade_id, erros = ler_json(request.get_json(silent=True), None)
        if erros:
            return _resposta_erros(erros)
        con = db.get_db()
        numero = T.proximo_numero(con)
        agora = db.agora()
        cur = con.execute(
            "INSERT INTO termos (numero, tipo, status, colaborador, cpf, unidade_id, unidade_nome, "
            "dados, criado_por, criado_em, atualizado_por, atualizado_em) "
            "VALUES (?, ?, 'ativo', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (numero, dados["tipo"], dados["nome"], dados["cpf"], unidade_id, dados["unidade"],
             _json(dados), g.usuario.nome, agora, g.usuario.nome, agora))
        tid = cur.lastrowid
        T.gravar_vinculos(con, tid, dados)
        _entregar_equipamentos(con, T.ids_equipamentos(dados), dados["nome"], dados["setor"], numero)
        T.historico(con, tid, g.usuario.nome, "criado", numero)
        con.commit()
        seg.auditar("termo_criado", f"{numero} {dados['nome']}")
        flash(f"Termo {numero} salvo.", "ok")
        return jsonify(id=tid, numero=numero, url=url_for("termos.detalhe", tid=tid))

    emp = T.empresa()
    dados = {"tipo": "equipamentos", "local": emp["local"], "data": db.agora()[:10],
             "recNome": g.usuario.nome, "itens": [], "acessos": []}
    eid = request.args.get("equipamento", "")
    if eid.isdigit():
        e = obter_equipamento(int(eid))
        item, serie = T.descricao_equipamento(e, hardware.carregar(e["id"]))
        dados["itens"].append({"equipamento_id": e["id"], "item": item, "serie": serie, "qtd": "1",
                               "estado": "Bom", "obs": ""})
        dados["nome"] = e["responsavel"] or ""
        dados["setor"] = e["setor"] or ""
        dados["unidade_id"] = e["unidade_id"]
        dados["unidade"] = e["unidade"]
    return _editor(None, dados)


@bp.route("/termos/<int:tid>/editar", methods=["GET", "POST"])
@seg.requer_editor
def editar(tid):
    t = obter_termo(tid)
    if request.method == "POST":
        dados, unidade_id, erros = ler_json(request.get_json(silent=True), t["dados"])
        if erros:
            return _resposta_erros(erros)
        con = db.get_db()
        antes = set(T.ids_equipamentos(t["dados"]))
        con.execute("UPDATE termos SET tipo = ?, colaborador = ?, cpf = ?, unidade_id = ?, "
                    "unidade_nome = ?, dados = ?, atualizado_por = ?, atualizado_em = ? WHERE id = ?",
                    (dados["tipo"], dados["nome"], dados["cpf"], unidade_id, dados["unidade"],
                     _json(dados), g.usuario.nome, db.agora(), tid))
        T.gravar_vinculos(con, tid, dados)
        if t["status"] == "ativo":
            depois = T.ids_equipamentos(dados)
            _entregar_equipamentos(con, [i for i in depois if i not in antes], dados["nome"],
                                   dados["setor"], t["numero"])
            for eid in antes - set(depois):
                registrar_mov(con, eid, f"Retirado do termo {t['numero']}")
        T.historico(con, tid, g.usuario.nome, "editado")
        con.commit()
        flash("Alterações salvas.", "ok")
        return jsonify(id=tid, numero=t["numero"], url=url_for("termos.detalhe", tid=tid))
    dados = dict(t["dados"], unidade_id=t["unidade_id"])
    return _editor(t, dados)


@bp.route("/termos/<int:tid>")
def detalhe(tid):
    t = obter_termo(tid)
    con = db.get_db()
    hist = con.execute("SELECT * FROM termo_historico WHERE termo_id = ? ORDER BY data DESC, id DESC",
                       (tid,)).fetchall()
    filtro, params = g.usuario.filtro_unidade("e.unidade_id")
    equips = con.execute(
        "SELECT e.id, e.tipo, e.marca, e.modelo, e.patrimonio, e.hostname, e.status, e.responsavel "
        "FROM termo_equipamentos te JOIN equipamentos e ON e.id = te.equipamento_id "
        f"WHERE te.termo_id = ? AND {filtro}", [tid] + params).fetchall()
    doc = T.para_documento(t["dados"])
    return render_template("termo_detalhe.html", t=t, doc=doc, hist=hist, equips=equips,
                           status=T.STATUS, tipos=T.TIPOS, empresa=T.empresa(),
                           tem_senhas=T.tem_senhas(t["dados"]), pode_senhas=pode_ver_senhas())


@bp.route("/termos/<int:tid>/imprimir")
def imprimir(tid):
    t = obter_termo(tid)
    com_senhas = request.args.get("senhas") == "1" and T.tem_senhas(t["dados"])
    if com_senhas:
        if not pode_ver_senhas():
            abort(403, "Seu usuário não tem acesso às senhas.")
        seg.auditar("termo_impresso_com_senhas", t["numero"])
        con = db.get_db()
        T.historico(con, tid, g.usuario.nome, "impresso com senhas")
        con.commit()
    doc = T.para_documento(t["dados"], g.dek if com_senhas else None)
    return render_template("termo_imprimir.html", t=t, doc=doc, empresa=T.empresa(),
                           com_senhas=com_senhas)


@bp.route("/termos/<int:tid>/status", methods=["POST"])
@seg.requer_editor
def mudar_status(tid):
    t = obter_termo(tid)
    novo_st = request.form.get("status")
    if novo_st not in T.STATUS or novo_st == t["status"]:
        return redirect(url_for("termos.detalhe", tid=tid))
    obs = txt(request.form, "observacao", 500)
    con = db.get_db()
    agora = db.agora()
    con.execute("UPDATE termos SET status = ?, devolvido_em = ?, atualizado_por = ?, atualizado_em = ? "
                "WHERE id = ?", (novo_st, agora if novo_st == "devolvido" else None,
                                 g.usuario.nome, agora, tid))
    nome = t["colaborador"]
    for eid in T.ids_equipamentos(t["dados"]):
        e = con.execute("SELECT responsavel FROM equipamentos WHERE id = ?", (eid,)).fetchone()
        if not e:
            continue
        if novo_st == "devolvido":
            if (e["responsavel"] or "").strip().lower() == nome.strip().lower():
                con.execute("UPDATE equipamentos SET responsavel = '', status = 'Em estoque', "
                            "atualizado_em = ? WHERE id = ?", (agora, eid))
            registrar_mov(con, eid, f"Devolvido por {nome} (termo {t['numero']})" +
                          (f": {obs}" if obs else ""))
        elif novo_st == "cancelado":
            registrar_mov(con, eid, f"Termo {t['numero']} cancelado")
        else:
            _entregar_equipamentos(con, [eid], nome, t["dados"].get("setor"), t["numero"])
    T.historico(con, tid, g.usuario.nome, f"status: {novo_st}", obs)
    con.commit()
    seg.auditar("termo_status", f"{t['numero']} {novo_st}")
    flash(f"Termo marcado como {T.STATUS[novo_st].lower()}.", "ok")
    return redirect(url_for("termos.detalhe", tid=tid))


@bp.route("/termos/<int:tid>/excluir", methods=["POST"])
@seg.requer_admin
def excluir(tid):
    t = obter_termo(tid)
    con = db.get_db()
    con.execute("DELETE FROM termos WHERE id = ?", (tid,))
    con.commit()
    seg.auditar("termo_excluido", f"{t['numero']} {t['colaborador']}")
    flash(f"Termo {t['numero']} excluído.", "ok")
    return redirect(url_for("termos.lista"))


@bp.route("/termos/empresa", methods=["GET", "POST"])
@seg.requer_admin
def empresa():
    emp = T.empresa()
    erros = []
    if request.method == "POST":
        f = request.form
        novo_emp = {k: txt(f, k, 400) for k in ("empresa", "cnpj", "empEndereco", "empContato",
                                                 "local", "dominioEmail")}
        arq = request.files.get("logo")
        if f.get("remover_logo"):
            novo_emp["logo"] = None
        elif arq and arq.filename:
            conteudo = arq.read(600 * 1024 + 1)
            tipo = "image/png" if conteudo.startswith(b"\x89PNG") else \
                "image/jpeg" if conteudo.startswith(b"\xff\xd8") else None
            if not tipo:
                erros.append("O logo precisa ser uma imagem PNG ou JPG.")
            elif len(conteudo) > 600 * 1024:
                erros.append("O logo deve ter no máximo 600 KB.")
            else:
                novo_emp["logo"] = f"data:{tipo};base64," + base64.b64encode(conteudo).decode()
        if not novo_emp["empresa"]:
            erros.append("Informe o nome da empresa.")
        if not erros:
            T.salvar_empresa(novo_emp)
            db.get_db().commit()
            seg.auditar("termos_empresa_alterada")
            flash("Dados da empresa salvos. Termos já emitidos mantêm os dados da época.", "ok")
            return redirect(url_for("termos.empresa"))
        emp.update(novo_emp)
    return render_template("termos_empresa.html", emp=emp, erros=erros)


# ------------------------------------------------------------ filtros Jinja ---
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]


@bp.app_template_filter("data_extenso")
def data_extenso(valor):
    try:
        a, m, d = (int(x) for x in (valor or "")[:10].split("-"))
        return f"{d} de {MESES[m - 1]} de {a}"
    except (ValueError, IndexError):
        return ""


@bp.app_template_filter("pill_estado")
def pill_estado(estado):
    e = (estado or "").lower()
    if e.startswith("novo"):
        return "novo"
    if e.startswith(("bom", "usado")):
        return "bom"
    if e.startswith("regular"):
        return "regular"
    if e.startswith("danif"):
        return "danificado"
    return ""
