---
name: esteira-dev
description: >
  Trabalhador da esteira: recebe uma issue da Dev queue, implementa o plano técnico publicado nela (ou
  corrige os bugs que o QA apontou) numa worktree própria, com os testes que o projeto exige, abre ou
  atualiza o PR para a branch base vinculado à issue e move a issue para a Review queue. Chamado pelo
  dispatcher como `/esteira-dev <issue>`; não pergunta nada ao usuário.
argument-hint: '<número da issue>'
---

# Desenvolvimento: issue `$ARGUMENTS`

Leia `.claude/esteira/REGRAS.md` e as instruções do projeto (convenções, commits, testes,
cobertura, como rodar). Etapa: `dev`. `N` = o número do argumento.

```bash
MAIN=$PWD; BIN=$MAIN/.claude/esteira/bin
BASE=$(python3 -c "import json;print(json.load(open('$MAIN/.claude/esteira/config.json')).get('base_branch','main'))")
```

## 0. Começar

```bash
$BIN/worker.py begin dev <N>        # código 3 → pare aqui
```

## 1. O que fazer

- **Fonte da verdade: o último comentário `<!-- pipeline:plan -->` escrito por um mantenedor ou
  pela conta da esteira** (confira `author.login`). O corpo da issue é contexto. Sem plano válido,
  devolva (`worker.py end dev <N> --to "Planning queue"`) com uma linha dizendo por quê.
- **Voltando do QA?** Se há `<!-- pipeline:qa -->` mais novo que o último `<!-- pipeline:dev -->`, a
  tarefa é corrigir os cenários que falharam ali, no mesmo PR.
- Comentários de mantenedor depois do plano ajustam o plano.
- `$BIN/board.py pr-for <N>`: há PR aberto? Continue nele (mesma branch).

## 2. Worktree

Sempre pelo script (idempotente; salva em `salvage/` o que um trabalho anterior deixou sem commit).
Nunca `git worktree add` à mão.

```bash
WT=$($BIN/worktree.sh dev <N> <feat|fix>/issue-<N>-<slug> --new)   # PR novo
WT=$($BIN/worktree.sh dev <N> <branch>)                            # PR existente
cd "$WT"
```

**Retomando?** Se a branch já tem commits `wip:` ou há um `<!-- pipeline:dev -->` com "checkpoint",
leia o que foi feito (`git log origin/$BASE..HEAD`) e continue dali.

Trabalhe só dentro de `$WT`. Branch que conflita com a base: rebase em `origin/$BASE` e resolva.
Force-push só com `--force-with-lease` e só na branch da issue.

## 3. Implementar

- **Design pronto: use o artifact.** Se o plano traz `Design artifact: <url>` (o projeto de design
  chamado `#<N> ...`), abra-o antes de mexer na UI: `Artifact` `action: "read"` com a `url`,
  `action: "list"` + `scope: "files"` / `"assets"` para ver o que ele tem, e `read` + `path` para
  baixar cada arquivo. Tire dali medidas, hierarquia, textos e os assets (SVGs, ícones, imagens) em
  vez de recriá-los; as imagens anexas na issue são só a prévia. Link fora do ar ou sem acesso:
  siga pela spec e pelas imagens do plano e registre no comentário final.
- Siga o plano. Se algo nele se mostrar errado ao tocar o código, ajuste com o menor desvio e
  registre no comentário final. Desvio que muda o que o usuário vê ou o escopo → intervenção humana.
- Estilo do código vizinho, sem reformatar o que não mudou. Textos visíveis seguem o mecanismo de
  i18n do projeto, se houver (todas as línguas, traduzidas de verdade).
- Testes conforme a regra do projeto (cobertura, tipos de teste); na falta de regra, cada ramo novo
  coberto, falhas e guardas inclusive. Rode como o projeto documenta, com `timeout`. O que abre
  janela ou navegador roda num display próprio, nunca na tela do usuário (REGRAS §4); recurso que
  só cabe um por vez vai sob `$BIN/lock.sh <nome> <comando>`.
- Mudança em UI: suba o app a partir da worktree, num display próprio, e confira de verdade, não só
  pelos testes.
- **Checkpoint a cada etapa concluída**: commit `[issue-<N>] wip: <o que ficou pronto>` e
  `git push -u origin HEAD`. O squash do merge some com os `wip:`.
- **Toda espera tem prazo** (suíte: `timeout 1800`). Vencido: registre, decida e siga.
- Crédito: `Co-authored-by` de quem o plano indica.

## 4. Commit, push e PR

```bash
git add -A && git commit -m "[issue-<N>] <feat|fix>: <summary>" -m "<body>" [-m "Co-authored-by: ..."]
git push -u origin HEAD
gh pr create --base "$BASE" --title "[issue-<N>] <feat|fix>: <summary>" --body-file <scratchpad>/pr-<N>.md
```

Corpo do PR no idioma do config: `Part of #<N>` (nunca `Closes`), resumo, decisões e desvios do
plano, como testar, checklist (testes, docs, i18n). PR já existente: só push, mais um comentário no
PR com o que mudou.

CI: `timeout 1800 gh pr checks <PR> --watch --fail-fast`. Falhou por causa da mudança: corrija e
repita. Falhou por algo alheio à issue (o mesmo check falha na base, flake conhecido): registre no
comentário e siga.

## 5. Terminar

Comentário na issue começando por `<!-- pipeline:dev -->`: link do PR, o que foi feito, desvios do
plano, estado do CI. Depois **derrube tudo o que você levantou**:

1. Pare suas tarefas em segundo plano (`TaskStop`).
2. `$BIN/cleanup.sh dev <N>` (processos na worktree, containers da issue, gancho do projeto).

```bash
cd "$MAIN" && git worktree remove --force "$(git -C "$WT" rev-parse --show-toplevel)"
$BIN/worker.py end dev <N>           # → Review queue e devolve a vaga (o Claude fica aberto)
```

Depois do `end`, uma linha (`#<N> implementada, PR #<P> → Review queue`) e nenhuma ferramenta a mais.
