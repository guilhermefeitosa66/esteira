# Evidências que permitem conferir a conclusão

## Captura e procedência

Uma pasta por CT e uma subpasta por tentativa preservam a sequência. Exemplo:
`runs/<run>/cases/ct-014/attempt-02/evidence/step-03-resultado.png`.
O mesmo print pode ser referenciado como contexto compartilhado, identificado
como tal; não apresente uma cópia como nova execução. Evidência do dev é insumo
para investigar; prova de aceitação e reteste deve vir da execução de QA.

Registre evidência com ID, CT/passo/tentativa, data com fuso, plataforma,
build, ambiente/persona, ferramenta, origem, arquivo, hash e o que comprova.
Hash detecta alteração; não prova autenticidade ou qualidade sem observação.
Para dado técnico, preserve request/response/query/arquivo real sanitizado e
compare esperado × observado. Rotule qualquer painel derivado como **evidência
técnica renderizada**, com referência à origem; não é print da aplicação.
Prova obtida em execução local declara commit, montagem e dublês na legenda ou
no contexto; o log de um dublê é evidência técnica do que o alvo enviou, não
do comportamento do terceiro real.

Capture contexto antes da ação quando ele importa e o resultado após cada
verificação. Mostre o campo/linha/erro com tamanho legível. Uma tela de contexto
pode acompanhar recorte de detalhe ou destaque que não altere o valor. Não
injete resultado no DOM, não esconda erro e não gere imagem como prova de QA.
Anotações e expurgo seguem ferramentas permitidas pelo hospedeiro; preserve
origem restrita e descreva transformações, sem contornar restrições de ferramentas.

Credenciais não são prova de identidade. Use alias de conta/persona e contexto
de sessão seguro. Evite coletar segredos. Se um bruto inevitavelmente os incluir,
segregue e saneie antes de distribuição. HAR/trace/log não é automaticamente
seguro. Nunca leve dados de um cliente ao pacote reutilizável da skill.

## Documento de CT / reteste

Use [scenario.md](../assets/templates/scenario.md) para o CT e
[retest.md](../assets/templates/retest.md) para o reteste.
Comece por ID e título, objetivo, regra e fonte, história/bug original,
status declarado no board, ambiente/build/persona/plataforma e resultado QA.
Depois: pré-condições/massa, BDD, critérios de aceite e sequência numerada.

Cada passo responde:

1. **Como chegamos:** menu/rota, persona, filtro, ação e valores necessários.
2. **Esperado:** critério objetivo daquele ponto.
3. **Observado:** valor/mensagem real, sem inferência não comprovada.
4. **Prova:** captura/artefato apropriado com legenda que diz o que comprova.
5. **Conclusão:** passou, falhou ou bloqueou, vinculando defeito quando existir.

Fecha com alcance da prova, limitações, efeito sobre dados e roteiro de
reconferência. No reteste, mostrar antes/depois por tentativas datadas e builds;
a evidência anterior permanece histórica. Roteiro deve permitir reprodução
por quem não acompanhou a conversa.

## Apresentação

Use identidade do projeto; QA BOT é padrão neutro quando não há outra
marca escolhida. Autoria humana deve ser a informada, sem cargo inventado;
declare executor técnico quando pertinente. Não importar logos de outro cliente.

PDF A4 com títulos claros, texto pesquisável, hierarquia de informação e status
escrito além da cor. Evite reduzir captura inteira até que o campo desapareça.
Separe passos longos em páginas, mantendo legenda com a imagem. Para app use
proporção original; para web muito larga, contexto mais detalhe. Não force
HML/PRD lado a lado se só um foi testado. Não estabeleça meta de páginas.

Entregas de campanha: plano/rastreabilidade, executivo para decisão, detalhado
com roteiro por CT, PDF por CT e por bug pertinente. Para pedido pequeno, reduza
a quantidade de arquivos preservando a prova. Tudo deriva dos mesmos resultados.
Executivo abre com conclusão, números com denominadores, impacto, pendências e
decisões. Detalhamento técnico fica acessível sem dominar a leitura gerencial.

## Gate de evidências

Antes de distribuir, abrir as provas e confrontar valor/legenda/veredito;
verificar referências, duplicatas suspeitas, arquivos faltantes, build/persona,
antes/depois, dados sensíveis e integridade. Para exportação, abrir o download.
Depois renderizar os PDFs e inspecionar páginas: legibilidade, cortes, paginação,
imagens, acentos, links e conclusões. Existir em disco não significa aprovado.
Registre revisão e pendências. Se faltar prova, recapture quando seguro; caso
contrário, reduza a conclusão ao que está demonstrado e declare o bloqueio.
