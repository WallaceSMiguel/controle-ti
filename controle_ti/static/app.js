(function () {
  "use strict";
  const csrf = document.querySelector('meta[name="csrf"]')?.content || "";
  const SEGUNDOS_VISIVEL = 20;
  const SEGUNDOS_AREA_TRANSF = 30;

  // ---------- aviso rápido
  let toastEl, toastTimer;
  function toast(texto) {
    if (!toastEl) {
      toastEl = document.createElement("div");
      toastEl.className = "toast";
      toastEl.setAttribute("role", "status");
      document.body.appendChild(toastEl);
    }
    toastEl.textContent = texto;
    toastEl.classList.add("visivel");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove("visivel"), 3200);
  }

  // ---------- busca a senha no servidor (cada acesso fica registrado na auditoria)
  async function buscarSenha(url, acao) {
    const resp = await fetch(url + (acao ? "?acao=" + acao : ""), {
      method: "POST",
      headers: { "X-CSRF-Token": csrf },
      credentials: "same-origin",
    });
    if (resp.status === 401) { location.href = "/login"; throw new Error("sessão"); }
    if (!resp.ok) throw new Error("Sem permissão para ver esta senha.");
    return (await resp.json()).senha;
  }

  async function copiarTexto(texto) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(texto);
      return;
    }
    const ta = document.createElement("textarea");
    ta.value = texto; ta.setAttribute("readonly", "");
    ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    document.execCommand("copy"); ta.remove();
  }

  document.addEventListener("click", async (ev) => {
    const revelar = ev.target.closest("[data-revelar]");
    const copiar = ev.target.closest("[data-copiar]");
    const gerar = ev.target.closest("[data-gerar]");
    const mostrar = ev.target.closest("[data-mostrar]");

    if (revelar) {
      const campo = revelar.closest(".senha-campo");
      const valor = campo.querySelector(".texto");
      if (campo.classList.contains("revelada")) { esconder(campo); return; }
      try {
        const senha = await buscarSenha(revelar.dataset.revelar);
        valor.textContent = senha;
        valor.classList.remove("pontos");
        campo.style.setProperty("--dur", SEGUNDOS_VISIVEL + "s");
        campo.classList.add("revelada");
        revelar.setAttribute("aria-label", "Ocultar senha");
        clearTimeout(campo._timer);
        campo._timer = setTimeout(() => esconder(campo), SEGUNDOS_VISIVEL * 1000);
      } catch (e) { toast(e.message); }
    }

    if (copiar) {
      try {
        const senha = await buscarSenha(copiar.dataset.copiar, "copiar");
        await copiarTexto(senha);
        toast(`Senha copiada. Ela será apagada da área de transferência em ${SEGUNDOS_AREA_TRANSF} s.`);
        setTimeout(() => { copiarTexto(" ").catch(() => {}); }, SEGUNDOS_AREA_TRANSF * 1000);
      } catch (e) { toast(e.message); }
    }

    if (gerar) {
      const alvo = document.querySelector(gerar.dataset.gerar);
      alvo.value = gerarSenha(20);
      alvo.type = "text";
      alvo.dispatchEvent(new Event("input"));
      toast("Senha forte gerada. Salve o formulário para gravar.");
    }

    if (mostrar) {
      const alvo = document.querySelector(mostrar.dataset.mostrar);
      alvo.type = alvo.type === "password" ? "text" : "password";
    }
  });

  function esconder(campo) {
    clearTimeout(campo._timer);
    const valor = campo.querySelector(".texto");
    valor.textContent = "••••••••••";
    valor.classList.add("pontos");
    campo.classList.remove("revelada");
  }

  function gerarSenha(tam) {
    const grupos = ["ABCDEFGHJKLMNPQRSTUVWXYZ", "abcdefghijkmnopqrstuvwxyz", "23456789", "!@#$%&*-_=+?"];
    const todos = grupos.join("");
    const rnd = (n) => { const a = new Uint32Array(1); crypto.getRandomValues(a); return a[0] % n; };
    const out = grupos.map((g) => g[rnd(g.length)]);
    while (out.length < tam) out.push(todos[rnd(todos.length)]);
    for (let i = out.length - 1; i > 0; i--) { const j = rnd(i + 1); [out[i], out[j]] = [out[j], out[i]]; }
    return out.join("");
  }

  // ---------- linhas clicáveis
  document.addEventListener("click", (ev) => {
    const tr = ev.target.closest("tr[data-href]");
    if (tr && !ev.target.closest("a, button, input, .senha-campo")) location.href = tr.dataset.href;
  });

  // ---------- confirmações
  document.addEventListener("submit", (ev) => {
    const msg = ev.target.dataset.confirmar;
    if (msg && !confirm(msg)) ev.preventDefault();
  });

  // ---------- filtros enviam ao mudar
  document.querySelectorAll("form.filtros select").forEach((s) =>
    s.addEventListener("change", () => s.form.submit()));

  // ---------- saída automática por inatividade
  const minutos = parseInt(document.body.dataset.timeout || "0", 10);
  if (minutos > 0) {
    let timer;
    const reiniciar = () => {
      clearTimeout(timer);
      timer = setTimeout(() => { location.href = "/logout"; }, minutos * 60 * 1000);
    };
    ["mousemove", "keydown", "click", "scroll", "touchstart"].forEach((e) =>
      document.addEventListener(e, reiniciar, { passive: true }));
    reiniciar();
  }

  // ---------- escolher o arquivo do msinfo32 já faz a leitura
  document.querySelectorAll("input[type=file][data-auto]").forEach((inp) =>
    inp.addEventListener("change", () => {
      if (!inp.files.length) return;
      const alvo = document.querySelector(inp.dataset.auto);
      if (!alvo) return;
      if (inp.form.requestSubmit) inp.form.requestSubmit(alvo); else alvo.click();
    }));
  document.querySelectorAll("form[data-carregando]").forEach((f) =>
    f.addEventListener("submit", () => {
      const b = f.querySelector("[data-carregando-btn]");
      if (b) { b.textContent = f.dataset.carregando; b.setAttribute("aria-busy", "true"); }
    }));

  // ---------- termos de responsabilidade
  document.querySelectorAll("[data-imprimir]").forEach((b) =>
    b.addEventListener("click", () => window.print()));

  const formTermo = document.querySelector("form[data-termo-form]");
  if (formTermo) {
    const aplicarTipo = () => {
      const tipo = (formTermo.querySelector("input[data-tipo]:checked") || {}).value || "equipamentos";
      formTermo.querySelectorAll("[data-so=eq]").forEach((el) => (el.hidden = tipo === "acessos"));
      formTermo.querySelectorAll("[data-so=acc]").forEach((el) => (el.hidden = tipo === "equipamentos"));
    };
    formTermo.querySelectorAll("input[data-tipo]").forEach((r) => r.addEventListener("change", aplicarTipo));
    aplicarTipo();

    formTermo.addEventListener("click", (ev) => {
      const add = ev.target.closest("[data-adicionar]");
      if (add) {
        const nome = add.dataset.adicionar;
        const modelo = formTermo.querySelector(`template[data-modelo="${nome}"]`);
        formTermo.querySelector(`[data-lista="${nome}"]`).appendChild(modelo.content.cloneNode(true));
      }
      const rem = ev.target.closest("[data-remover-linha]");
      if (rem) rem.closest("[data-linha]").remove();
      const ger = ev.target.closest("[data-gerar-linha]");
      if (ger) {
        const linha = ger.closest("[data-linha]");
        linha.querySelector("input[name=ac_senha]").value = gerarSenha(12);
        const og = linha.querySelector("select[data-origem]");
        if (og) og.value = "digitada";
      }
    });

    formTermo.addEventListener("change", (ev) => {
      const sel = ev.target;
      const linha = sel.closest("[data-linha]");
      if (!linha) return;
      const opt = sel.selectedOptions && sel.selectedOptions[0];
      if (sel.matches("select[data-equip]") && opt && opt.value) {
        linha.querySelector("input[name=item]").value = opt.dataset.item || "";
        linha.querySelector("input[name=serie]").value = opt.dataset.serie || "";
      }
      if (sel.matches("select[data-cofre]")) {
        const og = linha.querySelector("select[data-origem]");
        if (opt && opt.value) {
          linha.querySelector("input[name=ac_sistema]").value = opt.dataset.sistema || "";
          linha.querySelector("input[name=ac_usuario]").value = opt.dataset.usuario || "";
          linha.querySelector("input[name=ac_detalhe]").value = opt.dataset.detalhe || "";
          if (og) og.value = "cofre";
        } else if (og && og.value === "cofre") og.value = "digitada";
      }
    });

    const cpf = formTermo.querySelector("[data-mascara-cpf]");
    cpf && cpf.addEventListener("input", () => {
      const d = cpf.value.replace(/\D/g, "").slice(0, 11);
      cpf.value = d.replace(/^(\d{3})(\d)/, "$1.$2").replace(/^(\d{3})\.(\d{3})(\d)/, "$1.$2.$3")
        .replace(/\.(\d{3})(\d{1,2})$/, ".$1-$2");
    });
    const previa = document.getElementById("previa");
    previa && previa.scrollIntoView({ behavior: "smooth" });
  }

  // ---------- perfil admin desativa a lista de unidades
  const perfil = document.querySelector("#perfil");
  const todas = document.querySelector("#todas_unidades");
  const lista = document.querySelector("#lista-unidades");
  function syncUnidades() {
    if (!lista) return;
    const livre = (perfil && perfil.value === "admin") || (todas && todas.checked);
    lista.querySelectorAll("input").forEach((i) => (i.disabled = livre));
    lista.style.opacity = livre ? 0.45 : 1;
  }
  perfil && perfil.addEventListener("change", syncUnidades);
  todas && todas.addEventListener("change", syncUnidades);
  syncUnidades();
})();
