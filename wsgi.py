"""Ponto de entrada WSGI (PythonAnywhere e outros servidores WSGI).

No PythonAnywhere, o arquivo WSGI da aba "Web" pode ficar assim:

    import os, sys
    os.environ["CONTROLE_TI_DADOS"] = "/home/SEU_USUARIO/controle-ti-dados"  # fora da pasta do código
    os.environ["SQLITE_JOURNAL"] = "DELETE"   # WAL não é seguro no disco de rede do PythonAnywhere
    sys.path.insert(0, "/home/SEU_USUARIO/controle-ti")
    from wsgi import application  # noqa

Localmente (Windows) continue usando iniciar.bat / run.py.
"""
from controle_ti import create_app

application = create_app()
app = application
