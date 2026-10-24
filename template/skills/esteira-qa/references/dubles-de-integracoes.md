# Dublês de integrações externas

Dublê é para o que sai do perímetro testado e não é alcançável ou seguro em
local: APIs de terceiros, gateways, SMS/e-mail/push, antifraude, identidade,
storage e filas gerenciadas, serviços irmãos fora da montagem. Ele permite
validar a implementação; não prova o comportamento do terceiro real.

## De onde vem o contrato

- **O contrato vem de fonte:** especificação, SDK, documentação, exemplos e
  testes do próprio projeto. Registre essa fonte em `sources` (arquivo da pasta
  ou link, com versão) e cite o ID dela no `name` do spec e da rota (o spec
  recusa chave desconhecida, não há campo próprio) e no `caption` do log.
  Guarde o spec na rodada (`mocks/`). Resposta inventada para o teste passar
  não prova nada; contrato desconhecido é lacuna.
- **Redirecione por configuração que o projeto já oferece** (URL base, connection
  string, modo sandbox). Endereço fixo no código é limitação de testabilidade a
  relatar; alterar o produto para testar só com pedido, e o que foi testado
  deixa de ser o PR puro.
- Não desligue validação de certificado nem proteção do produto para o dublê
  funcionar; prefira URL base local em HTTP quando o projeto permite.
- **Credenciais sintéticas.** Configure chaves e tokens fictícios para as
  integrações simuladas: o log do dublê mascara cabeçalhos sensíveis, mas grava
  caminho, query e corpo como chegaram.

## Dublê HTTP da skill

`scripts/qa_local.py mock` serve respostas declaradas, em sequência por rota
(permite 500, 500, 200 para retry), responde 501 a rota não declarada e grava em
JSONL o que o alvo enviou. Esse log, revisado e saneado, é evidência técnica do
contrato de saída. Sintaxe do spec em
[contrato-de-artefatos.md](contrato-de-artefatos.md). Prefira o que o projeto
já tem: fakes do repositório, WireMock/MockServer, emuladores oficiais, broker
em contêiner com nome da rodada.

**Um dublê por CT/tentativa:** suba com `--log` novo em
`cases/<ct>/attempt-NN/`, execute, pare, registre. A posição na sequência de
`responses` só volta ao início quando o processo reinicia: dublê mantido entre
CTs entrega ao seguinte o resto da sequência do anterior e mistura as
requisições dos dois na mesma prova. Reiniciar na mesma porta não exige
reconfigurar o alvo.

Antes do veredito, leia o log. Linha com 501, `route: null`, `error` ou
`response_error` dentro do CT precisa de explicação registrada; sem ela o passo
não é `PASSOU`. Passo que deveria chamar o terceiro com o log vazio: o alvo
falou com outro destino; pare e localize.

**Alvo em contêiner** não alcança o `127.0.0.1` do host. No Docker Engine em
Linux `host.docker.internal` só existe se o override declarar
`extra_hosts: ["host.docker.internal:host-gateway"]`; suba o dublê com `--bind`
no IP da bridge para onde `host-gateway` aponta, não em todas as interfaces.
Não contorne com `network_mode: host`.

## O que só o dublê permite

Timeout, 5xx, payload inválido, duplicata, lentidão, callback fora de ordem:
são os riscos de integração, e raramente dá para provocá-los em dev. Cubra os
que a regra ou o diff tornam relevantes.

**Entrada de terceiros** (webhook, callback): faça o papel do terceiro chamando
o endpoint local com payload do contrato e segredo de teste local.

**Fila, storage e cache gerenciados:** emulador oficial ou broker em contêiner
da rodada. Sem emulador viável, o CT que depende do serviço real fica
`BLOQUEADO` em local e segue para dev; não troque o serviço por um stub escrito
dentro do produto.
