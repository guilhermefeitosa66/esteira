#!/usr/bin/env node
// Alvo de brinquedo do exemplo do palco de API: uma API de tarefas com login e um "worker" que conclui a
// tarefa em segundo plano e escreve no log. Só existe para ensaiar o palco sem depender de projeto nenhum.
//
//   node alvo.js <porta> <arquivo-de-log>
'use strict'
const http = require('http')
const fs = require('fs')
const crypto = require('crypto')

const porta = Number(process.argv[2] || 18080)
const logArq = process.argv[3] || 'alvo.log'
const tarefas = {}
const TOKEN = crypto.randomBytes(12).toString('hex')
const escrever = (linha) => fs.appendFileSync(logArq, `${new Date().toISOString()} ${linha}\n`)
fs.writeFileSync(logArq, '')

http.createServer((req, res) => {
  let corpo = ''
  req.on('data', c => { corpo += c })
  req.on('end', () => {
    const responder = (status, dados) => {
      res.writeHead(status, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify(dados))
    }
    const json = (() => { try { return JSON.parse(corpo || '{}') } catch (_) { return null } })()
    if (req.method === 'POST' && req.url === '/api/login') {
      if (json?.password !== process.env.SENHA_ALVO) return responder(401, { detail: 'credenciais inválidas' })
      return responder(200, { token: TOKEN, user: { email: json.email } })
    }
    if (req.headers.authorization !== `Token ${TOKEN}`) return responder(401, { detail: 'sem autenticação' })
    if (req.method === 'POST' && req.url === '/api/tarefas') {
      if (!json?.titulo) return responder(400, { titulo: ['campo obrigatório'] })
      const id = crypto.randomUUID().slice(0, 8)
      tarefas[id] = { id, titulo: json.titulo, status: 'PENDENTE' }
      escrever(`[worker] tarefa ${id} recebida`)
      setTimeout(() => escrever(`[worker] tarefa ${id} processando token=${TOKEN}`), 800)
      setTimeout(() => { tarefas[id].status = 'CONCLUIDA'; escrever(`[worker] tarefa ${id} CONCLUIDA em 1.6s`) }, 1600)
      return responder(201, tarefas[id])
    }
    const m = req.url.match(/^\/api\/tarefas\/(\w+)$/)
    if (req.method === 'GET' && m) return tarefas[m[1]] ? responder(200, tarefas[m[1]]) : responder(404, { detail: 'não encontrada' })
    responder(404, { detail: 'rota inexistente' })
  })
}).listen(porta, '127.0.0.1')
