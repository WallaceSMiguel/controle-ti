"""Gera arquivos de exemplo no formato do msinfo32 para os testes.

    python testes/gerar_amostras.py
"""
from pathlib import Path

PASTA = Path(__file__).parent / "amostras"

RESUMO_PT = [
    ("Nome do sistema operacional", "Microsoft Windows 11 Pro"),
    ("Versão", "10.0.22631 Compilação 22631"),
    ("Descrição adicional do sistema operacional", "Não Disponível"),
    ("Fabricante do sistema operacional", "Microsoft Corporation"),
    ("Nome do sistema", "VAL-DC-021"),
    ("Fabricante do sistema", "Dell Inc."),
    ("Modelo do sistema", "OptiPlex 3080"),
    ("Tipo do sistema", "PC baseado em x64"),
    ("SKU do sistema", "09A3"),
    ("Processador", "Intel(R) Core(TM) i5-10500 CPU @ 3.10GHz, 3096 Mhz, 6 Núcleo(s), 12 Processador(es) Lógico(s)"),
    ("Versão/data do BIOS", "Dell Inc. 2.21.0, 12/03/2024"),
    ("Versão do SMBIOS", "3.2"),
    ("Modo da BIOS", "UEFI"),
    ("Fabricante da Placa Base", "Dell Inc."),
    ("Produto da Placa Base", "0M5WJ8"),
    ("Função da Plataforma", "Área de Trabalho"),
    ("Estado de Inicialização Segura", "Ativado"),
    ("Pasta do Windows", "C:\\WINDOWS"),
    ("Localidade", "Brasil"),
    ("Nome de usuário", "VALORIZACAO\\juliana.lima"),
    ("Fuso horário", "Hora oficial do Brasil"),
    ("Memória física (RAM) instalada", "16,0 GB"),
    ("Memória Física Total", "15,7 GB"),
    ("Memória Física Disponível", "8,92 GB"),
]
DISCOS_PT = [
    [("Descrição", "Unidade de disco"), ("Fabricante", "(Unidades de disco padrão)"),
     ("Modelo", "KINGSTON SNV2S500G"), ("Bytes/Setor", "512"), ("Tipo de Mídia", "Mídia de disco rígido fixo"),
     ("Partições", "3"), ("Tamanho", "465,76 GB (500.105.249.280 bytes)"),
     ("Partição", "Disco nº 0, Partição nº 0"), ("Tamanho da partição", "100,00 MB (104.857.600 bytes)"),
     ("Partição", "Disco nº 0, Partição nº 1"), ("Tamanho da partição", "464,98 GB (499.270.123.520 bytes)")],
    [("Descrição", "Unidade de disco"), ("Modelo", "ST1000DM010-2EP102"), ("Partições", "1"),
     ("Tamanho", "931,51 GB (1.000.202.273.280 bytes)"), ("Tipo de Interface", "IDE")],
    [("Descrição", "Unidade de disco"), ("Modelo", "SanDisk Cruzer Blade USB Device"),
     ("Tamanho", "14,91 GB (16.008.609.792 bytes)"), ("Tipo de Interface", "USB")],
]
UNIDADES_PT = [
    [("Unidade", "C:"), ("Descrição", "Disco fixo local"), ("Sistema de arquivos", "NTFS"),
     ("Tamanho", "464,98 GB (499.270.123.520 bytes)"), ("Espaço livre", "38,40 GB (41.231.458.304 bytes)")],
    [("Unidade", "D:"), ("Descrição", "Disco fixo local"), ("Sistema de arquivos", "NTFS"),
     ("Tamanho", "931,51 GB (1.000.202.273.280 bytes)"), ("Espaço livre", "702,10 GB (753.866.031.104 bytes)")],
    [("Unidade", "E:"), ("Descrição", "Disco removível"), ("Tamanho", "14,91 GB (16.008.609.792 bytes)")],
]
REDE_PT = [
    [("Nome", "[00000001] Intel(R) Ethernet Connection (11) I219-LM"), ("Tipo de adaptador", "Ethernet 802.3"),
     ("Tipo de produto", "Intel(R) Ethernet Connection (11) I219-LM"), ("Endereço IP", "192.168.10.21, fe80::1c2:3d4:5e6:7f8"),
     ("Endereço MAC", "a4:bb:6d:12:34:56")],
    [("Nome", "[00000002] WAN Miniport (IP)"), ("Tipo de produto", "WAN Miniport (IP)"), ("Endereço MAC", "Não disponível")],
    [("Nome", "[00000005] Hyper-V Virtual Ethernet Adapter"), ("Tipo de produto", "Hyper-V Virtual Ethernet Adapter"),
     ("Endereço IP", "172.20.0.1"), ("Endereço MAC", "00:15:5D:01:02:03")],
]
VIDEO_PT = [[("Nome", "Intel(R) UHD Graphics 630"), ("RAM do adaptador", "1,00 GB (1.073.741.824 bytes)"),
             ("Resolução", "1920 x 1080 x 60 hertz")]]


def txt_pt():
    out = ["Relatório de Informações do Sistema gerado em: 15/10/2026 12:58:41", "Nome do sistema: VAL-DC-021",
           "[Resumo do Sistema]", "", "Item\tValor\t"]
    out += [f"{k}\t{v}\t" for k, v in RESUMO_PT]
    out += ["", "[Recursos de Hardware]", "", "[Conflitos/Compartilhamento]", "", "Recurso\tDispositivo\t",
            "Porta de E/S 0x00000000-0x00000CF7\tComplexo Raiz PCI Express\t", "", "[Componentes]", ""]

    def bloco(nome, regs):
        linhas = ["", f"[{nome}]", "", "Item\tValor\t"]
        for i, r in enumerate(regs):
            if i:
                linhas.append("\t\t")
            linhas += [f"{k}\t{v}\t" for k, v in r]
        return linhas

    out += bloco("Vídeo", VIDEO_PT)
    out += ["", "[Rede]", ""] + bloco("Adaptador", REDE_PT)
    out += ["", "[Armazenamento]", ""] + bloco("Unidades", UNIDADES_PT) + bloco("Discos", DISCOS_PT)
    out += ["", "[Ambiente de Software]", ""]
    return "\r\n".join(out) + "\r\n"


def nfo(resumo, nome_resumo, comps):
    """comps: lista de (caminho, registros) onde caminho = ['Componentes','Armazenamento','Discos']"""
    def cd(s):
        return f"<![CDATA[{s}]]>"

    def data(k, v):
        return f"<Data>\n<Item>{cd(k)}</Item>\n<Value>{cd(v)}</Value>\n</Data>"

    x = ['<?xml version="1.0"?>', "<MsInfo>", "<Metadata>", "<Version>8.0</Version>",
         "<CreationUTC>10/15/26 15:58:41</CreationUTC>", "</Metadata>", f'<Category name="{nome_resumo}">']
    x += [data(k, v) for k, v in resumo]
    x += ['<Category name="Hardware Resources"><Category name="Conflicts/Sharing">',
          f"<Data>\n<Resource>{cd('I/O Port 0x00000000-0x00000CF7')}</Resource>\n<Device>{cd('PCI Express Root Complex')}</Device>\n</Data>",
          "</Category></Category>"]
    arvore: dict = {}
    for caminho, regs in comps:
        no = arvore
        for p in caminho:
            no = no.setdefault(p, {})
        no["__regs__"] = regs

    def emitir(no):
        partes = []
        for nome, filho in no.items():
            if nome == "__regs__":
                continue
            partes.append(f'<Category name="{nome}">')
            for i, r in enumerate(filho.get("__regs__", [])):
                if i:
                    partes.append(data("", ""))
                partes += [data(k, v) for k, v in r]
            partes += emitir(filho)
            partes.append("</Category>")
        return partes

    x += emitir(arvore)
    x += ["</Category>", "</MsInfo>"]
    return "\n".join(x)


RESUMO_EN = [
    ("OS Name", "Microsoft Windows 10 Pro"), ("Version", "10.0.19045 Build 19045"),
    ("System Name", "VAL-BR-003"), ("System Manufacturer", "LENOVO"), ("System Model", "ThinkPad E14 Gen 2"),
    ("System Type", "x64-based PC"),
    ("Processor", "11th Gen Intel(R) Core(TM) i5-1135G7 @ 2.40GHz, 2419 Mhz, 4 Core(s), 8 Logical Processor(s)"),
    ("BIOS Version/Date", "LENOVO R1AET45W (1.21 ), 3/7/2023"), ("BIOS Mode", "UEFI"),
    ("BaseBoard Manufacturer", "LENOVO"), ("BaseBoard Product", "20TA0054BR"), ("Platform Role", "Mobile"),
    ("Secure Boot State", "On"), ("User Name", "VALORIZACAO\\fernanda.rocha"),
    ("Installed Physical Memory (RAM)", "8.00 GB"), ("Total Physical Memory", "7.73 GB"),
]
COMPS_EN = [
    (["Components", "Display"], [[("Name", "Intel(R) Iris(R) Xe Graphics"), ("Resolution", "1920 x 1080 x 60 hertz")]]),
    (["Components", "Network", "Adapter"], [
        [("Name", "[00000001] Intel(R) Wi-Fi 6 AX201 160MHz"), ("Product Type", "Intel(R) Wi-Fi 6 AX201 160MHz"),
         ("IP Address", "192.168.30.44, fe80::aa:bb"), ("MAC Address", "3C:58:C2:AA:BB:CC")],
        [("Name", "[00000003] Bluetooth Device (Personal Area Network)"), ("MAC Address", "3C:58:C2:AA:BB:CD")]]),
    (["Components", "Storage", "Drives"], [
        [("Drive", "C:"), ("Description", "Local Fixed Disk"), ("File System", "NTFS"),
         ("Size", "237.85 GB (255,385,104,384 bytes)"), ("Free Space", "12.10 GB (12,992,446,464 bytes)")]]),
    (["Components", "Storage", "Disks"], [
        [("Description", "Disk drive"), ("Model", "SAMSUNG MZALQ256HAJD-000L1"), ("Partitions", "3"),
         ("Size", "238.47 GB (256,052,966,400 bytes)"), ("Partition", "Disk #0, Partition #0"),
         ("Partition Size", "260.00 MB (272,629,760 bytes)")]]),
]
RESUMO_SRV = [
    ("Nome do sistema operacional", "Microsoft Windows Server 2022 Standard"), ("Versão", "10.0.20348 Compilação 20348"),
    ("Nome do sistema", "VAL-SRV-01"), ("Fabricante do sistema", "Dell Inc."), ("Modelo do sistema", "PowerEdge T150"),
    ("Tipo do sistema", "PC baseado em x64"),
    ("Processador", "Intel(R) Xeon(R) E-2314 CPU @ 2.80GHz, 2808 Mhz, 4 Núcleo(s), 4 Processador(es) Lógico(s)"),
    ("Função da Plataforma", "Servidor Empresarial"), ("Memória física (RAM) instalada", "32,0 GB"),
]
COMPS_SRV = [(["Componentes", "Armazenamento", "Discos"], [
    [("Descrição", "Unidade de disco"), ("Modelo", "DELL PERC H355 SCSI Disk Device"),
     ("Tamanho", "1,82 TB (1.999.844.147.200 bytes)")]])]


def main():
    PASTA.mkdir(exist_ok=True)
    (PASTA / "VAL-DC-021.txt").write_bytes(b"\xff\xfe" + txt_pt().encode("utf-16-le"))
    (PASTA / "VAL-BR-003.nfo").write_bytes(nfo(RESUMO_EN, "System Summary", COMPS_EN).encode("utf-16"))
    (PASTA / "VAL-SRV-01.nfo").write_bytes(nfo(RESUMO_SRV, "Resumo do Sistema", COMPS_SRV).encode("utf-8"))
    print("Amostras em", PASTA)


if __name__ == "__main__":
    main()
