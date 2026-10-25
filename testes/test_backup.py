"""Backup e restauração:  python -m pytest testes -q"""
import io
import re
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from controle_ti import backup, create_app, seguranca  # noqa: E402


def csrf(html):
    return re.search(r'name="csrf" content="([^"]+)"', html).group(1)


@pytest.fixture()
def amb(tmp_path):
    seguranca._falhas.clear()
    seguranca.encerrar_todas_sessoes()
    app = create_app(str(tmp_path))
    app.config["SESSION_COOKIE_SECURE"] = False
    c = app.test_client()
    tk = csrf(c.get("/instalacao").get_data(as_text=True))
    c.post("/instalacao", data={"_csrf": tk, "nome": "Ana", "usuario": "admin",
                                "senha": "SenhaForte123", "confirmacao": "SenhaForte123"})
    entrar(c)
    return app, c, tmp_path


def entrar(c, senha="SenhaForte123"):
    tk = csrf(c.get("/login").get_data(as_text=True))
    return c.post("/login", data={"_csrf": tk, "usuario": "admin", "senha": senha})


def tok(c):
    return csrf(c.get("/").get_data(as_text=True))


def novo_equip(c, nome):
    return c.post("/estoque/novo", data={"_csrf": tok(c), "acao": "salvar", "unidade_id": "1",
                                         "tipo": "Desktop", "status": "Em uso", "modelo": nome},
                  content_type="multipart/form-data")


def modelos(app):
    con = sqlite3.connect(app.config["DB_PATH"])
    r = sorted(x[0] for x in con.execute("SELECT modelo FROM equipamentos"))
    con.close()
    return r


def test_restaurar_pela_tela(amb):
    app, c, pasta = amb
    novo_equip(c, "Antes")
    c.post("/admin/backup", data={"_csrf": tok(c)})
    arq = next((pasta / "backups").glob("controle_ti_*.db")).name
    novo_equip(c, "Depois")
    assert modelos(app) == ["Antes", "Depois"]

    tela = c.get("/admin/backup").get_data(as_text=True)
    assert "1 equipamentos · 0 senhas no cofre · 1 usuários" in tela

    # confirmação errada: nada muda
    r = c.post(f"/admin/backup/{arq}/restaurar", data={"_csrf": tok(c), "confirmacao": "sim"}, follow_redirects=True)
    assert "digite RESTAURAR" in r.get_data(as_text=True)
    assert modelos(app) == ["Antes", "Depois"]

    r = c.post(f"/admin/backup/{arq}/restaurar", data={"_csrf": tok(c), "confirmacao": "restaurar"})
    assert r.status_code == 302 and "/login" in r.location
    login = c.get("/login").get_data(as_text=True)
    assert "restaurado: 1 equipamentos" in login
    assert modelos(app) == ["Antes"]
    assert c.get("/").status_code == 302  # todos precisam entrar de novo

    entrar(c)
    aud = c.get("/admin/auditoria").get_data(as_text=True)
    assert "backup restaurado" in aud
    antes = list((pasta / "backups").glob("*antes_da_restauracao.db"))
    assert len(antes) == 1

    # desfazer: restaurar o estado anterior traz "Depois" de volta
    c.post(f"/admin/backup/{antes[0].name}/restaurar", data={"_csrf": tok(c), "confirmacao": "RESTAURAR"})
    assert modelos(app) == ["Antes", "Depois"]


def test_restaurar_arquivo_enviado_e_antigo(amb):
    app, c, pasta = amb
    novo_equip(c, "Original")
    copia = pasta / "copia_externa.db"
    backup.fazer_backup(app.config["DB_PATH"], str(pasta / "externo"))
    origem = next((pasta / "externo").glob("*.db"))
    # simula backup de uma versão antiga, sem a tabela de hardware
    con = sqlite3.connect(origem)
    con.execute("DROP TABLE hardware")
    con.commit()
    con.close()
    copia.write_bytes(origem.read_bytes())
    novo_equip(c, "Novo")

    # arquivo inválido é recusado e descartado
    r = c.post("/admin/backup/enviar", data={"_csrf": tok(c), "confirmacao": "RESTAURAR",
                                            "arquivo": (io.BytesIO(b"nada"), "x.db")},
               content_type="multipart/form-data", follow_redirects=True)
    assert "formato inválido" in r.get_data(as_text=True)
    assert not list((pasta / "backups").glob("*enviado.db"))

    r = c.post("/admin/backup/enviar", data={"_csrf": tok(c), "confirmacao": "RESTAURAR",
                                            "arquivo": (io.BytesIO(copia.read_bytes()), "copia_externa.db")},
               content_type="multipart/form-data")
    assert "/login" in r.location
    assert modelos(app) == ["Original"]
    con = sqlite3.connect(app.config["DB_PATH"])
    assert con.execute("SELECT name FROM sqlite_master WHERE name = 'hardware'").fetchone()  # recriada
    con.close()
    entrar(c)
    assert c.get("/estoque").status_code == 200


def test_inspecionar_recusa_outro_banco(tmp_path):
    outro = tmp_path / "outro.db"
    con = sqlite3.connect(outro)
    con.execute("CREATE TABLE x (a)")
    con.commit()
    con.close()
    with pytest.raises(backup.ErroBackup):
        backup.inspecionar(outro)


def test_restaurar_pelo_terminal(amb, monkeypatch, capsys):
    app, c, pasta = amb
    novo_equip(c, "Antes")
    c.post("/admin/backup", data={"_csrf": tok(c)})
    novo_equip(c, "Depois")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import gerenciar
    respostas = iter(["1", "RESTAURAR"])
    monkeypatch.setattr("builtins.input", lambda *_: next(respostas))
    assert gerenciar.restaurar(app) == 0
    assert modelos(app) == ["Antes"]
    assert "Restaurado" in capsys.readouterr().out
