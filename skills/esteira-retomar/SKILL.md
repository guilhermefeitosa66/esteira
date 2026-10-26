---
name: esteira-retomar
description: >
  Retoma uma ou todas as filas da esteira pausadas com `/esteira-pausar`: apaga o sinalizador e
  acorda o loop da fila na hora, para ele despachar o que estiver esperando se houver vaga e RAM. Use
  quando o usuário chamar `/esteira-retomar` ou pedir para "despausar", "voltar a fila de X",
  "liberar o QA", "pode voltar a puxar".
argument-hint: '<plan | dev | review | qa | all>'
---

# `/esteira-retomar <etapa>`

`$ARGUMENTS` = `plan`, `dev`, `review`, `qa` ou `all` (sem argumento = as que estiverem pausadas:
`ls <state_dir>/paused-*`). Nomes em português valem como no `/esteira-pausar`.

```bash
.claude/esteira/bin/dispatch.py resume <etapa|all>
```

O comando apaga `paused-<etapa>` e toca `wake-<etapa>`: o loop roda uma passada em uns 10 s.

Responda com o que o comando imprimiu e, depois de uns 15 s, a última linha daquela etapa em
`dispatch.log` no `state_dir` (`dispatched ...`, ou o motivo de nada ter saído: fila vazia, vagas
ocupadas, memória baixa). Se não aparecer passada nenhuma, o loop não está de pé: diga isso e sugira
`/esteira-up`.
