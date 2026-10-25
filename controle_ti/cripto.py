"""Criptografia do sistema.

Modelo de chaves:
- Existe UMA chave de dados (DEK, 256 bits) que cifra todas as senhas (AES-256-GCM).
- A DEK nunca é gravada em claro. Cada usuário com acesso a senhas guarda uma cópia
  da DEK "envolvida" (cifrada) com uma chave derivada da própria senha de login (scrypt).
- Uma cópia extra é envolvida pelo CÓDIGO DE RECUPERAÇÃO, exibido uma única vez na
  instalação, para recuperar o acesso caso todos os administradores esqueçam a senha.
- Ao fazer login, a DEK é aberta e fica só na memória do servidor durante a sessão.
"""
import base64
import hashlib
import os
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_SCRYPT = dict(n=2 ** 15, r=8, p=1, maxmem=128 * 1024 * 1024, dklen=32)


class ErroCripto(Exception):
    pass


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def derivar_chave(segredo: str, salt: bytes) -> bytes:
    return hashlib.scrypt(segredo.encode("utf-8"), salt=salt, **_SCRYPT)


def nova_dek() -> bytes:
    return AESGCM.generate_key(bit_length=256)


def cifrar_bytes(chave: bytes, dados: bytes, contexto: bytes) -> str:
    nonce = os.urandom(12)
    return _b64(nonce + AESGCM(chave).encrypt(nonce, dados, contexto))


def decifrar_bytes(chave: bytes, token: str, contexto: bytes) -> bytes:
    try:
        bruto = _unb64(token)
        return AESGCM(chave).decrypt(bruto[:12], bruto[12:], contexto)
    except (InvalidTag, ValueError, TypeError) as e:
        raise ErroCripto("Falha ao decifrar") from e


def cifrar(chave: bytes, texto: str, contexto: str) -> str:
    return cifrar_bytes(chave, (texto or "").encode("utf-8"), contexto.encode())


def decifrar(chave: bytes, token: str, contexto: str) -> str:
    if not token:
        return ""
    return decifrar_bytes(chave, token, contexto.encode()).decode("utf-8")


def envolver_dek(dek: bytes, segredo: str) -> tuple[str, str]:
    """Retorna (salt_b64, dek_envolvida_b64)."""
    salt = os.urandom(16)
    kek = derivar_chave(segredo, salt)
    return _b64(salt), cifrar_bytes(kek, dek, b"dek")


def abrir_dek(salt_b64: str, envolvida: str, segredo: str) -> bytes:
    kek = derivar_chave(segredo, _unb64(salt_b64))
    return decifrar_bytes(kek, envolvida, b"dek")


def gerar_codigo_recuperacao() -> str:
    alfabeto = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    bruto = "".join(secrets.choice(alfabeto) for _ in range(30))
    return "-".join(bruto[i:i + 5] for i in range(0, 30, 5))


def normalizar_codigo(codigo: str) -> str:
    limpo = "".join(c for c in codigo.upper() if c.isalnum())
    return "-".join(limpo[i:i + 5] for i in range(0, len(limpo), 5))
