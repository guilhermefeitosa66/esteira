---
name: esteira-pausar
description: >
  Pausa uma ou todas as filas da esteira (plan, dev, review, qa): o que já está numa vaga termina
  normalmente, mas a fila não puxa nada novo enquanto estiver pausada. O loop do monitor continua de
  pé (e o supervisor segue cuidando das vagas), então nada precisa ser morto nem reiniciado. A pausa
  sobrevive a reinício da máquina e ao `/esteira-up`, até um `/esteira-retomar`. Use quando o usuário
  chamar `/esteira-pausar` ou pedir para "pausar a fila de X", "segurar o QA", "parar de puxar issue
  nova no dev", "congelar a esteira".
argument-hint: '<plan | dev | review | qa | all> [motivo]'
---

# `/esteira-pausar <etapa> [motivo]`

`$ARGUMENTS` = `plan`, `dev`, `review`, `qa` ou `all`, seguido opcionalmente do motivo (aparece no
log e no `/esteira-status`). Sem etapa, **pergunte** qual: pausar tudo por engano para a esteira
inteira. Aceite também planejamento → plan, desenvolvimento → dev, revisão → review.

```bash
.claude/esteira/bin/dispatch.py pause <etapa|all> [motivo]
```

O comando cria `paused-<etapa>` no `state_dir` da config. A partir da próxima passada do loop
daquela fila, o dispatcher:

- **continua** reconciliando a fila e mantendo as vagas abertas;
- **não despacha** nada da fila: registra `<etapa>: N queued, paused by the maintainer`;
- **não mexe** em quem já está numa vaga. Esse trabalho termina e anda para a próxima fila como
  sempre. Se a próxima fila também estiver pausada, a issue espera lá.

O supervisor não desfaz a pausa: ele cuida das vagas, não da fila. Uma vaga que ele recicla devolve a
issue para a fila, e ali ela fica até a retomada.

Responda curto com a linha que o comando imprimiu e o que estava em andamento naquela fila
(`.claude/esteira/bin/status.py`: as vagas com issue continuam até o fim). Lembre que para voltar é
`/esteira-retomar <etapa>`.
