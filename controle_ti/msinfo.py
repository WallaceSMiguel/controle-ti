"""Leitura dos relatórios do Windows "Informações do Sistema" (msinfo32).

Aceita os dois formatos que o msinfo32 gera:
  - .nfo  -> Arquivo > Salvar   (XML, normalmente UTF-16)
  - .txt  -> Arquivo > Exportar (texto com tabulações, normalmente UTF-16)
em português ou inglês.

Uso:  dados = ler_msinfo(bytes_do_arquivo)   ->  dict com os campos de hardware
"""
import math
import re
import unicodedata

try:  # proteção contra XML malicioso, se disponível
    from defusedxml import ElementTree as ET
except ImportError:  # pragma: no cover
    import xml.etree.ElementTree as ET


class ErroMsinfo(Exception):
    pass


# ------------------------------------------------------------ utilidades ---
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


VAZIOS = {"", "not available", "nao disponivel", "n/a", "none", "nenhum", "nenhuma"}


def _valor(v):
    v = (v or "").strip()
    return None if _norm(v) in VAZIOS else v


def _decodificar(dados: bytes) -> str:
    if dados.startswith(b"\xff\xfe") or dados.startswith(b"\xfe\xff"):
        return dados.decode("utf-16")
    if dados.startswith(b"\xef\xbb\xbf"):
        return dados[3:].decode("utf-8", errors="replace")
    amostra = dados[:2000]
    if amostra and amostra.count(b"\x00") > len(amostra) // 4:
        return dados.decode("utf-16-le", errors="replace")
    try:
        return dados.decode("utf-8")
    except UnicodeDecodeError:
        return dados.decode("cp1252", errors="replace")


# ------------------------------------------------- leitura em categorias ---
# Resultado intermediário: { nome_categoria_normalizado: [ (chave, valor) | None ] }
# None marca a separação entre registros (ex.: um disco e outro).

def _categorias_nfo(texto: str) -> dict:
    texto = re.sub(r"^<\?xml[^>]*\?>", "", texto.lstrip("﻿").lstrip())
    try:
        raiz = ET.fromstring(texto)
    except Exception as e:  # noqa: BLE001
        raise ErroMsinfo("O arquivo .nfo não pôde ser lido (XML inválido).") from e
    cats: dict = {}

    def visitar(cat):
        nome = _norm(cat.get("name", ""))
        linhas = cats.setdefault(nome, [])
        for filho in cat:
            if filho.tag == "Data":
                cols = [(c.text or "").strip() for c in filho]
                if len(cols) >= 2 and (cols[0] or cols[1]):
                    linhas.append((cols[0], cols[1]))
                else:
                    linhas.append(None)
            elif filho.tag == "Category":
                visitar(filho)

    # visitar() desce nas categorias filhas
    for cat in ([raiz] if raiz.tag == "Category" else raiz.findall("Category")):
        visitar(cat)
    if not cats:
        raise ErroMsinfo("Nenhuma informação encontrada no arquivo .nfo.")
    return cats


def _categorias_txt(texto: str) -> dict:
    cats: dict = {}
    atual = None
    cabecalho_pendente = False
    for linha in texto.splitlines():
        crua = linha.rstrip("\r\n")
        m = re.match(r"^\[(.+)\]\s*$", crua.strip())
        if m and "\t" not in crua:
            atual = cats.setdefault(_norm(m.group(1)), [])
            cabecalho_pendente = True
            continue
        if atual is None:
            continue
        partes = crua.split("\t")
        if not crua.strip():
            atual.append(None)
            continue
        if cabecalho_pendente:  # linha "Item  Valor" / "Item  Value"
            cabecalho_pendente = False
            continue
        if len(partes) >= 2:
            atual.append((partes[0].strip(), partes[1].strip()))
    if not any(cats.values()):
        raise ErroMsinfo("Arquivo de texto sem o formato do msinfo32.")
    return cats


def _achar(cats: dict, *nomes):
    for n in nomes:
        n = _norm(n)
        if n in cats and cats[n]:
            return cats[n]
    return []


def _registros(linhas, chaves_inicio):
    """Separa as linhas em registros (um por disco, unidade, adaptador...)."""
    inicio = {_norm(k) for k in chaves_inicio}
    regs, atual = [], {}
    for item in linhas:
        if item is None:
            if atual:
                regs.append(atual)
            atual = {}
            continue
        k, v = _norm(item[0]), item[1]
        if k in inicio and k in atual:
            regs.append(atual)
            atual = {}
        atual.setdefault(k, v)
    if atual:
        regs.append(atual)
    return regs


def _pega(reg: dict, *chaves):
    for c in chaves:
        v = reg.get(_norm(c))
        if _valor(v):
            return _valor(v)
    return None


# ----------------------------------------------------------- conversões ---
def _numero(txt: str):
    """'16,0' -> 16.0 ; '1.234,5' -> 1234.5 ; '476.94' -> 476.94"""
    m = re.search(r"\d[\d.,]*", txt or "")
    if not m:
        return None
    s = m.group(0).rstrip(".,")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _bytes(txt: str):
    """Tamanho em bytes. Usa o valor entre parênteses quando existe."""
    if not txt:
        return None
    m = re.search(r"\(([\d.,\s ]+)\s*bytes?\)", txt, re.I)
    if m:
        dig = re.sub(r"\D", "", m.group(1))
        if dig:
            return int(dig)
    n = _numero(txt)
    if n is None:
        return None
    t = txt.upper()
    mult = 1024 ** 4 if "TB" in t else 1024 ** 3 if "GB" in t else 1024 ** 2 if "MB" in t else 1
    return int(n * mult)


CAPACIDADES = [32, 60, 64, 120, 128, 160, 240, 250, 256, 320, 480, 500, 512, 640, 750,
               960, 1000, 1024, 2000, 2048, 3000, 4000, 6000, 8000]


def capacidade(b) -> str:
    """Bytes -> capacidade comercial ('512 GB', '1 TB')."""
    if not b:
        return "—"
    gb = b / 1e9
    perto = min(CAPACIDADES, key=lambda c: abs(c - gb))
    if abs(perto - gb) / perto < 0.05:
        gb = perto
    if gb >= 1000:
        tb = gb / 1000
        return f"{tb:.1f}".rstrip("0").rstrip(".").replace(".", ",") + " TB"
    return f"{gb:.0f} GB"


def gb_legivel(b) -> str:
    if b is None:
        return "—"
    gb = b / 1024 ** 3
    return (f"{gb:.0f}" if gb >= 100 else f"{gb:.1f}").replace(".", ",") + " GB"


def processador_curto(nome: str) -> str:
    if not nome:
        return ""
    s = re.sub(r"\((R|TM|tm|r)\)", "", nome)
    s = re.sub(r"\s*@.*$", "", s)
    s = re.sub(r"\b(CPU|Processor|Processador|with Radeon.*|w/ Radeon.*)\b", "", s, flags=re.I)
    s = re.sub(r"\b\d+(st|nd|rd|th)\s+Gen\b", "", s, flags=re.I)
    s = re.sub(r"^\s*(Intel|AMD)\s+", "", s.strip())
    return re.sub(r"\s+", " ", s).strip()


MARCAS = [
    (r"dell", "Dell"), (r"lenovo", "Lenovo"), (r"hewlett|^hp\b|\bhp\b", "HP"),
    (r"asus", "ASUS"), (r"acer", "Acer"), (r"positivo", "Positivo"), (r"samsung", "Samsung"),
    (r"microsoft", "Microsoft"), (r"apple", "Apple"), (r"multilaser", "Multilaser"),
    (r"vaio", "VAIO"), (r"gigabyte", "Gigabyte"), (r"msi|micro-star", "MSI"), (r"intel", "Intel"),
    (r"daten", "Daten"), (r"itautec", "Itautec"), (r"compaq", "Compaq"), (r"avell", "Avell"),
]
GENERICOS = {"to be filled by o.e.m.", "system manufacturer", "system product name",
             "default string", "oem", "o.e.m.", "not applicable", "all series"}


def marca(fabricante: str) -> str:
    if not fabricante or _norm(fabricante) in GENERICOS:
        return ""
    for pad, nome in MARCAS:
        if re.search(pad, fabricante, re.I):
            return nome
    return re.sub(r"\s+(Inc\.?|Corporation|Corp\.?|Co\.,? ?Ltd\.?|Ltda\.?|S\.?A\.?)$", "", fabricante.strip(), flags=re.I)


# --------------------------------------------------------- interpretação ---
def _resumo(cats):
    linhas = _achar(cats, "resumo do sistema", "system summary", "resumo")
    res: dict[str, list] = {}
    for item in linhas:
        if item:
            v = _valor(item[1])
            if v:
                res.setdefault(_norm(item[0]), []).append(v)
    return res


def _campo(res, *opcoes, todos=False):
    """Busca no resumo por nome exato ou pelo conjunto de palavras."""
    for op in opcoes:
        if isinstance(op, tuple):  # todas as palavras precisam estar na chave
            for k, v in res.items():
                if all(p in k for p in op):
                    return v if todos else v[0]
        else:
            v = res.get(_norm(op))
            if v:
                return v if todos else v[0]
    return [] if todos else None


def _plataforma_tipo(plataforma, os_nome, modelo):
    p = _norm(plataforma or "")
    if "server" in _norm(os_nome or "") or "servidor" in p or "server" in p:
        return "Servidor"
    if p and any(x in p for x in ("mobile", "movel", "slate", "portatil")):
        return "Notebook"
    if p and any(x in p for x in ("desktop", "area de trabalho", "workstation", "estacao")):
        return "Desktop"
    m = _norm(modelo or "")
    if re.search(r"latitude|thinkpad|vostro 1|vostro 3[45]|inspiron 1[45]|inspiron 3[45]|ideapad|elitebook|probook|"
                 r"zenbook|vivobook|aspire [357]|notebook|laptop|macbook|thinkbook|surface|precision 3[45]|xps 1", m):
        return "Notebook"
    return "Desktop" if m else ""


def ler_msinfo(dados: bytes) -> dict:
    if not dados:
        raise ErroMsinfo("Arquivo vazio.")
    texto = _decodificar(dados)
    inicio = texto.lstrip("﻿ \r\n\t")[:200].lower()
    if inicio.startswith("<?xml") or inicio.startswith("<msinfo"):
        cats = _categorias_nfo(texto)
    else:
        cats = _categorias_txt(texto)

    res = _resumo(cats)
    if not res:
        raise ErroMsinfo("Não encontrei o “Resumo do Sistema” no arquivo. "
                         "Gere de novo pelo msinfo32 (Arquivo > Salvar ou Exportar).")

    os_nome = _campo(res, "os name", "nome do so", "nome do sistema operacional", ("nome", "sistema operacional"))
    fabricante = _campo(res, "system manufacturer", "fabricante do sistema")
    modelo = _campo(res, "system model", "modelo do sistema")
    plataforma = _campo(res, "platform role", "funcao da plataforma", "funcao de plataforma", ("funcao", "plataforma"))

    # processador(es)
    procs = _campo(res, "processor", "processador", todos=True)
    proc_nome, nucleos, threads, freq = None, 0, 0, None
    for p in procs:
        partes = [x.strip() for x in p.split(",")]
        proc_nome = proc_nome or partes[0]
        m = re.search(r"(\d+)\s*(core|nucleo|n[uú]cleo)", _norm(p))
        nucleos += int(m.group(1)) if m else 0
        m = re.search(r"(\d+)\s*(logical|processador\(es\) logico|processadores logicos|logico)", _norm(p))
        threads += int(m.group(1)) if m else 0
        m = re.search(r"@\s*([\d.,]+\s*GHz)", p, re.I)
        freq = freq or (m.group(1).replace(" ", "") if m else None)
    if len(procs) > 1 and proc_nome:
        proc_nome = f"{len(procs)}x {proc_nome}"

    # memória
    ram_txt = _campo(res, "installed physical memory (ram)", "memoria fisica (ram) instalada",
                     ("memoria", "instalada"), ("installed", "memory"))
    ram_total_txt = _campo(res, "total physical memory", "memoria fisica total", ("memoria fisica", "total"))
    memoria = _numero(ram_txt) if ram_txt else None
    if memoria is None and ram_total_txt:
        memoria = _numero(ram_total_txt)
        if memoria and "MB" in ram_total_txt.upper():
            memoria /= 1024
        memoria = float(round(memoria)) if memoria else None
    elif memoria and "MB" in (ram_txt or "").upper():
        memoria = memoria / 1024

    # discos físicos
    discos = []
    for r in _registros(_achar(cats, "discos", "disks"), ["description", "descricao"]):
        tam = _bytes(_pega(r, "size", "tamanho"))
        mod = _pega(r, "model", "modelo")
        if not tam and not mod:
            continue
        nm = _norm(mod or "")
        interface = _pega(r, "interface type", "tipo de interface")
        if any(x in nm for x in ("usb", "card reader", "flash", "sd ", "mmc")) and (tam or 0) < 300e9:
            continue  # pendrive / leitor de cartão
        nvme = bool(re.search(r"nvme", nm + " " + _norm(interface or "")))
        tipo = "SSD" if nvme or re.search(r"ssd|solid|m\.2|kingston (sa|sn|sk|snv|nv)|\bsa400|\ba400|\bsnv\d|\bsk[cl]|wds\d|"
                                          r"mz[-a-z]|ct\d+(p|mx|bx)|sk hynix|hfm|hfs\d|kbg|pm9|pc sn|\bsn\d{3}|crucial|"
                                          r"\bmtfd|intenso|wd (green|blue) sn|\bkxg|\bthnsn|lite-?on c|liteon cv|cv[38]-", nm) else "HD" if re.search(r"\bst\d|wdc wd|hgst|toshiba dt|toshiba mq|hitachi|hts|hds", nm) else ""
        discos.append({"modelo": mod or "Disco", "bytes": tam, "capacidade": capacidade(tam),
                       "tipo": tipo, "interface": interface})

    # unidades lógicas (C:, D:...)
    unidades = []
    for r in _registros(_achar(cats, "unidades", "drives"), ["drive", "unidade"]):
        letra = _pega(r, "drive", "unidade")
        desc = _norm(_pega(r, "description", "descricao") or "")
        tam = _bytes(_pega(r, "size", "tamanho"))
        livre = _bytes(_pega(r, "free space", "espaco livre"))
        if not letra or not tam:
            continue
        if desc and not any(x in desc for x in ("fixed", "fixo", "local")):
            continue
        unidades.append({"letra": letra, "bytes": tam, "livre": livre,
                         "sistema_arquivos": _pega(r, "file system", "sistema de arquivos"),
                         "uso": round(100 * (1 - (livre or 0) / tam)) if tam else None})

    # rede
    rede = []
    ignorar = re.compile(r"virtual|hyper-v|vpn|bluetooth|wan miniport|loopback|tap-|vmware|virtualbox|"
                         r"teredo|isatap|kernel debug|ras async|fortinet|wireguard|npcap", re.I)
    for r in _registros(_achar(cats, "adaptador", "adapter"), ["name", "nome"]):
        nome = _pega(r, "product type", "tipo de produto") or re.sub(r"^\[\d+\]\s*", "", _pega(r, "name", "nome") or "")
        mac = _pega(r, "mac address", "endereco mac")
        ips = _pega(r, "ip address", "endereco ip") or ""
        ipv4 = [i.strip() for i in ips.split(",") if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", i.strip())]
        if not nome or not mac or ignorar.search(nome):
            continue
        rede.append({"nome": nome, "mac": mac.upper(), "ip": ", ".join(ipv4) or None})

    # vídeo
    video = []
    for r in _registros(_achar(cats, "video", "display", "exibicao", "exibir", "monitor"), ["name", "nome"]):
        nome = _pega(r, "name", "nome")
        if not nome or re.search(r"basic display|remote|mirror|dameware|indirect", nome, re.I):
            continue
        video.append({"nome": nome, "resolucao": _pega(r, "resolution", "resolucao"),
                      "memoria": _pega(r, "adapter ram", "ram do adaptador")})

    placa = " ".join(x for x in [_campo(res, "baseboard manufacturer", ("fabricante", "placa")),
                                  _campo(res, "baseboard product", ("produto", "placa"))] if x) or None
    hostname = _campo(res, "system name", "nome do sistema")

    hw = {
        "hostname": hostname,
        "fabricante": fabricante,
        "marca": marca(fabricante or "") or marca(_campo(res, "baseboard manufacturer", ("fabricante", "placa")) or ""),
        "modelo": None if _norm(modelo or "") in GENERICOS else modelo,
        "tipo": _plataforma_tipo(plataforma, os_nome, modelo),
        "plataforma": plataforma,
        "sistema_operacional": (os_nome or "").replace("Microsoft ", "") or None,
        "versao_so": _campo(res, "version", "versao"),
        "arquitetura": _campo(res, "system type", "tipo do sistema", "tipo de sistema"),
        "processador": proc_nome,
        "nucleos": nucleos or None,
        "threads": threads or None,
        "frequencia": freq,
        "memoria_gb": round(memoria, 1) if memoria else None,
        "discos": discos,
        "unidades": unidades,
        "rede": rede,
        "video": video,
        "placa_mae": placa,
        "bios": _campo(res, "bios version/date", "versao/data do bios", "versao/data da bios", ("bios", "data")),
        "bios_modo": _campo(res, "bios mode", "modo da bios", "modo do bios", ("modo", "bios")),
        "secure_boot": _campo(res, "secure boot state", "estado de inicializacao segura", ("inicializacao segura",)),
        "usuario_logado": _campo(res, "user name", "nome de usuario", "nome do usuario"),
    }
    hw["armazenamento"] = resumo_armazenamento(discos)
    if not any([hw["processador"], hw["memoria_gb"], hw["sistema_operacional"], hostname]):
        raise ErroMsinfo("O arquivo não tem os dados de hardware esperados do msinfo32.")
    return hw


def resumo_armazenamento(discos) -> str | None:
    partes = [f"{d.get('tipo') + ' ' if d.get('tipo') else ''}{d.get('capacidade') or capacidade(d.get('bytes'))}".strip()
              for d in discos or [] if d.get("bytes")]
    return " + ".join(partes) or None


def memoria_txt(gb) -> str:
    if not gb:
        return "—"
    return (f"{gb:.0f}" if float(gb).is_integer() or gb >= 10 else f"{gb:.1f}").replace(".", ",") + " GB"


def resumo_curto(hw: dict | None) -> str:
    if not hw:
        return ""
    partes = [processador_curto(hw.get("processador") or ""),
              memoria_txt(hw.get("memoria_gb")) if hw.get("memoria_gb") else "",
              hw.get("armazenamento") or ""]
    return " · ".join(p for p in partes if p)


def arredonda_gb(x):
    return None if x is None else math.floor(x * 10 + 0.5) / 10
