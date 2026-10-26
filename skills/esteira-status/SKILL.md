---
name: esteira-status
description: >
  Mostra o estado da esteira: as filas do board, cada vaga do Herdr (livre ou com qual issue e há
  quanto tempo), as travas de recurso, a RAM livre e quais loops estão de pé. Só lê, não muda nada.
  Use quando o usuário perguntar "como está a esteira", "os loops estão de pé?", "o que está
  rodando", "tem algo travado?" ou chamar /esteira-status.
---

# Estado da esteira

```bash
.claude/esteira/bin/status.py          # --json para o mesmo em JSON
```

Fora do Herdr ele mostra as filas e os loops, mas não as vagas. Responda em português, curto:

1. **Loops**: quais estão de pé (✓) e quais não (✗). Algum ✗ → `/esteira-up` dentro do Herdr.
2. **Por fila**: quantas na fila e o que cada vaga está fazendo. Destaque vaga com a mesma issue há
   mais de 1 h, vaga "sem Claude" e fila parada com vaga livre. Fila marcada `PAUSADA` (com
   `/esteira-pausar`) não puxa nada novo até um `/esteira-retomar`: diga isso, com há quanto tempo.
3. **Recursos**: RAM livre (abaixo do limite, as etapas pesadas pausam) e quem segura cada trava.
4. Algo parece travado: `grep supervisor <state_dir>/dispatch.log | tail` diz o que o supervisor já
   tentou.

Não aja sobre nada aqui: esta skill é só leitura.
