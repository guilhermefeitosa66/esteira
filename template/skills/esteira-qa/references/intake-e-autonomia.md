# Entrada no projeto e autonomia

Abra o contexto que o usuário indicou. Quando a chamada traz uma pasta, ela é
o projeto: leia as instruções dela mesmo que a sessão esteja em outro
diretório, e siga [pull-request-e-contexto.md](pull-request-e-contexto.md) se
houver link de PR. Se houver mais de um cliente/projeto plausível, ou um link
que não pertence à pasta, esclareça a identidade antes de conectar ou escrever
no destino. A skill não guarda credenciais nem contexto de cliente algum.

Registre apenas os dados necessários para a rodada:

- Cliente, projeto, consultoria quando houver, assinatura e idioma dos artefatos.
- Objetivo, fonte funcional, história/bug, plataformas e critérios de conclusão.
- Mudança avaliada (PR, commit head) e ambiente efetivo: dev ou local, com
  URL/app/package/API, build, tenant/empresa, personas e dublês em uso.
- Ferramentas confirmadas, forma protegida de obter acesso e limitações observadas.
- Operações cobertas pela autorização, massa, limpeza e destino dos relatórios.

Use contexto já fornecido. Em um pedido de teste de tela, web está no escopo;
não exija escolher banco, carga e segurança. Carga, ataque de segurança e criação
de suíte reutilizável são trabalhos próprios, incluídos quando solicitados.
Um reteste isolado não exige refazer toda a campanha.
Verificações funcionais de permissão da história pertencem ao QA dessa história.

## Ações e autorização

Leitura local, planejamento, geração de documentos e organização reversível
avançam sem nova confirmação. A autorização para testar uma jornada em ambiente
de teste normalmente inclui suas ações funcionais e massa descartável dentro
dos limites definidos. Registre a origem dessa autorização, não um carimbo genérico.

Pedir o teste de um PR a partir de uma pasta cobre: ler a pasta e o PR, buscar
a ref do PR no clone existente (`git fetch`, sem alterar branch), criar worktree
isolada, restaurar as dependências que o projeto declara a partir dos feeds já
configurados, baixar as imagens que o compose do projeto declara, compilar,
subir a aplicação local em portas livres com nomes próprios, usar dublês locais
(em loopback, ou na interface da rede Docker da rodada quando o alvo roda em
contêiner) e encerrar o que foi iniciado. Se o hospedeiro exigir confirmação
para download, peça **uma vez**, no início, com a lista, e avance na análise
enquanto aguarda. Não cobre: parar ou reconfigurar o que já rodava, instalar
ferramenta global, publicar no PR/board, implantar, disparar pipeline, trocar
conta ou perfil de CLI, nem pacote, imagem ou ferramenta que o projeto não
declara. Detalhes em [ambiente-dev-e-local.md](ambiente-dev-e-local.md).

Em dev (ambiente compartilhado), a mesma chamada cobre as **ações funcionais do
fluxo em teste, pela interface ou API do produto, com a persona de teste do
projeto**. A massa criada é descartável, identificável pela rodada (prefixo ou
ID quando o campo permite) e registrada em `effects` com a reversão. Sem pedido
explícito, não cobre: escrita direta em banco ou fila; mudar configuração,
feature flag, permissão ou dado de outra pessoa; excluir o que a rodada não
criou; volume em lote; passo que acione terceiro real (cobrança, SMS, e-mail,
push, webhook para fora). Se as instruções da pasta não dizem que dev usa
sandbox naquela integração, trate como real: o CT vai para local com dublê ou
aguarda a decisão. Limites escritos na pasta ou na chamada prevalecem sobre
este padrão. Registre a origem como "chamada + instruções da pasta", com data.

Produção começa como leitura. Escrita em produção, pagamento, comunicação para
pessoas, exclusão relevante, mudança de acesso e publicação externa precisam
de autorização que realmente cubra o efeito. Um nome HML não prova o destino:
confira redirecionamentos e dependências quando houver indício de divergência.
Mudança de papel/tenant requer reconfirmar a identidade observável da sessão.

Não reapresente perguntas já respondidas. Ao faltar autorização para um efeito,
prepare roteiro/pacote e todas as verificações independentes; peça somente a
decisão concreta faltante. A regra local que causou a pergunta deve ser explicada.

## Ferramentas e alcance

Registre `capacidade | ferramenta real | teste de conexão | contexto | limite`.
Exemplos: navegação e captura web; desktop para diálogo nativo; dispositivo app;
HTTP autenticado; banco autorizado; leitura/publicação de board; renderização PDF;
leitura de PR pela CLI do provedor; runtime/SDK e Docker para a subida local.
Um conector listado mas inacessível é capacidade não confirmada. Não herde nomes
de MCP, contas, IDs, bindings ou políticas de outro projeto.

Sem executor de uma plataforma, avance no que é possível e descreva exatamente
o recurso faltante. Não simule app usando viewport móvel nem declare integração
operacional por existir um arquivo de configuração.
