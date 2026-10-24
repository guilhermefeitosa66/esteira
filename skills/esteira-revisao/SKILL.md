---
name: esteira-revisao
description: >
  Trabalhador da esteira: recebe uma issue da Review queue, encontra o PR dela, roda a skill nativa
  `/code-review medium <PR> --fix` numa worktree da branch do PR, valida as correções, faz commit e
  push e move a issue para a QA queue. Também revisa PRs externos já aprovados pelo monitor. Chamado
  pelo dispatcher como `/esteira-revisao <issue>`; não pergunta nada ao usuário.
argument-hint: '<número da issue>'
---

# Revisão de código: issue `$ARGUMENTS`

Leia `.claude/esteira/REGRAS.md` e as instruções do projeto. Etapa: `review`. `N` = o número do
argumento. `MAIN=$PWD; BIN=$MAIN/.claude/esteira/bin`.

## 0. Começar

```bash
$BIN/worker.py begin review <N>     # código 3 → pare aqui
$BIN/board.py pr-for <N>            # o PR da issue
```

- Sem PR aberto → comentário `<!-- pipeline:review -->` dizendo isso e
  `worker.py end review <N> --to "Dev queue"`.
- **PR externo** (o JSON traz `approved_sha`): se `headRefOid` ≠ `approved_sha`, o autor mudou o PR
  depois da aprovação. Não revise: `gh pr edit <PR> --remove-label triaged` e
  `worker.py end review <N> --to Backlog` (o monitor de PRs analisa de novo).

## 1. Worktree na branch do PR

```bash
WT=$($BIN/worktree.sh review <N> --detach) && cd "$WT" && gh pr checkout <PR>
```

**Retomando?** Se a branch já tem commits `fix: address code review findings` depois do último
commit do desenvolvimento, ou há um `<!-- pipeline:review -->` desta rodada, revise só o que veio
depois.

## 2. Revisar e corrigir

Invoque a skill nativa de revisão:

```
Skill: code-review   args: "medium <PR> --fix"
```

Ela aplica os achados na árvore de trabalho. **Prazo: 25 min.** Passou disso: encerre a tarefa
(`TaskStop`), registre a revisão como parcial e siga com o que já foi aplicado. Se a skill
`code-review` não existir nesta instalação do Claude Code, revise você mesmo o diff
(`gh pr diff <PR>`) procurando defeitos de correção, segurança e regressão, e corrija.

**Assim que terminar, antes de qualquer outra coisa**, commit e push do que foi aplicado
(`[issue-<N>] fix: address code review findings`). Correção sem commit não sobrevive a uma queda.
Depois:

- Leia o diff das correções. Descarte o que contradiz o plano técnico (`<!-- pipeline:plan -->`) ou
  as instruções do projeto.
- Rode os testes afetados, como o projeto documenta (UI num display próprio, sob trava).
- Ajustes e descartes vão em commits seguintes, cada um com push na hora.
- **PR externo sem permissão de push** (`maintainerCanModify: false`, ou push recusado): não force.
  Publique os achados como review no PR (`gh pr review <PR> --comment --body-file ...`, cordial) e
  peça intervenção humana (`worker.py human review <N> <arquivo>`).

Achado grave que a correção automática não resolve (desenho errado, segurança, perda de dados):
`worker.py end review <N> --to "Dev queue"` com o achado no comentário.

## 3. Terminar

Comentário na issue começando por `<!-- pipeline:review -->`: PR, quantos achados, o que foi
corrigido, o que foi descartado e por quê. Depois derrube o que subiu (`TaskStop` nas suas tarefas
em segundo plano, `$BIN/cleanup.sh review <N>`) e:

```bash
cd "$MAIN" && git worktree remove --force "$(git -C "$WT" rev-parse --show-toplevel)"
$BIN/worker.py end review <N>        # → QA queue e devolve a vaga (o Claude fica aberto)
```

Depois do `end`, uma linha e nenhuma ferramenta a mais.
