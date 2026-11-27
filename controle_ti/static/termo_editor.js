const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const digits = s => String(s||"").replace(/\D/g,"");
const maskCPF = v => { v=digits(v).slice(0,11); return v.replace(/(\d{3})(\d)/,"$1.$2").replace(/(\d{3})(\d)/,"$1.$2").replace(/(\d{3})(\d{1,2})$/,"$1-$2"); };
const maskCNPJ = v => { v=digits(v).slice(0,14); return v.replace(/^(\d{2})(\d)/,"$1.$2").replace(/^(\d{2})\.(\d{3})(\d)/,"$1.$2.$3").replace(/\.(\d{3})(\d)/,".$1/$2").replace(/(\d{4})(\d)/,"$1-$2"); };
const MESES = ["janeiro","fevereiro","março","abril","maio","junho","julho","agosto","setembro","outubro","novembro","dezembro"];
const dataExtenso = s => { if(!s) return ""; const [y,m,d]=s.split("-").map(Number); return `${d} de ${MESES[m-1]} de ${y}`; };
const hoje = () => { const d=new Date(); return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,10); };
const ESTADOS = ["Novo","Bom","Usado (funcionando)","Regular","Danificado"];

function pillClass(e){ e=(e||"").toLowerCase(); if(e.startsWith("novo"))return"novo"; if(e.startsWith("bom")||e.startsWith("usado"))return"bom"; if(e.startsWith("regular"))return"regular"; if(e.startsWith("danif"))return"danificado"; return""; }
const fill = (v, w=28) => v ? `<span class="fill">${esc(v)}</span>` : `<span class="fill empty">${"&nbsp;".repeat(w)}</span>`;

/* Catálogo de acessos (botões no formulário) */
const SISTEMAS = [
  {id:"rede",   nome:"Computador / Rede - VPN", ic:"🖥️", det:"Computador / VPN",         ph:"Ex.: PC-DP-03 / VPN Barra"},
  {id:"email",  nome:"E-mail corporativo",      ic:"✉️", det:"Webmail / observação",     ph:"Ex.: outlook.office.com"},
  {id:"onvio",  nome:"Onvio",                   ic:"☁️", det:"Link / perfil",            ph:"Ex.: onvio.com.br – perfil DP"},
  {id:"dominio",nome:"Domínio Web",             ic:"📊", det:"Módulos / observação",     ph:"Ex.: Folha, Escrita Fiscal"},
  {id:"linkus", nome:"Telefonia Linkus",        ic:"☎️", det:"Ramal",                    ph:"Ex.: Ramal 2031"},
  {id:"pasta",  nome:"Pasta mapeada",           ic:"📁", det:"Caminho / unidade de rede", ph:"Ex.: \\\\servidor\\DP  (Z:)"},
];
const TIPO_LABEL = {equipamentos:"Equipamentos", acessos:"Acessos", completo:"Equipamentos + Acessos"};
const tipoDe = S => S.tipo || (S.incluirAcessos ? "completo" : "equipamentos");

function docHTML(S, numero){
  const E = Object.assign({}, EMPRESA||{}, S.empresaSnapshot||{});
  const logo = (EMPRESA && EMPRESA.logo) || LOGO_PADRAO;
  const tipo = tipoDe(S);
  const itens = (S.itens||[]).filter(i=>i.item||i.serie||i.obs);
  const rowsItens = (itens.length?itens:[{},{},{}]).map((it,i)=>`
    <tr><td class="c">${i+1}</td><td>${esc(it.item)||"&nbsp;"}</td><td>${esc(it.serie)}</td>
    <td class="c">${it.item?esc(it.qtd):""}</td>
    <td>${it.item&&it.estado?`<span class="pill ${pillClass(it.estado)}">${esc(it.estado)}</span>`:""}</td><td>${esc(it.obs)}</td></tr>`).join("");
  const acessos = (S.acessos||[]).filter(a=>a.sistema||a.usuario);
  const tabelaAcessos = `
      <table class="items acc"><thead><tr><th style="width:28px">Nº</th><th>Sistema / Serviço</th><th>Usuário / Login</th><th>Detalhe</th><th style="width:22%">Senha</th></tr></thead><tbody>
      ${(acessos.length?acessos:[{},{},{}]).map((a,i)=>`<tr><td class="c">${i+1}</td><td><b>${esc(a.sistema)||"&nbsp;"}</b></td><td>${esc(a.usuario)}</td>
        <td>${esc(a.detalhe||a.link)}</td><td>${a.senha?`<span class="mono-doc">${esc(a.senha)}</span>`:(a.usar_cofre||a.tem_senha)?`<span class="mono-doc">••••••••</span>`:`<span class="blank-line"></span>`}</td></tr>`).join("")}
      </tbody></table>
      <p class="note">Senhas gravadas de forma criptografada; aparecem por extenso só na impressão com senhas. Linhas em branco são preenchidas à mão.</p>`;
  let n = 0; const C = () => `${++n}ª`;

  const head = `
    <header class="doc-head">
      <img src="${esc(logo)}" alt="Logo">
      <div class="meta"><b>${esc(E.empresa)}</b><br>CNPJ ${esc(E.cnpj)}${S.unidade?`<br>Unidade <b>${esc(S.unidade)}</b>`:""}<br><span class="doc-num">${numero?`Termo nº ${esc(numero)}`:"Rascunho – não salvo"}</span></div>
    </header>`;
  const sigs = (declaracao) => `
    <p style="margin-top:14px">${declaracao}</p>
    <div class="sig-wrap">
      <div class="place-date">${fill(S.local,30)}, ${fill(dataExtenso(S.data),30)}.</div>
      <div class="sigs">
        <div class="sig">
          <div class="line">${esc(S.nome)||"&nbsp;"}</div>
          <div class="role">Colaborador(a) – RESPONSÁVEL</div>
          <dl><dt>CPF:</dt><dd>${esc(S.cpf)||"_____________________"}</dd>${S.cargo?`<dt>Cargo:</dt><dd>${esc(S.cargo)}</dd>`:""}</dl>
        </div>
        <div class="sig">
          <div class="line">${esc(S.recNome)||"&nbsp;"}</div>
          <div class="role">Entregue por – ${esc(E.empresa)}</div>
          <dl><dt>Cargo:</dt><dd>${esc(S.recCargo)||"_____________________"}</dd></dl>
        </div>
      </div>
      <div class="obs-box"><b>Observações:</b> ${esc(S.obs).replace(/\n/g,"<br>")}</div>
    </div>
    <footer class="doc-foot"><span>${esc(E.empresa)} · CNPJ ${esc(E.cnpj)}${S.unidade?` · Unidade ${esc(S.unidade)}`:""}${numero?` · ${esc(numero)}`:""}</span><span>${esc(E.empContato)}</span></footer>`;

  const clausulasCredenciais = `
      <ul><li>Utilizar os acessos exclusivamente para atividades relacionadas à EMPRESA;</li>
      <li>Manter usuário e senha em sigilo — as credenciais são pessoais e intransferíveis;</li>
      <li>Alterar a senha no primeiro acesso, utilizando senha forte;</li>
      <li>Não anotar senhas em locais visíveis nem compartilhá-las com terceiros, inclusive colegas;</li>
      <li>Bloquear o computador ao se ausentar da estação de trabalho;</li>
      <li>Comunicar imediatamente qualquer suspeita de uso indevido, vazamento ou acesso não autorizado.</li></ul>`;

  /* ---------------- somente ACESSOS (ficha de acessos) ---------------- */
  if(tipo==="acessos"){
    return head + `
    <h2 class="doc-title">TERMO DE RESPONSABILIDADE DE ACESSOS</h2>
    <p class="doc-sub">Ficha de acessos do colaborador a sistemas e serviços da empresa</p>
    <div class="ficha">
      <div><span>Nome</span><b>${esc(S.nome)||"&nbsp;"}</b></div>
      <div><span>CPF</span><b>${esc(S.cpf)||"&nbsp;"}</b></div>
      <div><span>Cargo / Setor</span><b>${esc([S.cargo,S.setor].filter(Boolean).join(" · "))||"&nbsp;"}</b></div>
      <div><span>Unidade</span><b>${esc(S.unidade)||"&nbsp;"}</b></div>
    </div>
    <p>Pelo presente instrumento, o(a) colaborador(a) acima identificado(a), doravante denominado(a) <b>RESPONSÁVEL</b>, declara receber da empresa
    <b>${esc(E.empresa)}</b>, inscrita no CNPJ sob nº ${esc(E.cnpj)}, doravante denominada <b>EMPRESA</b>, os acessos relacionados abaixo, nas condições a seguir.</p>

    <section class="clause"><h3>Cláusula ${C()} – Acessos fornecidos</h3>${tabelaAcessos}</section>
    <section class="clause"><h3>Cláusula ${C()} – Responsabilidades do(a) responsável</h3><p>O(a) RESPONSÁVEL compromete-se a:</p>${clausulasCredenciais}</section>
    <section class="clause"><h3>Cláusula ${C()} – Confidencialidade e proteção de dados</h3>
      <p>As informações acessadas — inclusive dados de clientes, colaboradores e documentos fiscais, contábeis e trabalhistas — são confidenciais e devem ser tratadas conforme a Lei Geral de Proteção de Dados (Lei nº 13.709/2018) e as normas internas da EMPRESA, sendo vedada sua cópia, divulgação ou uso para fins pessoais, sob pena de responsabilidade civil, trabalhista e/ou criminal.</p></section>
    <section class="clause"><h3>Cláusula ${C()} – Monitoramento</h3>
      <p>O(a) RESPONSÁVEL está ciente de que os sistemas, e-mails, telefonia e recursos de rede são ferramentas de trabalho de propriedade da EMPRESA e podem ser monitorados para fins de segurança e conformidade.</p></section>
    <section class="clause"><h3>Cláusula ${C()} – Revogação dos acessos</h3>
      <p>Os acessos poderão ser alterados ou revogados a qualquer tempo e serão obrigatoriamente cancelados no término do vínculo ou mudança de função, sendo vedada qualquer tentativa de acesso posterior.</p></section>
    ${sigs("Declaro que recebi meus acessos e estou ciente da responsabilidade sobre o uso adequado das informações e sistemas da empresa.")}`;
  }

  /* ---------------- EQUIPAMENTOS (e COMPLETO = equipamentos + acessos) ---------------- */
  const completo = tipo==="completo";
  const c1=C(), c2=C(), c3 = completo?C():null;
  return head + `
    <h2 class="doc-title">${completo?"TERMO DE RESPONSABILIDADE POR EQUIPAMENTOS E ACESSOS":"TERMO DE RESPONSABILIDADE POR EQUIPAMENTOS"}</h2>
    <p class="doc-sub">${completo?"Instrumento de entrega de bens e de acessos a sistemas":"Instrumento de entrega, guarda e devolução de bens"}</p>

    <p>Pelo presente instrumento, eu ${fill(S.nome,40)}, portador(a) do CPF nº ${fill(S.cpf,20)} e RG nº ${fill(S.rg,20)},
    residente à ${fill(S.endereco,50)}${S.cargo||S.setor?`, ocupante do cargo de ${fill(S.cargo,20)}${S.setor?` no setor ${fill(S.setor)}`:""}`:""}${S.unidade?`, lotado(a) na unidade ${fill(S.unidade)}`:""},
    doravante denominado(a) <b>RESPONSÁVEL</b>, declaro estar ciente das condições e responsabilidades referentes ao uso e conservação dos bens${completo?" e acessos":""}
    fornecidos pela empresa <b>${esc(E.empresa)}</b>, inscrita no CNPJ sob nº ${esc(E.cnpj)}, com sede em ${esc(E.empEndereco)},
    doravante denominada <b>EMPRESA</b>.</p>

    <section class="clause"><h3>Cláusula ${c1} – Objeto</h3>
      <p>O presente termo formaliza a responsabilidade do(a) RESPONSÁVEL pelo uso, guarda, conservação e devolução dos bens fornecidos pela EMPRESA, incluindo equipamentos, materiais, ferramentas e documentos${completo?", bem como pelo uso dos acessos a sistemas e serviços corporativos":""}.</p></section>

    <section class="clause"><h3>Cláusula ${c2} – Registro dos itens</h3>
      <p>O(a) RESPONSÁVEL declara estar recebendo os seguintes itens sob sua responsabilidade:</p>
      <table class="items"><thead><tr><th style="width:28px">Nº</th><th>Item / Equipamento</th><th>Patrimônio / Nº de série</th><th style="width:40px">Qtd.</th><th>Estado</th><th>Observações</th></tr></thead>
      <tbody>${rowsItens}</tbody></table></section>

    ${completo?`<section class="clause"><h3>Cláusula ${c3} – Acessos e credenciais</h3>
      <p>Além dos bens acima, o(a) RESPONSÁVEL recebe os seguintes acessos, de uso pessoal e intransferível:</p>${tabelaAcessos}
      <p>Quanto aos acessos, o(a) RESPONSÁVEL compromete-se a:</p>${clausulasCredenciais}</section>`:""}

    <section class="clause"><h3>Cláusula ${C()} – Responsabilidades do(a) responsável</h3>
      <p>O(a) RESPONSÁVEL compromete-se a:</p>
      <ul><li>Utilizar os bens exclusivamente para atividades relacionadas à EMPRESA;</li>
      <li>Zelar pela conservação e bom estado dos equipamentos;</li>
      <li>Não ceder, transferir ou emprestar os bens a terceiros sem autorização expressa da EMPRESA;</li>
      <li>Comunicar imediatamente qualquer dano, perda, furto ou mau funcionamento;</li>
      <li>Devolver os bens nas mesmas condições em que foram recebidos, considerando desgaste natural;</li>
      <li>Cumprir normas internas de segurança, confidencialidade e operação dos bens.</li></ul></section>

    <section class="clause"><h3>Cláusula ${C()} – Responsabilidade por danos</h3>
      <p>O(a) RESPONSÁVEL poderá ser responsabilizado(a) por danos, perdas ou extravios resultantes de:</p>
      <ul><li>Uso inadequado ou negligente;</li><li>Descumprimento das normas internas;</li><li>Perda ou extravio por ação ou omissão do(a) RESPONSÁVEL.</li></ul>
      <p>O ressarcimento será calculado pelo valor de reposição ou reparo do item.</p></section>

    <section class="clause"><h3>Cláusula ${C()} – Devolução dos bens${completo?" e revogação dos acessos":""}</h3>
      <p>A devolução dos bens deverá ocorrer:</p>
      <ul><li>No término do vínculo com a EMPRESA;</li><li>Quando solicitado formalmente;</li><li>Com todos os acessórios, manuais e documentos;</li><li>Em perfeitas condições de uso, considerando desgaste natural.</li></ul>
      ${completo?"<p>Os acessos serão revogados no término do vínculo ou mudança de função, sendo vedada qualquer tentativa de acesso posterior.</p>":""}</section>

    <section class="clause"><h3>Cláusula ${C()} – Confidencialidade</h3>
      <p>O(a) RESPONSÁVEL compromete-se a não divulgar informações confidenciais obtidas em razão do uso dos bens${completo?" e sistemas, observando a Lei Geral de Proteção de Dados (Lei nº 13.709/2018)":""}, sob pena de responsabilidade civil e/ou criminal.</p></section>

    <section class="clause"><h3>Cláusula ${C()} – Vigência</h3>
      <p>O presente termo entra em vigor na data de assinatura e permanecerá válido enquanto o(a) RESPONSÁVEL estiver utilizando os bens da EMPRESA, inclusive até a completa devolução.</p></section>

    <section class="clause"><h3>Cláusula ${C()} – Não devolução</h3>
      <p>O(a) RESPONSÁVEL reconhece que os bens listados neste termo são propriedade exclusiva da EMPRESA. A não devolução ou apropriação dos bens sem autorização expressa da EMPRESA poderá caracterizar apropriação indébita, nos termos da legislação vigente, sujeitando o(a) RESPONSÁVEL às medidas civis e criminais cabíveis, além do ressarcimento integral do valor dos bens.</p>
      <p><b>Parágrafo único:</b> A EMPRESA fará notificação (e-mail, mensagem) antes de acionar quaisquer medidas legais.</p></section>
    ${sigs(`E por estarem as partes assim pactuadas, firmam o presente termo de responsabilidade, declarando o(a) RESPONSÁVEL que recebeu os itens listados na Cláusula ${c2}${completo?` e os acessos listados na Cláusula ${c3}`:""}.`)}`;
}

/* =================================================================== editor (Controle TI) */
const $ = (s, el=document) => el.querySelector(s);
const $$ = (s, el=document) => [...el.querySelectorAll(s)];
const CFG = JSON.parse(document.getElementById("termo-config").textContent);
const EMPRESA = CFG.empresa;
const LOGO_PADRAO = CFG.logo_padrao;
const DRAFT_KEY = "controle-ti-termo-rascunho";
const sem_acento = s => (s||"").normalize("NFD").replace(/[̀-ͯ]/g,"");
function loginPadrao(nome){
  const p = sem_acento(nome).toLowerCase().replace(/[^a-z\s]/g,"").split(/\s+/).filter(x=>x && !["da","de","do","das","dos","e"].includes(x));
  return p.length ? (p.length>1 ? `${p[0]}.${p[p.length-1]}` : p[0]) : "";
}
function gerarSenha(){
  const A="ABCDEFGHJKLMNPQRSTUVWXYZ", a="abcdefghijkmnpqrstuvwxyz", d="23456789", s="@#*!$";
  const r = n => { const b=new Uint32Array(1); crypto.getRandomValues(b); return b[0]%n; };
  const pick = set => set[r(set.length)];
  return pick(A)+pick(a)+pick(s)+pick(d)+pick(d)+pick(d)+pick(a)+pick(A)+pick(s);
}
function toast(msg){ const t=document.createElement("div"); t.className="toast visivel"; t.textContent=msg; document.body.append(t); setTimeout(()=>t.remove(),2800); }

const NOVO = () => ({
  tipo:"equipamentos", unidade:"", unidade_id:null,
  nome:"",cpf:"",rg:"",endereco:"",email:"",cargo:"",setor:"",
  local:(EMPRESA&&EMPRESA.local)||"", data:hoje(), recNome:CFG.usuario_nome||"", recCargo:"", obs:"",
  itens:[{item:"",serie:"",qtd:1,estado:"Novo",obs:""}],
  acessos:[]
});

(function editor(){
  const root = $("#termo-editor");
  const id = CFG.modo === "editar";
  const numero = CFG.numero || null;
  let S = Object.assign(NOVO(), CFG.dados || {});
  if(!id && !CFG.dados_vindos){
    try{ const d = JSON.parse(localStorage.getItem(DRAFT_KEY)||"null"); if(d && (d.nome||d.itens?.some(i=>i.item)||d.acessos?.length)) S = Object.assign(S,d); }catch(e){}
  }
  S.tipo = tipoDe(S); delete S.incluirAcessos;
  if(!S.itens || !S.itens.length) S.itens = [{item:"",serie:"",qtd:1,estado:"Novo",obs:""}];
  S.acessos = (S.acessos||[]).filter(a=>a.sistema||a.usuario).map((a,i)=>({
    sid:a.sid||"", sistema:a.sistema||"", usuario:a.usuario||"", detalhe:a.detalhe||a.link||"", senha:a.senha||"",
    cofre_id:a.cofre_id||null, usar_cofre:!!a.usar_cofre, tem_senha:!!a.tem_senha, orig:(a.orig!=null?a.orig:(id?i:null))}));
  const UNIDADES = CFG.unidades || [];
  const EQUIP = CFG.equipamentos || [];
  const COFRE = CFG.cofre || [];
  if(!S.unidade_id && S.unidade){ const u = UNIDADES.find(u=>u.nome.toLowerCase()===S.unidade.toLowerCase()); if(u) S.unidade_id = u.id; }

  root.innerHTML = `
  <div class="editor">
    <aside class="form">
      <div class="form-actions">
        <a class="btn ghost small" href="${esc(CFG.url_voltar)}">← Voltar</a><span class="sp"></span>
        ${id?"":`<button type="button" class="btn small ghost" id="btnLimpar">Limpar</button>`}
        <button type="button" class="btn primary" id="btnSalvar">${id?"Salvar alterações":"Salvar termo"}</button>
      </div>

      <div class="tipo-pick" id="tipoPick">
        ${[["equipamentos","💻","Equipamentos","Notebook, monitor, celular…"],["acessos","🔑","Acessos","Ficha de sistemas e logins"],["completo","🧩","Junto","Equipamentos + acessos"]]
          .map(([v,ic,t,d])=>`<button type="button" class="tipo-opt" data-tipo="${v}"><span class="ic">${ic}</span><b>${t}</b><small>${d}</small></button>`).join("")}
      </div>

      <details class="sec" open><summary><span class="num">1</span>Colaborador(a) e unidade</summary><div class="body">
        ${UNIDADES.length?`<div><div class="lbl">Unidade</div><div class="chips" id="unidPick">
          ${UNIDADES.map(u=>`<button type="button" class="chip" data-un="${u.id}">📍 ${esc(u.nome)}</button>`).join("")}</div></div>`:""}
        <label class="f">Nome completo<input data-k="nome" placeholder="Ex.: Maria da Silva"></label>
        <div class="row"><label class="f">CPF<input data-k="cpf" data-mask="cpf" placeholder="000.000.000-00" inputmode="numeric"></label>
          <label class="f">RG<input data-k="rg" placeholder="00.000.000-0"></label></div>
        <label class="f" data-only="eq">Endereço<input data-k="endereco" placeholder="Rua, nº, bairro, cidade - UF"></label>
        <label class="f">E-mail pessoal<input data-k="email" type="email" placeholder="nome@exemplo.com"></label>
        <div class="row"><label class="f">Cargo / Função<input data-k="cargo"></label><label class="f">Setor<input data-k="setor"></label></div>
      </div></details>

      <details class="sec" open data-only="eq"><summary><span class="num">2</span>Itens entregues</summary><div class="body">
        <div id="itemsForm" style="display:grid;gap:10px"></div>
        <button class="btn small" id="btnAddItem" type="button">+ Adicionar item</button>
        ${EQUIP.length?`<p class="hint">💡 Escolha "Do estoque" para puxar marca, modelo, configuração e patrimônio. Ao salvar, o equipamento fica com este colaborador como responsável.</p>`:""}
      </div></details>

      <details class="sec" open data-only="acc"><summary><span class="num">3</span>Acessos fornecidos</summary><div class="body">
        <div class="lbl">Selecione os acessos entregues</div>
        <div class="sys-grid" id="sysGrid">
          ${SISTEMAS.map(s=>`<button type="button" class="sys" data-sid="${s.id}"><span class="ic">${s.ic}</span><span>${esc(s.nome)}</span><i class="ck">✓</i></button>`).join("")}
          <button type="button" class="sys outro" id="btnOutro"><span class="ic">＋</span><span>Outro acesso</span></button>
        </div>
        ${COFRE.length?`<label class="f">🔐 Adicionar do cofre de senhas<select id="cofrePick"><option value="">Escolha um registro do cofre…</option>
          ${COFRE.map(c=>`<option value="${c.id}">${esc(c.sistema)}${c.usuario?` · ${esc(c.usuario)}`:""} (${esc(c.unidade||"Geral")})</option>`).join("")}</select></label>`:""}
        <div class="acc-tools"><button type="button" class="btn small" id="btnLogins">✨ Preencher logins pelo nome</button>
          <button type="button" class="btn small" id="btnSenhas">🔐 Gerar senhas</button></div>
        <div id="accForm" style="display:grid;gap:10px"></div>
        <p class="hint">🔒 As senhas ficam gravadas no termo <b>criptografadas</b> e só aparecem por extenso em "Imprimir com senhas" (registrado na Auditoria).</p>
      </div></details>

      <details class="sec" open><summary><span class="num">4</span>Assinaturas, local e data</summary><div class="body">
        <div class="row"><label class="f">Local<input data-k="local"></label><label class="f">Data<input type="date" data-k="data"></label></div>
        <div class="row"><label class="f">Entregue por (nome)<input data-k="recNome"></label><label class="f">Cargo<input data-k="recCargo"></label></div>
        <label class="f">Observações<textarea data-k="obs"></textarea></label>
      </div></details>
      <p class="hint">${id?"As alterações ficam registradas no histórico do termo.":"O rascunho fica guardado neste navegador até você salvar (sem as senhas)."}</p>
    </aside>
    <main class="preview"><article class="sheet" id="doc"></article></main>
  </div>`;

  const salvarRascunho = ()=>{ if(id) return; try{ const c = JSON.parse(JSON.stringify(S)); c.acessos.forEach(a=>delete a.senha); localStorage.setItem(DRAFT_KEY, JSON.stringify(c)); }catch(e){} };
  const update = ()=>{ $("#doc").innerHTML = docHTML(S, numero); salvarRascunho(); };
  const aplicaTipo = ()=>{
    $$("#tipoPick .tipo-opt").forEach(b=>b.classList.toggle("on", b.dataset.tipo===S.tipo));
    $$("[data-only=eq]").forEach(el=>el.hidden = S.tipo==="acessos");
    $$("[data-only=acc]").forEach(el=>el.hidden = S.tipo==="equipamentos");
  };
  const aplicaUnidade = ()=> $$("#unidPick .chip").forEach(b=>b.classList.toggle("on", +b.dataset.un===+S.unidade_id));
  const bind = ()=> $$("[data-k]").forEach(el=>{
    const k=el.dataset.k; el.value=S[k]??"";
    el.oninput = ()=>{ if(el.dataset.mask==="cpf") el.value=maskCPF(el.value); S[k] = el.value; update(); };
  });
  const itemsForm = ()=>{
    const box=$("#itemsForm");
    box.innerHTML = S.itens.map((it,i)=>`
      <div class="item-card"><span class="idx">Item ${i+1}${it.equipamento_id?" · do estoque":""}</span>
        ${S.itens.length>1?`<button type="button" class="btn small ghost rm" data-rm="${i}" title="Remover">✕</button>`:""}
        ${EQUIP.length?`<label class="f">Do estoque<select data-eq="${i}"><option value="">— digitar manualmente —</option>
          ${EQUIP.map(e=>`<option value="${e.id}" ${+it.equipamento_id===e.id?"selected":""}>${esc(e.rotulo)} (${esc(e.unidade)})</option>`).join("")}</select></label>`:""}
        <label class="f">Item / Equipamento<input data-i="${i}" data-f="item" value="${esc(it.item)}" placeholder="Ex.: Notebook Dell"></label>
        <div class="row3">
          <label class="f">Patrimônio / Nº série<input data-i="${i}" data-f="serie" value="${esc(it.serie)}" placeholder="PT 0195 ou S/N"></label>
          <label class="f">Qtd.<input type="number" min="1" data-i="${i}" data-f="qtd" value="${esc(it.qtd)}"></label>
          <label class="f">Estado<select data-i="${i}" data-f="estado">${[...new Set([...ESTADOS, it.estado].filter(Boolean))].map(e=>`<option ${e===it.estado?"selected":""}>${esc(e)}</option>`).join("")}</select></label>
        </div>
        <label class="f">Observações<input data-i="${i}" data-f="obs" value="${esc(it.obs)}" placeholder="Ex.: acompanha carregador"></label>
      </div>`).join("");
    $$("[data-f]",box).forEach(el=>el.oninput=()=>{ S.itens[el.dataset.i][el.dataset.f]=el.value; update(); });
    $$("[data-rm]",box).forEach(b=>b.onclick=()=>{ S.itens.splice(+b.dataset.rm,1); itemsForm(); update(); });
    $$("[data-eq]",box).forEach(sel=>sel.onchange=()=>{
      const it=S.itens[sel.dataset.eq], e=EQUIP.find(x=>x.id===+sel.value);
      if(e){ it.equipamento_id=e.id; it.item=e.item; it.serie=e.serie; if(!S.setor && e.setor) S.setor=e.setor; }
      else delete it.equipamento_id;
      itemsForm(); bind(); update();
    });
  };
  const catalogo = sid => SISTEMAS.find(s=>s.id===sid);
  const accForm = ()=>{
    $$("#sysGrid .sys[data-sid]").forEach(b=>b.classList.toggle("on", S.acessos.some(a=>a.sid===b.dataset.sid)));
    const box=$("#accForm");
    box.innerHTML = S.acessos.length ? S.acessos.map((a,i)=>{ const c = catalogo(a.sid); const cof = a.cofre_id; return `
      <div class="item-card acc-card"><span class="idx">${cof?"🔐 ":c?c.ic+" ":""}${esc(c?c.nome:(a.sistema||"Outro acesso"))}${cof?" · do cofre":""}</span>
        <button type="button" class="btn small ghost rm" data-rma="${i}" title="Remover">✕</button>
        ${c?"":`<label class="f">Sistema / Serviço<input data-a="${i}" data-f="sistema" value="${esc(a.sistema)}" placeholder="Ex.: Zap Contábil"></label>`}
        <div class="row"><label class="f">Usuário / Login<input data-a="${i}" data-f="usuario" value="${esc(a.usuario)}" placeholder="${a.sid==="email"?"nome.sobrenome@empresa.com":a.sid==="linkus"?"(opcional)":"nome.sobrenome"}"></label>
          <label class="f">${esc(c?c.det:"Detalhe")}<input data-a="${i}" data-f="detalhe" value="${esc(a.detalhe)}" placeholder="${esc(c?c.ph:"Link, observação…")}"></label></div>
        ${cof?`<label class="toggle"><input type="checkbox" data-uc="${i}" ${a.usar_cofre?"checked":""}> Usar a senha guardada no cofre</label>`:""}
        <label class="f" ${a.usar_cofre?"hidden":""}>Senha${a.tem_senha?" (já gravada)":""}<div class="pw"><input data-a="${i}" data-f="senha" value="${esc(a.senha)}" autocomplete="off" spellcheck="false" placeholder="${a.tem_senha?"Em branco mantém a senha gravada":"Opcional — em branco sai uma linha para preencher à mão"}"><button type="button" class="btn small" data-gen="${i}" title="Gerar senha">🎲</button></div></label>
        ${a.tem_senha&&!a.usar_cofre?`<label class="toggle"><input type="checkbox" data-limpa="${i}"> Remover a senha gravada (linha em branco)</label>`:""}
      </div>`; }).join("") : `<div class="empty-acc">Toque nos acessos acima para adicioná-los ao termo.</div>`;
    $$("[data-f]",box).forEach(el=>el.oninput=()=>{ S.acessos[el.dataset.a][el.dataset.f]=el.value; if(el.dataset.f==="sistema") S.acessos[el.dataset.a].sid=""; update(); });
    $$("[data-rma]",box).forEach(b=>b.onclick=()=>{ S.acessos.splice(+b.dataset.rma,1); accForm(); update(); });
    $$("[data-gen]",box).forEach(b=>b.onclick=()=>{ S.acessos[b.dataset.gen].senha=gerarSenha(); accForm(); update(); });
    $$("[data-uc]",box).forEach(b=>b.onchange=()=>{ S.acessos[b.dataset.uc].usar_cofre=b.checked; accForm(); update(); });
    $$("[data-limpa]",box).forEach(b=>b.onchange=()=>{ const a=S.acessos[b.dataset.limpa]; a.tem_senha=!b.checked; a.limpar=b.checked; update(); });
  };
  bind(); itemsForm(); accForm(); aplicaTipo(); aplicaUnidade(); update();

  $$("#tipoPick .tipo-opt").forEach(b=>b.onclick=()=>{ S.tipo=b.dataset.tipo; aplicaTipo(); update(); });
  $$("#unidPick .chip").forEach(b=>b.onclick=()=>{
    const u = UNIDADES.find(u=>u.id===+b.dataset.un);
    if(+S.unidade_id===u.id){ S.unidade_id=null; S.unidade=""; } else { S.unidade_id=u.id; S.unidade=u.nome; }
    aplicaUnidade(); update(); });
  $$("#sysGrid .sys[data-sid]").forEach(b=>b.onclick=()=>{
    const sid=b.dataset.sid, i=S.acessos.findIndex(a=>a.sid===sid);
    if(i>=0) S.acessos.splice(i,1);
    else S.acessos.push({sid, sistema:catalogo(sid).nome, usuario:"", detalhe:"", senha:""});
    accForm(); update();
  });
  $("#btnOutro").onclick = ()=>{ S.acessos.push({sid:"", sistema:"", usuario:"", detalhe:"", senha:""}); accForm(); update(); $$("#accForm [data-f=sistema]").pop()?.focus(); };
  if($("#cofrePick")) $("#cofrePick").onchange = (ev)=>{
    const c = COFRE.find(x=>x.id===+ev.target.value); ev.target.value="";
    if(!c) return;
    S.acessos.push({sid:"", sistema:c.sistema, usuario:c.usuario||"", detalhe:c.url||"", senha:"", cofre_id:c.id, usar_cofre:true});
    accForm(); update();
  };
  $("#btnLogins").onclick = ()=>{
    const login = loginPadrao(S.nome); if(!login){ toast("Preencha o nome do colaborador primeiro"); return; }
    const dom = (EMPRESA && EMPRESA.dominioEmail) || "";
    const primeiro = sem_acento(S.nome.trim().split(/\s+/)[0]||"").toUpperCase();
    S.acessos.forEach(a=>{ if(a.usuario || a.cofre_id) return;
      if(a.sid==="email") a.usuario = dom ? `${login}@${dom}` : login;
      else if(a.sid==="dominio") a.usuario = primeiro;
      else if(a.sid==="linkus" || a.sid==="pasta") return;
      else a.usuario = login; });
    accForm(); update(); toast("Logins sugeridos — confira antes de salvar");
  };
  $("#btnSenhas").onclick = ()=>{ S.acessos.forEach(a=>{ if(!a.senha && !a.tem_senha && !a.usar_cofre && a.sid!=="pasta") a.senha=gerarSenha(); }); accForm(); update(); };
  $("#btnAddItem").onclick = ()=>{ S.itens.push({item:"",serie:"",qtd:1,estado:"Novo",obs:""}); itemsForm(); update(); };
  if($("#btnLimpar")) $("#btnLimpar").onclick = ()=>{ if(confirm("Limpar o formulário?")){ localStorage.removeItem(DRAFT_KEY); location.reload(); } };
  $("#btnSalvar").onclick = async ()=>{
    if(!S.nome.trim()){ toast("Informe o nome do colaborador"); $("[data-k=nome]").focus(); return; }
    if(UNIDADES.length && !S.unidade_id){ toast("Selecione a unidade"); return; }
    if(S.tipo!=="acessos" && !S.itens.some(i=>(i.item||"").trim())){ toast("Adicione pelo menos um item"); return; }
    if(S.tipo!=="equipamentos" && !S.acessos.some(a=>(a.sistema||"").trim())){ toast("Selecione pelo menos um acesso"); return; }
    const btn=$("#btnSalvar"); btn.disabled=true;
    try{
      const dados = JSON.parse(JSON.stringify(S));
      if(dados.tipo==="acessos") dados.itens = [];
      if(dados.tipo==="equipamentos") dados.acessos = [];
      const r = await fetch(CFG.url_salvar, {method:"POST", credentials:"same-origin",
        headers:{"Content-Type":"application/json","X-CSRF-Token":CFG.csrf}, body:JSON.stringify({dados})});
      const j = await r.json().catch(()=>({}));
      if(r.status===401){ location.href="/login"; return; }
      if(!r.ok) throw new Error(j.erro || "Não foi possível salvar.");
      if(!id) localStorage.removeItem(DRAFT_KEY);
      location.href = j.url;
    }catch(e){ toast(e.message); btn.disabled=false; }
  };
})();
