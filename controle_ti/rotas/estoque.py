import csv
import io
import json

from flask import (Blueprint, Response, abort, flash, g, jsonify, redirect,
                   render_template, request, url_for)

from .. import cripto, db, hardware, msinfo
from .. import seguranca as seg
from . import data_form, txt

bp = Blueprint("estoque", __name__)

TIPOS = ["Desktop", "Notebook", "Monitor", "Impressora", "Nobreak", "Servidor",
         "Switch/Roteador", "Telefone/Celular", "Periférico", "Outro"]
STATUS = ["Em uso", "Em estoque", "Em manutenção", "Emprestado", "Baixado"]
TIPOS_CREDENCIAL = ["Usuário local", "Administrador local", "Usuário de domínio",
                    "BIOS/UEFI", "PIN/Windows Hello", "BitLocker", "Outro"]

CAMPOS = ["unidade_id", "tipo", "marca", "modelo", "numero_serie", "patrimonio", "hostname",
          "responsavel", "setor", "status", "especificacoes", "data_compra", "garantia_ate",
          "fornecedor", "nota_fiscal", "observacoes"]
ROTULOS = {"unidade_id": "Unidade", "status": "Status", "responsavel": "Responsável",
           "setor": "Setor", "hostname": "Hostname", "patrimonio": "Patrimônio"}


def unidades_do_usuario(somente_ativas=True):
    filtro, params = g.usuario.filtro_unidade("id")
    extra = "AND ativa = 1" if somente_ativas else ""
    return db.get_db().execute(
        f"SELECT id, nome FROM unidades WHERE {filtro} {extra} ORDER BY nome", params).fetchall()


def obter_equipamento(eid):
    row = db.get_db().execute(
        "SELECT e.*, un.nome unidade FROM equipamentos e "
        "JOIN unidades un ON un.id = e.unidade_id WHERE e.id = ?", (eid,)).fetchone()
    if not row or not g.usuario.acessa_unidade(row["unidade_id"]):
        abort(404)
    return row


def registrar_mov(con, eid, descricao):
    con.execute("INSERT INTO movimentacoes (equipamento_id, data, usuario, descricao) "
                "VALUES (?, ?, ?, ?)", (eid, db.agora(), g.usuario.nome, descricao))


def ler_form():
    f = request.form
    dados = {c: txt(f, c, 2000 if c in ("observacoes", "especificacoes") else 200)
             for c in CAMPOS}
    dados["data_compra"] = data_form(f.get("data_compra"))
    dados["garantia_ate"] = data_form(f.get("garantia_ate"))
    erros = []
    try:
        dados["unidade_id"] = int(dados["unidade_id"])
    except ValueError:
        dados["unidade_id"] = None
    if not dados["unidade_id"] or not g.usuario.acessa_unidade(dados["unidade_id"]):
        erros.append("Selecione uma unidade válida.")
    if dados["tipo"] not in TIPOS:
        erros.append("Selecione o tipo do equipamento.")
    if dados["status"] not in STATUS:
        erros.append("Selecione o status.")
    if dados["numero_serie"]:
        dup = db.get_db().execute(
            "SELECT id FROM equipamentos WHERE numero_serie = ? AND id != ?",
            (dados["numero_serie"], request.view_args.get("eid", 0))).fetchone()
        if dup:
            erros.append("Já existe um equipamento com esse número de série.")
    if dados["patrimonio"]:
        dup = db.get_db().execute(
            "SELECT id FROM equipamentos WHERE patrimonio = ? AND id != ?",
            (dados["patrimonio"], request.view_args.get("eid", 0))).fetchone()
        if dup:
            erros.append("Já existe um equipamento com esse patrimônio.")
    return dados, erros


ALERTAS = {
    "win10": ("Windows 10 ou anterior (sem suporte)",
              "(h.sistema_operacional LIKE 'Windows 10%' OR h.sistema_operacional LIKE 'Windows 8%' "
              "OR h.sistema_operacional LIKE 'Windows 7%')"),
    "memoria": ("Até 4 GB de memória", "h.memoria_gb <= 4"),
    "disco": ("Disco com 90% ou mais ocupado",
              "EXISTS (SELECT 1 FROM json_each(h.unidades) WHERE json_extract(value, '$.uso') >= 90)"),
    "sem_hw": ("Computadores sem configuração", "h.equipamento_id IS NULL AND e.tipo IN ('Desktop','Notebook','Servidor')"),
}


def consulta_lista():
    a = request.args
    filtro, params = g.usuario.filtro_unidade("e.unidade_id")
    where = [filtro]
    if a.get("unidade"):
        where.append("e.unidade_id = ?")
        params.append(a.get("unidade"))
    if a.get("tipo"):
        where.append("e.tipo = ?")
        params.append(a.get("tipo"))
    if a.get("status"):
        where.append("e.status = ?")
        params.append(a.get("status"))
    elif not a.get("baixados"):
        where.append("e.status != 'Baixado'")
    if a.get("alerta") in ALERTAS:
        where.append(ALERTAS[a.get("alerta")][1])
    if a.get("q"):
        termo = f"%{a.get('q').strip()}%"
        where.append("(e.marca LIKE ? OR e.modelo LIKE ? OR e.numero_serie LIKE ? OR "
                     "e.patrimonio LIKE ? OR e.hostname LIKE ? OR e.responsavel LIKE ? OR "
                     "e.setor LIKE ? OR e.especificacoes LIKE ? OR h.processador LIKE ? OR "
                     "h.sistema_operacional LIKE ? OR h.rede LIKE ?)")
        params += [termo] * 11
    sql = ("SELECT e.*, un.nome unidade, h.processador, h.memoria_gb, h.armazenamento, "
           "h.sistema_operacional, h.unidades hw_unidades FROM equipamentos e "
           "JOIN unidades un ON un.id = e.unidade_id "
           "LEFT JOIN hardware h ON h.equipamento_id = e.id WHERE " + " AND ".join(where) +
           " ORDER BY un.nome, e.tipo, e.patrimonio")
    return db.get_db().execute(sql, params).fetchall()


@bp.route("/estoque")
def lista():
    itens = consulta_lista()
    return render_template("estoque_lista.html", itens=itens, tipos=TIPOS, status=STATUS,
                           unidades=unidades_do_usuario(False), f=request.args, alertas=ALERTAS)


@bp.route("/estoque/exportar")
def exportar():
    itens = consulta_lista()
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    cab = ["Unidade", "Tipo", "Marca", "Modelo", "Nº série", "Patrimônio", "Hostname",
           "Responsável", "Setor", "Status", "Processador", "Memória (GB)", "Armazenamento",
           "Sistema operacional", "Outras especificações", "Data compra",
           "Garantia até", "Fornecedor", "Nota fiscal", "Observações"]
    w.writerow(cab)
    for e in itens:
        mem = str(e["memoria_gb"]).replace(".", ",").removesuffix(",0") if e["memoria_gb"] else ""
        w.writerow([e["unidade"], e["tipo"], e["marca"], e["modelo"], e["numero_serie"],
                    e["patrimonio"], e["hostname"], e["responsavel"], e["setor"], e["status"],
                    e["processador"], mem, e["armazenamento"], e["sistema_operacional"],
                    e["especificacoes"], e["data_compra"], e["garantia_ate"], e["fornecedor"],
                    e["nota_fiscal"], e["observacoes"]])
    seg.auditar("estoque_exportado", f"{len(itens)} equipamentos")
    return Response("﻿" + buf.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=estoque_ti.csv"})


# ------------------------------------------------- msinfo32 / hardware ---
LIMITE_ARQUIVO = 25 * 1024 * 1024


def ler_arquivo_msinfo(arquivo):
    """Lê um arquivo enviado. Retorna (hw, erro)."""
    if not arquivo or not arquivo.filename:
        return None, "Escolha o arquivo gerado pelo msinfo32 (.nfo ou .txt)."
    nome = arquivo.filename.lower()
    if not nome.endswith((".nfo", ".txt")):
        return None, f"{arquivo.filename}: use um arquivo .nfo (Salvar) ou .txt (Exportar) do msinfo32."
    dados = arquivo.read(LIMITE_ARQUIVO + 1)
    if len(dados) > LIMITE_ARQUIVO:
        return None, f"{arquivo.filename}: arquivo maior que 25 MB."
    try:
        hw = msinfo.ler_msinfo(dados)
    except msinfo.ErroMsinfo as e:
        return None, f"{arquivo.filename}: {e}"
    hw["origem"] = f"msinfo32 ({arquivo.filename[-80:]})"
    return hw, None


def hw_do_form(base):
    """Junta os detalhes (JSON oculto ou já gravados) com os campos editados na tela."""
    try:
        hw = json.loads(request.form.get("hw_json") or "null") or base or {}
    except ValueError:
        hw = base or {}
    hw = hardware.limpar(hw)
    f = request.form
    hw["processador"] = txt(f, "hw_processador", 200) or None
    hw["sistema_operacional"] = txt(f, "hw_sistema_operacional", 120) or None
    armaz = txt(f, "hw_armazenamento", 120)
    hw["armazenamento"] = armaz or None
    try:
        mem = float(txt(f, "hw_memoria_gb", 10).replace(",", "."))
        hw["memoria_gb"] = mem if 0 < mem < 100000 else None
    except ValueError:
        hw["memoria_gb"] = None
    if hw["processador"] is None:
        hw["nucleos"] = hw["threads"] = hw["frequencia"] = None
    return hw


def aplicar_identificacao(dados, hw, so_vazios=True):
    """Usa hostname, marca, modelo e tipo vindos do msinfo32."""
    for campo in ("hostname", "marca", "modelo"):
        if hw.get(campo) and (not so_vazios or not dados.get(campo)):
            dados[campo] = hw[campo][:200]
    if hw.get("tipo") in TIPOS and not dados.get("tipo"):
        dados["tipo"] = hw["tipo"]


def equipamento_por_hostname(hostname, ignorar_id=0):
    if not hostname:
        return None
    filtro, params = g.usuario.filtro_unidade("e.unidade_id")
    return db.get_db().execute(
        f"SELECT e.id, e.tipo, e.modelo, e.hostname, un.nome unidade FROM equipamentos e "
        f"JOIN unidades un ON un.id = e.unidade_id WHERE e.hostname = ? COLLATE NOCASE "
        f"AND e.id != ? AND {filtro} LIMIT 1", [hostname, ignorar_id] + params).fetchone()


def tela_form(dados, hw, erros, novo, avisos=()):
    return render_template("estoque_form.html", e=dados, hw=hw or {}, erros=erros, tipos=TIPOS,
                           status=STATUS, unidades=unidades_do_usuario(), novo=novo, avisos=avisos,
                           hw_json=json.dumps(hw or {}, ensure_ascii=False))


@bp.route("/estoque/novo", methods=["GET", "POST"])
@seg.requer_editor
def novo():
    dados, erros, hw, avisos = {"status": "Em uso"}, [], {}, []
    if request.method == "POST":
        dados, erros = ler_form()
        hw = hw_do_form({})
        if request.form.get("acao") == "importar":
            novo_hw, erro = ler_arquivo_msinfo(request.files.get("msinfo"))
            if erro:
                return tela_form(dados, hw, [erro], True)
            hw = hardware.limpar(novo_hw)
            aplicar_identificacao(dados, novo_hw)
            avisos.append(f"Dados lidos de {request.files['msinfo'].filename}. Confira, complete unidade, "
                          "patrimônio e responsável, e salve.")
            existente = equipamento_por_hostname(novo_hw.get("hostname"))
            if existente:
                avisos.append(("existe", existente))
            return tela_form(dados, hw, [], True, avisos)
        if not erros:
            con = db.get_db()
            agora = db.agora()
            cur = con.execute(
                f"INSERT INTO equipamentos ({', '.join(CAMPOS)}, criado_em, atualizado_em) "
                f"VALUES ({', '.join('?' * len(CAMPOS))}, ?, ?)",
                [dados[c] for c in CAMPOS] + [agora, agora])
            eid = cur.lastrowid
            hardware.salvar(con, eid, hw, g.usuario.nome)
            registrar_mov(con, eid, f"Cadastrado com status “{dados['status']}”"
                          + (f" — {msinfo.resumo_curto(hw)}" if hardware.tem_dados(hw) else ""))
            con.commit()
            seg.auditar("equipamento_criado", f"#{eid} {dados['tipo']} {dados['modelo']}")
            flash("Equipamento cadastrado.", "ok")
            return redirect(url_for("estoque.detalhe", eid=eid))
    return tela_form(dados, hw, erros, True, avisos)


@bp.route("/estoque/<int:eid>")
def detalhe(eid):
    e = obter_equipamento(eid)
    con = db.get_db()
    movs = con.execute("SELECT * FROM movimentacoes WHERE equipamento_id = ? "
                       "ORDER BY data DESC, id DESC", (eid,)).fetchall()
    creds = []
    if g.usuario.pode_senhas_pc:
        creds = con.execute("SELECT id, tipo, usuario, observacoes, atualizado_em, "
                            "atualizado_por FROM credenciais_pc WHERE equipamento_id = ? "
                            "ORDER BY tipo", (eid,)).fetchall()
    return render_template("estoque_detalhe.html", e=e, movs=movs, creds=creds,
                           hw=hardware.carregar(eid))


@bp.route("/estoque/<int:eid>/editar", methods=["GET", "POST"])
@seg.requer_editor
def editar(eid):
    atual = obter_equipamento(eid)
    hw_atual = hardware.carregar(eid)
    dados, erros, hw, avisos = dict(atual), [], hw_atual or {}, []
    if request.method == "POST":
        dados, erros = ler_form()
        dados["id"] = eid
        hw = hw_do_form(hw_atual)
        if request.form.get("acao") == "importar":
            novo_hw, erro = ler_arquivo_msinfo(request.files.get("msinfo"))
            if erro:
                return tela_form(dados, hw, [erro], False)
            hw = hardware.limpar(novo_hw)
            aplicar_identificacao(dados, novo_hw)
            avisos.append(f"Configuração lida de {request.files['msinfo'].filename}. Confira e salve.")
            if novo_hw.get("hostname") and dados.get("hostname") and \
                    novo_hw["hostname"].lower() != dados["hostname"].lower():
                avisos.append(f"Atenção: o arquivo é do computador {novo_hw['hostname']}, "
                              f"mas este cadastro é {dados['hostname']}.")
            return tela_form(dados, hw, [], False, avisos)
        if not erros:
            con = db.get_db()
            nomes = {r["id"]: r["nome"] for r in con.execute("SELECT id, nome FROM unidades")}
            mudancas = []
            for campo, rotulo in ROTULOS.items():
                antes, depois = atual[campo], dados[campo]
                if (antes or "") != (depois or ""):
                    if campo == "unidade_id":
                        antes, depois = nomes.get(antes), nomes.get(depois)
                    mudancas.append(f"{rotulo}: “{antes or '—'}” → “{depois or '—'}”")
            con.execute(
                f"UPDATE equipamentos SET {', '.join(c + ' = ?' for c in CAMPOS)}, "
                "atualizado_em = ? WHERE id = ?",
                [dados[c] for c in CAMPOS] + [db.agora(), eid])
            mudancas += hardware.salvar(con, eid, hw, g.usuario.nome)
            if mudancas:
                registrar_mov(con, eid, "; ".join(mudancas))
            con.commit()
            seg.auditar("equipamento_editado", f"#{eid} " + "; ".join(mudancas))
            flash("Alterações salvas.", "ok")
            return redirect(url_for("estoque.detalhe", eid=eid))
    return tela_form(dados, hw, erros, False, avisos)


@bp.route("/estoque/<int:eid>/msinfo", methods=["POST"])
@seg.requer_editor
def atualizar_msinfo(eid):
    """Atualiza só a configuração, direto da ficha do equipamento."""
    e = obter_equipamento(eid)
    hw, erro = ler_arquivo_msinfo(request.files.get("msinfo"))
    if erro:
        flash(erro, "erro")
        return redirect(url_for("estoque.detalhe", eid=eid))
    con = db.get_db()
    mud = hardware.salvar(con, eid, hw, g.usuario.nome)
    dados = dict(e)
    aplicar_identificacao(dados, hw)
    con.execute("UPDATE equipamentos SET hostname = ?, marca = ?, modelo = ?, atualizado_em = ? WHERE id = ?",
                (dados["hostname"], dados["marca"], dados["modelo"], db.agora(), eid))
    registrar_mov(con, eid, "Configuração atualizada pelo msinfo32" + (": " + "; ".join(mud) if mud else ""))
    con.commit()
    seg.auditar("hardware_importado", f"#{eid} {hw.get('hostname') or ''} — {hw['origem']}")
    if e["hostname"] and hw.get("hostname") and e["hostname"].lower() != hw["hostname"].lower():
        flash(f"Configuração atualizada, mas o arquivo é do computador {hw['hostname']} "
              f"e este cadastro é {e['hostname']}. Confira.", "aviso")
    else:
        flash("Configuração atualizada pelo msinfo32.", "ok")
    return redirect(url_for("estoque.detalhe", eid=eid))


@bp.route("/estoque/importar", methods=["GET", "POST"])
@seg.requer_editor
def importar_lote():
    """Vários arquivos de uma vez: atualiza quem já existe (pelo hostname) e cadastra o resto."""
    resultados = []
    escolha = {"unidade_id": "", "status": "Em uso"}
    if request.method == "POST":
        escolha = {"unidade_id": request.form.get("unidade_id", ""), "status": request.form.get("status", "Em uso")}
        try:
            unidade_id = int(escolha["unidade_id"])
        except ValueError:
            unidade_id = None
        arquivos = [a for a in request.files.getlist("arquivos") if a and a.filename]
        if not unidade_id or not g.usuario.acessa_unidade(unidade_id):
            flash("Selecione a unidade dos computadores novos.", "erro")
        elif escolha["status"] not in STATUS:
            flash("Status inválido.", "erro")
        elif not arquivos:
            flash("Selecione um ou mais arquivos do msinfo32.", "erro")
        elif len(arquivos) > 100:
            flash("Envie no máximo 100 arquivos por vez.", "erro")
        else:
            con = db.get_db()
            for arq in arquivos:
                hw, erro = ler_arquivo_msinfo(arq)
                if erro:
                    resultados.append({"arquivo": arq.filename, "situacao": "erro", "msg": erro})
                    continue
                existente = equipamento_por_hostname(hw.get("hostname"))
                if existente:
                    eid = existente["id"]
                    mud = hardware.salvar(con, eid, hw, g.usuario.nome)
                    registrar_mov(con, eid, "Configuração atualizada pelo msinfo32 (importação em lote)"
                                  + (": " + "; ".join(mud) if mud else ""))
                    situacao, msg = "atualizado", ("; ".join(mud) or "Sem mudanças na configuração")
                else:
                    tipo = hw.get("tipo") if hw.get("tipo") in TIPOS else "Desktop"
                    agora = db.agora()
                    cur = con.execute(
                        "INSERT INTO equipamentos (unidade_id, tipo, marca, modelo, hostname, status, "
                        "criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (unidade_id, tipo, hw.get("marca") or None, (hw.get("modelo") or "")[:200] or None,
                         hw.get("hostname"), escolha["status"], agora, agora))
                    eid = cur.lastrowid
                    hardware.salvar(con, eid, hw, g.usuario.nome)
                    registrar_mov(con, eid, f"Cadastrado pela importação do msinfo32 — {msinfo.resumo_curto(hw)}")
                    situacao, msg = "novo", "Cadastrado. Complete patrimônio, série e responsável."
                resultados.append({"arquivo": arq.filename, "situacao": situacao, "msg": msg, "eid": eid,
                                   "hostname": hw.get("hostname"), "resumo": msinfo.resumo_curto(hw)})
            con.commit()
            n_novo = sum(r["situacao"] == "novo" for r in resultados)
            n_atu = sum(r["situacao"] == "atualizado" for r in resultados)
            n_err = sum(r["situacao"] == "erro" for r in resultados)
            seg.auditar("hardware_importacao_lote", f"{n_novo} novos, {n_atu} atualizados, {n_err} com erro")
    return render_template("estoque_importar.html", resultados=resultados, unidades=unidades_do_usuario(),
                           status=STATUS, escolha=escolha)


@bp.route("/estoque/<int:eid>/anotacao", methods=["POST"])
@seg.requer_editor
def anotacao(eid):
    obter_equipamento(eid)
    texto = txt(request.form, "texto", 500)
    if texto:
        con = db.get_db()
        registrar_mov(con, eid, texto)
        con.commit()
        flash("Anotação registrada no histórico.", "ok")
    return redirect(url_for("estoque.detalhe", eid=eid))


@bp.route("/estoque/<int:eid>/excluir", methods=["POST"])
@seg.requer_admin
def excluir(eid):
    e = obter_equipamento(eid)
    con = db.get_db()
    con.execute("DELETE FROM equipamentos WHERE id = ?", (eid,))
    con.commit()
    seg.auditar("equipamento_excluido",
                f"#{eid} {e['tipo']} {e['marca'] or ''} {e['modelo'] or ''} "
                f"série {e['numero_serie'] or '—'}")
    flash("Equipamento excluído.", "ok")
    return redirect(url_for("estoque.lista"))


# ------------------------------------------------------ senhas dos PCs ---
def obter_credencial(cid):
    c = db.get_db().execute("SELECT * FROM credenciais_pc WHERE id = ?", (cid,)).fetchone()
    if not c:
        abort(404)
    obter_equipamento(c["equipamento_id"])  # valida a unidade
    return c


@bp.route("/estoque/<int:eid>/senhas/nova", methods=["GET", "POST"])
@bp.route("/estoque/senhas/<int:cid>/editar", methods=["GET", "POST"], endpoint="cred_editar")
@seg.requer_senhas_pc
def cred_nova(eid=None, cid=None):
    cred = obter_credencial(cid) if cid else None
    eid = cred["equipamento_id"] if cred else eid
    e = obter_equipamento(eid)
    dek = seg.dek_atual()
    erros = []
    dados = dict(cred) if cred else {"tipo": "Administrador local"}
    if request.method == "POST":
        dados = {"tipo": txt(request.form, "tipo", 50),
                 "usuario": txt(request.form, "usuario", 150),
                 "observacoes": txt(request.form, "observacoes", 500)}
        senha = request.form.get("senha", "")
        if dados["tipo"] not in TIPOS_CREDENCIAL:
            erros.append("Selecione o tipo de credencial.")
        if not cred and not senha:
            erros.append("Informe a senha.")
        if not erros:
            con = db.get_db()
            if cred:
                senha_enc = cripto.cifrar(dek, senha, "pc") if senha else cred["senha_enc"]
                con.execute("UPDATE credenciais_pc SET tipo = ?, usuario = ?, senha_enc = ?, "
                            "observacoes = ?, atualizado_em = ?, atualizado_por = ? WHERE id = ?",
                            (dados["tipo"], dados["usuario"], senha_enc, dados["observacoes"],
                             db.agora(), g.usuario.nome, cid))
                acao = "senha_pc_alterada" if senha else "credencial_pc_editada"
            else:
                con.execute("INSERT INTO credenciais_pc (equipamento_id, tipo, usuario, "
                            "senha_enc, observacoes, atualizado_em, atualizado_por) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (eid, dados["tipo"], dados["usuario"],
                             cripto.cifrar(dek, senha, "pc"), dados["observacoes"],
                             db.agora(), g.usuario.nome))
                acao = "senha_pc_criada"
            con.commit()
            seg.auditar(acao, f"Equip. #{eid} {e['hostname'] or ''} — {dados['tipo']}")
            flash("Credencial salva.", "ok")
            return redirect(url_for("estoque.detalhe", eid=eid))
    return render_template("credencial_form.html", e=e, c=dados, cred=cred, erros=erros,
                           tipos=TIPOS_CREDENCIAL)


@bp.route("/estoque/senhas/<int:cid>/excluir", methods=["POST"])
@seg.requer_senhas_pc
def cred_excluir(cid):
    c = obter_credencial(cid)
    con = db.get_db()
    con.execute("DELETE FROM credenciais_pc WHERE id = ?", (cid,))
    con.commit()
    seg.auditar("senha_pc_excluida", f"Equip. #{c['equipamento_id']} — {c['tipo']}")
    flash("Credencial excluída.", "ok")
    return redirect(url_for("estoque.detalhe", eid=c["equipamento_id"]))


@bp.route("/api/revelar/pc/<int:cid>", methods=["POST"])
@seg.requer_senhas_pc
def revelar_pc(cid):
    c = obter_credencial(cid)
    senha = cripto.decifrar(seg.dek_atual(), c["senha_enc"], "pc")
    acao = "senha_pc_copiada" if request.args.get("acao") == "copiar" else "senha_pc_visualizada"
    seg.auditar(acao, f"Equip. #{c['equipamento_id']} — {c['tipo']} {c['usuario'] or ''}")
    return jsonify({"senha": senha})
