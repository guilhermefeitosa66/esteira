---
name: esteira-limpar-abas
description: >
  Fecha as abas ociosas que ficaram para trás nos spaces das etapas da esteira no Herdr: só as que
  estão com o shell parado no prompt, sem agente e sem processo rodando. A aba 1 (monitor) e as vagas
  nunca são tocadas. Use quando o usuário chamar /esteira-limpar-abas ou pedir para "limpar as abas",
  "fechar as abas paradas". Exige HERDR_ENV=1.
---

# Limpar abas ociosas

Requer Herdr: `test "${HERDR_ENV:-}" = 1`. Se falhar, diga que não está dentro do Herdr e pare.

```bash
.claude/skills/esteira-limpar-abas/limpar_abas.py          # --dry só lista
```

Uma aba só é fechada quando **tudo** isto vale: está num space de etapa (`stages.<x>.space` no
config); não é a primeira aba nem uma **vaga** (aba `vaga`); tem uma pane só; nenhum agente roda
nela (nem `idle`, nem `done`); e o título da pane é o do prompt do shell (nada em primeiro plano).
Não feche nada fora desse critério.

Responda em português: por space, quantas abas fechou e o que ficou. Para cada aba mantida com
agente, uma linha do que ele está fazendo (`herdr pane read <pane> --source visible`), em especial
um agente parado com texto digitado e não enviado, ou sem nome (órfão de um reinício: o supervisor
resolve sozinho se o loop dele estiver de pé).
