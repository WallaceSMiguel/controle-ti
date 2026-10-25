"""Leitura do msinfo32 e telas de hardware:  python -m pytest testes -q"""
import io
import re
import sqlite3
import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent))
from controle_ti import create_app  # noqa: E402
from controle_ti.msinfo import ErroMsinfo, capacidade, ler_msinfo, resumo_curto  # noqa: E402

AM = BASE / "amostras"


@pytest.fixture(scope="module", autouse=True)
def amostras():
    from gerar_amostras import main  # noqa: PLC0415
    sys.path.insert(0, str(BASE))
    main()


sys.path.insert(0, str(BASE))


def ler(nome):
    return (AM / nome).read_bytes()


# ------------------------------------------------------------- leitor ---
def test_txt_portugues():
    hw = ler_msinfo(ler("VAL-DC-021.txt"))
    assert hw["hostname"] == "VAL-DC-021"
    assert hw["marca"] == "Dell" and hw["modelo"] == "OptiPlex 3080" and hw["tipo"] == "Desktop"
    assert hw["sistema_operacional"] == "Windows 11 Pro"
    assert hw["nucleos"] == 6 and hw["threads"] == 12 and hw["memoria_gb"] == 16.0
    assert [d["capacidade"] for d in hw["discos"]] == ["500 GB", "1 TB"]       # pendrive ignorado
    assert hw["discos"][0]["tipo"] == "SSD" and hw["discos"][1]["tipo"] == "HD"
    assert [u["letra"] for u in hw["unidades"]] == ["C:", "D:"]                 # E: removível ignorado
    assert hw["unidades"][0]["uso"] == 92
    assert len(hw["rede"]) == 1 and hw["rede"][0]["ip"] == "192.168.10.21"     # virtuais ignorados
    assert resumo_curto(hw) == "Core i5-10500 · 16 GB · SSD 500 GB + HD 1 TB"


def test_nfo_ingles_utf16():
    hw = ler_msinfo(ler("VAL-BR-003.nfo"))
    assert hw["marca"] == "Lenovo" and hw["tipo"] == "Notebook"
    assert hw["sistema_operacional"] == "Windows 10 Pro"
    assert hw["memoria_gb"] == 8.0 and hw["armazenamento"] == "SSD 256 GB"
    assert hw["unidades"][0]["uso"] == 95
    assert [r["mac"] for r in hw["rede"]] == ["3C:58:C2:AA:BB:CC"]             # bluetooth ignorado


def test_nfo_servidor_utf8():
    hw = ler_msinfo(ler("VAL-SRV-01.nfo"))
    assert hw["tipo"] == "Servidor" and hw["memoria_gb"] == 32.0 and hw["armazenamento"] == "2 TB"


def test_arquivo_invalido():
    with pytest.raises(ErroMsinfo):
        ler_msinfo(b"isto nao e um relatorio")
    with pytest.raises(ErroMsinfo):
        ler_msinfo(b"<?xml version='1.0'?><MsInfo><broken>")


def test_capacidade():
    assert capacidade(512_110_190_592) == "512 GB"
    assert capacidade(2_000_398_934_016) == "2 TB"
    assert capacidade(1_500_000_000_000) == "1,5 TB"


# -------------------------------------------------------------- telas ---
def csrf(html):
    return re.search(r'name="csrf" content="([^"]+)"', html).group(1)


@pytest.fixture()
def cli(tmp_path):
    from controle_ti import seguranca
    seguranca._falhas.clear()  # o teste de bloqueio de login usa o mesmo usuário
    app = create_app(str(tmp_path))
    app.config["SESSION_COOKIE_SECURE"] = False
    c = app.test_client()
    tk = csrf(c.get("/instalacao").get_data(as_text=True))
    c.post("/instalacao", data={"_csrf": tk, "nome": "Ana", "usuario": "admin",
                                "senha": "SenhaForte123", "confirmacao": "SenhaForte123"})
    tk = csrf(c.get("/login").get_data(as_text=True))
    c.post("/login", data={"_csrf": tk, "usuario": "admin", "senha": "SenhaForte123"})
    c.db = app.config["DB_PATH"]
    return c


def tok(c):
    return csrf(c.get("/").get_data(as_text=True))


def test_cadastro_com_msinfo(cli):
    # 1) lê o arquivo: a tela volta preenchida
    r = cli.post("/estoque/novo", data={"_csrf": tok(cli), "acao": "importar", "status": "Em uso",
                                        "msinfo": (io.BytesIO(ler("VAL-DC-021.txt")), "VAL-DC-021.txt")},
                 content_type="multipart/form-data")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and 'value="VAL-DC-021"' in html and 'value="OptiPlex 3080"' in html
    assert "Intel(R) Core(TM) i5-10500" in html and "KINGSTON SNV2S500G" in html
    hw_json = re.search(r'name="hw_json" value="([^"]*)"', html).group(1)
    import html as h
    hw_json = h.unescape(hw_json)

    # 2) salva com unidade e patrimônio
    r = cli.post("/estoque/novo", data={
        "_csrf": tok(cli), "acao": "salvar", "hw_json": hw_json, "unidade_id": "1", "tipo": "Desktop",
        "status": "Em uso", "marca": "Dell", "modelo": "OptiPlex 3080", "hostname": "VAL-DC-021",
        "patrimonio": "PAT-77", "hw_processador": "Intel(R) Core(TM) i5-10500 CPU @ 3.10GHz",
        "hw_memoria_gb": "16", "hw_armazenamento": "SSD 500 GB + HD 1 TB", "hw_sistema_operacional": "Windows 11 Pro"},
        content_type="multipart/form-data")
    assert r.status_code == 302, r.get_data(as_text=True)
    eid = int(r.location.rstrip("/").split("/")[-1])
    ficha = cli.get(f"/estoque/{eid}").get_data(as_text=True)
    assert "Core i5-10500" in ficha and "16 GB" in ficha and "92% ocupado" in ficha
    assert "A4:BB:6D:12:34:56" in ficha and "Windows 11 Pro" in ficha
    lista = cli.get("/estoque").get_data(as_text=True)
    assert "Core i5-10500 · 16 GB · SSD 500 GB + HD 1 TB" in lista
    assert "i5-10500" in cli.get("/estoque?q=i5-10500").get_data(as_text=True)
    assert "VAL-DC-021" in cli.get("/estoque?alerta=disco").get_data(as_text=True)
    csv = cli.get("/estoque/exportar").get_data(as_text=True)
    assert "Processador" in csv and "SSD 500 GB + HD 1 TB" in csv

    # 3) memória trocada manualmente gera histórico
    r = cli.post(f"/estoque/{eid}/editar", data={
        "_csrf": tok(cli), "acao": "salvar", "unidade_id": "1", "tipo": "Desktop", "status": "Em uso",
        "hostname": "VAL-DC-021", "patrimonio": "PAT-77", "hw_processador": "Intel(R) Core(TM) i5-10500 CPU @ 3.10GHz",
        "hw_memoria_gb": "32", "hw_armazenamento": "SSD 500 GB + HD 1 TB", "hw_sistema_operacional": "Windows 11 Pro"},
        content_type="multipart/form-data")
    assert r.status_code == 302
    ficha = cli.get(f"/estoque/{eid}").get_data(as_text=True)
    assert "Memória: “16 GB” → “32 GB”" in ficha
    assert "92% ocupado" in ficha  # detalhes dos discos preservados


def test_atualizar_pela_ficha_e_lote(cli):
    tk = tok(cli)
    r = cli.post("/estoque/novo", data={"_csrf": tk, "acao": "salvar", "unidade_id": "3", "tipo": "Notebook",
                                        "status": "Em uso", "hostname": "val-br-003"},
                 content_type="multipart/form-data")
    eid = int(r.location.rstrip("/").split("/")[-1])
    assert "Configuração ainda não cadastrada" in cli.get(f"/estoque/{eid}").get_data(as_text=True)

    r = cli.post(f"/estoque/{eid}/msinfo", data={"_csrf": tok(cli),
                 "msinfo": (io.BytesIO(ler("VAL-BR-003.nfo")), "VAL-BR-003.nfo")}, content_type="multipart/form-data")
    assert r.status_code == 302
    ficha = cli.get(f"/estoque/{eid}").get_data(as_text=True)
    assert "Core i5-1135G7" in ficha and "Sem suporte da Microsoft" in ficha
    assert "Lenovo" in ficha  # marca preenchida porque estava vazia

    # arquivo inválido não quebra
    r = cli.post(f"/estoque/{eid}/msinfo", data={"_csrf": tok(cli),
                 "msinfo": (io.BytesIO(b"lixo"), "x.txt")}, content_type="multipart/form-data", follow_redirects=True)
    assert "x.txt:" in r.get_data(as_text=True)

    # lote: BR-003 já existe (atualiza), os outros dois são novos, um arquivo errado
    r = cli.post("/estoque/importar", data={
        "_csrf": tok(cli), "unidade_id": "1", "status": "Em estoque",
        "arquivos": [(io.BytesIO(ler("VAL-BR-003.nfo")), "VAL-BR-003.nfo"),
                     (io.BytesIO(ler("VAL-DC-021.txt")), "VAL-DC-021.txt"),
                     (io.BytesIO(ler("VAL-SRV-01.nfo")), "VAL-SRV-01.nfo"),
                     (io.BytesIO(b"oi"), "notas.docx")]}, content_type="multipart/form-data")
    html = r.get_data(as_text=True)
    assert "2 cadastrados · 1 atualizados · 1 com erro" in html
    con = sqlite3.connect(cli.db)
    tipos = dict(con.execute("SELECT hostname, tipo FROM equipamentos").fetchall())
    assert tipos == {"val-br-003": "Notebook", "VAL-DC-021": "Desktop", "VAL-SRV-01": "Servidor"}
    assert con.execute("SELECT COUNT(*) FROM hardware").fetchone()[0] == 3

    painel = cli.get("/").get_data(as_text=True)
    assert "Pontos de atenção" in painel
    assert "VAL-BR-003" not in cli.get("/estoque?alerta=memoria").get_data(as_text=True)
    assert "val-br-003" in cli.get("/estoque?alerta=win10").get_data(as_text=True)
