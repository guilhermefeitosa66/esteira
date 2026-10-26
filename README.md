# esteira

Uma esteira de produção para issues do GitHub, tocada por agentes do Claude Code.

Você descreve o que quer numa issue. A esteira planeja, implementa, revisa, testa (com vídeo narrado
mostrando que funciona) e deixa pronto para você homologar. Cada etapa tem a sua fila no board do
GitHub e um agente dedicado no [Herdr](https://github.com/herdrdev/herdr); loops em shell, que não
gastam token, entregam a próxima issue para quem estiver livre.

> **Só Linux.** A esteira foi feita e testada no Linux e depende dele: os scripts usam `/proc`,
> `flock` e X11 (os displays próprios onde o QA grava os testes), e o Herdr é a base de tudo. macOS
> e Windows (mesmo com WSL) não foram testados e, do jeito que está, não devem funcionar.
>
> **Usa outro sistema?** As skills e os scripts são texto legível e o Claude Code os entende bem:
> depois de copiar as skills para o projeto, peça a ele para adaptar ao seu contexto. Por exemplo:
> *"adapte as skills `esteira-*` e os scripts em `.claude/skills/esteira-bootstrap/pipeline/bin/`
> para o macOS: troque o `flock`, o `/proc` e o Xephyr por equivalentes daqui"*. O mesmo vale para
> outro multiplexador no lugar do Herdr, outro jeito de testar ou outras colunas no board.

```
 Planning queue ─► plan ─► Dev queue ─► dev ─► Review queue ─► review ─► QA queue ─► qa ─► Ready for release
                    │                    │                       │                    │          (você homologa)
                    └────────────────────┴───── Needs maintainer (só o que é decisão sua) ─┘
```

Você só entra em dois lugares: **Ready for release** (conferir e lançar) e **Needs maintainer**
(decisões que a esteira não toma sozinha).

## Sumário

- [Como funciona](#como-funciona)
- [Pré-requisitos](#pré-requisitos)
- [Instalação](#instalação)
- [O dia a dia](#o-dia-a-dia)
- [O QA e o vídeo narrado](#o-qa-e-o-vídeo-narrado)
- [Projeto público: triagem e monitor de PRs](#projeto-público-triagem-e-monitor-de-prs)
- [Configuração](#configuração)
- [Recursos da máquina](#recursos-da-máquina)
- [Segurança](#segurança)
- [Problemas comuns](#problemas-comuns)
- [O que tem neste repositório](#o-que-tem-neste-repositório)

## Como funciona

**O board é a fonte da verdade.** Cada issue está numa coluna de um GitHub Project. As colunas de
fila (`Planning queue`, `Dev queue`, `Review queue`, `QA queue`) são onde a issue espera; as colunas
ativas (`Planning`, `In development`, `In review`, `In QA`) dizem que um agente está trabalhando nela.

**Cada etapa é um space do Herdr.** O Herdr é um multiplexador de terminal feito para agentes:
spaces, abas e um socket para controlar tudo de fora. A esteira cria um space por etapa:

| Space | Aba 1 (`monitor`) | Demais abas |
|---|---|---|
| `product` | — | seu, para discovery, criar issues (`/esteira-criar-issue`) e acompanhar a esteira |
| `plan`, `dev`, `review`, `qa` | o loop da fila (`dispatch.py`), sem LLM | as **vagas**: um Claude sempre aberto |
| `homolog`, `release` | — | seus, para homologar e lançar |
| `supervisor` | o supervisor (`supervise.py`), sem LLM | — |
| `monitor-issues`, `monitor-pr` | triagem e monitor de PRs (só em projeto público) | — |

**Vagas fixas.** Cada etapa tem um número fixo de vagas (1 por padrão; `/esteira-scale qa 3` muda).
Uma vaga é uma aba com um Claude que nunca é fechado: entre um trabalho e outro ele recebe `/clear`.
Havendo issue na fila e vaga livre, o loop da fila move a issue para a coluna ativa, limpa a vaga e
manda a skill da etapa (`/esteira-dev 42`), conferindo que o turno começou.

**O loop acorda quando um trabalho termina.** Sem nada acontecendo, o loop olha o board a cada 15
minutos. Mas quando um trabalho termina, o `worker.py end` avisa localmente (um arquivo
`wake-<etapa>` no diretório de estado) o loop da própria etapa, que ganhou uma vaga livre, e o da
etapa seguinte, que ganhou um item na fila. O loop roda a passada em segundos, sem esperar os 15
minutos. Esperar pelo aviso não consulta o GitHub; vários fins juntos viram uma passada só.

**O trabalhador termina sozinho.** Cada skill de etapa trabalha numa worktree própria (o seu
checkout principal nunca é tocado), comenta na issue o que fez, derruba tudo o que subiu e chama
`worker.py end`, que move a issue para a próxima fila e devolve a vaga.

**O supervisor cuida do que trava.** A cada 2 minutos ele confere as vagas: Enter que se perdeu,
diálogo parado, agente ocioso com a issue na coluna ativa (manda um lembrete e, se continuar
parado, recicla a vaga e devolve a issue para a fila), duplicatas depois de um reinício, tarefa em
segundo plano esquecida. Depois de 3 tentativas fracassadas na mesma etapa, a issue vai para
`Needs maintainer`.

**Nada se perde quando algo cai.** Worktrees são idempotentes (o que ficou sem commit vira um patch
em `salvage/`), o dev faz commits `wip:` de checkpoint, a revisão comita cada correção na hora e o
QA guarda a rodada por commit testado. Quem retoma uma issue continua de onde parou.

## Pré-requisitos

A esteira em si precisa só disto:

| Ferramenta | Para quê | Como instalar |
|---|---|---|
| [Claude Code](https://claude.com/claude-code) | os agentes | `curl -fsSL https://claude.ai/install.sh \| bash` |
| [Herdr](https://github.com/herdrdev/herdr) | os spaces, as abas e o controle dos agentes | binário nas releases do repositório do Herdr |
| [GitHub CLI](https://cli.github.com) (`gh`) | board, issues, PRs | `sudo apt install gh` / `sudo dnf install gh`, depois `gh auth login` e `gh auth refresh -s project` |
| git, Python 3.10+, `flock` | scripts | já vêm na maioria das distros Linux (`flock` é do `util-linux`) |

**Linux.** A esteira foi feita e testada no Linux (veja o aviso no topo). Distros testadas: Ubuntu
e derivadas; qualquer distro com as ferramentas acima deve servir.

**O ambiente do seu projeto é com você.** Linguagem, banco, Docker, SDKs: os agentes rodam e testam
o projeto do jeito que o README e o `CLAUDE.md` dele explicam, com o que já está instalado na
máquina. A esteira não instala nada disso.

**Para o vídeo do QA** (opcional, mas é o que torna a homologação rápida): `ffmpeg`, `Xephyr`,
`xdotool`, `xdpyinfo`, Node 18+, Chrome ou Chromium e `uv`. Depois da instalação,
`.claude/skills/esteira-qa/scripts/preparar-video.sh verificar` diz o que falta e
`preparar-video.sh instalar` baixa os modelos de voz offline. Sem essas ferramentas o QA roda
normalmente, só que sem vídeo.

## Instalação

A esteira é um conjunto de skills do Claude Code. Instalar é colocar essas skills no
`.claude/skills/` do projeto em que você trabalha; daí em diante, a skill `/esteira-bootstrap`
configura o resto.

### O jeito mais fácil: peça ao Claude

Abra o Claude Code na pasta do seu projeto (de preferência já dentro do Herdr) e mande:

```text
Instale a esteira neste projeto: clone https://github.com/guilhermefeitosa66/esteira numa pasta
temporária, rode o install.sh dela a partir desta pasta (ele copia as skills esteira-* para
.claude/skills), apague o clone e me diga o que foi instalado. Depois, chame /esteira-bootstrap.
```

Se as skills novas não aparecerem logo para o `/esteira-bootstrap`, saia e abra o Claude de novo
na mesma pasta: ele lê o `.claude/skills/` ao iniciar.

### Passo a passo

**1. Copie as skills para o projeto.** Na pasta onde você abre o Claude Code para trabalhar:

```bash
cd ~/caminho/do/seu-projeto
d=$(mktemp -d) && git clone -q --depth 1 https://github.com/guilhermefeitosa66/esteira.git "$d" \
  && "$d/install.sh" && rm -rf "$d"
```

O comando clona a esteira numa pasta temporária, copia as pastas `skills/esteira-*` para
`.claude/skills/` (criando a pasta se ela ainda não existe) e apaga o clone. Nenhuma outra skill do
projeto é tocada. Se preferir fazer à mão, é só isto:

```bash
git clone --depth 1 https://github.com/guilhermefeitosa66/esteira.git /tmp/esteira
mkdir -p .claude/skills && cp -r /tmp/esteira/skills/esteira-* .claude/skills/
```

**Monorepo?** Copie para o `.claude/skills/` da pasta onde você abre o Claude Code:

- na **subpasta do projeto** (`monorepo/apps/loja/.claude/skills/`), para a esteira cuidar só
  daquele projeto. Ela registra a subpasta e os agentes trabalham dentro dela;
- na **raiz do monorepo** (`monorepo/.claude/skills/`), para a esteira cuidar do repositório
  inteiro.

Cada projeto do monorepo pode ter a sua esteira, com o seu board. Só os nomes dos spaces no Herdr
precisam ser diferentes (veja [Configuração](#configuração)).

**Versionar ou não?** As skills em `.claude/skills/` podem ir para o git do projeto, se você quiser
que o time tenha as mesmas. A configuração que o bootstrap gera (`.claude/esteira/`) tem caminhos
da sua máquina e fica fora do git automaticamente (via `.git/info/exclude`, sem mexer no seu
`.gitignore`).

**2. Abra o Herdr, entre na pasta do projeto e rode o Claude:**

```bash
herdr
# dentro do Herdr:
cd ~/caminho/do/seu-projeto
claude
```

A esteira roda em cima do Herdr: o bootstrap precisa ser chamado de dentro dele, porque é ali que
ele cria os spaces e as abas.

**3. Chame o bootstrap:**

```
/esteira-bootstrap
```

Ele:

1. confere os pré-requisitos e diz como resolver o que faltar;
2. pergunta:
   - se você quer **usar um projeto (board) que já tem no GitHub** ou **criar um novo** com as
     colunas da esteira;
   - se o projeto é **público com contribuições externas** (liga a triagem de issues e o monitor de
     PRs) ou **privado**;
   - se o QA aprovado **já faz o merge** do PR ou se você prefere fazer o merge na homologação;
   - em que **idioma** a esteira escreve no GitHub (inglês ou português);
3. instala os scripts do pipeline em `.claude/esteira/` (fora do git, via `.git/info/exclude`);
4. cria ou adota o board, as labels e um repositório de evidências (`<repo>-evidence`, com a mesma
   visibilidade do projeto, onde ficam os vídeos do QA);
5. cria os spaces no Herdr, abre as vagas e põe os loops para rodar.

Pronto: a esteira está de pé, esperando a primeira issue.

> **Board existente.** A esteira não mexe nas visões que você já usa: cria uma visão nova, "Esteira",
> em quadro e filtrada pelo repositório. Se o seu board não tem as colunas da esteira, ela também cria
> um campo próprio chamado "Esteira", sem apagar nada do seu "Status". A API do GitHub não escolhe o
> campo das colunas, então, nesse caso, abra a visão "Esteira" e troque na interface (menu da visão →
> Column by: Esteira).

**Atualizar.** No Claude, dentro do projeto:

```
/esteira-atualizar
```

O commit da esteira instalado fica em `.claude/esteira-versao.json`. A skill compara esse commit com
a `main` do repositório e, se houver novidade, faz o merge de 3 vias de cada arquivo (a versão
instalada, a do projeto e a nova): o que você não mexeu recebe a versão nova, o que só você mexeu
fica como está, e o que os dois mudaram é mesclado. Quando as mudanças batem no mesmo trecho, o
Claude junta as duas intenções e, se elas forem incompatíveis, pergunta. As suas melhorias nas
skills e nos scripts não se perdem; o `config.json` e os `hooks/` nunca são tocados. Os loops que
já estão rodando pegam o código novo quando são reiniciados: feche a aba 1 dos spaces e rode
`/esteira-up`.

Instalou antes de existir o `/esteira-atualizar`? Rode o comando do passo 1 de novo: com a esteira
já instalada, ele não sobrescreve nada e só copia a skill de atualização (abra o Claude de novo para
ela aparecer). Sem o arquivo de versão, a skill estima de qual commit veio a sua instalação. Para
trocar tudo pelas skills novas, descartando os ajustes locais, rode `install.sh --sobrescrever`.

## O dia a dia

**Criar trabalho.** No Claude, dentro do projeto:

```
/esteira-criar-issue quero que a tela de login aceite entrar com o e-mail ou com o nome de usuário
```

A skill organiza o pedido numa issue (contexto, problema, proposta, critérios de aceite), aplica as
labels e põe na `Planning queue`. Uma issue criada à mão entra quando você a arrasta para a
`Planning queue`.

**Acompanhar.**

| Comando | O que faz |
|---|---|
| `/esteira-status` | filas, o que cada vaga está fazendo, travas, RAM, loops de pé |
| `/esteira-fila dev` | uma passada na hora numa fila, sem esperar os 15 minutos |
| `/esteira-acordar dev` | avisa o loop da fila que tem coisa nova (issue arrastada à mão no board) |
| `/esteira-scale qa 3` | quantos trabalhos simultâneos a fila roda (abre ou fecha vagas) |
| `/esteira-up` | sobe tudo de novo (depois de um reinício, por exemplo); não duplica nada |
| `/esteira-limpar-abas` | fecha abas ociosas que ficaram para trás nos spaces |
| `/esteira-atualizar` | traz as novidades da esteira sem perder os seus ajustes nas skills |

**Homologar.** A issue chega em `Ready for release` com o plano, o PR, a revisão e o relatório do QA
na própria issue, e o vídeo da rodada aprovada. Confira, teste à mão se quiser, e lance.

**Decidir.** Em `Needs maintainer` ficam as issues em que a esteira precisa de você: uma escolha de
produto, um acesso que só você tem, três tentativas que não deram certo, ou uma issue que o QA
reprovou mais de `max_qa_failures` vezes (a esteira não deixa dev e QA ficarem num vaivém sem fim). O comentário
`<!-- pipeline:human -->` explica o que falta e recomenda uma saída. Responda na issue e devolva-a
para a fila da etapa.

**Depois de reiniciar o computador:** abra o Herdr, entre no projeto, `claude`, `/esteira-up`.

## O QA e o vídeo narrado

A skill `esteira-qa` é o QA BOT adaptado à esteira. Para cada issue:

1. deriva os casos de teste do plano técnico e dos critérios de aceite, com o esperado escrito
   antes de executar;
2. sobe o projeto a partir do PR, em portas livres e num **display próprio** (Xephyr + Chrome limpo,
   Xvfb, emulador sem janela): nada abre na sua tela;
3. executa interface e API, guardando localmente uma prova por passo;
4. grava **sempre** um vídeo narrado da jornada, com voz sintetizada offline: o que vai ser
   verificado, de onde vem a regra, a ação, o que o sistema respondeu e o veredito;
5. publica na issue **só o relatório escrito**: a tabela de casos, os totais e os bugs documentados
   (passos, esperado, observado, impacto). Nenhum print é anexado;
6. **aprovado**: anexa o link do vídeo ao relatório, faz o merge (se você escolheu assim) e move para
   `Ready for release`. **Reprovado**: não anexa vídeo e devolve para a `Dev queue` com os bugs.

**Teste de API também tem vídeo.** Para cenários sem tela (REST, fila, worker), o vídeo é gravado
sobre o **palco de API**: uma página local de duas colunas, com a requisição à esquerda (método, URL,
headers, body) e a resposta à direita (status, tempo, body), mais os selos "esperado × obtido" e,
para processos assíncronos, o trecho real do log. As chamadas são executadas de verdade no instante
em que o cursor clica em Enviar, e segredos aparecem mascarados. Quem assiste entende o que foi
testado sem ler JSON. Um exemplo completo está em `skills/esteira-qa/assets/exemplo-api/`,
e `preparar-video.sh teste` roda esse exemplo sem câmera.

O vídeo não substitui o teste: é a prova que deixa você conferir, em poucos minutos, que foi
implementado o que você pediu, do jeito que pediu.

## Projeto público: triagem e monitor de PRs

Em projeto público, qualquer pessoa pode abrir issue e PR, e esse texto chega aos agentes. Por isso
dois monitores extras (a cada 60 minutos):

- **Triagem** (`esteira-triagem`): cada issue nova passa por sinais determinísticos (texto dirigido
  a IA, caracteres invisíveis, comandos, links estranhos) e por um subagente isolado que só devolve
  um veredito. Legítima vai para a `Planning queue`; o que precisa de você vai para `Needs
  maintainer`; o que parece malicioso vai, em silêncio, para `Future ideas` (a quarentena), sem
  comentário nenhum.
- **Monitor de PRs** (`esteira-monitor-prs`): PR externo é analisado só de forma estática (nunca é
  executado). Aprovado, entra na esteira pela revisão de código; recusado por segurança ou por fugir
  da direção do produto, é fechado com um comentário cordial que nunca atribui má intenção. A direção
  do produto é lida do próprio projeto (`docs/PRODUCT.md`, `README.md`, `CONTRIBUTING.md`).

Em projeto privado esses dois não sobem: as issues vêm de você e do seu time.

## Configuração

Tudo fica em `.claude/esteira/config.json` no projeto. Os loops releem o arquivo a cada passada; um
config inválido é recusado (a passada é pulada) em vez de usado pela metade.

| Chave | Padrão | O que é |
|---|---|---|
| `stages.<etapa>.max` | `1` | vagas por etapa (agentes em paralelo) |
| `max_workers` | `4` | teto de agentes trabalhando ao mesmo tempo, somando as etapas |
| `max_qa_failures` | `3` | reprovações do QA que voltam para o dev; a seguinte vai para `Needs maintainer` |
| `min_free_ram_gb` | `4` | abaixo disso, as etapas pesadas (dev, review, qa) não recebem trabalho |
| `loops.dispatch_seconds` | `900` | intervalo das filas (15 min) |
| `loops.supervise_seconds` | `120` | intervalo do supervisor |
| `loops.triage_seconds`, `loops.prs_seconds` | `3600` | triagem e monitor de PRs (projeto público) |
| `merge_on_qa` | escolhido no bootstrap | o QA aprovado faz o merge |
| `language` | escolhido no bootstrap | idioma dos textos no GitHub |
| `base_branch` | a padrão do repo | para onde vão os PRs |
| `maintainers` | a sua conta | autores confiáveis (issues e comentários) |
| `claude_command` | `claude --dangerously-skip-permissions` | como as vagas abrem o Claude |
| `git_ssh_command` | vazio | chave SSH fixa para push/pull, se a máquina tiver várias |
| `trusted_domains` | `[]` | domínios normais em issues do projeto (para os sinais da triagem) |
| `product_space`, `stages.<etapa>.space`, `monitor_spaces`, `manual_spaces` | `product`, `plan`, `dev`... | nomes dos spaces no Herdr |

Um loop já rodando só pega um intervalo novo quando é reiniciado (feche a aba 1 do space e rode
`/esteira-up`).

**Dois projetos na mesma máquina.** Os loops são separados por caminho, mas os nomes dos spaces
precisam ser diferentes: troque `stages.<etapa>.space` e afins para algo como `loja-plan`,
`loja-dev`...

## Recursos da máquina

A esteira roda na sua máquina, então ela tem cuidado com o que sobe:

- **Uma vaga por etapa** por padrão. Mais vagas = mais RAM; aumente aos poucos.
- **Orçamento de memória**: abaixo de `min_free_ram_gb` livres, nada pesado é despachado.
- **Tudo é derrubado no fim**: cada trabalho termina com `cleanup.sh`, que mata os processos que
  ficaram rodando nas worktrees da issue e para os containers com a label `esteira.issue=<N>`.
- **Gancho do projeto**: se o seu projeto sobe algo que só ele sabe derrubar (emulador, VM, display
  de teste), escreva `.claude/esteira/hooks/cleanup.sh <etapa> <issue>` (executável). O
  `cleanup.sh` chama esse gancho.
- **Travas**: recurso que só cabe um por vez é usado sob `.claude/esteira/bin/lock.sh <nome>
  <comando>`; o `/esteira-status` mostra quem está com cada trava.
- **Nada na sua tela**: app, navegador de teste e suíte que abre janelas rodam num display próprio.

## Segurança

- **As vagas rodam com `--dangerously-skip-permissions`**, porque trabalham sem ninguém olhando.
  Use a esteira só em projetos e máquinas em que isso é aceitável, e leia `REGRAS.md` para saber o
  que os agentes podem e não podem fazer. Troque `claude_command` se quiser outro modo.
- **Conteúdo de issue e PR é dado, não instrução.** As regras proíbem os agentes de seguir ordens
  que venham de issue, PR, comentário ou página web, de rodar comandos copiados de lá e de tocar em
  credenciais. A triagem guarda o hash de cada issue triada: se o texto mudar depois, a issue volta
  para a triagem.
- **Só comentários de mantenedores** (e os marcados pela própria esteira) valem como direção.
- **Nada de atribuição a IA** em commits, PRs e comentários, a menos que o projeto peça.
- **Publicar release nunca é automático.** O space `release` é seu.

## Problemas comuns

| Sintoma | O que fazer |
|---|---|
| `/esteira-status` mostra um loop com ✗ | `/esteira-up` dentro do Herdr |
| Fila andando, vaga livre e nada despachado | veja o motivo no fim de `<state_dir>/dispatch.log` (RAM baixa, teto de agentes, vaga com tarefa em segundo plano) |
| Uma vaga parada há muito tempo | o supervisor recicla sozinho; `grep supervisor <state_dir>/dispatch.log` mostra o que ele já tentou |
| `gh: ... project scope` | `gh auth refresh -s project` |
| Comentários na conta errada | a conta ativa do `gh` é a que a esteira usa; troque e rode `/esteira-up` |
| Abas sobrando nos spaces | `/esteira-limpar-abas` |

O estado de cada projeto fica em `~/.local/state/esteira/<dono>-<repo>/` (log, claims, travas,
patches de `salvage/`, rodadas do QA).

## O que tem neste repositório

```
install.sh                                  copia skills/esteira-* para o .claude/skills do projeto
                                            e grava o commit em .claude/esteira-versao.json
skills/                                     → .claude/skills/ do projeto
  esteira-bootstrap/                        instalação: perguntas, board, labels, Herdr
    scripts/esteira.py                      check / projects / install / configure
    pipeline/                               → .claude/esteira/ (o bootstrap copia)
      REGRAS.md                             regras comuns que todo agente lê
      config.template.json                  base do config.json
      bin/
        dispatch.py                         loop de uma fila: vagas, despacho, reconciliação
        supervise.py                        loop do supervisor
        worker.py                           begin/end/human dos trabalhadores
        board.py                            operações no board e nas issues (via gh)
        signals.py                          sinais determinísticos de risco (triagem e PRs)
        worktree.sh, cleanup.sh, lock.sh    worktree idempotente, limpeza, travas
        evidence.sh                         publica evidências no repositório de evidências
        start-all.sh, run-loop.sh, status.py  subir tudo, loop de sessão nova, painel
  esteira-criar-issue                       a porta de entrada: pedido → issue na Planning queue
  esteira-planejamento, esteira-dev, esteira-revisao, esteira-qa       as etapas
  esteira-fila, esteira-acordar, esteira-scale, esteira-up, esteira-status,
  esteira-limpar-abas                       operação
  esteira-atualizar                         atualização com merge de 3 vias (scripts/atualizar.py)
  esteira-triagem, esteira-monitor-prs      monitores de projeto público
```

## Licença

[MIT](LICENSE): use, copie, modifique e distribua à vontade, inclusive em projetos fechados,
mantendo o aviso de copyright.
