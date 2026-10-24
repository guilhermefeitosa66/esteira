# Da documentação ao teste

## Leitura que produz entendimento

Inventarie arquivos, histórias, anexos, manuais e decisões por ID, origem, versão
ou hash, autoridade e trecho lido. Extraia PDF/DOCX para busca quando útil,
preservando páginas/seções; confira visualmente tabelas, fluxos e páginas
digitalizadas que a extração não representou. Registre partes inacessíveis.
Uma busca de palavras não substitui a leitura da seção e de suas tabelas/imagens.

Primeiro entenda a jornada; depois volte às exceções e dependências relevantes.
Essa segunda passagem é orientada por risco, não uma obrigação de reler todo
arquivo inalterado em cada sessão. Não diga que leu um documento inteiro quando
só consultou trechos. Código ajuda a investigar; não substitui a regra funcional.

Para cada regra, registre: ID estável, texto verificável, fonte exata, persona,
pré-condição, entrada, resultado, exceção e estado. Transforme tabelas de ações
em matrizes estado × persona × ação, distinguindo permitido e proibido.

Conflito entre manual, card e decisão não se resolve escolhendo o que o produto
faz hoje. Registre as versões e peça decisão atribuída se a prioridade não estiver
definida. Bloqueie só as conclusões afetadas. Resposta posterior que muda a regra
gera nova versão e revisão dos CTs; não apague o histórico nem esconda a mudança.

## Cenários úteis

Um CT descreve um objetivo real, não um proxy: valor e regra, não só existência
de botão, registro, arquivo ou HTTP 200. Use Gherkin pt-BR e passos executáveis,
com labels/rotas/valores observados, persona, massa e resultado comparável.
Seletores podem ser descobertos por leitura antes da execução; não invente nomes.

Selecione técnicas conforme a regra:

| Tipo de regra | Variações relevantes |
|---|---|
| Campo obrigatório/importação | vazio, inválido, válido, erro por linha, persistência |
| Intervalo/cálculo | imediatamente abaixo/no/acima do limite, arredondamento, fuso |
| Estado | transição permitida/proibida, repetição, retorno, estado substituído |
| Persona/tenant | papel real, registro próprio/alheio autorizado, rota e operação |
| Filtros/grid | cada filtro, combinação significativa, ordenação, paginação, reset |
| Exportação | escopo filtrado, colunas, conteúdo, tipos, acentos, totais, paginação |
| Integração | aceite versus entrega, falha, timeout, duplicação, consistência eventual |
| App | offline/sincronização, permissões do dispositivo, retomada, teclado |

Positivo e negativo com conclusões distintas são CTs/variações identificados.
Não multiplique todas as combinações sem benefício: justifique amostra e risco
residual. Um E2E pode cruzar várias regras; mantenha verificações identificadas
e não esconda a falha de uma delas no resultado final.

## Cobertura e veredito

Matriz: `fonte/regra | CT/variação | plataforma | persona | resultado | prova | bug`.
Toda regra em escopo tem CT ou lacuna explícita. Verifique regras sem cenário,
cenários sem fonte, CTs planejados sem execução e requisitos com prova insuficiente.
Itens administrativos fora do QA funcional não viram cenários só para inflar números.

Mantenha separados:

- **Classificação:** itens que receberam um estado; não significa executados.
- **Execução conclusiva:** CTs `PASSOU + FALHOU`.
- **Aprovação entre conclusivos:** `PASSOU / (PASSOU + FALHOU)`.
- **Cobertura de execução:** conclusivos / CTs aplicáveis planejados.
- **Regra comprovada:** todos os CTs obrigatórios da regra passaram; cenários
  falhos cobrem a investigação, mas não comprovam atendimento do requisito.

Bloqueados entram nos aplicáveis; não aplicáveis com justificativa saem desse
denominador e permanecem visíveis. Total zero é sem base. Recalcule após reteste
sem somar tentativas antigas como novos CTs. Não confunda bug count com CT count.
