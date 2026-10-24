# Vídeo de cenário de API: o palco de duas colunas

Cenário sem tela (API REST, fila, worker, integração) também ganha vídeo. Ele é gravado sobre o
**palco de API**: uma página local, servida pela skill, aberta num Chrome limpo dentro de um display
próprio (Xephyr). Quem assiste vê a requisição, a resposta e o veredito de cada etapa, com a voz
explicando, sem precisar ler JSON solto num relatório.

- **No topo:** título e descrição do cenário, ambiente e as etapas (`1 Login · 2 Criar · 3 Worker`).
  Cada etapa mostra ✓ ou ✗ e o status depois de executada.
- **Faixa da nota:** o esperado da etapa, com a fonte da regra (critério de aceite, plano técnico).
- **Coluna da esquerda:** a requisição (método, URL, query, headers e body formatado) e o botão
  **Enviar**.
- **Coluna da direita:** a resposta (status, tempo, tamanho, headers e body), com os selos
  "esperado × obtido".
- **Etapa de log:** à esquerda a fonte (arquivo ou comando), o filtro e a espera; à direita o trecho
  do log, com as linhas que interessam destacadas.

A chamada é **executada de verdade** pelo servidor do palco (`scripts/palco-api/servidor.js`, Node
18+, sem dependências) no instante em que o cursor clica em Enviar. A página só mostra o que voltou.
Não há encenação: o que aparece é a resposta real, com os segredos mascarados.

Exemplo completo e testado em `assets/exemplo-api/` (alvo de brinquedo, `cenario.json`,
`roteiro.json`, `demo.js`). `scripts/preparar-video.sh teste` roda esse exemplo sem câmera.

## cenario.json

Veja `assets/exemplo-api/cenario.json`. Os campos:

- **`variaveis`** e **`{{NOME}}`**: resolvido na hora de executar, nesta ordem: valor capturado numa
  etapa anterior, `variaveis`, ambiente do processo do servidor. Variável sem valor quebra a etapa
  dizendo o que falta.
- **`segredos`**: nomes cujo valor nunca aparece (página, `trocas.jsonl`, log exibido). Exporte no
  shell que sobe o servidor, nunca em arquivo da gravação. Nomes capturados (o token do login) também
  entram na lista.
- **Mascarados sempre**, além dos `segredos`: headers e chaves de JSON com nome sensível
  (Authorization, Cookie, `x-api-key`, password/senha, token, cvv, número de cartão) e, no log,
  padrões de credencial e de cartão. `mascarar` acrescenta chaves; `mascarar_log` acrescenta regex.
- **`capturar`**: guarda um valor da resposta (`body.a.b[0]`, `headers.location`, `status`) para as
  etapas seguintes.
- **`esperado`**: gera os selos e o `confere` no `trocas.jsonl`. `status` (número ou lista), `campos`
  (caminho e valor exato), `existe` (caminhos que precisam vir preenchidos), `contem` (regex, só em
  etapa de log). Etapa sem `esperado` fica neutra (•): use para mostrar contexto sem dar a impressão
  de aprovação. É o esperado escrito **antes**, como em todo CT.
- **`grupos`**: etapas com `grupo` (o CT) mostram no topo só as etapas do grupo atual. O `esperado`
  do grupo aparece na faixa da nota quando a etapa não tem `nota`.
- **`timeout_s`**: por etapa ou no cenário (padrão 30 s). Sem resposta, a etapa aparece em vermelho.

### Etapa de captura (quando quem executa é a suíte de testes)

Quando a chamada não pode sair do palco (o código roda dentro da suíte, a mensagem é publicada pelo
próprio código testado, a integração está atrás de um dublê iniciado pelo teste), quem executa é o
harness, e ele grava cada troca num JSON. O palco mostra essas trocas com `"tipo": "captura"`,
`"arquivo"` e `"troca"` (a chave da troca no arquivo). O botão vira "Ver resposta" e, no lugar do
tempo, aparece "capturado HH:MM:SS". **Diga isso no vídeo**: a execução foi feita pela suíte, quando
e em qual commit. A captura nunca é escrita à mão.

### Log de processos assíncronos

O vídeo não inventa o que aconteceu dentro de um worker: ele coleta o log real.

- `fontes_log.<nome>.arquivo`: o log que o processo escreve (redirecione a saída do worker para um
  arquivo da gravação). Só aparecem as linhas escritas depois que o servidor do palco subiu.
- `fontes_log.<nome>.comando`: um comando **só de leitura** (por exemplo `docker logs <container>
  --since=5m`), executado sem shell, com 30 s de limite.
- `filtro` (regex) recorta as linhas do cenário, normalmente pelo id capturado. `esperar.regex` e
  `timeout_s` fazem o servidor reler a fonte a cada segundo até a linha aparecer. `destacar` marca as
  linhas que a narração vai explicar.

## Subir, ensaiar e gravar

```bash
SK=<pasta desta skill>; G=<pasta da rodada>
export SENHA=... TOKEN=...                        # segredos só no shell, nunca em arquivo
node $SK/scripts/palco-api/servidor.js ensaio --cenario $G/work/cenario.json --pasta $G/work/ensaio   # sem câmera
node $SK/scripts/palco-api/servidor.js subir  --cenario $G/work/cenario.json --pasta $G/work/api --porta <livre> > $G/work/palco.out 2>&1 &
echo $! > $G/work/palco.pid                       # palco.out recebe {"url": ...}
$SK/scripts/chrome-limpo.sh subir $G "<url do palco>"
set -a; source $G/work/navegador.env; set +a      # QA_DISPLAY, CDP, GEOMETRIA
$SK/scripts/preparar-video.sh pasta $G/work       # playwright-core da gravação
```

- **Ensaio** executa tudo e imprime etapa, status e divergências; sai 1 se algo divergir. Ele também
  escreve: só com massa descartável. Escrita que só pode acontecer uma vez: ensaie com
  `--ate <última etapa de leitura>`.
- **O servidor guarda estado** (resultados, capturas). Antes da tomada, derrube e suba de novo na
  mesma porta e recarregue a página.
- A geometria padrão do Chrome limpo (1440x900) é a que o layout espera.

A tomada (`demo.js` em `$G/work`, modelo em `assets/exemplo-api/demo.js`) usa
`scripts/palco-api/api-lib.js`:

- `mostrar(etapa)` troca a etapa na tela; ponha no `preparo` da cena para a fala começar com a
  requisição já visível.
- `enviar()` move o cursor real até Enviar, clica, espera a resposta (ou o log) e devolve o resultado.
- `destacar(caminho)` acende a linha e leva o cursor para o lado dela: `req.url`,
  `req.headers.<nome>`, `req.query.<chave>`, `req.body.<a.b[0]>`, `res.status`,
  `res.headers.<nome>`, `res.body.<...>` e `log:<regex>`. Caminho sem nada para destacar quebra a
  tomada: a resposta não é a que a fala supõe.
- Também `apontar`, `clicar`, `pausa` e `limpar()`, do `demo-lib.js`.

Depois, a sequência de [vídeo web](video-web.md#tomada), rodando o demo com
`SK=$SK V=$G/work/video node demo.js`.

## Roteiro sobre o palco

- Abertura: o cenário e o que vai ser provado, apontando para as etapas do topo.
- Por etapa, duas cenas: `<etapa>-req` (o que a requisição leva e por quê) e `<etapa>-res` (o que
  voltou, comparado com o esperado). Etapa simples cabe numa cena só.
- Na etapa de log, a fala conta o processo linha a linha.
- No fechamento, o resultado com o denominador ("três de quatro etapas como esperado; a terceira
  veio 404").

## Depois da tomada

- `$G/work/api/trocas.jsonl` tem cada troca mascarada, com o `confere`. A fala tem de bater com o
  que voltou; se não bater, refaça a fala (e a tomada).
- `grep` dos valores dos segredos no `trocas.jsonl` e na transcrição do vídeo tem que dar zero.
- Derrube o servidor (`kill $(cat $G/work/palco.pid)`) e o navegador (`chrome-limpo.sh descer $G`).
