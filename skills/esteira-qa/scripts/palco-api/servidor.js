#!/usr/bin/env node
// Palco de API: serve a página de duas colunas (request | response) e executa DE VERDADE cada etapa do
// cenário, a pedido da página. Só Node 18+, sem dependências.
//
//   node servidor.js subir  --cenario <cenario.json> --pasta <work/api> [--porta N]
//   node servidor.js ensaio --cenario <cenario.json> --pasta <work/api> [--ate <etapa>]
//
// `subir` escuta só em 127.0.0.1 e imprime {"url": ...}. `ensaio` roda as etapas sem navegador e
// imprime o que cada uma respondeu. Toda troca vai para <pasta>/trocas.jsonl já mascarada.
// Segredos vêm do ambiente deste processo e nunca saem dele: na página, no log e no jsonl viram ••••.
'use strict'
const http = require('http')
const fs = require('fs')
const path = require('path')
const { execFile } = require('child_process')

const PAGINA = path.join(__dirname, 'pagina')
const MASCARA = '••••••'
const CHAVES_SENSIVEIS = ['authorization', 'proxy-authorization', 'cookie', 'set-cookie', 'x-api-key', 'api-key', 'apikey',
  'x-auth-token', 'private-key', 'password', 'senha', 'secret', 'client_secret', 'token', 'access_token', 'refresh_token',
  'cvv', 'securitycode', 'security_code', 'card_number', 'cardnumber', 'numero_cartao']
const PADROES_LOG = [
  /((?:authorization|bearer|token|api[_-]?key|apikey|password|senha|secret|private[_-]?key)["']?\s*[:=]\s*["']?)(?:(?:token|bearer|basic)\s+)?[^\s"',;}]+/gi,
  /\b(?:\d[ -]?){13,19}\b/g
]

function args (argv) {
  const r = { _: [] }
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith('--')) r[argv[i].slice(2)] = argv[i + 1]?.startsWith('--') || argv[i + 1] === undefined ? true : argv[++i]
    else r._.push(argv[i])
  }
  return r
}

function carregar (arquivo) {
  const c = JSON.parse(fs.readFileSync(arquivo, 'utf8'))
  if (!Array.isArray(c.etapas) || !c.etapas.length) throw new Error('cenário sem etapas')
  const ids = new Set()
  for (const e of c.etapas) {
    if (!/^[a-zA-Z0-9][\w.-]{0,63}$/.test(e.id || '')) throw new Error(`id de etapa inválido: ${e.id}`)
    if (ids.has(e.id)) throw new Error(`etapa repetida: ${e.id}`)
    ids.add(e.id)
    e.tipo = e.tipo || (e.fonte ? 'log' : e.troca ? 'captura' : 'http')
    if (e.tipo === 'http' && !e.request?.url) throw new Error(`etapa ${e.id} sem request.url`)
    if (e.tipo === 'captura' && (!e.arquivo || !e.troca)) throw new Error(`etapa ${e.id}: captura precisa de arquivo e troca`)
    if (e.tipo === 'log' && !c.fontes_log?.[e.fonte]) throw new Error(`etapa ${e.id}: fonte de log ${e.fonte} não declarada em fontes_log`)
  }
  for (const nome of c.segredos || []) {
    if (!(nome in process.env) && !c.etapas.some(e => e.capturar && nome in e.capturar)) {
      throw new Error(`segredo ${nome} não está no ambiente nem é capturado por uma etapa: exporte antes de subir`)
    }
  }
  return c
}

function criarPalco (cenario, pasta) {
  fs.mkdirSync(pasta, { recursive: true })
  const trocas = path.join(pasta, 'trocas.jsonl')
  const capturadas = {}
  const resultados = {}
  const segredos = new Set(cenario.segredos || [])
  const mascarar = new Set([...CHAVES_SENSIVEIS, ...(cenario.mascarar || []).map(s => s.toLowerCase())])

  const valor = (nome) => {
    if (nome in capturadas) return capturadas[nome]
    if (cenario.variaveis && nome in cenario.variaveis) return resolver(String(cenario.variaveis[nome]))
    if (nome in process.env) return process.env[nome]
    throw new Error(`variável {{${nome}}} sem valor: declare em variaveis, exporte no ambiente ou capture numa etapa anterior`)
  }
  const valoresSecretos = () => [...segredos].map(n => { try { return valor(n) } catch (_) { return '' } }).filter(v => v && v.length >= 4)

  const resolver = (x) => {
    if (typeof x === 'string') return x.replace(/\{\{\s*([A-Za-z_][\w]*)\s*\}\}/g, (_, n) => valor(n))
    if (Array.isArray(x)) return x.map(resolver)
    if (x && typeof x === 'object') return Object.fromEntries(Object.entries(x).map(([k, v]) => [k, resolver(v)]))
    return x
  }
  const tirarSegredos = (texto) => {
    let t = String(texto)
    for (const v of valoresSecretos()) t = t.split(v).join(MASCARA)
    return t
  }
  const mascararValor = (v) => typeof v === 'string' ? v.replace(/^((?:token|bearer|basic)\s+)?.*$/i, (_, p) => (p || '') + MASCARA) : MASCARA
  const mascararObj = (x) => {
    if (typeof x === 'string') return tirarSegredos(x)
    if (Array.isArray(x)) return x.map(mascararObj)
    if (x && typeof x === 'object') {
      return Object.fromEntries(Object.entries(x).map(([k, v]) =>
        [k, mascarar.has(k.toLowerCase()) && v !== null && v !== '' ? mascararValor(typeof v === 'object' ? '' : v) : mascararObj(v)]))
    }
    return x
  }
  const mascararLinha = (linha) => {
    let t = tirarSegredos(linha)
    for (const p of PADROES_LOG) t = t.replace(p, (m, prefixo) => (typeof prefixo === 'string' ? prefixo : '') + MASCARA)
    for (const extra of cenario.mascarar_log || []) t = t.replace(new RegExp(extra, 'g'), MASCARA)
    return t
  }

  const fonte = (nome) => resolver(cenario.fontes_log[nome])
  const inicioArquivos = {}
  for (const nome of Object.keys(cenario.fontes_log || {})) {
    const f = fonte(nome)
    if (f.arquivo) inicioArquivos[nome] = f.desde !== 'inicio' && fs.existsSync(f.arquivo) ? fs.statSync(f.arquivo).size : 0
  }

  const etapa = (id) => {
    const e = cenario.etapas.find(x => x.id === id)
    if (!e) throw new Error(`etapa desconhecida: ${id}`)
    return e
  }

  function montarRequest (e) {
    const r = resolver(e.request)
    const url = new URL(r.url)
    for (const [k, v] of Object.entries(r.query || {})) url.searchParams.set(k, String(v))
    const headers = { ...(r.headers || {}) }
    let corpo
    if (r.body !== undefined && r.body !== null) {
      if (typeof r.body === 'string') corpo = r.body
      else {
        corpo = JSON.stringify(r.body)
        if (!Object.keys(headers).some(h => h.toLowerCase() === 'content-type')) headers['Content-Type'] = 'application/json'
      }
    }
    return { method: (r.method || 'GET').toUpperCase(), url: url.toString(), query: r.query || {}, headers, body: r.body, corpo }
  }

  function preVisualizar (id) {
    const e = etapa(id)
    const base = { id: e.id, rotulo: e.rotulo || e.id, tipo: e.tipo, grupo: e.grupo || null, nota: e.nota || null, esperado: e.esperado || null }
    if (e.tipo === 'captura') {
      const t = lerCaptura(e)
      return { ...base, titulos: t.titulos || null, request: mascararObj(t.request) }
    }
    if (e.tipo === 'log') {
      const f = fonte(e.fonte)
      return { ...base, log: { fonte: e.fonte, descricao: f.descricao || null, origem: f.arquivo ? `arquivo ${path.basename(f.arquivo)}` : mascararLinha(f.comando.join(' ')), filtro: resolverOuModelo(e.filtro) || null, esperar: resolverOuModelo(e.esperar) || null } }
    }
    try {
      const r = montarRequest(e)
      return { ...base, request: { method: r.method, url: tirarSegredos(r.url), query: mascararObj(r.query), headers: mascararObj(r.headers), body: mascararObj(r.body ?? null) } }
    } catch (err) {
      return { ...base, request: { method: (e.request.method || 'GET').toUpperCase(), url: e.request.url, query: e.request.query || {}, headers: e.request.headers || {}, body: e.request.body ?? null }, pendente: String(err.message) }
    }
  }

  const resolverOuModelo = (x) => { try { return resolver(x) } catch (_) { return x } }

  const pegar = (obj, caminho) => caminho.split(/\.|\[(\d+)\]/).filter(Boolean).reduce((o, k) => (o == null ? undefined : o[k]), obj)

  function conferir (e, resposta) {
    const esp = e.esperado || {}
    const itens = []
    if (esp.status !== undefined) {
      const lista = [].concat(esp.status)
      itens.push({ campo: 'status', esperado: esp.status, obtido: resposta.status, ok: lista.includes(resposta.status) })
    }
    for (const [caminho, v] of Object.entries(esp.campos || {})) {
      const obtido = pegar(resposta, caminho)
      itens.push({ campo: caminho, esperado: v, obtido, ok: JSON.stringify(obtido) === JSON.stringify(v) })
    }
    for (const caminho of [].concat(esp.existe || [])) {
      const obtido = pegar(resposta, caminho)
      const ok = obtido !== undefined && obtido !== null && obtido !== ''
      itens.push({ campo: caminho, esperado: 'presente', obtido: ok ? 'presente' : 'ausente', ok })
    }
    if (esp.contem) {
      const ok = (resposta.linhas || []).some(l => new RegExp(esp.contem).test(l.texto))
      itens.push({ campo: 'log', esperado: esp.contem, obtido: ok ? 'encontrado' : 'ausente', ok })
    }
    return { itens, ok: itens.every(i => i.ok) }
  }

  async function executarHttp (e) {
    const r = montarRequest(e)
    const t0 = Date.now()
    const timeout = (e.timeout_s || cenario.timeout_s || 30) * 1000
    let resposta
    try {
      const res = await fetch(r.url, { method: r.method, headers: r.headers, body: r.corpo, redirect: 'manual', signal: AbortSignal.timeout(timeout) })
      const texto = await res.text()
      const headers = Object.fromEntries(res.headers.entries())
      let body = texto
      if (/json/i.test(headers['content-type'] || '') || /^\s*[[{]/.test(texto)) { try { body = JSON.parse(texto) } catch (_) {} }
      if (typeof body === 'string' && body.length > 20000) body = body.slice(0, 20000) + '\n… (cortado)'
      resposta = { status: res.status, statusText: res.statusText, headers, body, ms: Date.now() - t0, bytes: Buffer.byteLength(texto) }
    } catch (err) {
      resposta = { status: 0, statusText: 'sem resposta', headers: {}, body: null, ms: Date.now() - t0, bytes: 0, erro: err.name === 'TimeoutError' ? `timeout de ${timeout / 1000}s` : String(err.cause?.code || err.cause?.errors?.[0]?.code || err.cause?.message || err.message) }
    }
    for (const [nome, caminho] of Object.entries(e.capturar || {})) {
      const v = pegar(resposta, caminho)
      if (v !== undefined && v !== null) capturadas[nome] = String(v)
    }
    return {
      request: { method: r.method, url: tirarSegredos(r.url), query: mascararObj(r.query), headers: mascararObj(r.headers), body: mascararObj(r.body ?? null) },
      response: { ...resposta, headers: mascararObj(resposta.headers), body: mascararObj(resposta.body) }
    }
  }

  function lerFonte (nome) {
    const f = fonte(nome)
    if (f.arquivo) {
      return new Promise((resolve) => {
        if (!fs.existsSync(f.arquivo)) return resolve('')
        const fd = fs.openSync(f.arquivo, 'r')
        const tam = fs.fstatSync(fd).size
        const de = Math.max(inicioArquivos[nome] || 0, tam - 2 * 1024 * 1024)
        const buf = Buffer.alloc(Math.max(0, tam - de))
        fs.readSync(fd, buf, 0, buf.length, de)
        fs.closeSync(fd)
        resolve(buf.toString('utf8'))
      })
    }
    return new Promise((resolve, reject) => {
      execFile(f.comando[0], f.comando.slice(1), { timeout: 30000, maxBuffer: 32 * 1024 * 1024 }, (err, stdout, stderr) => {
        if (err) reject(new Error(`fonte ${nome} falhou: ${mascararLinha(String(stderr || err.message)).slice(0, 400)}`))
        else resolve(stdout)
      })
    })
  }

  async function executarLog (modelo) {
    const e = { ...modelo, filtro: resolver(modelo.filtro), destacar: resolver(modelo.destacar), esperar: resolver(modelo.esperar) }
    const t0 = Date.now()
    const filtro = e.filtro ? new RegExp(e.filtro, 'i') : null
    const alvo = e.esperar?.regex ? new RegExp(e.esperar.regex, 'i') : null
    const limite = (e.esperar?.timeout_s || 0) * 1000
    let linhas = []
    for (;;) {
      const texto = await lerFonte(e.fonte)
      linhas = texto.split('\n').filter(l => l.trim() && (!filtro || filtro.test(l)))
      if (!alvo || linhas.some(l => alvo.test(l)) || Date.now() - t0 >= limite) break
      await new Promise(r => setTimeout(r, 1000))
    }
    const destaque = e.destacar ? new RegExp(e.destacar, 'i') : alvo
    linhas = linhas.slice(-(e.linhas || 40)).map(l => ({ texto: mascararLinha(l), destaque: !!(destaque && destaque.test(l)) }))
    const encontrou = alvo ? linhas.some(l => alvo.test(l.texto)) : null
    return { log: { fonte: e.fonte, linhas, ms: Date.now() - t0, encontrou, esgotou: alvo ? !encontrou : false } }
  }

  function lerCaptura (e) {
    const arquivo = resolver(e.arquivo)
    const trocas = JSON.parse(fs.readFileSync(arquivo, 'utf8'))
    const t = trocas[resolver(e.troca)]
    if (!t) throw new Error(`troca ${e.troca} não existe em ${path.basename(arquivo)}`)
    return t
  }

  function executarCaptura (e) {
    const t = lerCaptura(e)
    const texto = JSON.stringify(t.response?.body ?? '')
    for (const [nome, caminho] of Object.entries(e.capturar || {})) {
      const v = pegar(t.response || {}, caminho)
      if (v !== undefined && v !== null) capturadas[nome] = String(v)
    }
    return {
      request: mascararObj(t.request),
      response: { headers: {}, ...mascararObj(t.response || {}), ms: null, bytes: Buffer.byteLength(texto) },
      captura: { em: t.em || null, origem: t.origem || null }
    }
  }

  async function executar (id) {
    const e = etapa(id)
    const em = new Date().toISOString()
    let troca
    try {
      troca = e.tipo === 'log' ? await executarLog(e) : e.tipo === 'captura' ? executarCaptura(e) : await executarHttp(e)
    } catch (err) {
      troca = { erro: mascararLinha(String(err.message)) }
    }
    const confere = conferir(e, troca.response || { linhas: troca.log?.linhas })
    if (troca.erro) confere.ok = false
    if (troca.response?.erro && ![].concat(e.esperado?.status).includes(0)) confere.ok = false
    resultados[id] = { em, ...troca, confere }
    fs.appendFileSync(trocas, JSON.stringify({ etapa: id, rotulo: e.rotulo || id, grupo: e.grupo || null, ...resultados[id] }) + '\n')
    return resultados[id]
  }

  function resumo (e) {
    if (e.tipo === 'log') return `log · ${e.fonte}`
    if (e.tipo === 'captura') {
      try {
        const r = lerCaptura(e).request
        return `${r.method} ${r.url.replace(/^[a-z]+:\/\/[^/]+/i, '').split('?')[0]}`
      } catch (_) { return 'captura' }
    }
    const caminho = e.request.url.replace(/^\{\{\s*\w+\s*\}\}/, '').replace(/^[a-z]+:\/\/[^/]+/i, '').split('?')[0] || '/'
    return `${(e.request.method || 'GET').toUpperCase()} ${caminho}`
  }

  function publico () {
    return {
      titulo: cenario.titulo || 'Cenário de API',
      descricao: cenario.descricao || '',
      ambiente: cenario.ambiente || '',
      grupos: cenario.grupos || {},
      etapas: cenario.etapas.map(e => ({ id: e.id, rotulo: e.rotulo || e.id, tipo: e.tipo, grupo: e.grupo || null, resumo: resumo(e) })),
      resultados
    }
  }

  return { executar, preVisualizar, publico }
}

const TIPOS = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8' }

function subir (palco, porta) {
  const servidor = http.createServer(async (req, res) => {
    const json = (codigo, dado) => { res.writeHead(codigo, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }); res.end(JSON.stringify(dado)) }
    try {
      const url = new URL(req.url, 'http://palco')
      if (url.pathname === '/__cenario') return json(200, palco.publico())
      const m = url.pathname.match(/^\/__(etapa|executar)\/([\w.-]+)$/)
      if (m && m[1] === 'etapa') return json(200, palco.preVisualizar(m[2]))
      if (m && m[1] === 'executar' && req.method === 'POST') return json(200, await palco.executar(m[2]))
      const nome = url.pathname === '/' ? 'index.html' : path.basename(url.pathname)
      const arquivo = path.join(PAGINA, nome)
      if (!TIPOS[path.extname(nome)] || !fs.existsSync(arquivo)) return json(404, { erro: 'não encontrado' })
      res.writeHead(200, { 'Content-Type': TIPOS[path.extname(nome)], 'Cache-Control': 'no-store' })
      fs.createReadStream(arquivo).pipe(res)
    } catch (err) {
      console.error(err)
      json(500, { erro: String(err.message) })
    }
  })
  servidor.listen(Number(porta) || 0, '127.0.0.1', () => {
    console.log(JSON.stringify({ url: `http://127.0.0.1:${servidor.address().port}/`, pid: process.pid }))
  })
}

async function ensaio (palco, cenario, ate) {
  const linhas = []
  for (const e of cenario.etapas) {
    const r = await palco.executar(e.id)
    const s = r.response ? `${r.response.status} ${r.response.statusText || ''}`.trim() : r.log ? `${r.log.linhas.length} linhas${r.log.esgotou ? ' (esperou e não achou)' : ''}` : r.erro
    linhas.push({ etapa: e.id, resultado: s, confere: r.confere.ok, divergencias: r.confere.itens.filter(i => !i.ok) })
    if (e.id === ate) break
  }
  console.log(JSON.stringify(linhas, null, 2))
  process.exit(linhas.every(l => l.confere) ? 0 : 1)
}

if (require.main === module) {
  const a = args(process.argv.slice(2))
  const acao = a._[0]
  if (!['subir', 'ensaio'].includes(acao) || !a.cenario || !a.pasta) {
    console.error('uso: servidor.js subir|ensaio --cenario <cenario.json> --pasta <dir> [--porta N] [--ate etapa]')
    process.exit(2)
  }
  const cenario = carregar(a.cenario)
  const palco = criarPalco(cenario, a.pasta)
  if (acao === 'subir') subir(palco, a.porta)
  else ensaio(palco, cenario, a.ate)
}

module.exports = { carregar, criarPalco }
