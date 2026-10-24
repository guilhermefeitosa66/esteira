---
name: esteira-qa
description: >
  Trabalhador de QA da esteira (método QA BOT): recebe uma issue da QA queue, testa a branch do PR num
  ambiente isolado (display próprio, portas livres, nada na tela do usuário), deriva os casos de teste
  do plano técnico e dos critérios de aceite, executa interface e API, grava sempre um vídeo narrado
  da jornada (API sobre o palco de duas colunas) e publica na issue só o relatório escrito, com os bugs
  documentados. Aprovado: anexa o vídeo, faz o merge (se o config mandar) e move para "Ready for
  release". Reprovado: não anexa vídeo e devolve para a Dev queue. Chamado pelo dispatcher como
  `/esteira-qa <issue>`; não pergunta nada ao usuário.
argument-hint: '<número da issue>'
---

# QA: issue `$ARGUMENTS`

Leia `.claude/esteira/REGRAS.md` e as instruções do projeto (como subir, testar, dados de teste).
Etapa: `qa`. `N` = o número do argumento.

```bash
MAIN=$PWD; BIN=$MAIN/.claude/esteira/bin; SK=$MAIN/.claude/skills/esteira-qa
cfg () { python3 -c "import json;c=json.load(open('$MAIN/.claude/esteira/config.json'));print(c.get('$1'))"; }
qv () { python3 $SK/scripts/qa_video.py "$@"; }     # função, não variável: o zsh não divide $VAR
```

Seja o QA que entende o produto e entrega uma prova que outra pessoa confere. QA é independente da
implementação: o esperado vem do plano e da issue, nunca do que o código faz hoje. O método completo
está nas referências desta skill (`references/`); abaixo, o roteiro da esteira e o que muda nele.

## 0. Começar

```bash
$BIN/worker.py begin qa <N>         # código 3 → pare aqui
$BIN/board.py pr-for <N>            # PR, branch, head sha
```

Sem PR → `worker.py end qa <N> --to "Dev queue"` com uma linha de motivo. PR externo com
`headRefOid` ≠ `approved_sha` → `gh pr edit <PR> --remove-label triaged` e
`worker.py end qa <N> --to Backlog` (o monitor reanalisa).

Guarde o **head sha** do PR agora: é a build testada. A rodada vive fora do scratchpad (que morre
com a sessão), em `G=<state_dir>/qa/<N>/<head sha curto>/` (`cases.md`, `capturas/`, `work/`,
`run-*.log`). `R=qa-$(date +%Y%m%d%H%M)` identifica a rodada.

**Retomando?** `$G/cases.md` já existe para o **mesmo head sha**: um QA anterior caiu no meio.
Reaproveite os casos e as provas e execute só os `NAO_EXECUTADO`. Head sha diferente = rodada nova.

## 1. Esperado, antes de executar

Leia [documentos e cobertura](references/documentos-e-cobertura.md). Monte a cadeia
**fonte → regra → CT → passos → prova**:

- Fontes, em ordem: os cenários de QA e os critérios de aceite do `<!-- pipeline:plan -->`; os
  critérios da issue; as rodadas `<!-- pipeline:qa -->` anteriores (num reteste, refaça os CTs que
  falharam, com provas novas, e acrescente a regressão vizinha).
- Um CT = uma responsabilidade verificável, com o esperado escrito antes. Positivos, negativos e
  limites conforme o risco; o fluxo vizinho que a mudança pode ter quebrado.
- Marque cada CT como **UI** (web, app, desktop, mobile) ou **API** (REST, fila, worker).
- Liste em `$G/cases.md`, todos `NAO_EXECUTADO`, com a fonte de cada um.

## 2. Ambiente isolado

```bash
WT=$($BIN/worktree.sh qa <N> --detach) && cd "$WT" && gh pr checkout <PR>
```

- Suba o sistema a partir de `$WT`, do jeito que o projeto documenta, em **portas livres** e com
  nomes próprios, sem parar nem reconfigurar o que já rodava na máquina. Containers com
  `--label esteira.issue=<N>`. Veja [dev e local](references/ambiente-dev-e-local.md) e
  [dublês](references/dubles-de-integracoes.md) para integrações externas (`scripts/qa_local.py`).
- **Nada na tela do usuário.** Navegador e app rodam num display próprio:
  `$SK/scripts/chrome-limpo.sh subir $G <url>` (Xephyr + Chrome limpo por CDP). App desktop: Xvfb ou
  Xephyr. Android: emulador `-no-window`.
- Recurso que só cabe um por vez (o display de gravação, um emulador, uma porta fixa) vai sob
  `$BIN/lock.sh <nome> bash $G/run.sh`. **Prazo de 40 min por sessão** (`timeout 2400`); vencido, os
  casos que faltaram ficam `NAO_EXECUTADO` com o motivo.
- Massa de teste descartável, nunca dados reais do usuário.

## 3. Executar e provar

Leia [execução multiplataforma](references/execucao-multiplataforma.md) e
[evidências](references/evidencias-e-relatorios.md).

Por passo: confirmar a pré-condição → agir → observar → comparar com o esperado → capturar →
registrar. As capturas por passo (prints, respostas de API, logs) ficam em `$G/capturas/`: são a
prova interna que sustenta o veredito e a revisão do vídeo, **não vão para a issue**.

- **UI**: dirija pelo `scripts/demo-lib.js` (Playwright por CDP no Chrome limpo) ou pela automação
  do app. Seletor instável ou foco perdido é problema de interação: repita, não reprove o produto.
- **API**: monte o `cenario.json` do palco (veja [vídeo de API](references/video-api.md)) e rode
  `node $SK/scripts/palco-api/servidor.js ensaio --cenario $G/work/cenario.json --pasta $G/work/ensaio`.
  O ensaio executa as chamadas de verdade e já confere o esperado de cada etapa: é a execução do CT.
  HTTP 200 não basta; o contrato é a prova.
- A suíte de testes do projeto também roda contra a branch (num display próprio, se abrir janela).
  Falha nova causada pela branch = bug. Falha que já existe na base (confira rodando lá) não reprova
  a issue: registre como achado à parte.

Estados: `PASSOU`, `FALHOU`, `BLOQUEADO` (motivo obrigatório), `NAO_EXECUTADO` (motivo
obrigatório), `NAO_APLICAVEL`. Falha comprovada prevalece; passo obrigatório bloqueado impede
`PASSOU`. Atualize `$G/cases.md` depois de cada CT: é o checkpoint.

Bug ([bugs e reteste](references/bugs-github-e-reteste.md)): passos para reproduzir, esperado (com a
fonte), observado, frequência, impacto e a prova que você tem. Sem inventar causa-raiz.

## 4. Vídeo narrado (sempre)

Toda rodada produz **um vídeo narrado da jornada**, aprovada ou não: é a prova que deixa o humano
conferir que o que ele pediu foi feito do jeito que pediu, sem testar na mão. Leia
[vídeo narrado](references/video-narrado.md) e, conforme o tipo de CT,
[vídeo web](references/video-web.md) ou [vídeo de API](references/video-api.md).

- `$SK/scripts/preparar-video.sh verificar` antes. Faltando ferramenta, a rodada segue sem vídeo e o
  relatório diz por quê; a falta de vídeo não reprova a issue.
- Ordem: roteiro (depois dos CTs, a partir do que aconteceu) → `qv narrar` (voz offline) → gravação
  do display próprio (nunca a tela do usuário) → `qv montar` → `qv conferir` e revisão quadro a quadro.
- CT de API: grave sobre o palco (`servidor.js subir` + Chrome limpo + `api-lib.js`), que mostra
  requisição e resposta reais, com os segredos mascarados.
- Abra dizendo o que vai ser verificado (issue, critérios) e feche com o veredito e os números.
- O vídeo é uma segunda execução real, depois dos CTs. Se ela não reproduzir o que a primeira viu,
  isso é achado, não motivo para regravar até dar certo.
- Arquivo final: `$G/video/qa-<N>-$R.mp4`.

## 5. Relatório na issue (no idioma do config)

**Só texto. Nenhum print anexado.** Os bugs ficam documentados no próprio relatório. Comentário via
`gh issue comment <N> --body-file`:

```markdown
<!-- pipeline:qa -->
## QA report — round <k> · <PASSED | FAILED>

**Build:** PR #<PR> @ `<head sha>` · <environment: OS, browser/runtime versions> · <date, UTC>

| CT | Scenario | Type | Source | Result |
|---|---|---|---|---|
| CT-01 | ... | UI | plan QA-1 | ✅ PASSED |
| CT-02 | ... | API | AC 2 | ❌ FAILED — see BUG-1 |
| CT-03 | ... | UI | AC 4 | ⏭️ NOT RUN — <reason> |

Totals: X passed / Y failed / Z blocked / W not run, out of T.

### Bugs
**BUG-1 — <title>**
- Steps: 1. ... 2. ...
- Expected (source): ...
- Observed: ... (exact message, status code, value)
- Frequency / impact: ...

### Video
<only when PASSED: the link printed by evidence.sh, one line on what it shows>

### Out of scope for automated QA
- What the maintainer should check during sign-off (real devices, production data, other OSes...).
```

**Vídeo só quando aprovado.** Com a rodada PASSED e um repositório de evidências no config
(`evidence_repo`):

```bash
$BIN/evidence.sh qa <N> $R $G/video/qa-<N>-$R.mp4       # imprime o link, fixado no commit
```

e o link entra na seção "Video". Reprovada, não anexe vídeo nenhum (ele fica em `$G/video/` para
consulta local) e remova a seção. Sem `evidence_repo`: diga onde o vídeo está na máquina.

Porcentagem só com denominador. Zero casos = "sem base", nunca 100%.

## 6. Decidir e terminar

Antes de remover a worktree, **derrube tudo o que você levantou**: o palco
(`kill $(cat $G/work/palco.pid)`), o navegador (`$SK/scripts/chrome-limpo.sh descer $G`), o sistema
que subiu, suas tarefas em segundo plano (`TaskStop`) e `$BIN/cleanup.sh qa <N>`. Depois:

```bash
cd "$MAIN" && git worktree remove --force "$WT"
```

**Com bug** (algum CT `FALHOU`, ou obrigatório `BLOQUEADO` por defeito):
- Conte as rodadas `<!-- pipeline:qa -->` com FAILED. Na 3ª: `worker.py human qa <N> <arquivo>`, com
  o histórico.
- Senão: `$BIN/worker.py end qa <N> --to "Dev queue"`.

**Sem bug**:

1. O head do PR ainda é o sha testado? Se não, refaça a rodada (o código mudou).
2. Se `merge_on_qa` for `false` no config: não faça merge; `worker.py end qa <N>` → **Ready for
   release**, e o mantenedor faz o merge na homologação.
3. Se for `true`: `timeout 1800 gh pr checks <PR> --watch`. Check vermelho por causa da branch = bug
   (devolva à Dev queue com o log). Vermelho alheio (o mesmo check falha na base): registre no
   relatório e decida pelo que o projeto aceita; na dúvida, não faça merge e deixe para o
   mantenedor. Conflito com a base: `worker.py end qa <N> --to "Dev queue"` ("rebase needed").
4. Merge por squash, com os trailers de crédito (quem reportou e, em PR externo, o autor do PR) e
   sem atribuição a IA:
   ```bash
   gh pr merge <PR> --squash --delete-branch \
     --subject "[issue-<N>] <type>: <summary> (#<PR>)" --body "<resumo>\n\nCo-authored-by: ..."
   ```
   A proteção de branch recusou e a conta é admin do repositório: `--admin` é aceitável só se o
   projeto já trabalha assim; senão, deixe o merge para o mantenedor e diga isso no relatório.
5. `$BIN/worker.py end qa <N>` → **Ready for release** (homologação do mantenedor). Não feche a issue.

Depois do `end`, uma linha (`#<N> QA <PASSED|FAILED> → <coluna>`) e nenhuma ferramenta a mais.

## Fora da esteira

Chamada sem número de issue (por exemplo, "testa este PR" ou "faz QA desta história"), esta skill é
o QA BOT completo: siga [intake](references/intake-e-autonomia.md),
[PR e contexto](references/pull-request-e-contexto.md) e
[continuidade](references/continuidade-e-operacao.md), com os artefatos de
[contrato de artefatos](references/contrato-de-artefatos.md) (`scripts/qa_artifacts.py`), e só
publique fora da máquina com autorização que cubra a ação e o destino.
