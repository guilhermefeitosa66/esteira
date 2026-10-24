# Utilitários locais e contrato 1.0

Python 3.10+; os utilitários usam somente biblioteca padrão. Execute pelo caminho
real da skill, não suponha um comando `qa` no PATH. `qa_artifacts.py` organiza
registros fornecidos pelo agente; `qa_local.py` apoia a subida local apontando
portas livres e servindo respostas HTTP que o agente declarou. Nenhum deles sobe
ou executa a aplicação, descobre MCPs ou integrações, decide contrato, nem
substitui julgamento, autorização ou revisão visual. Datas são ISO com fuso.

## Comandos

Nos exemplos, `scripts/…` é o caminho dentro da pasta da skill e `qa/runs/…` é
relativo à **pasta do projeto**: rode a partir da pasta do projeto chamando o
script pelo caminho real da skill, ou passe caminhos absolutos. Nunca crie
rodada, spec ou log dentro da pasta da skill. Substitua caminhos e valores.
Os comandos estão em Linux/macOS (`python3`); em Windows use `python -X utf8`
e as aspas próprias do shell.

```text
python3 scripts/qa_artifacts.py init --path "qa/runs/rodada-001" --id rodada-001 --project "Projeto" --client "Cliente" --platform web --executor Codex
python3 scripts/qa_artifacts.py validate --run "qa/runs/rodada-001/run.json"
python3 scripts/qa_artifacts.py evidence --run "qa/runs/rodada-001/run.json" --id EV-001 --file "cases/ct-001/attempt-01/step-01.png" --kind screenshot --caption "Mensagem real após enviar formulário" --tool "ferramenta efetivamente usada" --at "2026-09-08T14:00:00-03:00"
python3 scripts/qa_artifacts.py checkpoint --run "qa/runs/rodada-001/run.json" --note "CT-001 concluído" --next "Retestar BUG-002 na build confirmada"
python3 scripts/qa_artifacts.py resume --run "qa/runs/rodada-001/run.json"
python3 scripts/qa_artifacts.py report --run "qa/runs/rodada-001/run.json" --snapshot entrega-001
python3 scripts/export_pdf.py --input "qa/runs/rodada-001/delivery/entrega-001/executive.html" --output "qa/runs/rodada-001/delivery/entrega-001/executive.pdf"
python3 scripts/qa_local.py ports --count 3 --start 18000 --end 18999 --avoid 5432,8080
python3 scripts/qa_local.py mock --spec "qa/runs/rodada-001/mocks/gateway.json" --port 18090 --log "qa/runs/rodada-001/cases/ct-001/attempt-01/gateway-requests.jsonl"
python3 scripts/qa_video.py narrar --roteiro "qa/runs/rodada-001/work/video/roteiro.json" --saida "qa/runs/rodada-001/work/video/narracao"
python3 scripts/qa_video.py marco --log "qa/runs/rodada-001/work/video/marcos.jsonl" --tipo cena --cena ct-001-p01
python3 scripts/qa_video.py aguardar --log "qa/runs/rodada-001/work/video/marcos.jsonl" --narracao "qa/runs/rodada-001/work/video/narracao" --cena ct-001-p01
python3 scripts/qa_video.py montar --roteiro "…/roteiro.json" --narracao "…/narracao" --bruto "…/bruto.mp4" --log "…/marcos.jsonl" --saida "qa/runs/rodada-001/cases/ct-001/attempt-01/jornada-narrada.mp4"
python3 scripts/qa_video.py conferir --video "qa/runs/rodada-001/cases/ct-001/attempt-01/jornada-narrada.mp4"
```

`qa_video.py` sintetiza a narração, registra marcos, monta o vídeo e extrai
quadros para a revisão. Ele **não grava a tela** e não executa o sistema sob
teste: a captura é feita pelas ferramentas do hospedeiro, num display ou aparelho
que a rodada controla. Precisa de `ffmpeg`/`ffprobe` e de um motor de voz, como
`export_pdf.py` precisa de um navegador; nada é instalado no projeto. Método
completo em [video-narrado.md](video-narrado.md).

O diretório de `init` deve ser novo. `evidence` calcula hash do arquivo existente;
não cria captura. Antes da distribuição, revisar arquivo/caption e dados sensíveis;
registrar `reviewed: true` e `review_note` no JSON, ou usar `--reviewed --review-note`
quando a revisão já ocorreu. Marcar esses campos não executa uma revisão por IA.
Não registrar segredos. `report` recusa inconsistências estruturais e cria snapshot
novo; documentos anteriores ficam preservados. `export_pdf` recusa sobrescrita.

## Apoio à execução local

`ports` só considera livre a porta em que o bind real funciona em loopback e em
todas as interfaces; `--avoid` exclui portas vistas em `docker ps`, compose ou
configuração. O resultado não reserva a porta: suba o serviço em seguida e
confirme que é o seu processo que escuta.

`mock` valida o spec antes de abrir a porta, escuta em `127.0.0.1` por padrão e
roda até receber SIGINT/SIGTERM; execute-o em segundo plano e anote o PID da
linha JSON de início. Spec:

```json
{
  "name": "gateway de pagamento (dublê)",
  "routes": [
    {"name": "criar cobrança", "method": "POST", "path": "/v1/charges",
     "responses": [{"status": 500, "body": "indisponível"}, {"status": 201, "json": {"id": "ch_1"}}]},
    {"method": "GET", "path_regex": "^/v1/charges/[^/]+$", "delay_ms": 200,
     "responses": [{"status": 200, "json": {"status": "paid"}}]}
  ]
}
```

Vence a primeira rota que casar método e caminho (query string é registrada,
não entra no casamento; `path_regex` precisa casar o caminho inteiro; `ANY`
aceita qualquer método; rota `GET` não atende `HEAD`). `responses` é sequência:
depois do último item, ele se repete; a posição só recomeça ao reiniciar o
processo, então use um dublê (e um log) por CT/tentativa. `status` vai de 200 a
599; cada resposta
usa `json` ou `body`. Chave desconhecida no spec é recusada, para que um erro
de digitação não mude o teste em silêncio.

Rota não declarada recebe 501 e aparece no log, para que chamada inesperada do
alvo não passe despercebida. Também ficam registrados, com `route: null` e
`error`, o que o servidor recusa antes das rotas: cliente em HTTPS ou HTTP/2
contra o dublê (que só fala HTTP/1.1 sem TLS), linha ou cabeçalhos grandes
demais, corpo interrompido. Uma linha extra `response_error` indica resposta
que não pôde ser entregue.

O log é JSONL criado em modo exclusivo e permissão restrita, uma linha por
requisição; caminho com link de filesystem é recusado. Cabeçalho com nome
sensível vira `<removido>`; cabeçalho de contrato apanhado por conter `key`,
`token` ou `signature` (por exemplo `Idempotency-Key`, necessário para provar
retry) volta ao log se listado em `"unredacted_headers"` no spec; nomes de
autenticação, cookie, segredo e sessão nunca voltam. Caminho, query e corpo
**não** são saneados: use credenciais de teste. Pare o dublê antes de registrar
o log como evidência `technical`, revise-o e cite no `caption` (e no `name` do
spec) o ID da fonte do contrato simulado. O relatório incorpora o extrato do
`.jsonl`. O dublê não prova o comportamento do terceiro real; método em
[dubles-de-integracoes.md](dubles-de-integracoes.md).

## Estrutura de run.json

O `init` cria metadados e listas vazias. Preencha com dados observados usando o
editor do hospedeiro; os helpers não geram interpretação funcional. Exemplo de
CT planejado (não é registro de teste executado):

```json
{
  "schema_version": "1.0",
  "id": "rodada-001",
  "project": "Portal exemplo",
  "client": "Cliente exemplo",
  "consultancy": "QA BOT",
  "author": "",
  "executor": "Codex",
  "created_at": "2026-09-08T14:00:00-03:00",
  "demonstration": false,
  "context": {
    "environment": "ambiente a confirmar",
    "build": "não identificada",
    "platform": "web",
    "persona": "operador",
    "tenant": "a confirmar"
  },
  "summary": "Planejamento; execução ainda não iniciada.",
  "sources": [{"id": "DOC-01", "location": "especificacao.md", "version": "1", "reviewed_sections": ["3.2"]}],
  "requirements": [{"id": "RF-01", "text": "Ordem de serviço é obrigatória.", "source": "DOC-01", "locator": "3.2", "scope": "in"}],
  "scenarios": [{
    "id": "CT-001", "title": "Recusar envio sem ordem de serviço",
    "objective": "Impedir gravação incompleta", "rules": ["RF-01"],
    "preconditions": "Conta e massa de teste a verificar no ambiente.",
    "gherkin": ["Dado um formulário sem ordem de serviço", "Quando enviar", "Então deve recusar sem gravar"],
    "status": "NAO_EXECUTADO", "bugs": [],
    "steps": [{"id": "P-01", "action": "Enviar formulário vazio", "expected": "Recusa sem gravação", "actual": "", "status": "NAO_EXECUTADO", "evidence": []}]
  }],
  "evidence": [], "bugs": [], "effects": []
}
```

Um pull request entra como fonte, sem campo novo no contrato: `location` é o
link, `version` é o commit head avaliado e `reviewed_sections` diz o que foi lido
(`descrição`, `diff`, `threads`); história ou work item vinculado é fonte à
parte, com a própria revisão como `version`. Novo commit no PR é nova versão:
antes de trocar o `build` da rodada, fixe em cada CT já executado o
`context.build` com que ele rodou. Em execução local, `context.environment`
declara a montagem, por exemplo `local — commit abc1234 — dublês: gateway`, e
`build` recebe o commit efetivamente montado (SHA de merge, com head e destino,
quando a ref de merge foi usada). Processos, projeto compose, worktree, dublês
e banco da rodada entram em `effects` **antes de nascer** (`uncertain`), passam
a `active` quando confirmados e terminam `cleaned` ou `kept`.

Ao executar, atualizar contexto real, `actual`, `status`, referências de prova,
conclusão e bloqueios. `context` no CT sobrescreve campos da rodada, permitindo
múltiplas plataformas/builds. Valores desconhecidos precisam ser declarados como
limite; preencher um texto qualquer satisfaz o tipo, mas não comprova o contexto.

### Campos adicionais

| Registro | Campos e finalidade |
|---|---|
| Evidence | `id`, `path` relativo ao run, `sha256`, `kind`, `caption`, `captured_at`, `tool`, `reviewed`, `review_note` |
| Kind | `screenshot` (PNG/JPEG real, conferido por assinatura), `technical` (extrato técnico), `download`, `recording` (gravação de tela, em geral o vídeo narrado) |
| Recording | O formato **não** é verificado: a garantia vem da revisão. `path` sem `:` (recusado como caminho) e com extensão real (`.mp4`, `.webm`), que é o que faz o relatório escolher o decodificador. Não substitui o screenshot do passo conclusivo. Sem vínculo a passo, vale como gravação da rodada e sai no relatório executivo; vinculada a um passo, sai na página do CT |
| CT status | `PASSOU` (verificações obrigatórias com prova suficiente, nenhum passo fora de PASSOU/NAO_APLICAVEL, nenhum bug impeditivo aberto), `FALHOU` (regra violada, com prova e bug aberto vinculado), `BLOQUEADO` (faltou acesso, massa, definição ou capacidade; exige `reason`), `NAO_EXECUTADO` e `NAO_APLICAVEL` (a regra não se aplica; exige `reason` e `decision` com a fonte) |
| Plataforma | `context.platform` aceita só `web`, `web-mobile`, `android`, `ios`, `desktop` (passo conclusivo exige screenshot), `api`, `database` e `document`. Consumidor de fila, job, migração e webhook provados por extrato técnico usam `api` (ou `database` quando a prova é a consulta), com o ponto de entrada real descrito no CT |
| CT | `reason` obrigatório em bloqueio/N/A; `decision` em N/A; `conclusion` opcional; `bugs` ligados às regras do CT |
| Passo | `reason` para bloqueio/N/A; `actual` e prova obrigatórios em PASSOU/FALHOU |
| Bug | `id`, `title`, `scenario`, `context` da falha original, `status`, `expected`, `observed`, `steps` textuais, `impact`, `severity`, `frequency`, `evidence` original |
| Bug status | `ABERTO`, `EM_RETESTE`, `REABERTO`, `CORRIGIDO_VERIFICADO` |
| Retest no bug | `at`, `build`, `scenario`, `status: PASSOU`, `conclusion`, `evidence` nova pertencente ao CT aprovado |
| Effect | `id`, `action`, `state`, `cleanup`. `state`: `uncertain` (não se sabe se ocorreu ou se ainda existe; gera pendência de reconciliação), `active` (existe e pede limpeza), `cleaned` (limpeza conferida), `kept` (mantido por decisão registrada) |

As listas usam IDs únicos, incluindo comparação sem diferenciar maiúsculas e
minúsculas, para portabilidade Windows. Nomes reservados como CON são recusados.
Todo CT inclui `steps` como lista (vazia se bloqueado antes de iniciar).
CT → bug e bug → CT são bidirecionais. Para reteste
em uma nova rodada, importar a referência e provas históricas necessárias,
preservando a origem, e apontar o bug ao CT corrente equivalente. Original e
reteste não podem compartilhar o mesmo hash; a cronologia deve ser coerente.
`retest.scenario` é o próprio CT vinculado ao bug, com a mesma persona, tenant e
plataforma do contexto original; um health check diferente não fecha o defeito.
Tentativa de reteste bloqueada/em espera pode usar `status: BLOQUEADO` ou
`NAO_EXECUTADO` com `reason`, sem criar prova fictícia. Registrar `at` e build
quando conhecidos; ausência é exibida explicitamente no documento. Isso não
permite marcar o bug como corrigido. Toda forma de `retest` é validada.
Efeitos/capacidades/autorizações
detalhados podem permanecer no `project.md` e handoff, sem segredos.

`validate` retorna JSON `valid/errors/warnings`, exit 0 válido, 1 inconsistente,
2 erro de uso/leitura. Bloqueios legítimos não invalidam o formato; são exibidos.
Ele verifica estados, vínculos, arquivos, hashes e metadados. Não prova que
screenshots mostram o esperado, que uma fonte foi compreendida ou que texto está
sanitizado. A revisão real é indispensável. Lock é local e cobre comandos de
mutação do helper, não edições concorrentes feitas por outros programas.

## Relatórios e preservação

Saída: `executive`, `detail`, `plan`, `cases/<CT>`, `bugs/<BUG>` em MD/HTML,
cópias das provas revisadas, snapshot da base e hashes dos arquivos gerados.
HTML incorpora imagens e funciona offline; Markdown tem links relativos.
Gravação não é incorporada: o HTML a toca por um player que aponta para o arquivo
irmão em `evidence/`, então mover só o `.html` quebra a reprodução.
PDFs são gerados do HTML usando navegador local.
O exportador remove links de arquivo da impressão para não gravar caminhos da
máquina geradora como navegação quebrada; links web são preservados. Para navegar
entre documentos e downloads em outra máquina, usar HTML/Markdown relativos.
Os PDFs mantêm texto e screenshots incorporados para leitura independente;
gravação fica de fora, com legenda, nome do arquivo e hash no lugar — vídeo é
prova de HTML e Markdown.
Arquivos adicionados depois,
incluindo PDF e revisão visual, precisam de manifesto final próprio se forem
parte da distribuição; o manifesto inicial não os certifica.

Não copie diretório bruto para board. Publique apenas os artefatos revisados,
com os mecanismos disponíveis no destino. O helper não realiza publicação.
