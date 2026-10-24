'use strict'
;(() => {
  const $ = (id) => document.getElementById(id)
  const esc = (s) => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
  const OCULTO = '••••••'
  const LIMITE_STRING = 96
  const TRANSPORTE = new Set(['connection', 'keep-alive', 'transfer-encoding'])
  let cenario = null
  let atual = null
  let previa = null
  let enviando = false

  const valorHtml = (v) => {
    if (v === null) return '<span class="b">null</span>'
    if (typeof v === 'boolean') return `<span class="b">${v}</span>`
    if (typeof v === 'number') return `<span class="n">${v}</span>`
    let s = String(v)
    if (s.includes(OCULTO)) return `<span class="s">"${esc(s).split(OCULTO).join(`<span class="oculto">${OCULTO}</span>`)}"</span>`
    if (s.length > LIMITE_STRING) s = `${s.slice(0, LIMITE_STRING)}… (${s.length} caracteres)`
    return `<span class="s">"${esc(s)}"</span>`
  }

  function linhasJson (valor, raiz) {
    const linhas = []
    const ir = (v, caminho, nivel, chave, ultimo) => {
      const pre = '  '.repeat(nivel) + (chave === null ? '' : `<span class="k">"${esc(chave)}"</span><span class="p">: </span>`)
      const virgula = ultimo ? '' : '<span class="p">,</span>'
      if (v && typeof v === 'object') {
        const lista = Array.isArray(v)
        const filhos = lista ? v.map((x, i) => [i, x]) : Object.entries(v)
        const [abre, fecha] = lista ? ['[', ']'] : ['{', '}']
        if (!filhos.length) return linhas.push({ html: `${pre}<span class="p">${abre}${fecha}</span>${virgula}`, caminho })
        linhas.push({ html: `${pre}<span class="p">${abre}</span>`, caminho })
        filhos.forEach(([k, x], i) => ir(x, lista ? `${caminho}[${k}]` : `${caminho}.${k}`, nivel + 1, lista ? null : k, i === filhos.length - 1))
        return linhas.push({ html: `${'  '.repeat(nivel)}<span class="p">${fecha}</span>${virgula}`, caminho })
      }
      linhas.push({ html: pre + valorHtml(v) + virgula, caminho })
    }
    ir(valor, raiz, 0, null, true)
    return linhas
  }

  const linhasTexto = (texto, raiz) => String(texto).split('\n').map(l => ({ html: `<span class="s">${esc(l)}</span>`, caminho: raiz }))
  const linhasPares = (obj, raiz, sep, classeChave) => Object.entries(obj || {}).map(([k, v]) => ({
    html: `<span class="${classeChave}">${esc(k)}</span><span class="p">${sep}</span>${String(v).includes(OCULTO) ? esc(String(v)).split(OCULTO).join(`<span class="oculto">${OCULTO}</span>`) : esc(v)}`,
    caminho: `${raiz}.${k.toLowerCase()}`
  }))

  const blocoCodigo = (linhas, compacto) => `<div class="codigo${compacto ? ' compacto' : ''}">${linhas.map((l, i) =>
    `<div class="ln" data-caminho="${esc(l.caminho)}"><span class="g">${i + 1}</span><span>${l.html}</span></div>`).join('')}</div>`

  const secao = (titulo, conteudo, qtd) => `<div class="secao"><header>${esc(titulo)}${qtd !== undefined ? `<span class="qtd">${qtd}</span>` : ''}</header>${conteudo}</div>`

  const corpoLinhas = (body, raiz) => (body !== null && typeof body === 'object') ? linhasJson(body, raiz) : linhasTexto(body, raiz)

  function urlHtml (metodo, url) {
    let host = ''
    let resto = url
    try { const u = new URL(url); if (u.origin !== 'null') { host = u.origin; resto = url.slice(host.length) } } catch (_) {}
    return `<div class="linha-url" data-caminho="req.url"><span class="metodo m-${esc(metodo)}">${esc(metodo)}</span><span><span class="host">${esc(host)}</span>${esc(resto).split(OCULTO).join(`<span class="oculto">${OCULTO}</span>`)}</span></div>`
  }

  function renderRequest (r) {
    let h = urlHtml(r.method, r.url)
    if (r.query && Object.keys(r.query).length) h += secao('Query', blocoCodigo(linhasPares(r.query, 'req.query', ' = ', 'k')), Object.keys(r.query).length)
    if (r.headers && Object.keys(r.headers).length) h += secao('Headers', blocoCodigo(linhasPares(r.headers, 'req.headers', ': ', 'h'), true), Object.keys(r.headers).length)
    if (r.body !== null && r.body !== undefined) h += secao('Body', blocoCodigo(corpoLinhas(r.body, 'req.body')))
    return h
  }

  function renderFonte (log) {
    let h = secao('Fonte', blocoCodigo([
      { html: `<span class="k">fonte</span><span class="p">: </span><span class="s">${esc(log.fonte)}</span>`, caminho: 'log.fonte' },
      ...(log.descricao ? [{ html: `<span class="k">o que é</span><span class="p">: </span>${esc(log.descricao)}`, caminho: 'log.descricao' }] : []),
      { html: `<span class="k">origem</span><span class="p">: </span>${esc(log.origem)}`, caminho: 'log.origem' }
    ]))
    if (log.filtro) h += secao('Filtro', blocoCodigo([{ html: `<span class="s">/${esc(log.filtro)}/i</span>`, caminho: 'log.filtro' }]))
    if (log.esperar) h += secao('Espera', blocoCodigo([{ html: `<span class="p">até aparecer </span><span class="s">/${esc(log.esperar.regex)}/i</span><span class="p"> · no máximo </span><span class="n">${esc(log.esperar.timeout_s || 0)}s</span>`, caminho: 'log.esperar' }]))
    return h
  }

  const kb = (n) => n < 1024 ? `${n} B` : `${(n / 1024).toFixed(1)} kB`

  function renderConfere (confere) {
    if (!confere || !confere.itens.length) return ''
    return `<div class="confere">${confere.itens.map(i => `<span class="${i.ok ? 'ok' : 'nao'}">${i.ok ? '✓' : '✗'} ${esc(i.campo)}: esperado ${esc(JSON.stringify(i.esperado))}${i.ok ? '' : ` · veio ${esc(JSON.stringify(i.obtido))}`}</span>`).join('')}</div>`
  }

  function renderResultado (r) {
    const dir = $('dir')
    const medidas = $('medidas')
    if (r.erro) {
      medidas.innerHTML = '<span class="status s0">erro</span>'
      dir.innerHTML = `<div class="entra"><div class="erro">${esc(r.erro)}</div>${renderConfere(r.confere)}</div>`
      return
    }
    if (r.log) {
      medidas.innerHTML = `<span>${r.log.linhas.length} linhas</span><span>${(r.log.ms / 1000).toFixed(1)} s</span>`
      const espera = r.log.esgotou ? '<div class="erro">o trecho esperado não apareceu dentro do tempo</div>' : ''
      const linhas = r.log.linhas.length
        ? `<div class="codigo log">${r.log.linhas.map((l, i) => `<div class="ln${l.destaque ? ' destaque' : ''}" data-caminho="log.linha"><span class="g">${i + 1}</span><span>${esc(l.texto)}</span></div>`).join('')}</div>`
        : '<div class="erro">nenhuma linha do log passou no filtro</div>'
      dir.innerHTML = `<div class="entra">${renderConfere(r.confere)}${espera}${secao('Log', linhas)}</div>`
      const primeiro = dir.querySelector('.ln.destaque')
      if (primeiro) primeiro.scrollIntoView({ block: 'center' })
      return
    }
    const res = r.response
    const temStatus = typeof res.status === 'number'
    const classe = temStatus ? `s${String(res.status).charAt(0)}` : 's3'
    const selo = temStatus ? `${res.status || '—'} ${esc(res.statusText || '')}` : esc(res.statusText || 'estado')
    const tempo = r.captura ? `<span>capturado ${esc((r.captura.em || '').replace(/^.*T(\d\d:\d\d:\d\d).*$/, '$1'))}</span>` : `<span>${res.ms} ms</span>`
    medidas.innerHTML = `<span class="status ${classe}" data-caminho="res.status">${selo}</span>${tempo}<span>${kb(res.bytes)}</span>`
    let h = renderConfere(r.confere)
    if (res.erro) h += `<div class="erro">${esc(res.erro)}</div>`
    const headers = Object.fromEntries(Object.entries(res.headers).filter(([k]) => !TRANSPORTE.has(k.toLowerCase())))
    if (Object.keys(headers).length) h += secao('Headers', blocoCodigo(linhasPares(headers, 'res.headers', ': ', 'h'), true), Object.keys(headers).length)
    if (res.body !== null && res.body !== '') h += secao('Body', blocoCodigo(corpoLinhas(res.body, 'res.body')))
    dir.innerHTML = `<div class="entra">${h}</div>`
  }

  function renderEtapas () {
    const etapaAtual = cenario.etapas.find(e => e.id === atual)
    const grupo = etapaAtual?.grupo || null
    const visiveis = grupo ? cenario.etapas.filter(e => e.grupo === grupo) : cenario.etapas
    const g = $('grupo')
    if (grupo) {
      const grupos = [...new Set(cenario.etapas.map(e => e.grupo).filter(Boolean))]
      const info = cenario.grupos[grupo] || {}
      g.hidden = false
      g.innerHTML = `<b>${esc(grupo)}</b>${info.titulo ? ` · ${esc(info.titulo)}` : ''}<span class="contador">${grupos.indexOf(grupo) + 1}/${grupos.length}</span>`
    } else g.hidden = true
    $('etapas').innerHTML = visiveis.map((e, i) => {
      const r = cenario.resultados[e.id]
      const neutro = r && !r.confere.itens.length && !r.erro
      const estado = [e.id === atual ? 'atual' : '', r ? (neutro ? 'neutro' : r.confere.ok ? 'ok' : 'falha') : ''].join(' ')
      let sub = e.resumo || e.tipo
      if (r?.response) sub = r.captura ? `${r.response.status ?? r.response.statusText ?? ''} · capturado` : `${r.response.status || 'sem resposta'} · ${r.response.ms} ms`
      if (r?.log) sub = `${r.log.linhas.length} linhas de log`
      if (r?.erro) sub = 'erro'
      const marca = r ? (neutro ? '•' : r.confere.ok ? '✓' : '✗') : i + 1
      return `<li class="${estado}" data-etapa="${esc(e.id)}"><span class="n">${marca}</span><span class="r"><b>${esc(e.rotulo)}</b><small>${esc(sub)}</small></span></li>`
    }).join('')
  }

  function renderNota (p) {
    const info = (p.grupo && cenario.grupos[p.grupo]) || {}
    const texto = p.nota || (info.esperado ? `Esperado: ${info.esperado}` : '')
    $('nota').hidden = !texto
    $('nota').textContent = texto
  }

  async function mostrar (id) {
    const r = await fetch(`/__etapa/${encodeURIComponent(id)}`)
    previa = await r.json()
    if (previa.erro) throw new Error(previa.erro)
    atual = id
    const log = previa.tipo === 'log'
    const titulos = previa.titulos || (log ? ['Fonte do log', 'Log'] : ['Request', 'Response'])
    $('esq-titulo').textContent = titulos[0]
    $('dir-titulo').textContent = titulos[1]
    $('enviar').querySelector('.rotulo').textContent = log ? 'Coletar log' : previa.tipo === 'captura' ? 'Ver resposta' : 'Enviar'
    $('esq').innerHTML = `<div class="entra">${log ? renderFonte(previa.log) : renderRequest(previa.request)}</div>`
    $('esq').scrollTop = 0
    $('dir').scrollTop = 0
    const resultado = cenario.resultados[id]
    if (resultado) renderResultado(resultado)
    else {
      $('medidas').innerHTML = ''
        $('dir').innerHTML = `<div class="vazio">${log ? 'Colete o log para ver o trecho' : previa.tipo === 'captura' ? 'Abra a resposta capturada' : 'Envie a request para ver a resposta'}</div>`
    }
    $('enviar').disabled = false
    renderEtapas()
    renderNota(previa)
    return previa
  }

  async function enviar () {
    if (!atual || enviando) return null
    enviando = true
    const botao = $('enviar')
    botao.classList.add('enviando')
    botao.disabled = true
    if (previa.tipo === 'log') {
      $('dir').innerHTML = `<div class="aguardando">lendo ${esc(previa.log.fonte)}${previa.log.esperar ? ` e esperando /${esc(previa.log.esperar.regex)}/` : ''}…</div>`
    }
    try {
      const r = await fetch(`/__executar/${encodeURIComponent(atual)}`, { method: 'POST' })
      const resultado = await r.json()
      cenario.resultados[atual] = resultado
      if (resultado.request) $('esq').innerHTML = `<div>${renderRequest(resultado.request)}</div>`
      renderResultado(resultado)
      renderEtapas()
      return resultado
    } finally {
      enviando = false
      botao.classList.remove('enviando')
      botao.disabled = false
    }
  }

  function limpar () {
    document.querySelectorAll('.destaque').forEach(el => el.classList.remove('destaque'))
    document.querySelectorAll('.destaque-bloco').forEach(el => el.classList.remove('destaque-bloco'))
  }

  function destacar (caminho, { manter = false } = {}) {
    if (!manter) limpar()
    if (caminho === 'res.status' || caminho === 'req.url') {
      const el = document.querySelector(`[data-caminho="${caminho}"]`)
      if (!el) return 0
      el.classList.add('destaque-bloco')
      return 1
    }
    if (caminho.startsWith('log:')) {
      const re = new RegExp(caminho.slice(4), 'i')
      const linhas = [...document.querySelectorAll('#dir .log .ln')].filter(l => re.test(l.textContent))
      linhas.forEach(l => l.classList.add('destaque'))
      if (linhas[0]) linhas[0].scrollIntoView({ block: 'center' })
      return linhas.length
    }
    const alvo = caminho.toLowerCase()
    const linhas = [...document.querySelectorAll('.ln[data-caminho]')].filter(l => {
      const c = l.dataset.caminho.toLowerCase()
      return c === alvo || c.startsWith(`${alvo}.`) || c.startsWith(`${alvo}[`)
    })
    linhas.forEach(l => l.classList.add('destaque'))
    if (linhas[0]) linhas[0].scrollIntoView({ block: 'center' })
    return linhas.length
  }

  async function iniciar () {
    cenario = await (await fetch('/__cenario')).json()
    document.title = cenario.titulo
    $('titulo').textContent = cenario.titulo
    $('descricao').textContent = cenario.descricao
    const amb = $('ambiente')
    amb.textContent = cenario.ambiente || 'ambiente não informado'
    amb.className = `ambiente ${(cenario.ambiente || '').toLowerCase().match(/local|dev|prod/)?.[0] || ''}`
    await mostrar(cenario.etapas[0].id)
    $('enviar').addEventListener('click', () => { enviar().catch(e => console.error(e)) })
    document.addEventListener('keydown', ev => { if (ev.key === 'Enter') enviar().catch(e => console.error(e)) })
    document.body.dataset.pronto = '1'
  }

  window.palco = { mostrar, enviar, destacar, limpar, estado: () => ({ atual, enviando, resultados: cenario.resultados }) }
  iniciar().catch(e => { document.body.dataset.pronto = 'erro'; console.error(e) })
})()
