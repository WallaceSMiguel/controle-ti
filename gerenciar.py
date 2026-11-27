r"""Ferramentas de manutenção pelo terminal.

    python gerenciar.py recuperar   -> redefine a senha de um administrador usando o
                                       CÓDIGO DE RECUPERAÇÃO gerado na instalação
    python gerenciar.py backup      -> cria um backup agora
    python gerenciar.py restaurar   -> volta o sistema para um backup (lista as cópias)
    python gerenciar.py restaurar caminho\do\arquivo.db
    python gerenciar.py importar-termos caminho/termos.db [--mapa "Duque de Caxias=Caxias"] [--simular]
                                    -> traz os termos do sistema antigo de Termos de
                                       Responsabilidade (o arquivo de origem não é alterado)
"""
import getpass
import sys

from werkzeug.security import generate_password_hash

from controle_ti import backup, create_app, cripto, db, termos


def recuperar(app):
    with app.app_context():
        con = db.get_db()
        salt = db.config_get("recuperacao_salt")
        env = db.config_get("recuperacao_dek")
        if not salt:
            print("Sistema ainda não instalado.")
            return 1
        codigo = cripto.normalizar_codigo(input("Código de recuperação: "))
        try:
            dek = cripto.abrir_dek(salt, env, codigo)
        except cripto.ErroCripto:
            print("Código de recuperação inválido.")
            return 1
        usuario = input("Usuário administrador a recuperar (ou novo usuário): ").strip()
        senha = getpass.getpass("Nova senha (mín. 8): ")
        if len(senha) < 8 or senha != getpass.getpass("Confirme: "):
            print("Senha inválida ou não confere.")
            return 1
        s, e = cripto.envolver_dek(dek, senha)
        row = con.execute("SELECT id FROM usuarios WHERE usuario = ?", (usuario,)).fetchone()
        if row:
            con.execute("UPDATE usuarios SET senha_hash = ?, kek_salt = ?, dek_envolvida = ?, "
                        "perfil = 'admin', ativo = 1, todas_unidades = 1, acesso_cofre = 1, "
                        "trocar_senha = 0 WHERE id = ?",
                        (generate_password_hash(senha), s, e, row["id"]))
        else:
            con.execute("INSERT INTO usuarios (usuario, nome, senha_hash, perfil, acesso_cofre, "
                        "todas_unidades, kek_salt, dek_envolvida, criado_em) "
                        "VALUES (?, ?, ?, 'admin', 1, 1, ?, ?, ?)",
                        (usuario, usuario, generate_password_hash(senha), s, e, db.agora()))
        con.execute("INSERT INTO auditoria (data, usuario, acao, detalhe, ip) "
                    "VALUES (?, ?, 'recuperacao_acesso', 'Via código de recuperação', 'terminal')",
                    (db.agora(), usuario))
        con.commit()
        print(f"Acesso de administrador recuperado para '{usuario}'.")
        print("Reinicie o servidor se ele estiver em execução.")
        return 0


def restaurar(app, arquivo=None):
    from datetime import datetime
    from pathlib import Path
    pasta = Path(app.config["PASTA_DADOS"]) / "backups"
    if arquivo:
        escolhido = Path(arquivo)
    else:
        copias = sorted(pasta.glob("controle_ti_*.db"), reverse=True)[:20] if pasta.exists() else []
        if not copias:
            print(f"Nenhum backup em {pasta}")
            return 1
        print("Backups disponíveis (mais recentes primeiro):\n")
        for i, c in enumerate(copias, 1):
            try:
                info = backup.inspecionar(c)
                resumo = f"{info['equipamentos']} equip., {info['cofre']} senhas, {info['usuarios']} usuários"
            except backup.ErroBackup as e:
                resumo = f"INVÁLIDO: {e}"
            data = datetime.fromtimestamp(c.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
            print(f"  {i:2}. {data}  {c.name}  ({resumo})")
        op = input("\nNúmero do backup a restaurar (Enter cancela): ").strip()
        if not op.isdigit() or not 1 <= int(op) <= len(copias):
            print("Cancelado.")
            return 1
        escolhido = copias[int(op) - 1]
    try:
        info = backup.inspecionar(escolhido)
    except backup.ErroBackup as e:
        print(f"Não é possível restaurar: {e}")
        return 1
    print(f"\nVai restaurar {escolhido.name}: {info['equipamentos']} equipamentos, "
          f"{info['cofre']} senhas no cofre, {info['usuarios']} usuários.")
    print("Tudo o que foi feito depois desse backup será desfeito (o estado atual fica guardado).")
    if input("Digite RESTAURAR para confirmar: ").strip().upper() != "RESTAURAR":
        print("Cancelado.")
        return 1
    antes, _ = backup.restaurar(app.config["DB_PATH"], escolhido, str(pasta))
    db.inicializar(app.config["DB_PATH"])
    with app.app_context():
        con = db.get_db()
        con.execute("INSERT INTO auditoria (data, usuario, acao, detalhe, ip) VALUES (?, NULL, 'backup_restaurado', ?, 'terminal')",
                    (db.agora(), f"{escolhido.name} restaurado pelo terminal. Estado anterior em {antes.name}"))
        con.commit()
    print(f"\nRestaurado. O estado anterior foi guardado em {antes.name}.")
    print("Se o servidor estiver aberto, reinicie-o para que todos entrem de novo.")
    return 0


def importar_termos(app, args):
    import shutil
    import tempfile
    from pathlib import Path
    if not args:
        print("Informe o caminho do termos.db. Ex.: python gerenciar.py importar-termos ~/dados-termos/termos.db")
        return 1
    origem = Path(args[0]).expanduser()
    if not origem.is_file():
        print(f"Arquivo não encontrado: {origem}")
        return 1
    mapa, simular = {}, "--simular" in args
    for i, a in enumerate(args):
        if a == "--mapa" and i + 1 < len(args):
            for par in args[i + 1].split(","):
                if "=" in par:
                    de, para = par.split("=", 1)
                    mapa[de.strip()] = para.strip()
    destino = app.config["DB_PATH"]
    if simular:
        # roda numa cópia do banco para mostrar o resultado sem gravar nada
        tmp = Path(tempfile.mkdtemp()) / "simulacao.db"
        shutil.copy(destino, tmp)
        destino = str(tmp)
    else:
        arq = backup.fazer_backup(destino, str(Path(app.config["PASTA_DADOS"]) / "backups"),
                                  manter=0, sufixo="antes_importacao_termos")
        print(f"Backup do estado atual: {arq}")
    con = db.conectar(destino)
    try:
        res = termos.importar_banco_termos(con, str(origem), mapa)
        if not simular:
            con.execute("INSERT INTO auditoria (data, usuario, acao, detalhe, ip) "
                        "VALUES (?, NULL, 'termos_importados', ?, 'terminal')",
                        (db.agora(), f"{res['importados']} termos de {origem.name}"))
            con.commit()
    except termos.ErroImportacao as e:
        print(f"Erro: {e}")
        return 1
    finally:
        con.close()
    print(("SIMULAÇÃO (nada foi gravado)\n" if simular else "") +
          f"Termos importados: {res['importados']}\n"
          f"Já existiam (ignorados): {res['ja_existiam']}\n"
          f"Registros de histórico: {res['historico']}\n"
          f"Itens ligados a equipamentos do estoque: {res['itens_vinculados']}\n"
          f"Termos antigos que agora ganharam unidade: {res['unidades_religadas']}\n"
          f"Dados da empresa/logo importados: {'sim' if res['empresa'] else 'não (já existiam)'}")
    if res["unidades_sem_correspondencia"]:
        print("\nUnidades sem correspondência no Controle TI (termos ficaram sem unidade vinculada, "
              "o nome foi mantido): " + ", ".join(res["unidades_sem_correspondencia"]))
        print('Rode de novo com --mapa "Nome antigo=Nome no Controle TI" (ou cadastre a unidade) para ligar; '
              "nada é duplicado.")
    return 0


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("recuperar", "backup", "restaurar", "importar-termos"):
        print(__doc__)
        return 1
    app = create_app()
    if sys.argv[1] == "recuperar":
        return recuperar(app)
    if sys.argv[1] == "importar-termos":
        return importar_termos(app, sys.argv[2:])
    if sys.argv[1] == "restaurar":
        return restaurar(app, sys.argv[2] if len(sys.argv) > 2 else None)
    from pathlib import Path
    arq = backup.fazer_backup(app.config["DB_PATH"],
                              str(Path(app.config["PASTA_DADOS"]) / "backups"),
                              app.config["BACKUP_MANTER"])
    print(f"Backup criado: {arq}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
