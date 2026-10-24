---
name: esteira-fila
description: >
  Passada manual de uma fila da esteira (plan, dev, review ou qa): entrega a próxima issue da fila à
  vaga livre do space da etapa no Herdr (um Claude sempre aberto, que recebe /clear e a skill da
  etapa). O loop permanente NÃO é esta skill: é `dispatch.py <etapa> --loop` na aba "monitor" de cada
  space, sem gastar tokens. Use quando o usuário pedir para "tocar a fila de dev agora", "despachar o
  QA já" ou chamar /esteira-fila <etapa>.
argument-hint: 'plan | dev | review | qa'
---

# Passada manual de uma fila

Requer Herdr (`HERDR_ENV=1`). `$ARGUMENTS` = a etapa (`plan`, `dev`, `review` ou `qa`); sem
argumento, rode as quatro, uma depois da outra.

```bash
.claude/esteira/bin/dispatch.py <etapa>
```

Não rode em `/loop`: o loop é o `dispatch.py <etapa> --loop` na aba "monitor" do space da etapa (o
`esteira-up` sobe), e o supervisor cuida das vagas travadas.

O que uma passada faz (sob uma trava compartilhada com as outras filas e o supervisor):

1. **Reconcilia.** Claim cuja issue já saiu da coluna ativa é descartado; issue na coluna ativa sem
   ninguém trabalhando volta para a fila.
2. **Vagas.** O space tem a aba 1 (monitor) e `stages.<etapa>.max` vagas: abas com um Claude
   permanente. Falta vaga, ela abre; o Claude da vaga caiu, ela sobe outro.
3. **Memória.** Etapa pesada não despacha com menos de `min_free_ram_gb` livres.
4. **Despacha**, enquanto houver vaga livre (ociosa e sem tarefa em segundo plano): confere o
   snapshot da triagem, move para a coluna ativa, dá `/clear` na vaga, nomeia a aba `#<N> <etapa>`,
   manda `/<skill da etapa> <N>` e confere que o turno começou.

Responda com o que o script imprimiu, sempre com o motivo quando nada foi despachado (vagas
ocupadas, memória baixa, fila vazia). Não investigue issue nenhuma aqui. Estado: `/esteira-status`.
Log: `<state_dir>/dispatch.log`.
