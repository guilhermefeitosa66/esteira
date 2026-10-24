# Execução com ferramentas reais

Selecione apenas as seções da plataforma em escopo. Descubra as ferramentas
efetivas da sessão; os nomes variam entre Codex, Claude e servidores MCP.
Registre nome/versão quando disponível, ambiente, build e alcance da prova.
O ambiente (dev ou local com dublês) é decidido antes, por
[ambiente-dev-e-local.md](ambiente-dev-e-local.md); as regras abaixo valem nos dois.

## Web e web mobile

Verifique URL final, persona e empresa selecionada antes do fluxo. Prefira
locators semânticos ou identificadores estáveis observados. Em iframe/shadow DOM,
inspecione o contexto correto; snapshot desatualizado pede nova observação.
Espere pelo estado relevante com prazo, não por um `networkidle` universal
nem por sleeps longos copiados de outra aplicação.

Preencha via interface, observe validação, blur, overlay e resultado do submit.
Se precisar acionar DOM como alternativa, registre a limitação; isso não prova
que o elemento é clicável por uma pessoa nem autoriza alterar estado interno.
Depois da alternativa, confirme a jornada normal quando esse é o critério.

Trate alert/confirm, impressão, seletor de arquivo, clipboard e compartilhar
com a ferramenta apropriada. Captura de página pode não incluir diálogo do SO.
Não proíba a funcionalidade por ela abrir diálogo nativo; investigue suporte de
desktop ou registre o trecho sem prova. Feche somente o diálogo da execução.

Web mobile: registrar browser, viewport, orientação, emulação ou dispositivo real,
touch/teclado, rolagem, foco e ausência de conteúdo inacessível. Não declare
cobertura Safari/iOS a partir de Chromium com viewport estreito.

## Aplicativo Android/iOS

Confirmar dispositivo/emulador, SO, package/bundle, versão/build instalada,
backend efetivo e persona. Conferir que o instalável corresponde à rodada.
Use automação mobile disponível ou interação observável com captura real.
Identifique elementos por árvore de acessibilidade; coordenadas dependem de
captura recente e geometria estável. Após teclado/rotação/modal, reobserve.

Quando pertinentes: permissão concedida/negada, background/foreground, offline,
fila local, retorno de rede, sincronização, duplicação e persistência após reabrir.
Correlacione o mesmo registro na web/API quando a jornada cruza plataformas.
Não use reinstalação/limpeza de dados para mascarar defeito; ela pode remover
massa e estado e deve estar coberta pelo teste. Preserve logs úteis do dispositivo.

## Aplicação desktop

Confirmar sistema, versão/build instalada, backend efetivo, persona e como o
instalável chegou ali. Preferir a automação de acessibilidade da plataforma;
coordenadas dependem de captura recente e de janela estável. Reobserve depois de
diálogo, menu, redimensionamento e troca de monitor.

Diálogo nativo (arquivo, impressão, permissão) costuma ficar fora da captura da
janela: capture a tela do ambiente controlado pela rodada. Trate instalação,
atualização, primeira execução, perfil novo, offline e reabertura quando
pertinentes, sem usar reinstalação para mascarar defeito. Preserve log e crash
dump do aplicativo. Rodar em ambiente próprio (VM, container com display) é o
que torna a execução repetível e a gravação possível.

## API, integrações e banco

Derive esperado do contrato/especificação. Observe método, endpoint sanitizado,
entrada, status, conteúdo, cabeçalhos relevantes, duração e correlação. Compare
campos, tipos, autorização, escopo, erros, paginação e efeitos pertinentes.
Aceite assíncrono não comprova processamento: siga correlação até estado final
ou prazo funcional. Uma chamada única não comprova desempenho sob carga.
Com integração substituída por dublê, a prova é dupla: a resposta do alvo e o
que o dublê recebeu dele; isso comprova o contrato de saída, não o terceiro real.

Persistência pode ser conferida por consulta autorizada da própria aplicação,
API ou banco conforme escopo. Leitura do banco não autoriza escrita direta.
Use consultas específicas, parâmetros e limites; registre antes/depois quando
necessário. Banco não selecionado não bloqueia um teste exclusivamente de UI.
Não executar coleções, seed ou SQL desconhecidos antes de revisar seus efeitos.

## Provas que costumam faltar

- Download: capture a ação, preserve arquivo recebido e verifique conteúdo
  real, cabeçalhos, filtros, colunas, formatos e totais. Renderização de XLSX
  para evidência deve ser rotulada e ligada ao arquivo de origem.
- Relatório: reconciliar o valor visível com dados no mesmo escopo de persona,
  filtros, fuso e período. Não usar o total do admin como referência de outro papel.
- Notificação: baseline e evento novo com timestamp/correlação/destinatário.
  Um toast de envio é insuficiente: confira o evento novo no destino autorizado.
  Ausência na caixa de controle não prova ausência em todas as caixas possíveis.
- Permissão: botão oculto não prova bloqueio de rota/operação. Admin funcionar
  é contraprova útil, não comprovação da causa-raiz. Nunca ampliar permissão para
  conseguir marcar o CT como aprovado.

## Falhas e massa

Diferencie desvio de produto, massa/configuração, ambiente/build, documentação
conflitante e limitação da ferramenta com evidência. Falta de implementação
prometida é desvio; backlog sem promessa de entrega é contexto do escopo.
Reproduza quando seguro; frequência intermitente deve registrar N/M tentativas.

Planeje consultas antes de alterações que consumam massa compartilhada. Use
marcador de run, identifique IDs criados e restaure configurações temporárias.
Apague apenas registros confirmadamente criados por esta execução e com limpeza
autorizada; prefixo semelhante sozinho não prova propriedade. Não remova fixtures
compartilhadas. Limpeza impossível vira pendência concreta, não declaração de
ambiente limpo.
