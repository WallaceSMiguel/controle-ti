# Controle TI — Valorização

Sistema web local para a equipe de TI, com três módulos:

- **Equipamentos**: inventário por unidade, com histórico de movimentações, garantias e exportação para Excel.
- **Senhas dos computadores**: administrador local, BIOS, BitLocker etc., vinculadas a cada equipamento.
- **Cofre de senhas**: acessos dos sistemas (SIEG, e-CAC, prefeituras, e-mails), por unidade ou "Geral".

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
├─ gerenciar.py          recuperação de acesso e backup pelo terminal
├─ ferramentas/          coletar_msinfo32.bat (coleta da configuração)
├─ controle_ti/
│  ├─ cripto.py          criptografia
│  ├─ msinfo.py          leitura dos arquivos do msinfo32
│  ├─ seguranca.py       sessões, perfis, auditoria
│  ├─ db.py              banco SQLite
│  ├─ rotas/             telas (painel, estoque, cofre, admin)
│  ├─ templates/         HTML
│  └─ static/            CSS, JS e logo
├─ testes/               testes automáticos (python -m pytest testes)
└─ dados/                criado na 1ª execução: banco, config, certificado, backups
```

A pasta `dados` contém o banco e a chave do certificado. Não compartilhe essa pasta na rede.
