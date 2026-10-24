---
name: esteira-scale
description: >
  Redefine quantos trabalhos simultâneos uma fila da esteira roda, ou seja, quantas vagas o space da
  etapa tem no Herdr: `/esteira-scale qa 3` deixa a fila de QA com 3 vagas. Abre as vagas que faltam
  e fecha as que sobram (uma vaga ocupada termina o trabalho antes de fechar). Use quando o usuário
  chamar /esteira-scale, pedir para "aumentar/diminuir a fila de X", "deixar N em paralelo na fila Y"
  ou perguntar quantas vagas tem cada fila. Exige HERDR_ENV=1.
argument-hint: '<plan | dev | review | qa> <vagas>'
---

# `/esteira-scale <etapa> <n>`

`$ARGUMENTS` = a etapa (`plan`, `dev`, `review` ou `qa`; aceite também planejamento → plan,
desenvolvimento → dev, revisão → review) e o número de vagas, de 1 a 9.

Sem argumentos, ou só com a etapa, **não mude nada**: mostre quantas vagas cada fila tem hoje e
pergunte.

```bash
python3 -c "import json;c=json.load(open('.claude/esteira/config.json'));print({k:v['max'] for k,v in c['stages'].items()}, 'max_workers:', c['max_workers'])"
```

Com os dois argumentos, todo o trabalho é determinístico:

```bash
.claude/esteira/bin/dispatch.py scale <etapa> <n>
```

O que o comando faz, sob a trava da esteira:

1. grava `stages.<etapa>.max = n` no `.claude/esteira/config.json` (o loop relê a config a cada
   passada, então nada precisa ser reiniciado);
2. **para cima**: abre as vagas que faltam (aba `vaga` com um Claude permanente);
3. **para baixo**: fecha as vagas livres que sobram, da última aba para a primeira. Uma vaga ocupada
   nunca é interrompida: ela termina o trabalho, o `worker.py end` acorda o loop e a passada seguinte
   fecha a vaga. A fila não despacha nada além do novo limite enquanto isso;
4. acorda o loop da fila, que já preenche as vagas novas se houver itens esperando.

Responda com o que o script imprimiu e repasse estes avisos quando couberem:

- **Teto geral:** se a soma das vagas passar de `max_workers`, o teto geral vale e algumas vagas
  ficam paradas. Só aumente `max_workers` se o usuário pedir.
- **Recursos compartilhados:** vagas a mais andam em paralelo, mas um recurso protegido por trava
  (`lock.sh`, por exemplo um display ou um emulador únicos) continua sendo usado por uma vaga de cada
  vez. Etapa pesada também não despacha com menos de `min_free_ram_gb` de RAM livre.

Estado depois da mudança: `/esteira-status`.
