"""Termos de responsabilidade:  python -m pytest testes/test_termos.py -q"""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from controle_ti import create_app, db, termos  # noqa: E402
from test_fluxo import instalar, login, post  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    a = create_app(str(tmp_path))
    a.config["SESSION_COOKIE_SECURE"] = False
    return a


def preparar(app):
    cli, _ = instalar(app)
    login(cli, "admin", "SenhaForte123")
    con = sqlite3.connect(app.config["DB_PATH"])
    unidades = dict(con.execute("SELECT nome, id FROM unidades").fetchall())
    r = post(cli, "/estoque/novo", {"unidade_id": unidades["Barra"], "tipo": "Notebook",
                                    "status": "Em estoque", "marca": "Dell", "modelo": "Latitude 3420",
                                    "numero_serie": "SN-XYZ-99", "patrimonio": "VAL-001",
                                    "hostname": "VAL-BR-01"}, pagina="/")
    eid = int(r.location.rstrip("/").split("/")[-1])
    post(cli, "/cofre/novo", {"sistema": "Domínio Web", "usuario": "MARIA", "url": "dominio.com",
                              "senha": "Cofre#Senha1", "unidade_id": ""}, pagina="/")
    cid = con.execute("SELECT id FROM cofre").fetchone()[0]
    return cli, con, unidades, eid, cid


def csrf_de(cli):
    import re
    return re.search(r'name="csrf" content="([^"]+)"', cli.get("/").get_data(as_text=True)).group(1)


def termo_json(unidade, eid, cid, **extra):
    d = {"tipo": "completo", "unidade_id": unidade, "nome": "Maria da Silva",
         "cpf": "123.456.789-00", "setor": "DP", "local": "Rio de Janeiro - RJ", "data": "2026-11-27",
         "recNome": "Ana Admin",
         "itens": [{"equipamento_id": eid, "item": "", "serie": "", "qtd": 1, "estado": "Bom", "obs": "com carregador"},
                   {"item": "Mouse", "serie": "", "qtd": 1, "estado": "Novo", "obs": ""}],
         "acessos": [{"cofre_id": cid, "sistema": "", "usuario": "MARIA", "detalhe": "", "usar_cofre": True},
                     {"sid": "email", "sistema": "E-mail corporativo", "usuario": "maria@val.com", "senha": "Provisoria#9"},
                     {"sid": "linkus", "sistema": "Telefonia Linkus", "usuario": "", "detalhe": "Ramal 2031"}]}
    d.update(extra)
    return d


def enviar(cli, url, dados):
    return cli.post(url, json={"dados": dados}, headers={"X-CSRF-Token": csrf_de(cli)})


def test_termo_com_estoque_e_cofre(app):
    cli, con, unidades, eid, cid = preparar(app)

    # editor abre com os dados de estoque e cofre para a tela
    html = cli.get("/termos/novo").get_data(as_text=True)
    assert 'id="termo-config"' in html and "termo_editor.js" in html and "Latitude 3420" in html
    assert "Cofre#Senha1" not in html

    # sem CSRF não grava
    assert cli.post("/termos/novo", json={"dados": termo_json(unidades["Barra"], eid, cid)}).status_code == 400

    r = enviar(cli, "/termos/novo", termo_json(unidades["Barra"], eid, cid))
    assert r.status_code == 200, r.get_data(as_text=True)
    tid = r.get_json()["id"]
    numero, dados_txt, unidade_id = con.execute(
        "SELECT numero, dados, unidade_id FROM termos WHERE id = ?", (tid,)).fetchone()
    assert numero.startswith("TR-") and numero.endswith("-0001") and unidade_id == unidades["Barra"]
    # senhas nunca em texto puro no banco
    assert "Cofre#Senha1" not in dados_txt and "Provisoria#9" not in dados_txt
    dados = json.loads(dados_txt)
    assert [bool(a.get("senha_enc")) for a in dados["acessos"]] == [True, True, False]
    assert dados["acessos"][0]["sistema"] == "Domínio Web" and dados["acessos"][0]["cofre_id"] == cid
    assert dados["unidade"] == "Barra" and "unidade_id" not in dados
    # item veio do estoque
    assert "Dell Latitude 3420" in dados["itens"][0]["item"] and "VAL-001" in dados["itens"][0]["serie"]
    assert dados["itens"][0]["equipamento_id"] == eid

    # equipamento recebeu o responsável e a movimentação
    resp, setor, status = con.execute(
        "SELECT responsavel, setor, status FROM equipamentos WHERE id = ?", (eid,)).fetchone()
    assert (resp, setor, status) == ("Maria da Silva", "DP", "Em uso")
    movs = [m[0] for m in con.execute("SELECT descricao FROM movimentacoes WHERE equipamento_id = ?", (eid,))]
    assert any(numero in m for m in movs)
    assert numero in cli.get(f"/estoque/{eid}").get_data(as_text=True)

    # tela do termo e editor não mostram senhas; impressão com senhas mostra e audita
    html = cli.get(f"/termos/{tid}").get_data(as_text=True)
    assert "Maria da Silva" in html and "Cofre#Senha1" not in html and "Provisoria#9" not in html
    html = cli.get(f"/termos/{tid}/editar").get_data(as_text=True)
    assert "Cofre#Senha1" not in html and "Provisoria#9" not in html and "senha_enc" not in html
    html = cli.get(f"/termos/{tid}/imprimir").get_data(as_text=True)
    assert "Cofre#Senha1" not in html
    html = cli.get(f"/termos/{tid}/imprimir?senhas=1").get_data(as_text=True)
    assert "Cofre#Senha1" in html and "Provisoria#9" in html
    assert con.execute("SELECT COUNT(*) FROM auditoria WHERE acao = 'termo_impresso_com_senhas'").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM auditoria WHERE acao = 'cofre_senha_no_termo'").fetchone()[0] == 1

    # edição com senha em branco mantém as senhas gravadas; "limpar" remove
    ed = termo_json(unidades["Barra"], eid, cid, cargo="Analista")
    for i, a in enumerate(ed["acessos"]):
        a["orig"] = i
        a.pop("senha", None)
        a["usar_cofre"] = False
    ed["acessos"][2]["limpar"] = True
    r = enviar(cli, f"/termos/{tid}/editar", ed)
    assert r.status_code == 200, r.get_data(as_text=True)
    html = cli.get(f"/termos/{tid}/imprimir?senhas=1").get_data(as_text=True)
    assert "Provisoria#9" in html and "Cofre#Senha1" in html and "Analista" in html

    # lista e busca
    assert numero in cli.get("/termos?q=VAL-001").get_data(as_text=True)

    # devolução devolve o equipamento ao estoque
    r = post(cli, f"/termos/{tid}/status", {"status": "devolvido", "observacao": "ok"}, pagina="/")
    assert r.status_code == 302
    resp, status = con.execute("SELECT responsavel, status FROM equipamentos WHERE id = ?", (eid,)).fetchone()
    assert (resp, status) == ("", "Em estoque")
    assert con.execute("SELECT status FROM termos WHERE id = ?", (tid,)).fetchone()[0] == "devolvido"

    # próximo número
    enviar(cli, "/termos/novo", termo_json(unidades["Barra"], eid, cid, tipo="equipamentos"))
    assert con.execute("SELECT numero FROM termos ORDER BY id DESC").fetchone()[0].endswith("-0002")


def test_termo_a_partir_do_equipamento(app):
    cli, con, unidades, eid, cid = preparar(app)
    html = cli.get(f"/termos/novo?equipamento={eid}").get_data(as_text=True)
    assert "Dell Latitude 3420" in html and "VAL-001" in html


def test_empresa_e_validacoes(app):
    cli, con, unidades, eid, cid = preparar(app)
    r = post(cli, "/termos/empresa", {"empresa": "Empresa Teste LTDA", "cnpj": "00.000.000/0001-00"},
             pagina="/")
    assert r.status_code == 302
    r = enviar(cli, "/termos/novo", termo_json(unidades["Barra"], eid, cid, nome=""))
    assert r.status_code == 400 and "Informe o nome do colaborador" in r.get_json()["erro"]
    r = enviar(cli, "/termos/novo", termo_json(unidades["Barra"], eid, cid))
    tid = r.get_json()["id"]
    assert "Empresa Teste LTDA" in cli.get(f"/termos/{tid}").get_data(as_text=True)


# ------------------------------------------------------------- importação ---
SCHEMA_ANTIGO = """
CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, login TEXT NOT NULL UNIQUE,
  senha_hash TEXT NOT NULL, perfil TEXT NOT NULL DEFAULT 'usuario', ativo INTEGER NOT NULL DEFAULT 1,
  trocar_senha INTEGER NOT NULL DEFAULT 1, criado_em TEXT NOT NULL, ultimo_acesso TEXT);
CREATE TABLE termos (id INTEGER PRIMARY KEY AUTOINCREMENT, numero TEXT NOT NULL UNIQUE,
  colaborador TEXT NOT NULL DEFAULT '', cpf TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'ativo',
  dados TEXT NOT NULL, criado_por INTEGER, criado_em TEXT NOT NULL, atualizado_por INTEGER,
  atualizado_em TEXT NOT NULL, devolvido_em TEXT, unidade TEXT NOT NULL DEFAULT '',
  tipo TEXT NOT NULL DEFAULT 'equipamentos');
CREATE TABLE historico (id INTEGER PRIMARY KEY AUTOINCREMENT, termo_id INTEGER NOT NULL, user_id INTEGER,
  acao TEXT NOT NULL, detalhe TEXT, quando TEXT NOT NULL);
CREATE TABLE config (chave TEXT PRIMARY KEY, valor TEXT NOT NULL);
"""


def banco_antigo(caminho):
    c = sqlite3.connect(caminho)
    c.executescript(SCHEMA_ANTIGO)
    c.execute("INSERT INTO users VALUES (1, 'Wallace', 'wallace', 'x', 'admin', 1, 0, '2026-01-01T00:00:00+00:00', NULL)")
    c.execute("INSERT INTO config VALUES ('empresa', ?)", (json.dumps({"empresa": "VALORIZAÇÃO ANTIGA", "cnpj": "1",
                                                                         "logo": "data:image/png;base64,AAAA"}),))
    termos_antigos = [
        ("TR-2026-0007", "João", "Barra", "ativo", "equipamentos",
         {"nome": "João", "itens": [{"item": "Notebook", "serie": "PT VAL-001", "qtd": 1, "estado": "Bom"}]}),
        ("TR-2026-0008", "Bia", "Duque de Caxias", "devolvido", "completo",
         {"nome": "Bia", "itens": [{"item": "Monitor", "serie": "S/N 123"}],
          "acessos": [{"sistema": "Onvio", "usuario": "bia", "senha": "nao-deveria-existir"}]}),
    ]
    for i, (num, nome, un, st, tipo, d) in enumerate(termos_antigos, 1):
        c.execute("INSERT INTO termos (id, numero, colaborador, cpf, status, dados, criado_por, criado_em, "
                  "atualizado_por, atualizado_em, unidade, tipo) VALUES (?, ?, ?, '', ?, ?, 1, ?, 1, ?, ?, ?)",
                  (i, num, nome, st, json.dumps(d), "2026-03-01T13:00:00+00:00", "2026-03-02T13:00:00+00:00", un, tipo))
        c.execute("INSERT INTO historico (termo_id, user_id, acao, detalhe, quando) VALUES (?, 1, 'criado', ?, ?)",
                  (i, num, "2026-03-01T13:00:00+00:00"))
    c.commit()
    c.close()


def test_importacao_do_sistema_antigo(app, tmp_path):
    cli, con, unidades, eid, cid = preparar(app)
    origem = tmp_path / "termos.db"
    banco_antigo(origem)
    antes = origem.read_bytes()

    alvo = db.conectar(app.config["DB_PATH"])
    res = termos.importar_banco_termos(alvo, str(origem))
    assert res["importados"] == 2 and res["historico"] == 2 and res["itens_vinculados"] == 1
    assert res["empresa"] is True
    assert res["unidades_sem_correspondencia"] == ["Duque de Caxias"]
    assert origem.read_bytes() == antes  # origem intacta

    t1 = alvo.execute("SELECT * FROM termos WHERE numero = 'TR-2026-0007'").fetchone()
    assert t1["unidade_id"] == unidades["Barra"] and t1["criado_por"] == "Wallace" and t1["origem"] == "importado"
    assert alvo.execute("SELECT equipamento_id FROM termo_equipamentos WHERE termo_id = ?",
                        (t1["id"],)).fetchone()[0] == eid
    t2 = alvo.execute("SELECT * FROM termos WHERE numero = 'TR-2026-0008'").fetchone()
    assert t2["unidade_id"] is None and t2["unidade_nome"] == "Duque de Caxias"
    assert "nao-deveria-existir" not in t2["dados"]

    # rodar de novo não duplica, e o mapa liga a unidade que faltou
    res = termos.importar_banco_termos(alvo, str(origem), {"Duque de Caxias": "Caxias"})
    assert res["importados"] == 0 and res["ja_existiam"] == 2 and res["unidades_religadas"] == 1
    assert alvo.execute("SELECT unidade_id FROM termos WHERE numero = 'TR-2026-0008'").fetchone()[0] == unidades["Caxias"]
    assert alvo.execute("SELECT COUNT(*) FROM termos").fetchone()[0] == 2
    alvo.close()

    # numeração continua depois do maior número importado do ano
    ano = termos.proximo_numero(con, 2026)
    assert ano == "TR-2026-0009"
    # termos importados aparecem na tela, com os dados da empresa importados
    html = cli.get(f"/termos/{t1['id']}").get_data(as_text=True)
    assert "João" in html and "VALORIZAÇÃO ANTIGA" in html


def test_importacao_rejeita_arquivo_errado(app, tmp_path):
    instalar(app)
    outro = tmp_path / "outro.db"
    sqlite3.connect(outro).execute("CREATE TABLE x (a)").connection.commit()
    alvo = db.conectar(app.config["DB_PATH"])
    with pytest.raises(termos.ErroImportacao):
        termos.importar_banco_termos(alvo, str(outro))
