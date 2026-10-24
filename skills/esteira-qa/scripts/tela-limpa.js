// Trava "nada na frente": confere que o display da rodada mostra só a página, sem balão do navegador
// (salvar senha, tradução, permissão, restaurar sessão) nem outra janela por cima. Compara o que a
// câmera vê (captura do display por ffmpeg x11grab, sem o cursor) com o que a página desenha
// (page.screenshot por CDP, que nunca inclui a interface do navegador). Balão do Chrome é desenhado
// dentro da janela dele, não é janela X à parte: só a comparação de imagem o enxerga.
//
//   cd $RUN/work && QA_DISPLAY=:90 CDP=http://127.0.0.1:<porta> node <skill>/scripts/tela-limpa.js [pasta]
//
// Rodar antes de começar a gravar e no fim de cada tomada. Saída JSON; código 1 = tem algo na frente
// (as duas imagens ficam na pasta para olhar), 0 = limpa, 2 = não conseguiu medir.
const { execFileSync, spawnSync } = require('child_process')
const fs = require('fs')
const path = require('path')
const { chromium } = require(require.resolve('playwright-core', { paths: [process.cwd()] }))

// Fração de pixels que pode diferir (antisserrilhado, cursor de texto piscando). Balão de verdade passa de 1%.
const LIMITE = Number(process.env.LIMITE_DIFERENCA || 0.002)

;(async () => {
  const display = process.env.QA_DISPLAY
  if (!display || display === process.env.DISPLAY) throw new Error('defina QA_DISPLAY com o display da rodada')
  const pasta = path.resolve(process.argv[2] || 'tela-limpa')
  fs.mkdirSync(pasta, { recursive: true })
  const pagina = path.join(pasta, 'pagina.png')
  const tela = path.join(pasta, 'tela.png')

  const browser = await chromium.connectOverCDP(process.env.CDP || 'http://127.0.0.1:9222')
  const page = browser.contexts()[0].pages()[0]
  await page.screenshot({ path: pagina })
  const { w, h } = await page.evaluate(() => ({ w: window.innerWidth, h: window.innerHeight }))
  await browser.close().catch(() => {})

  execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-f', 'x11grab', '-draw_mouse', '0',
    '-video_size', `${w}x${h}`, '-i', `${display}+0,0`, '-frames:v', '1', tela])
  // Pixel a pixel, em cinza: a captura do display tem de ser a própria página. Conta o que difere
  // além do ruído de compressão e devolve o retângulo do que está por cima, para achar o intruso.
  const cinza = (png) => spawnSync('ffmpeg', ['-loglevel', 'error', '-i', png, '-vf', `scale=${w}:${h}`,
    '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], { maxBuffer: 64 * 1024 * 1024 }).stdout
  const a = cinza(tela)
  const b = cinza(pagina)
  let dif = 0; let x0 = w; let y0 = h; let x1 = -1; let y1 = -1
  for (let i = 0; i < a.length; i++) {
    if (Math.abs(a[i] - b[i]) > 32) {
      dif++
      const x = i % w; const y = (i / w) | 0
      if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y
    }
  }
  const fracao = dif / (w * h)
  const limpa = fracao <= LIMITE
  const regiao = dif ? { x: x0, y: y0, largura: x1 - x0 + 1, altura: y1 - y0 + 1 } : null
  console.log(JSON.stringify({ limpa, pixels_diferentes: dif, fracao: Number(fracao.toFixed(5)), limite: LIMITE, regiao, tela, pagina }))
  if (limpa) { fs.rmSync(pasta, { recursive: true, force: true }) }
  process.exit(limpa ? 0 : 1)
})().catch(e => { console.error(JSON.stringify({ erro: String(e.message || e) })); process.exit(2) })
