"""Gravação e leitura da configuração de hardware de cada equipamento."""
import json

from . import db
from .msinfo import memoria_txt, resumo_armazenamento

CAMPOS = ["sistema_operacional", "versao_so", "arquitetura", "processador", "nucleos", "threads",
          "frequencia", "memoria_gb", "armazenamento", "discos", "unidades", "rede", "video",
          "placa_mae", "bios", "bios_modo", "secure_boot", "usuario_logado", "origem"]
LISTAS = {"discos", "unidades", "rede", "video"}
# campos que a pessoa pode editar no formulário
EDITAVEIS = ["processador", "memoria_gb", "armazenamento", "sistema_operacional"]
LIMITES = {"discos": 12, "unidades": 26, "rede": 10, "video": 6}


def _str(v, lim=300):
    return None if v in (None, "") else str(v)[:lim]


def _num(v, inteiro=False):
    try:
        n = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None
    if n < 0 or n > 1e15:
        return None
    return int(n) if inteiro else n


def limpar(hw: dict | None) -> dict:
    """Normaliza e limita o que vem do formulário (JSON oculto) ou do msinfo32."""
    hw = hw if isinstance(hw, dict) else {}
    out = {}
    for c in CAMPOS:
        v = hw.get(c)
        if c in LISTAS:
            itens = []
            for item in (v if isinstance(v, list) else [])[:LIMITES[c]]:
                if isinstance(item, dict):
                    itens.append({str(k)[:30]: (x if isinstance(x, (int, float)) and not isinstance(x, bool) else _str(x, 200))
                                  for k, x in list(item.items())[:12]})
            out[c] = itens
        elif c in ("nucleos", "threads"):
            out[c] = _num(v, inteiro=True)
        elif c == "memoria_gb":
            n = _num(v)
            out[c] = round(n, 1) if n else None
        else:
            out[c] = _str(v)
    if not out.get("armazenamento"):
        out["armazenamento"] = resumo_armazenamento(out.get("discos"))
    return out


def tem_dados(hw: dict | None) -> bool:
    return bool(hw) and any(hw.get(c) for c in CAMPOS if c != "origem")


def carregar(eid: int) -> dict | None:
    row = db.get_db().execute("SELECT * FROM hardware WHERE equipamento_id = ?", (eid,)).fetchone()
    if not row:
        return None
    hw = dict(row)
    for c in LISTAS:
        try:
            hw[c] = json.loads(hw[c]) if hw[c] else []
        except ValueError:
            hw[c] = []
    return hw


def diferencas(antes: dict | None, depois: dict) -> list[str]:
    if not antes:
        return []
    rot = {"processador": "Processador", "memoria_gb": "Memória", "armazenamento": "Armazenamento",
           "sistema_operacional": "Sistema operacional"}
    mud = []
    for c, r in rot.items():
        a, d = antes.get(c), depois.get(c)
        if c == "memoria_gb":
            a, d = (memoria_txt(a) if a else None), (memoria_txt(d) if d else None)
        if (a or "") != (d or "") and d:
            mud.append(f"{r}: “{a or '—'}” → “{d}”")
    return mud


def salvar(con, eid: int, hw: dict, usuario: str, origem: str | None = None) -> list[str]:
    """Grava (insere ou substitui) e devolve a lista de mudanças relevantes."""
    hw = limpar(hw)
    if origem:
        hw["origem"] = origem
    antes = carregar(eid)
    if not tem_dados(hw):
        if antes:
            con.execute("DELETE FROM hardware WHERE equipamento_id = ?", (eid,))
        return []
    valores = [json.dumps(hw[c], ensure_ascii=False) if c in LISTAS else hw[c] for c in CAMPOS]
    con.execute(
        f"INSERT INTO hardware (equipamento_id, {', '.join(CAMPOS)}, atualizado_em, atualizado_por) "
        f"VALUES (?, {', '.join('?' * len(CAMPOS))}, ?, ?) "
        f"ON CONFLICT(equipamento_id) DO UPDATE SET "
        + ", ".join(f"{c} = excluded.{c}" for c in CAMPOS + ["atualizado_em", "atualizado_por"]),
        [eid] + valores + [db.agora(), usuario])
    return diferencas(antes, hw)
