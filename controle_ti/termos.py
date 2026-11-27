"""Regras do módulo de Termos de Responsabilidade.

O termo é guardado como JSON ("dados") no mesmo formato usado pelo sistema antigo
de termos, para que os termos importados e os novos sejam tratados igual:

    {"tipo": "equipamentos|acessos|completo", "nome", "cpf", "rg", "endereco", "email",
     "cargo", "setor", "unidade", "local", "data", "recNome", "recCargo", "obs",
     "itens":   [{"item", "serie", "qtd", "estado", "obs", "equipamento_id"?}],
     "acessos": [{"sistema", "usuario", "detalhe", "cofre_id"?, "senha_enc"?}],
     "empresaSnapshot": {...}}

Senhas de acessos são gravadas cifradas (AES-256-GCM com a chave do cofre),
nunca em texto puro.
"""
import json
import re
import sqlite3
from datetime import datetime, timezone

from . import cripto, db, msinfo

TIPOS = {"equipamentos": "Equipamentos", "acessos": "Acessos",
         "completo": "Equipamentos + Acessos"}
STATUS = {"ativo": "Ativo", "devolvido": "Devolvido", "cancelado": "Cancelado"}
ESTADOS = ["Novo", "Bom", "Usado", "Regular", "Danificado"]
CONTEXTO_SENHA = "termo-senha"

EMPRESA_PADRAO = {
    "empresa": "VALORIZAÇÃO ASSESSORIA CONTÁBIL LTDA",
    "cnpj": "37.864.788/0001-94",
    "empEndereco": "Avenida Pastor Martin Luther King Jr., 126, Bl 9, sala 1315, torre 1, "
                   "Del Castilho, CEP: 20.765-000, Rio de Janeiro - RJ",
    "empContato": "",
    "local": "Rio de Janeiro - RJ",
    "logo": None,
    "dominioEmail": "valorizacao.com",
}
CHAVE_EMPRESA = "termos_empresa"


# ------------------------------------------------------------------ empresa ---
def empresa() -> dict:
    bruto = db.config_get(CHAVE_EMPRESA)
    try:
        salvo = json.loads(bruto) if bruto else {}
    except ValueError:
        salvo = {}
    return {k: salvo.get(k, v) for k, v in EMPRESA_PADRAO.items()}


def salvar_empresa(dados: dict):
    atual = empresa()
    atual.update({k: v for k, v in dados.items() if k in EMPRESA_PADRAO})
    db.config_set(CHAVE_EMPRESA, json.dumps(atual, ensure_ascii=False))


def snapshot_empresa() -> dict:
    e = empresa()
    return {k: e[k] for k in ("empresa", "cnpj", "empEndereco", "empContato")}


# ------------------------------------------------------------------- número ---
def proximo_numero(con: sqlite3.Connection, ano: int | None = None) -> str:
    ano = ano or datetime.now().year
    maior = 0
    for (numero,) in con.execute("SELECT numero FROM termos WHERE numero LIKE ?", (f"TR-{ano}-%",)):
        try:
            maior = max(maior, int(numero.rsplit("-", 1)[-1]))
        except ValueError:
            pass
    return f"TR-{ano}-{maior + 1:04d}"


# ---------------------------------------------------- equipamentos do estoque ---
def descricao_equipamento(e, hw=None) -> tuple[str, str]:
    """(item, patrimônio/série) a partir do cadastro do estoque e da configuração do msinfo32."""
    nome = " ".join(x for x in (e["tipo"], e["marca"], e["modelo"]) if x)
    if hw:
        resumo = msinfo.resumo_curto({k: hw.get(k) for k in ("processador", "memoria_gb", "armazenamento")})
        if resumo:
            nome += f" ({resumo})"
    ident = []
    if e["patrimonio"]:
        ident.append(f"Patrimônio {e['patrimonio']}")
    if e["numero_serie"]:
        ident.append(f"S/N {e['numero_serie']}")
    if e["hostname"]:
        ident.append(e["hostname"])
    return nome, " · ".join(ident)


def _norm(s) -> str:
    return re.sub(r"[^0-9A-Z]", "", (s or "").upper())


def achar_equipamento_por_serie(con, texto: str):
    """Liga um item de termo antigo a um equipamento do estoque pelo patrimônio ou nº de série."""
    partes = [p for p in re.split(r"[/,;·|]| - ", texto or "") if p.strip()] + [texto or ""]
    chaves = {_norm(p) for p in partes}
    chaves |= {_norm(re.sub(r"^\s*(PT|PATRIM[ÔO]NIO|S/?N|SERIE|SÉRIE)[:\s]*", "", p, flags=re.I))
               for p in partes}
    chaves = {c for c in chaves if len(c) >= 3}
    if not chaves:
        return None
    for e in con.execute("SELECT id, patrimonio, numero_serie FROM equipamentos"):
        if _norm(e["patrimonio"]) in chaves or _norm(e["numero_serie"]) in chaves:
            return e["id"]
    return None


def ids_equipamentos(dados: dict) -> list[int]:
    if dados.get("tipo") == "acessos":
        return []
    out = []
    for it in dados.get("itens") or []:
        try:
            eid = int(it.get("equipamento_id") or 0)
        except (TypeError, ValueError):
            eid = 0
        if eid and eid not in out:
            out.append(eid)
    return out


def gravar_vinculos(con, termo_id: int, dados: dict):
    con.execute("DELETE FROM termo_equipamentos WHERE termo_id = ?", (termo_id,))
    for eid in ids_equipamentos(dados):
        if con.execute("SELECT 1 FROM equipamentos WHERE id = ?", (eid,)).fetchone():
            con.execute("INSERT OR IGNORE INTO termo_equipamentos VALUES (?, ?)", (termo_id, eid))


# ---------------------------------------------------------------- senhas ---
def cifrar_senha(dek: bytes, senha: str) -> str:
    return cripto.cifrar(dek, senha, CONTEXTO_SENHA)


def abrir_senhas(dek: bytes | None, acessos: list[dict]) -> list[dict]:
    """Cópia dos acessos com o campo 'senha' em claro (só para exibir/imprimir)."""
    out = []
    for a in acessos or []:
        a = dict(a)
        enc = a.pop("senha_enc", None)
        a["senha"] = ""
        a["tem_senha"] = bool(enc)
        if enc and dek:
            try:
                a["senha"] = cripto.decifrar(dek, enc, CONTEXTO_SENHA)
            except cripto.ErroCripto:
                a["senha"] = ""
        out.append(a)
    return out


def para_documento(dados: dict, dek: bytes | None = None) -> dict:
    """Dados prontos para a folha: linhas vazias fora e senhas abertas (se dek for dada)."""
    doc = dict(dados)
    doc["itens"] = [i for i in dados.get("itens") or [] if i.get("item") or i.get("serie") or i.get("obs")]
    doc["acessos"] = [a for a in abrir_senhas(dek, dados.get("acessos")) if a.get("sistema") or a.get("usuario")]
    return doc


def tem_senhas(dados: dict) -> bool:
    return any(a.get("senha_enc") for a in dados.get("acessos") or [])


def historico(con, termo_id: int, usuario: str | None, acao: str, detalhe: str = ""):
    con.execute("INSERT INTO termo_historico (termo_id, data, usuario, acao, detalhe) "
                "VALUES (?, ?, ?, ?, ?)", (termo_id, db.agora(), usuario, acao, detalhe))


# --------------------------------------------------------------- importação ---
class ErroImportacao(Exception):
    pass


def _data_local(iso: str | None) -> str | None:
    """'2026-03-01T13:00:00+00:00' (UTC, sistema antigo) -> '2026-03-01 10:00:00' (hora local)."""
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def importar_banco_termos(con: sqlite3.Connection, origem: str, mapa_unidades: dict | None = None,
                          importar_empresa: bool = True) -> dict:
    """Copia os termos do banco do sistema antigo (termos.db) para o banco do Controle TI.

    - O arquivo de origem é aberto só para leitura: nada é alterado nele.
    - Termos cujo número já existe no Controle TI são ignorados (pode rodar de novo sem duplicar).
    - Unidades são ligadas pelo nome (sem diferenciar maiúsculas) ou pelo mapa informado.
    - Itens cujo patrimônio/nº de série bate com um equipamento do estoque ficam vinculados a ele.
    """
    try:
        src = sqlite3.connect(f"file:{origem}?mode=ro", uri=True)
        src.row_factory = sqlite3.Row
        tabelas = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.DatabaseError as e:
        raise ErroImportacao(f"Não foi possível abrir {origem}: {e}") from e
    if not {"termos", "historico", "users"} <= tabelas:
        src.close()
        raise ErroImportacao("O arquivo não é um banco do sistema de Termos de Responsabilidade.")

    mapa = {k.strip().lower(): v.strip() for k, v in (mapa_unidades or {}).items()}
    unidades = {r["nome"].lower(): r["id"] for r in con.execute("SELECT id, nome FROM unidades")}
    usuarios = {r["id"]: r["nome"] for r in src.execute("SELECT id, nome FROM users")}
    cols = {c[1] for c in src.execute("PRAGMA table_info(termos)")}
    res = {"importados": 0, "ja_existiam": 0, "historico": 0, "itens_vinculados": 0,
           "unidades_sem_correspondencia": set(), "empresa": False, "unidades_religadas": 0}

    for t in src.execute("SELECT * FROM termos ORDER BY id"):
        existente = con.execute("SELECT id, unidade_id, unidade_nome, origem FROM termos WHERE numero = ?",
                                (t["numero"],)).fetchone()
        if existente:
            res["ja_existiam"] += 1
            # nova execução com --mapa: liga a unidade de termos importados que ficaram sem
            if existente["origem"] == "importado" and existente["unidade_id"] is None and existente["unidade_nome"]:
                nome = existente["unidade_nome"]
                alvo = mapa.get(nome.lower(), nome)
                un_id = unidades.get(alvo.lower())
                if un_id:
                    con.execute("UPDATE termos SET unidade_id = ?, unidade_nome = ? WHERE id = ?",
                                (un_id, alvo, existente["id"]))
                    res["unidades_religadas"] += 1
                else:
                    res["unidades_sem_correspondencia"].add(nome)
            continue
        try:
            dados = json.loads(t["dados"] or "{}")
        except ValueError:
            dados = {}
        tipo = (t["tipo"] if "tipo" in cols else None) or dados.get("tipo") or \
            ("completo" if dados.get("incluirAcessos") else "equipamentos")
        if tipo not in TIPOS:
            tipo = "equipamentos"
        dados["tipo"] = tipo
        dados.pop("incluirAcessos", None)
        dados.pop("logo", None)
        # o sistema antigo nunca gravava senhas; garante que nada passe em claro
        dados["acessos"] = [{k: v for k, v in (a or {}).items() if k != "senha"}
                            for a in dados.get("acessos") or []]
        vinc = 0
        for it in dados.get("itens") or []:
            eid = achar_equipamento_por_serie(con, it.get("serie")) if it.get("serie") else None
            if eid:
                it["equipamento_id"] = eid
                vinc += 1
        res["itens_vinculados"] += vinc

        un_nome = (t["unidade"] if "unidade" in cols else "") or dados.get("unidade") or ""
        alvo = mapa.get(un_nome.lower(), un_nome)
        un_id = unidades.get(alvo.lower()) if alvo else None
        if un_nome and not un_id:
            res["unidades_sem_correspondencia"].add(un_nome)

        criado_por = usuarios.get(t["criado_por"])
        cur = con.execute(
            "INSERT INTO termos (numero, tipo, status, colaborador, cpf, unidade_id, unidade_nome, "
            "dados, criado_por, criado_em, atualizado_por, atualizado_em, devolvido_em, origem) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'importado')",
            (t["numero"], tipo, t["status"], t["colaborador"] or dados.get("nome", ""),
             t["cpf"] or dados.get("cpf", ""), un_id, alvo or un_nome,
             json.dumps(dados, ensure_ascii=False), criado_por, _data_local(t["criado_em"]),
             usuarios.get(t["atualizado_por"]), _data_local(t["atualizado_em"]),
             _data_local(t["devolvido_em"])))
        tid = cur.lastrowid
        gravar_vinculos(con, tid, dados)
        for h in src.execute("SELECT * FROM historico WHERE termo_id = ? ORDER BY id", (t["id"],)):
            con.execute("INSERT INTO termo_historico (termo_id, data, usuario, acao, detalhe) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (tid, _data_local(h["quando"]), usuarios.get(h["user_id"]), h["acao"], h["detalhe"]))
            res["historico"] += 1
        historico(con, tid, "Importação", "importado do sistema de termos",
                  f"{vinc} item(ns) vinculado(s) ao estoque" if vinc else "")
        res["importados"] += 1

    if importar_empresa and "config" in tabelas and not db_config_existe(con, CHAVE_EMPRESA):
        r = src.execute("SELECT valor FROM config WHERE chave = 'empresa'").fetchone()
        if r:
            try:
                antigo = json.loads(r["valor"])
            except ValueError:
                antigo = {}
            novo = {k: antigo.get(k, v) for k, v in EMPRESA_PADRAO.items()}
            con.execute("INSERT INTO config (chave, valor) VALUES (?, ?)",
                        (CHAVE_EMPRESA, json.dumps(novo, ensure_ascii=False)))
            res["empresa"] = True
    src.close()
    con.commit()
    res["unidades_sem_correspondencia"] = sorted(res["unidades_sem_correspondencia"])
    return res


def db_config_existe(con, chave) -> bool:
    return con.execute("SELECT 1 FROM config WHERE chave = ?", (chave,)).fetchone() is not None
