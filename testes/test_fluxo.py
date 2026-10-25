"""Testes de ponta a ponta:  python -m pytest testes -q"""
import re
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from controle_ti import create_app, cripto  # noqa: E402


def csrf(html: str) -> str:
    return re.search(r'name="csrf" content="([^"]+)"', html).group(1)


def post(cli, url, dados=None, pagina="/login", **kw):
    token = csrf(cli.get(pagina).get_data(as_text=True))
    return cli.post(url, data={**(dados or {}), "_csrf": token}, **kw)


@pytest.fixture()
def app(tmp_path):
    a = create_app(str(tmp_path))
    a.config["SESSION_COOKIE_SECURE"] = False
    return a


def instalar(app):
    cli = app.test_client()
    r = cli.get("/")
    assert r.status_code == 302 and "/instalacao" in r.location
    r = post(cli, "/instalacao", {"nome": "Ana Admin", "usuario": "admin",
                                  "senha": "SenhaForte123", "confirmacao": "SenhaForte123"},
             pagina="/instalacao")
    html = r.get_data(as_text=True)
    codigo = re.search(r'class="codigo-recuperacao">([^<]+)<', html).group(1)
    return cli, codigo


def login(cli, usuario, senha):
    return post(cli, "/login", {"usuario": usuario, "senha": senha})


def test_fluxo_completo(app, tmp_path):
    cli, codigo = instalar(app)
    assert login(cli, "admin", "errada123").status_code == 200
    r = login(cli, "admin", "SenhaForte123")
    assert r.status_code == 302

    # painel
    assert "Olá, Ana" in cli.get("/").get_data(as_text=True)

    # unidades padrão
    con = sqlite3.connect(app.config["DB_PATH"])
    unidades = dict(con.execute("SELECT nome, id FROM unidades").fetchall())
    assert set(unidades) == {"Del Castilho (Matriz)", "Caxias", "Barra"}
    caxias, barra = unidades["Caxias"], unidades["Barra"]

    # equipamento
    r = post(cli, "/estoque/novo", {"unidade_id": caxias, "tipo": "Notebook", "status": "Em uso",
                                    "marca": "Dell", "modelo": "Latitude 3420",
                                    "numero_serie": "ABC123", "patrimonio": "VAL-001",
                                    "hostname": "VAL-CX-01", "responsavel": "Maria"}, pagina="/")
    assert r.status_code == 302
    eid = int(r.location.rstrip("/").split("/")[-1])
    # duplicidade de série
    r = post(cli, "/estoque/novo", {"unidade_id": caxias, "tipo": "Desktop", "status": "Em uso",
                                    "numero_serie": "ABC123"}, pagina="/")
    assert "mesmo número de série" in r.get_data(as_text=True) or \
        "esse número de série" in r.get_data(as_text=True)

    # edição gera movimentação
    post(cli, f"/estoque/{eid}/editar", {"unidade_id": barra, "tipo": "Notebook",
                                         "status": "Em manutenção", "marca": "Dell",
                                         "modelo": "Latitude 3420", "numero_serie": "ABC123",
                                         "patrimonio": "VAL-001", "hostname": "VAL-CX-01",
                                         "responsavel": "Maria"}, pagina="/")
    html = cli.get(f"/estoque/{eid}").get_data(as_text=True)
    assert "Caxias" in html and "Barra" in html and "Em manutenção" in html

    # senha do PC
    r = post(cli, f"/estoque/{eid}/senhas/nova",
             {"tipo": "Administrador local", "usuario": "suporte", "senha": "PcSecreta!9"},
             pagina="/")
    assert r.status_code == 302
    cid = con.execute("SELECT id, senha_enc FROM credenciais_pc").fetchone()
    assert "PcSecreta" not in cid[1]  # cifrada no banco
    token = csrf(cli.get("/").get_data(as_text=True))
    r = cli.post(f"/api/revelar/pc/{cid[0]}", headers={"X-CSRF-Token": token})
    assert r.get_json()["senha"] == "PcSecreta!9"
    # sem CSRF -> bloqueado
    assert cli.post(f"/api/revelar/pc/{cid[0]}").status_code == 400

    # cofre
    r = post(cli, "/cofre/novo", {"sistema": "SIEG", "url": "sieg.com", "usuario": "fiscal@val",
                                  "senha": "Cofre#2026", "notas": "2FA no celular da TI",
                                  "unidade_id": ""}, pagina="/")
    assert r.status_code == 302
    item = con.execute("SELECT id, senha_enc, notas_enc, url FROM cofre").fetchone()
    assert "Cofre" not in item[1] and "2FA" not in item[2] and item[3] == "https://sieg.com"
    r = cli.post(f"/api/revelar/cofre/{item[0]}", headers={"X-CSRF-Token": token})
    assert r.get_json()["senha"] == "Cofre#2026"
    r = post(cli, "/cofre/novo", {"sistema": "Prefeitura Caxias", "senha": "x1",
                                  "unidade_id": str(caxias)}, pagina="/")

    # usuários: técnico só da Barra, sem cofre
    r = post(cli, "/admin/usuarios/novo", {"nome": "Téo Técnico", "usuario": "teo",
                                           "perfil": "tecnico", "ativo": "on",
                                           "unidades": [str(barra)], "senha": "Temporaria1",
                                           "confirmacao": "Temporaria1"}, pagina="/")
    assert r.status_code == 302, r.get_data(as_text=True)
    # consulta da Caxias com cofre
    post(cli, "/admin/usuarios/novo", {"nome": "Carla Consulta", "usuario": "carla",
                                       "perfil": "consulta", "ativo": "on", "acesso_cofre": "on",
                                       "unidades": [str(caxias)], "senha": "Temporaria2",
                                       "confirmacao": "Temporaria2"}, pagina="/")

    # auditoria registrou a visualização
    aud = cli.get("/admin/auditoria").get_data(as_text=True)
    assert "cofre senha visualizada" in aud and "senha pc visualizada" in aud

    backup = post(cli, "/admin/backup", pagina="/")
    assert backup.status_code == 302
    assert list((tmp_path / "backups").glob("*.db"))

    # ---- técnico
    t = app.test_client()
    login(t, "teo", "Temporaria1")
    assert "/conta/senha" in t.get("/").location  # obrigado a trocar
    r = post(t, "/conta/senha", {"atual": "Temporaria1", "nova": "TeoNova123",
                                 "confirmacao": "TeoNova123"}, pagina="/conta/senha")
    assert r.status_code == 302
    t.get("/logout")
    login(t, "teo", "TeoNova123")
    assert t.get(f"/estoque/{eid}").status_code == 200   # está na Barra
    assert t.get("/cofre").status_code == 403
    assert t.get("/admin/usuarios").status_code == 403
    tk = csrf(t.get("/").get_data(as_text=True))
    assert t.post(f"/api/revelar/pc/{cid[0]}", headers={"X-CSRF-Token": tk}).get_json()["senha"] == "PcSecreta!9"

    # ---- consulta: Caxias, cofre sim, sem senhas de PC, não edita
    c = app.test_client()
    login(c, "carla", "Temporaria2")
    post(c, "/conta/senha", {"atual": "Temporaria2", "nova": "CarlaNova1",
                             "confirmacao": "CarlaNova1"}, pagina="/conta/senha")
    assert c.get(f"/estoque/{eid}").status_code == 404   # equipamento está na Barra
    assert c.get("/estoque/novo").status_code == 403
    lista = c.get("/cofre").get_data(as_text=True)
    assert "SIEG" in lista and "Prefeitura Caxias" in lista
    tk = csrf(c.get("/").get_data(as_text=True))
    assert c.post(f"/api/revelar/cofre/{item[0]}", headers={"X-CSRF-Token": tk}).status_code == 200
    assert c.post(f"/api/revelar/pc/{cid[0]}", headers={"X-CSRF-Token": tk}).status_code == 403

    # ---- código de recuperação abre a chave
    salt, env = [r[0] for r in con.execute(
        "SELECT valor FROM config WHERE chave IN ('recuperacao_salt','recuperacao_dek') "
        "ORDER BY chave DESC")]
    dek = cripto.abrir_dek(salt, env, cripto.normalizar_codigo(codigo.lower()))
    assert cripto.decifrar(dek, item[1], "cofre") == "Cofre#2026"

    # todas as páginas renderizam
    for url in ["/", "/estoque", "/estoque/exportar", f"/estoque/{eid}", f"/estoque/{eid}/editar",
                "/cofre", f"/cofre/{item[0]}/editar", "/admin/usuarios", "/admin/unidades",
                "/admin/auditoria", "/admin/backup", "/conta/senha", "/estoque?q=dell"]:
        assert cli.get(url).status_code == 200, url


def test_bloqueio_login(app):
    cli, _ = instalar(app)
    for _ in range(5):
        login(cli, "admin", "errada")
    r = login(cli, "admin", "SenhaForte123")
    assert "Muitas tentativas" in r.get_data(as_text=True)
