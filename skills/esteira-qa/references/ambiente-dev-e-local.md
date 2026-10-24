# Onde executar: dev primeiro, local quando for preciso

A ordem é: **dev** (ou o ambiente compartilhado de teste do projeto) quando ele
prova a mudança; **local com dublês** quando não prova ou não é alcançável;
análise com bloqueio declarado quando nem isso é viável. Registre na rodada por
que cada ambiente foi escolhido. Cada CT declara o seu em `context`.

## Quando dev é possível

Dev serve ao veredito somente se tudo abaixo for verdade:

1. **A mudança está lá agora.** Dev é compartilhado e muda sem aviso. Prova
   aceitável: a versão em execução (endpoint de versão/health, cabeçalho,
   rodapé, hash do bundle servido) é o commit de merge ou um descendente dele;
   ou a implantação desse commit é a **mais recente** do componente em dev; ou
   existe ambiente efêmero do próprio PR. Pipeline concluída que não é a última
   implantação prova que o commit passou por dev, não que continua lá. Se o PR
   altera mais de um implantável (front e API), prove cada um; no front,
   recarregue sem cache nem service worker. Sem versão observável, registre a
   prova usada, o horário e esse limite no veredito. Um PR ainda ativo
   normalmente **não** está em dev: testar dev nesse caso prova a versão
   anterior, útil como linha de base ou contraprova, não como veredito.
2. **Há alcance.** Host resolve, rede/VPN disponível, persona e acesso obtidos
   pelo caminho protegido do projeto.
3. **A autorização cobre os efeitos.** Massa descartável, e o que dev aciona de
   verdade: sandbox de pagamento, SMS, e-mail, push, integrações de terceiros.
   O padrão do que a chamada cobre está em
   [intake-e-autonomia.md](intake-e-autonomia.md).
4. **O resultado é observável.** Log, consulta ou API que confirme efeitos
   assíncronos, não só a resposta imediata.

Sem o item 1, dev só dá linha de base e contraprova, e o veredito da mudança vem
de local. Os itens 2 a 4 decidem **por CT**, não pela rodada: vai para local o
CT sem alcance, o CT cujo efeito não está coberto e o CT cujo resultado não é
observável em dev; desafio de login não resolvido conta como falta de alcance
para os CTs daquela sessão. Os demais ficam em dev. Faltando só autorização,
peça a decisão concreta uma vez, nomeando efeito e destino, e siga com o que já
está coberto. Registre no CT qual item faltou. Não implante, não dispare
pipeline e não faça merge para "tornar dev possível".

Falha vista em dev: antes do bug, reconfirme a versão em execução e registre-a
na evidência. Versão diferente da avaliada é problema de ambiente, não defeito
do PR. Reconfira também ao retomar e ao encerrar a execução em dev.

## Subir local sem atrapalhar o que já roda

1. **Como o projeto sobe.** Leia os scripts e documentos da pasta; liste as
   dependências: banco, fila, cache, storage, identidade, serviços irmãos.
2. **Linha de base antes de tudo.** Inventarie listeners (`ss -ltnpH`; sem root
   a coluna de processo vem vazia para sockets de outros usuários, e `lsof` nem
   os lista, logo não prova porta livre), contêineres e projetos compose
   (`docker ps -a`, `docker compose ls -a`: parado ainda segura nome e volume)
   e processos do próprio projeto que o usuário deixou rodando. O que existia
   antes é intocável: não pare, reinicie, recrie nem reconfigure. Não aproveite
   uma instância do usuário como alvo, salvo leitura e com prova de que ela
   executa o commit do PR; o padrão é instância própria. Guarde a linha de base
   na rodada (`local/baseline.json`) só com dado neutro, portas em escuta e IDs
   de contêiner: esses comandos mostram nomes, imagens, caminhos e linhas de
   comando de **outros projetos e clientes** da mesma máquina, e nada disso
   entra em `run.json`, handoff, evidência ou relatório.
3. **Portas.** Escolha portas livres fora das padrões do projeto.
   `scripts/qa_local.py ports` testa o bind real; cruze com as portas publicadas
   pelo Docker, que podem não aparecer como listener, usando `--avoid`. Lembre
   das secundárias: debug, métricas, recarga a quente, gRPC, banco do compose.
   Sobrescreva por variável ou argumento (`ASPNETCORE_URLS`/`--urls`, `PORT`,
   `SERVER_PORT`, `--port`), sem editar arquivo versionado, e confira no
   `--help` da stack. Perfis de execução podem vencer a variável: em ASP.NET
   Core use `dotnet run --no-launch-profile` e declare `ASPNETCORE_ENVIRONMENT`
   de propósito (o valor decide quais arquivos e segredos locais são lidos;
   ver passo 5); endpoint declarado em configuração (`Kestrel:Endpoints`) também
   vence, e se sobrescreve pela própria chave
   (`Kestrel__Endpoints__<Nome>__Url=http://127.0.0.1:<livre>`). Servidor de
   desenvolvimento que pula para a porta seguinte em silêncio pede o modo
   estrito (`--strictPort`) ou leitura da porta real na saída. Porta fixa em
   código é limitação a relatar; falha de bind na porta padrão nunca é motivo
   para parar a instância do usuário. Porta livre agora não é reserva: suba em
   seguida e confirme que quem escuta é o seu processo.
4. **Nomes próprios.** `docker compose -p qa-<run>` com arquivo de override
   guardado na rodada. Rede, volumes e banco próprios: contêiner efêmero da
   rodada é o padrão. Database `qa_<run>` dentro de um servidor que **já rodava**
   só quando o contêiner próprio é inviável e a credencial local documentada
   no projeto permite criar e apagar database: registre como efeito e apague só
   ele; nunca aponte a aplicação da rodada para um database existente, que a
   migração de inicialização alteraria. Filas e tópicos com prefixo valem no
   broker **da rodada**: prefixo em broker compartilhado é escrita em dev, e
   consumir do broker local do usuário tira mensagens da instância dele. Dados
   temporários sob `<rodada>/work/`, não no temporário do sistema. No merge de
   arquivos compose, `ports` **acrescenta**: para trocar a porta publicada use
   `ports: !override ["127.0.0.1:<livre>:<interna>"]` (ou `!reset []`) e valide
   antes de subir com `docker compose … config --quiet`; para ver portas e
   nomes use `config --no-interpolate`, porque `config` puro imprime os valores
   do `.env` já interpolados. `container_name`, `name:` fixo em rede/volume,
   `external: true` e `image:` fixo junto de `build:` (o build da rodada
   retagueia a imagem do usuário) furam o isolamento do `-p`: sobrescreva-os no
   override ou declare a limitação.
5. **Configuração e destinos efetivos.** Variáveis de ambiente ou override fora
   do versionamento; se editar arquivo for inevitável, edite na worktree da
   rodada, nunca na árvore do usuário. Antes da **primeira subida** (a
   inicialização já escreve: migração automática, declaração de filas, seed),
   liste os destinos de saída da configuração efetiva: connection strings,
   fila/cache/storage, URLs base, cofre e configuração remota, em arquivos por
   ambiente, perfil de execução, compose e segredos de usuário (só nomes de
   chave). Cada destino tem de ser recurso da rodada, dublê ou leitura coberta;
   destino não identificado: não suba. Dois padrões enganam: `localhost` na
   porta padrão é o banco ou a fila **do usuário**, e o modo de desenvolvimento
   da stack carrega sozinho arquivos e segredos locais que costumam apontar
   para dev. Destino compartilhado é escrita em dev: aplique as regras de dev
   ou redirecione para recurso da rodada.
6. **Build e migrações** na worktree, contra o banco da rodada. Restaurar o que
   o projeto declara e baixar as imagens do compose dele fazem parte de
   compilar e subir; prefira o cache e, se o hospedeiro pedir confirmação, peça
   uma vez, com a lista. Não instale SDK nem ferramenta global sem pedido.
   Compile sem residentes (`dotnet build --disable-build-servers`,
   `gradle --no-daemon`). Restore em feed privado e aplicação que busca
   credencial da CLI ao subir herdam a identidade do shell que os lançou: lance
   pelo mesmo meio em que a conta foi conferida, prefira valores sintéticos e
   fontes remotas desligadas por configuração. Falha de autenticação no restore
   não se resolve com login nem com token de outro contexto: avise.
7. **A porta participa de contratos.** Trocar a porta quebra o que a tinha
   fixa: origem de CORS, redirect URI registrada no provedor de identidade, URL
   base embutida no build do front-end, callback de webhook, deep link. Levante
   esses pontos antes de escolher e ajuste só por configuração local (origem
   extra, URL base por variável, proxy de desenvolvimento). Redirect URI que só
   aceita a porta padrão é limitação: use a padrão se estiver livre ou declare
   o login como não coberto em local. Erro de CORS ou redirect causado pela sua
   porta é montagem, não defeito do PR. Front-end: confirme na rede do
   navegador que as chamadas vão para a API da rodada, não para dev. App: o
   bundler tem porta própria e o emulador alcança o host por endereço próprio;
   emulador, dispositivo e app que o usuário já tinha abertos são linha de
   base: instância própria, sem reinstalar nem limpar dados neles.
8. **Confirme o que subiu.** Health/versão, commit, log de inicialização, e o PID
   dono da porta (`ss -ltnpH 'sport = :<porta>'` deve mostrar o PID anotado).
   Responder 200 na porta esperada não prova que é o seu build. Prove também
   para onde o alvo foi: migração no banco da rodada, conexão no broker da
   rodada, requisição no log do dublê.
9. **`effects` se escreve antes.** Sessão que cai não avisa. Antes de criar
   worktree, subir processo, compose ou dublê, registre o efeito com
   `state: uncertain` e o `cleanup` previsto. Confirmado o passo 8, complete a
   `action` (PID do lançador e do dono da porta com horário de início, comando,
   porta, projeto compose, caminho) e passe a `active`. O mesmo vale para
   gravação não idempotente em ambiente compartilhado.

Nunca: `kill` por nome ou por porta; `docker compose down` no projeto do
usuário; `docker system prune`; remover volume ou imagem que não criou;
desligamento global de servidores de build (`dotnet build-server shutdown`,
`gradle --stop`), que derruba os do usuário.

Integrações externas entram por dublê: leia
[dubles-de-integracoes.md](dubles-de-integracoes.md) antes de subir o alvo.

## O que a prova local sustenta

Sustenta: a implementação do PR, no commit avaliado, cumpre a regra com as
dependências simuladas conforme o contrato citado. **Não** sustenta: integração
real, configuração e infraestrutura de dev, dados reais, desempenho, deploy.

Declare isso em `context.environment` (por exemplo
`local — commit abc1234 — dublês: gateway, SMS`), na conclusão do CT e no
executivo, e liste o que reconferir em dev após o merge. CT cujo objetivo é a
integração real fica `BLOQUEADO` em local, não `PASSOU`. Prova vinda de dublê
é rotulada como tal; request/response do alvo e capturas de tela seguem as
regras normais de evidência.

Falha vista só em local: antes do bug, separe defeito do PR de montagem
incompleta (seed, configuração, dublê errado). Repetir o passo na branch de
destino, na mesma montagem, distingue regressão do PR de problema anterior.

## Encerrar

Pare apenas o que iniciou. Lançadores (`npm run`, `dotnet run`, `mvn`, `make`)
criam filhos: sinalizar só o lançador pode deixar o filho escutando. Sinalize os
dois PIDs anotados, desde que a identidade (comando e horário de início,
`ps -o pid,lstart,args -p <pid>`) ainda confira, e confirme a porta livre. Porta
ainda ocupada por PID que você não anotou: não mate; registre `uncertain`.

Contêineres: o seu projeto compose **com os mesmos `-f` da subida**
(`docker compose -p qa-<run> -f <base> -f <override> down --rmi local`, que
remove também as imagens construídas pela rodada). Só acrescente `-v` depois de
conferir em `config` que todo volume declarado é da rodada.

Remova worktree e temporários, confirme as portas liberadas e compare com a
linha de base: os mesmos contêineres e listeners de antes continuam de pé.
Cada efeito termina `cleaned`, `kept` com a decisão registrada, ou `uncertain`
com o que falta conferir. Limpeza impossível é efeito registrado, não "ambiente
limpo". Interrupção não avisa: o que permite reconciliar é o registro prévio em
`effects` (ver [continuidade-e-operacao.md](continuidade-e-operacao.md)).
