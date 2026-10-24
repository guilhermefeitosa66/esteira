---
name: esteira-up
description: >
  Sobe a esteira inteira no Herdr, do zero ou depois de um reinício, sem duplicar nada: confere os
  spaces plan, dev, review, qa, homolog, release, supervisor (e monitor-issues e monitor-pr em projeto
  público), cria os que faltam, sobe os loops das filas, do supervisor e dos monitores e abre as vagas.
  Use quando o usuário chamar /esteira-up ou pedir para "subir a esteira", "levantar os loops",
  "reiniciei o computador, sobe tudo de novo". Exige HERDR_ENV=1.
---

# Subir a esteira

Requer Herdr: `test "${HERDR_ENV:-}" = 1`. Se falhar, diga que não está dentro do Herdr e pare.

Tudo é determinístico e idempotente:

```bash
.claude/esteira/bin/start-all.sh          # --dry só mostra o que faria
```

| Space | Aba 1 `monitor` | Demais abas |
|---|---|---|
| `plan`, `dev`, `review`, `qa` | `dispatch.py <etapa> --loop` (a cada `loops.dispatch_seconds`) | as vagas: um Claude sempre aberto |
| `homolog`, `release` | nenhum loop: espaço do mantenedor para homologar e lançar | — |
| `monitor-issues`, `monitor-pr` | triagem e monitor de PRs (só com `monitors: true`, projeto público) | — |
| `supervisor` | `supervise.py --loop` (a cada `loops.supervise_seconds`) | — |

- Space que não existe é criado; com nome antigo (`legacy_space_names`), é renomeado.
- Loop que já está rodando fica como está. Nunca mate um loop para "reiniciar limpo" sem pedido.
- Aba 1 com um Claude dentro é só reportada: diga para fechar (`/exit`) e rodar de novo.
- Intervalos, limites e nomes mudam no `.claude/esteira/config.json`. Um loop já de pé só pega um
  intervalo novo quando é reiniciado.
- Nunca rode release nem nada no space `release` por conta própria.

Depois, rode `.claude/esteira/bin/status.py` e responda em português, curto: o que foi criado (`+`),
renomeado (`~`), iniciado (`>`), o que já estava de pé (`=`), qualquer `!` com o que fazer, e a
linha dos loops (todos ✓?).
