# Controle TI — Valorização

Sistema web para a equipe de TI, com quatro módulos:

- **Equipamentos**: inventário por unidade, com histórico de movimentações, garantias e exportação para Excel.
- **Senhas dos computadores**: administrador local, BIOS, BitLocker etc., vinculadas a cada equipamento.
- **Cofre de senhas**: acessos dos sistemas (SIEG, e-CAC, prefeituras, e-mails), por unidade ou "Geral".
- **Termos de responsabilidade**: termos de equipamentos, de acessos ou completos, com numeração `TR-AAAA-NNNN`, impressão/PDF em A4, devolução e histórico. Itens vêm do estoque e acessos do cofre (antigo sistema *termoderesponsabilidade*, agora unificado aqui).

## Instalação (Windows)

1. Instale o **Python 3.10 ou superior** (python.org). Na instalação, marque **"Add python.exe to PATH"**.
2. Copie a pasta `controle_ti` para o computador que fará o papel de servidor.
3. Dê dois cliques em **`iniciar.bat`**. Na primeira vez ele prepara o ambiente, o que leva cerca de 1 minuto.
4. A janela mostra os endereços de acesso, por exemplo `https://192.168.0.10:8443`.
5. Abra o endereço no navegador. Ele vai avisar que o certificado não é confiável: clique em **Avançado → Continuar**. Isso acontece porque o certificado é gerado pelo próprio sistema. A conexão continua criptografada.
6. No primeiro acesso, crie o administrador. Em seguida vai aparecer o **código de recuperação**: imprima e guarde em local seguro.

Para os outros computadores acessarem, libere a porta **8443** no Firewall do Windows do servidor (entrada, TCP).

Para iniciar junto com o Windows: crie um atalho do `iniciar.bat` na pasta `shell:startup`, ou agende pelo Agendador de Tarefas.

## Configuração dos computadores (msinfo32)

O sistema lê o relatório do Windows **Informações do Sistema** (`msinfo32`) e preenche hostname, marca, modelo, processador, memória, discos (com espaço livre), sistema operacional, rede (MAC/IP), vídeo, placa-mãe e BIOS. Aceita `.nfo` (*Arquivo › Salvar*) e `.txt` (*Arquivo › Exportar*), em português ou inglês.

- **Um computador**: em *Cadastrar equipamento*, escolha o arquivo em "Preencher pelo msinfo32" e confira os campos antes de salvar. Na ficha de um equipamento já cadastrado, use *Atualizar pelo msinfo32*.
- **Vários de uma vez**: *Equipamentos › Importar do msinfo32*. Quem já existe (pelo hostname) tem a configuração atualizada; os demais são cadastrados na unidade escolhida.
- **Coleta automática**: copie `ferramentas\coletar_msinfo32.bat` para uma pasta compartilhada e execute em cada máquina. Ele grava `NOME-DO-PC.nfo` nessa pasta.

O número de série e o patrimônio não constam no msinfo32 e continuam sendo digitados.

O painel inicial mostra os pontos de atenção encontrados: Windows 10 ou anterior (sem suporte da Microsoft), máquinas com até 4 GB de memória, discos com 90% ou mais ocupados e computadores ainda sem configuração. Mudanças de memória, processador, disco ou sistema operacional entram automaticamente no histórico do equipamento.

## Termos de responsabilidade

- **Novo termo**: menu *Termos › Novo termo*, ou o botão **Gerar termo** na ficha de um equipamento (já vem com o equipamento, o responsável e o setor).
- **Itens do estoque**: em cada item, escolha o equipamento do estoque. A descrição sai com marca, modelo e a configuração do msinfo32 (processador, memória, disco), e o patrimônio/série/hostname. Ao salvar, o equipamento passa a ter o colaborador como responsável, fica "Em uso" e a entrega entra no histórico dele. Itens digitados à mão continuam permitidos.
- **Acessos do cofre**: em cada acesso, escolha o registro do cofre (preenche sistema, usuário e link) e defina a senha no termo: *Senha do cofre*, *Digitar senha* ou *Linha em branco*.
- **Senhas no termo**: ficam gravadas no termo **criptografadas** (AES-256-GCM, mesma chave do cofre). A tela do termo e a impressão comum mostram `••••`. O botão **Imprimir com senhas** só aparece para quem tem acesso a senhas, e cada uso fica na **Auditoria** e no histórico do termo.
- **Devolução**: em *Situação*, marque **Devolvido**. Os equipamentos ligados voltam para "Em estoque", sem responsável, e a devolução entra no histórico deles.
- **Dados da empresa e logo** (administrador): *Termos › Dados da empresa*. Termos já emitidos mantêm os dados da época.
- Quem pode: Administrador e Técnico criam e editam; Consulta só visualiza e imprime; só o Administrador exclui.

### Trazer os termos do sistema antigo

Os termos já emitidos no sistema *termoderesponsabilidade* (arquivo `termos.db`) são trazidos com o mesmo número, status, datas, itens, acessos, histórico e dados da empresa/logo:

```
python gerenciar.py importar-termos caminho/termos.db --simular      # mostra o resultado sem gravar
python gerenciar.py importar-termos caminho/termos.db --mapa "Duque de Caxias=Caxias,Nova América=Nova América"
```

- Antes de gravar, é feito um backup `..._antes_importacao_termos.db`. O `termos.db` de origem só é lido, nunca alterado.
- Pode rodar quantas vezes quiser: termos com número já existente são ignorados (rodar de novo com `--mapa` liga a unidade dos que ficaram sem).
- Unidades são ligadas pelo nome. As que não existirem no Controle TI aparecem no resumo; use `--mapa` ou cadastre a unidade.
- Itens cujo patrimônio ou nº de série bate com um equipamento do estoque ficam ligados a ele (o equipamento não é alterado).
- Os usuários do sistema antigo **não** viram usuários aqui (o login do Controle TI protege a chave do cofre). Os nomes deles continuam no histórico de cada termo.
- O envio do termo por e-mail (Gmail/SMTP) do sistema antigo ainda não foi trazido.

## Perfis

| Perfil        | Estoque            | Editar estoque | Senhas dos PCs | Cofre         | Administração |
|---------------|--------------------|----------------|----------------|---------------|---------------|
| Administrador | Todas as unidades  | Sim            | Sim            | Sim           | Sim           |
| Técnico       | Unidades liberadas | Sim            | Sim            | Se liberado   | Não           |
| Consulta      | Unidades liberadas | Não            | Não            | Se liberado   | Não           |

Registros do cofre marcados como "Geral" aparecem para todos que têm acesso ao cofre.

## Segurança

- Senhas e notas do cofre são gravadas com **AES-256-GCM**. Nada fica em texto puro no banco.
- A chave de criptografia é protegida pela senha de cada usuário (scrypt). Por isso, ao criar um técnico ou redefinir a senha dele, o administrador define uma **senha temporária**, que o usuário troca no primeiro acesso.
- Cada vez que alguém vê ou copia uma senha, a ação fica registrada em **Auditoria**, com usuário, data e IP.
- A senha revelada some sozinha após 20 s. A copiada é apagada da área de transferência após 30 s.
- A sessão encerra após 15 minutos sem uso.
- O login bloqueia por 5 minutos depois de 5 tentativas erradas.
- O acesso é por HTTPS na rede local.

### Se todos os administradores esquecerem a senha

No servidor, com o sistema parado:

```
.venv\Scripts\python.exe gerenciar.py recuperar
```

O comando pede o **código de recuperação** e redefine o acesso de um administrador. Sem o código, as senhas guardadas **não podem ser recuperadas**.

## Backup

- O sistema faz um backup automático ao iniciar e a cada 24 h, em `dados\backups`, e mantém as últimas 30 cópias.
- O menu **Backup** permite criar um backup na hora e baixar as cópias.
- Copie a pasta `dados\backups` para outro local (por exemplo, a pasta do servidor de rede). As senhas continuam criptografadas no backup.
- **Para restaurar** pela tela: menu **Backup** › **Restaurar** na cópia desejada, digite `RESTAURAR` e confirme. Também dá para enviar um arquivo `.db` baixado antes (**Restaurar de um arquivo**). Antes de restaurar, o sistema guarda o estado atual como `..._antes_da_restauracao.db`, então dá para desfazer restaurando essa cópia. Depois da restauração todos entram de novo, com a senha que valia na data do backup.
- **Pelo terminal** (servidor parado ou sem acesso à tela): `.venv\Scripts\python.exe gerenciar.py restaurar` lista as cópias e pede confirmação.

## PythonAnywhere

1. **Código**: no console Bash, `git clone https://github.com/WallaceSMiguel/controle-ti.git` (ou `cd ~/controle-ti && git pull`). Crie um virtualenv e `pip install -r requirements.txt`.
2. **Dados fora do código**: crie `~/controle-ti-dados`. Se o Controle TI já roda aí, use a pasta de dados atual.
3. **Arquivo WSGI** (aba *Web*): veja o modelo no topo de `wsgi.py`. Defina `CONTROLE_TI_DADOS` e `SQLITE_JOURNAL=DELETE` (o modo WAL do SQLite não é seguro no disco de rede do PythonAnywhere).
4. **Arquivos estáticos** (aba *Web › Static files*): URL `/static/` → `/home/SEU_USUARIO/controle-ti/controle_ti/static`.
5. **Force HTTPS**: ative na aba *Web*. O `config.ini` deve ficar com `https = sim` (cookies seguros).
6. **Um worker só**: as sessões e a chave do cofre ficam na memória do processo. Com mais de um worker, o usuário cai da sessão aleatoriamente. Em contas pagas, deixe 1 worker para este app (ou peça a migração das sessões para outro armazenamento).
7. **Backup**: o backup diário do `run.py` não roda no PythonAnywhere. Crie uma *Scheduled task* diária:
   `cd ~/controle-ti && CONTROLE_TI_DADOS=~/controle-ti-dados ~/.virtualenvs/SEU_VENV/bin/python gerenciar.py backup`
8. **Importar os termos de produção** (uma vez), no console, com as mesmas variáveis do WSGI:
   ```
   cd ~/controle-ti
   export CONTROLE_TI_DADOS=~/controle-ti-dados SQLITE_JOURNAL=DELETE
   python gerenciar.py importar-termos ~/CAMINHO_DO_DATA_DIR_ANTIGO/termos.db --simular
   python gerenciar.py importar-termos ~/CAMINHO_DO_DATA_DIR_ANTIGO/termos.db --mapa "..."
   ```
   O caminho do `termos.db` é o `DATA_DIR` definido no WSGI do app antigo. Depois clique em **Reload**.
9. Confira os termos importados e só então desative o app antigo. O arquivo `termos.db` continua lá como cópia de segurança.

Não há migração manual de banco: as tabelas novas (`termos`, `termo_equipamentos`, `termo_historico`) são criadas sozinhas na primeira execução, sem tocar nos dados existentes.

## Configuração

Na primeira execução é criado o arquivo `dados\config.ini`:

```ini
[servidor]
host = 0.0.0.0
porta = 8443
https = sim
timeout_minutos = 15
backup_manter = 30
```

## Estrutura

```
controle_ti/
├─ iniciar.bat           inicia o sistema no Windows
├─ run.py                servidor (HTTPS, backup diário)
├─ gerenciar.py          recuperação de acesso, backup e importação de termos pelo terminal
├─ wsgi.py               entrada para PythonAnywhere / servidores WSGI
├─ ferramentas/          coletar_msinfo32.bat (coleta da configuração)
├─ controle_ti/
│  ├─ cripto.py          criptografia
│  ├─ msinfo.py          leitura dos arquivos do msinfo32
│  ├─ seguranca.py       sessões, perfis, auditoria
│  ├─ db.py              banco SQLite
│  ├─ termos.py          regras dos termos de responsabilidade e importação
│  ├─ rotas/             telas (painel, estoque, termos, cofre, admin)
│  ├─ templates/         HTML
│  └─ static/            CSS, JS e logo
├─ testes/               testes automáticos (python -m pytest testes)
└─ dados/                criado na 1ª execução: banco, config, certificado, backups
```

A pasta `dados` contém o banco e a chave do certificado. Não compartilhe essa pasta na rede.
