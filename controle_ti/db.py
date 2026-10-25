import sqlite3
from datetime import datetime

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS config (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS unidades (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL UNIQUE COLLATE NOCASE,
    ativa INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY,
    usuario TEXT NOT NULL UNIQUE COLLATE NOCASE,
    nome TEXT NOT NULL,
    senha_hash TEXT NOT NULL,
    perfil TEXT NOT NULL CHECK (perfil IN ('admin', 'tecnico', 'consulta')),
    acesso_cofre INTEGER NOT NULL DEFAULT 0,
    todas_unidades INTEGER NOT NULL DEFAULT 0,
    ativo INTEGER NOT NULL DEFAULT 1,
    trocar_senha INTEGER NOT NULL DEFAULT 0,
    kek_salt TEXT,
    dek_envolvida TEXT,
    criado_em TEXT NOT NULL,
    ultimo_login TEXT
);

CREATE TABLE IF NOT EXISTS usuario_unidades (
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    unidade_id INTEGER NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    PRIMARY KEY (usuario_id, unidade_id)
);

CREATE TABLE IF NOT EXISTS equipamentos (
    id INTEGER PRIMARY KEY,
    unidade_id INTEGER NOT NULL REFERENCES unidades(id),
    tipo TEXT NOT NULL,
    marca TEXT,
    modelo TEXT,
    numero_serie TEXT,
    patrimonio TEXT,
    hostname TEXT,
    responsavel TEXT,
    setor TEXT,
    status TEXT NOT NULL,
    especificacoes TEXT,
    data_compra TEXT,
    garantia_ate TEXT,
    fornecedor TEXT,
    nota_fiscal TEXT,
    observacoes TEXT,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_equip_unidade ON equipamentos(unidade_id);

CREATE TABLE IF NOT EXISTS hardware (
    equipamento_id INTEGER PRIMARY KEY REFERENCES equipamentos(id) ON DELETE CASCADE,
    sistema_operacional TEXT,
    versao_so TEXT,
    arquitetura TEXT,
    processador TEXT,
    nucleos INTEGER,
    threads INTEGER,
    frequencia TEXT,
    memoria_gb REAL,
    armazenamento TEXT,
    discos TEXT,
    unidades TEXT,
    rede TEXT,
    video TEXT,
    placa_mae TEXT,
    bios TEXT,
    bios_modo TEXT,
    secure_boot TEXT,
    usuario_logado TEXT,
    origem TEXT,
    atualizado_em TEXT NOT NULL,
    atualizado_por TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS movimentacoes (
    id INTEGER PRIMARY KEY,
    equipamento_id INTEGER NOT NULL REFERENCES equipamentos(id) ON DELETE CASCADE,
    data TEXT NOT NULL,
    usuario TEXT NOT NULL,
    descricao TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS credenciais_pc (
    id INTEGER PRIMARY KEY,
    equipamento_id INTEGER NOT NULL REFERENCES equipamentos(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL,
    usuario TEXT,
    senha_enc TEXT NOT NULL,
    observacoes TEXT,
    atualizado_em TEXT NOT NULL,
    atualizado_por TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cofre (
    id INTEGER PRIMARY KEY,
    unidade_id INTEGER REFERENCES unidades(id),
    categoria TEXT,
    sistema TEXT NOT NULL,
    url TEXT,
    usuario TEXT,
    senha_enc TEXT NOT NULL,
    notas_enc TEXT,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    atualizado_por TEXT NOT NULL,
    senha_alterada_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auditoria (
    id INTEGER PRIMARY KEY,
    data TEXT NOT NULL,
    usuario TEXT,
    acao TEXT NOT NULL,
    detalhe TEXT,
    ip TEXT
);
CREATE INDEX IF NOT EXISTS ix_auditoria_data ON auditoria(data);
"""


def agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def conectar(caminho: str) -> sqlite3.Connection:
    con = sqlite3.connect(caminho, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = conectar(current_app.config["DB_PATH"])
    return g.db


def fechar_db(_exc=None):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def inicializar(caminho: str):
    con = conectar(caminho)
    con.execute("PRAGMA journal_mode = WAL")
    con.executescript(SCHEMA)
    con.commit()
    con.close()


def config_get(chave, padrao=None):
    r = get_db().execute("SELECT valor FROM config WHERE chave = ?", (chave,)).fetchone()
    return r["valor"] if r else padrao


def config_set(chave, valor):
    get_db().execute(
        "INSERT INTO config (chave, valor) VALUES (?, ?) "
        "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
        (chave, valor),
    )


def existe_usuario() -> bool:
    return get_db().execute("SELECT 1 FROM usuarios LIMIT 1").fetchone() is not None
