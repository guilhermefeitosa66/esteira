---
name: esteira-acordar
description: >
  Acorda na hora o monitor (loop `dispatch.py --loop`) de uma ou de todas as filas da esteira, para
  ele olhar a fila agora em vez de esperar a próxima passada. Serve para quando uma issue entrou na
  fila por fora dos scripts, por exemplo arrastada à mão no board do GitHub. Não gasta tokens nem
  despacha nada por conta própria: só avisa o loop. Use quando o usuário chamar `/esteira-acordar`
  ou pedir para "avisar o monitor", "acordar a fila de X", "tem coisa nova na fila, manda olhar".
argument-hint: '<plan | dev | review | qa | all>'
---

# `/esteira-acordar <etapa>`

`$ARGUMENTS` = `plan`, `dev`, `review`, `qa` ou `all` (sem argumento = `all`). Aceite também
planejamento → plan, desenvolvimento → dev, revisão → review.

```bash
.claude/esteira/bin/dispatch.py wake <etapa|all>
```

O comando toca o arquivo `wake-<etapa>` no `state_dir` da config. O loop da fila vê o arquivo em
uns 3 s, espera mais 5 s (para juntar avisos que chegam juntos) e roda uma passada: despacha o que
estiver na fila se houver vaga livre e RAM.

Quem já avisa sozinho, sem precisar desta skill:

- `worker.py end`: a fila que liberou a vaga e a fila seguinte, para onde a issue foi;
- `board.py move` / `move-url` para a coluna de fila de uma etapa (criação de issue, triagem,
  sub-issues do planejamento, monitor de PRs).

Diferença para `/esteira-fila`: aquela roda a passada ela mesma, nesta sessão; esta só acorda o loop
que já está de pé.

Responda com o que o comando imprimiu e, depois de uns 10 s, a última linha da etapa em
`dispatch.log` no `state_dir` (`woken ...`, ou o motivo de nada ter saído: vagas ocupadas, memória
baixa, fila vazia, `paused by the maintainer` = fila pausada, `/esteira-retomar` para voltar). Se não aparecer `woken`, o loop não está de pé: diga isso e sugira `/esteira-up`.
