"""Inicia o Controle TI na rede local.

    python run.py

Na primeira execução cria a pasta "dados" com o banco, o config.ini e um
certificado HTTPS autoassinado (o navegador vai pedir para aceitar uma vez).
"""
import ipaddress
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cheroot import wsgi
from cheroot.ssl.builtin import BuiltinSSLAdapter

from controle_ti import backup, create_app, ler_config


def ips_locais():
    ips = {"127.0.0.1"}
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    return sorted(ips)


def garantir_certificado(pasta: Path):
    cert, chave = pasta / "certificado.pem", pasta / "chave_privada.pem"
    if cert.exists() and chave.exists():
        return cert, chave
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    host = socket.gethostname()
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"Controle TI - {host}"),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Valorização")])
    sans = [x509.DNSName(host), x509.DNSName("localhost")]
    sans += [x509.IPAddress(ipaddress.ip_address(ip)) for ip in ips_locais()]
    agora = datetime.now(timezone.utc)
    c = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome)
         .public_key(k.public_key()).serial_number(x509.random_serial_number())
         .not_valid_before(agora - timedelta(days=1))
         .not_valid_after(agora + timedelta(days=3650))
         .add_extension(x509.SubjectAlternativeName(sans), critical=False)
         .sign(k, hashes.SHA256()))
    chave.write_bytes(k.private_bytes(serialization.Encoding.PEM,
                                      serialization.PrivateFormat.TraditionalOpenSSL,
                                      serialization.NoEncryption()))
    cert.write_bytes(c.public_bytes(serialization.Encoding.PEM))
    return cert, chave


def backup_diario(app):
    pasta = Path(app.config["PASTA_DADOS"]) / "backups"
    while True:
        try:
            arq = backup.fazer_backup(app.config["DB_PATH"], str(pasta),
                                      app.config["BACKUP_MANTER"])
            print(f"[backup] {arq.name}")
        except Exception as e:  # noqa: BLE001
            print(f"[backup] falhou: {e}")
        time.sleep(24 * 3600)


def main():
    app = create_app()
    pasta = Path(app.config["PASTA_DADOS"])
    cfg = ler_config(pasta)
    host, porta = cfg.get("host"), int(cfg.get("porta"))
    https = app.config["SESSION_COOKIE_SECURE"]

    threading.Thread(target=backup_diario, args=(app,), daemon=True).start()

    servidor = wsgi.Server((host, porta), app, numthreads=8, server_name="ControleTI")
    if https:
        cert, chave = garantir_certificado(pasta)
        servidor.ssl_adapter = BuiltinSSLAdapter(str(cert), str(chave))

    esquema = "https" if https else "http"
    print("=" * 60)
    print(" Controle TI — Valorização")
    print(f" Dados em: {pasta}")
    print(" Acesse em:")
    for ip in ips_locais():
        print(f"   {esquema}://{ip}:{porta}")
    print(" Ctrl+C para encerrar")
    print("=" * 60)
    try:
        servidor.start()
    except KeyboardInterrupt:
        servidor.stop()


if __name__ == "__main__":
    main()
