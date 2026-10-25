---
name: esteira-bootstrap
description: >
  Instala e configura a esteira (pipeline autônomo de issues com agentes Claude no Herdr) no projeto
  aberto: confere os pré-requisitos (Claude Code, Herdr, gh autenticado com escopo de projeto),
  pergunta se usa um board do GitHub existente ou cria um novo com as colunas da esteira, se o projeto
  é público (liga os monitores de issues e PRs) ou privado, copia skills e scripts para .claude/,
  cria labels e o repositório de evidências, e sobe os spaces, as vagas e os loops no Herdr. Use quando
  o usuário chamar /esteira-bootstrap ou pedir para "instalar a esteira", "configurar a esteira neste
  projeto", "fazer o bootstrap da esteira".
---

# Bootstrap da esteira

Você instala a esteira **no projeto da pasta atual**. Aqui, diferente das skills da esteira, você
conversa com o usuário: pergunte o que for decisão dele (com `AskUserQuestion`) e explique em
português o que está fazendo. Nada de instalar ferramenta do projeto dele (linguagem, banco,
framework): isso é dele.

```bash
E=.claude/skills/esteira-bootstrap/scripts/esteira.py
```

As skills da esteira já estão em `.claude/skills/` (foi assim que esta chegou aqui). Se esta skill
estiver rodando de outro lugar (do clone, de `~/.claude/skills`), explique que ela precisa ser
copiada para o `.claude/skills` do projeto, com as demais (veja o README), e pare.

## 1. Pré-requisitos

```bash
python3 $E check
```

Mostre uma tabela curta (item, ok/falta, como resolver). Os obrigatórios: git, Python 3.10+,
`flock`, Claude Code, Herdr, **estar dentro do Herdr**, `gh` instalado, autenticado e com o escopo
`project`, e a pasta estar num repositório com remoto no GitHub (num monorepo, a pasta do projeto
pode ser uma subpasta: a esteira registra isso como `subdir`).

- Faltando algo obrigatório: diga exatamente o comando para resolver. O que não pede `sudo` nem
  interação você pode oferecer para rodar (por exemplo `preparar-video.sh instalar`, que só baixa os
  modelos de voz). Login (`gh auth login`, `gh auth refresh -s project`) é interativo: sugira que
  ele rode com `! <comando>` no prompt. Depois, rode o `check` de novo.
- Fora do Herdr: explique que a esteira roda em cima dele (cada etapa é um space, cada trabalhador
  é uma aba com um Claude aberto) e que ele precisa abrir o Herdr, entrar na pasta do projeto, rodar
  `claude` e chamar `/esteira-bootstrap` de lá. Pare aqui.
- Ferramentas do vídeo do QA faltando: não bloqueia; avise que o QA vai rodar sem vídeo até ele
  instalar (mostre o que falta).
- Confirme a conta do `gh` mostrada no `check`: é com ela que a esteira vai comentar, abrir PR e
  fazer merge. Se não for a certa, pare: ele troca e roda de novo.

## 2. Perguntas

Rode `python3 $E projects` para ter a lista de boards do dono do repositório. Depois pergunte, numa
chamada só de `AskUserQuestion`:

1. **Board**: "Usar um projeto do GitHub que você já tem, ou criar um novo com as colunas da
   esteira?" Opções: "Criar um novo (Recomendado)" e os projetos existentes (até três; o resto ele
   escreve em "Other"). Num board existente a esteira não mexe nas visões que ele já usa: cria uma
   visão nova, "Esteira", em quadro e filtrada pelo repositório. Se o board não tiver as colunas, ela
   também cria um campo próprio, "Esteira", sem apagar nada; nesse caso avise que ele precisa abrir
   a visão "Esteira" e trocar o agrupamento das colunas para esse campo na interface do GitHub (a
   API cria a visão, mas não escolhe o campo das colunas).
2. **Projeto**: "O projeto é open source e recebe contribuição de fora?" Opções: "Privado / só eu e
   o time" e "Público, com contribuições externas". Público liga a triagem de issues e o monitor de
   PRs (com a quarentena silenciosa); privado não sobe esses dois.
3. **Merge**: "Quando o QA aprovar, a esteira já faz o merge do PR?" Opções: "Sim, faz o merge
   (Recomendado)" e "Não, eu faço o merge na homologação".
4. **Idioma**: "Em que idioma a esteira escreve no GitHub (issues, PRs, comentários)?" Opções:
   "Inglês" e "Português".

A branch base é a padrão do repositório (mostrada no `check`); só pergunte se houver `develop` e
`main` e não der para saber qual recebe os PRs. Os mantenedores são a conta ativa; pergunte se há
mais alguém cujas issues e comentários devem ser tratados como confiáveis, só em projeto público.

## 3. Instalar e configurar

```bash
python3 $E install
python3 $E configure --board <new|número> [--title "<nome>"] --visibility <public|private> \
  --merge-on-qa <yes|no> --language <en|pt-BR> [--base <branch>] [--maintainers a,b]
```

- `install` copia os scripts do pipeline (que vêm dentro desta skill, em `pipeline/`) para
  `.claude/esteira/` e põe essa pasta no `.git/info/exclude`: o config tem caminhos desta máquina,
  então fica fora do git sem mexer no `.gitignore` do projeto. As skills em `.claude/skills/` ele
  pode versionar, se quiser que o time tenha as mesmas. Reinstalar atualiza os scripts e preserva o
  `config.json` e `hooks/`.
- `configure` cria (ou adota) o board e as colunas, liga o board ao repositório, cria as labels que
  faltam (`triaged`, `community-report`, tipos e, em público, `future`) e o repositório de
  evidências `<repo>-evidence` (mesma visibilidade do projeto; é onde o QA publica o vídeo das
  rodadas aprovadas e o planejamento as imagens de UI). Grava `.claude/esteira/config.json`.
- Se `configure` recusar (colunas faltando num board existente, escopo do `gh`), explique e resolva
  com ele.
- Num board existente, a saída traz `board.view`. Se `agrupamento_manual` vier `true`, passe o link
  do board e diga: na visão "Esteira", "Column by" → o campo em `agrupar_colunas_por`.

Diga a ele, em uma linha cada:
- se o projeto precisa derrubar algo específico no fim de cada trabalho (emulador, VM, display de
  teste), isso vai num gancho executável `.claude/esteira/hooks/cleanup.sh <etapa> <issue>`;
- recurso que só cabe um por vez vai sob `.claude/esteira/bin/lock.sh <nome> <comando>`;
- as instruções do projeto (`CLAUDE.md`, `README.md`) são o que os agentes leem para saber como
  rodar e testar: quanto mais claras, melhor a esteira trabalha.

## 4. Subir no Herdr

```bash
.claude/esteira/bin/start-all.sh
.claude/esteira/bin/status.py
```

Isso cria os spaces (`plan`, `dev`, `review`, `qa`, `homolog`, `release`, `supervisor` e, em
público, `monitor-issues` e `monitor-pr`), abre uma vaga com um Claude em cada etapa e põe os loops
para rodar. Se um space com o mesmo nome já existir e for de outro projeto (a aba 1 roda o loop de
outra pasta), troque os nomes no config (`stages.<x>.space`, `monitor_spaces`, `manual_spaces`) para
algo como `<projeto>-plan` e rode `start-all.sh` de novo.

## 5. Fechar

Explique em português, curto:

- **Como entra trabalho**: `/esteira-criar-issue <o que você quer>` cria a issue já na Planning
  queue; issue criada à mão entra quando ele a põe na Planning queue (ou, em projeto público, pela
  triagem). Daí em diante: plano → dev → revisão → QA → **Ready for release**, onde ele homologa.
- **Onde ele entra**: só em "Ready for release" (homologar e lançar) e em "Needs maintainer"
  (decisões que a esteira não toma sozinha).
- **Ritmo**: as filas são olhadas a cada 15 min (`loops.dispatch_seconds`); `/esteira-fila <etapa>`
  adianta uma passada.
- **Comandos**: `/esteira-status` (o que está rodando), `/esteira-up` (subir de novo depois de um
  reinício), `/esteira-limpar-abas`.
- O link do board e o caminho do config.
