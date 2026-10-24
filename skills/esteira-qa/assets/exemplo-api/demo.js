// Tomada narrada do exemplo. Roda na pasta work da gravação (onde está o playwright-core):
//   SK=<pasta da skill> V=<work>/video node demo.js
const path = require('path')
const api = require(path.join(process.env.SK, 'scripts/palco-api/api-lib.js'))
;(async () => {
  const a = await api.iniciar({ video: process.env.V, display: process.env.QA_DISPLAY, cdp: process.env.CDP })
  await a.cena('abertura', async () => { await a.apontar('#etapas') })
  await a.cena('login', async () => { await a.destacar('req.body.password'); await a.enviar(); await a.destacar('res.status') }, async () => { await a.mostrar('login') })
  await a.cena('criar-req', async () => { await a.destacar('req.body.titulo') }, async () => { await a.mostrar('criar') })
  await a.cena('criar-res', async () => { await a.enviar(); await a.destacar('res.status'); await a.pausa(1200); await a.destacar('res.body.status') })
  await a.cena('worker', async () => { await a.enviar(); await a.destacar('log:recebida'); await a.pausa(2000); await a.destacar('log:CONCLUIDA') }, async () => { await a.mostrar('worker') })
  await a.cena('consultar', async () => { await a.enviar(); await a.destacar('res.body.status') }, async () => { await a.mostrar('consultar') })
  await a.cena('fechamento', async () => { await a.apontar('#etapas') })
  await a.fim()
})().catch(e => { console.error(e); process.exit(1) })
