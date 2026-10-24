// Tomada narrada do palco de API, sobre o demo-lib.js: o cursor real vai até o botão Enviar e até o
// trecho que a fala cita. Roda em <gravação>/work, onde está o playwright-core.
//
//   const api = require('<skill>/scripts/palco-api/api-lib.js')
//   const a = await api.iniciar({ video: process.env.V, display: process.env.QA_DISPLAY, cdp: process.env.CDP })
//   await a.cena('login-req', async () => { await a.destacar('req.body') }, async () => { await a.mostrar('login') })
//   await a.cena('login-res', async () => { await a.enviar(); await a.destacar('res.status') })
//   await a.fim()
'use strict'
const path = require('path')
const demo = require(path.join(__dirname, '..', 'demo-lib.js'))

async function iniciar (opcoes) {
  const d = await demo.iniciar(opcoes)
  const { page } = d
  await page.waitForFunction(() => document.body.dataset.pronto === '1', null, { timeout: 15000 })

  async function mostrar (id) {
    await page.evaluate(i => window.palco.mostrar(i), id)
    await d.pausa(400)
  }

  async function enviar ({ timeout = 180000 } = {}) {
    const id = await page.evaluate(() => window.palco.estado().atual)
    await d.clicar('#enviar')
    await page.waitForFunction(i => !window.palco.estado().enviando && window.palco.estado().resultados[i], id, { timeout })
    await d.pausa(350)
    return page.evaluate(i => window.palco.estado().resultados[i], id)
  }

  // `caminho`: req.url, req.headers.<nome>, req.query.<chave>, req.body.<a.b[0]>, res.status,
  // res.headers.<nome>, res.body.<...> ou log:<regex>. Sem nada para destacar, a tomada quebra.
  async function destacar (caminho, { apontar = true, manter = false } = {}) {
    const n = await page.evaluate(([c, m]) => window.palco.destacar(c, { manter: m }), [caminho, manter])
    if (!n) throw new Error(`nada para destacar em ${caminho}`)
    await d.pausa(500)
    if (!apontar) return n
    const alvo = page.locator('.destaque, .destaque-bloco').first()
    const caixa = await alvo.boundingBox()
    const bloco = await alvo.evaluate(el => el.classList.contains('destaque-bloco'))
    if (caixa && bloco) await d.apontar(alvo, { dx: -caixa.width / 2 + 8, dy: caixa.height / 2 + 14 })
    else if (caixa) await d.apontar(alvo, { dx: Math.min(0, -caixa.width / 2 + 26), dy: 4 })
    return n
  }

  return { ...d, mostrar, enviar, destacar, limpar: () => page.evaluate(() => window.palco.limpar()) }
}

module.exports = { iniciar }
