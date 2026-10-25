"""Backup e restauração do banco.

As senhas ficam cifradas dentro do banco, então o backup também fica protegido:
sem a senha de um usuário ou o código de recuperação, ninguém lê as senhas da cópia.

A restauração usa a API de backup do SQLite para copiar o arquivo escolhido
por cima do banco em uso. Funciona com o sistema rodando, e antes dela é feita
automaticamente uma cópia do estado atual ("antes_da_restauracao").
"""
import sqlite3
from datetime import datetime
from pathlib import Path

CABECALHO_SQLITE = b"SQLite format 3\x00"
TABELAS_OBRIGATORIAS = {"config", "unidades", "usuarios", "equipamentos", "cofre", "auditoria"}


class ErroBackup(Exception):
    pass


def fazer_backup(db_path: str, pasta_destino: str, manter: int = 30, sufixo: str = "") -> Path:
    destino = Path(pasta_destino)
    destino.mkdir(parents=True, exist_ok=True)
    base = f"controle_ti_{datetime.now():%Y-%m-%d_%H%M%S}"
    fim = f"_{sufixo}.db" if sufixo else ".db"
    arquivo = destino / (base + fim)
    n = 2
    while arquivo.exists():  # nunca sobrescreve uma cópia existente
        arquivo = destino / f"{base}-{n}{fim}"
        n += 1
    origem = sqlite3.connect(db_path, timeout=30)
    copia = sqlite3.connect(arquivo)
    with copia:
        origem.backup(copia)
    copia.close()
    origem.close()
    if manter > 0:
        automaticos = sorted(a for a in destino.glob("controle_ti_*.db")
                             if "antes_da_restauracao" not in a.name and "enviado" not in a.name)
        for velho in automaticos[:-manter]:
            velho.unlink(missing_ok=True)
    return arquivo


def inspecionar(caminho) -> dict:
    """Confere se o arquivo é um backup válido do Controle TI e resume o conteúdo."""
    caminho = Path(caminho)
    if not caminho.is_file():
        raise ErroBackup("Arquivo de backup não encontrado.")
    with open(caminho, "rb") as f:
        if f.read(16) != CABECALHO_SQLITE:
            raise ErroBackup("O arquivo não é um banco do Controle TI (formato inválido).")
    try:
        con = sqlite3.connect(caminho, timeout=10)
        try:
            ok = con.execute("PRAGMA quick_check").fetchone()[0]
            if ok != "ok":
                raise ErroBackup("O arquivo de backup está danificado.")
            tabelas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            faltam = TABELAS_OBRIGATORIAS - tabelas
            if faltam:
                raise ErroBackup("O arquivo não é um backup do Controle TI.")

            def conta(t):
                return con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]

            verif = con.execute("SELECT valor FROM config WHERE chave = 'verificador'").fetchone()
            ultima = con.execute("SELECT MAX(data) FROM auditoria").fetchone()[0]
            info = {
                "arquivo": caminho.name,
                "tamanho": caminho.stat().st_size,
                "equipamentos": conta("equipamentos"),
                "cofre": conta("cofre"),
                "usuarios": conta("usuarios"),
                "ultima_atividade": ultima,
                "verificador": verif[0] if verif else None,
            }
        finally:
            con.close()
    except sqlite3.DatabaseError as e:
        raise ErroBackup("O arquivo de backup não pôde ser aberto.") from e
    if not info["usuarios"]:
        raise ErroBackup("O backup não tem nenhum usuário cadastrado.")
    return info


def restaurar(db_path: str, origem, pasta_backups: str) -> tuple[Path, dict]:
    """Substitui o banco atual pelo backup. Devolve (cópia_do_estado_anterior, info_do_backup)."""
    info = inspecionar(origem)
    antes = fazer_backup(db_path, pasta_backups, manter=0, sufixo="antes_da_restauracao")
    src = sqlite3.connect(origem, timeout=30)
    dst = sqlite3.connect(db_path, timeout=30)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    return antes, info
