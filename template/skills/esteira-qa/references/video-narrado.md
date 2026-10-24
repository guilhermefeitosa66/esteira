# Vídeo narrado do processo de teste

Quando a rodada exercita interface — página web, web mobile, app Android/iOS ou aplicação desktop —
grave **um vídeo com narração contando o processo de teste**: o que vai ser verificado, de onde vem
a regra, o que foi feito, o que o sistema respondeu e qual o veredito. É a jornada que os prints por
passo documentam, agora contínua e falada, para quem precisa entender a rodada sem ler o relatório
inteiro.

O vídeo é **prova complementar, nunca substituta**: passo conclusivo em plataforma de UI continua
exigindo a captura do passo (`validate` recusa sem ela). Rodada só de API, banco ou documento não
tem vídeo, e isso se declara.

Três etapas, nesta ordem: **roteiro → narração → gravação e montagem**. A narração é gerada antes da
gravação porque é ela que dita o ritmo: cada cena dura ao menos o tempo da sua fala.

Daí decorre o que o vídeo é, e é preciso ser exato nisso: como a fala precisa existir antes da
gravação, o vídeo é **uma segunda execução real**, feita depois de os CTs terem rodado, percorrendo a
mesma jornada com os resultados já conhecidos. Continua sendo o sistema sendo usado de verdade, no
mesmo build e ambiente — nunca uma encenação, nunca um resultado forjado, e nada de injetar tela ou
mensagem para a câmera. A prova primária de cada passo continua sendo a captura da execução original;
o vídeo mostra a mesma jornada de forma contínua e explicada. A legenda da prova diz isso: gravação
narrada da jornada, feita após a execução que a documentou.

Se a segunda passagem **não reproduzir** o que a primeira observou, isso não se resolve regravando até
dar certo: é achado. Registre a divergência (intermitência, dependência de estado, massa consumida) e
trate-a como qualquer outro resultado inesperado.

```bash
V=<rodada>/work/video            # insumos: roteiro, falas, marcos, gravação bruta
qv () { python3 <caminho-da-skill>/scripts/qa_video.py "$@"; }   # função, não variável: o zsh
```                                                              # não divide `$VAR` em palavras

Insumos ficam em `work/video/` dentro da rodada; o vídeo final é uma prova, e mora onde as provas da
rodada moram. Nada disso entra na pasta da skill.

## 1. Regra dura: o que pode ser gravado

**Grave apenas o display ou o aparelho que a rodada controla.** Um vídeo é artefato distribuído: vai
para a entrega, para o anexo, para o comentário. Qualquer pixel capturado por acidente vaza junto, de
forma irreversível e sem passar pela conferência item a item.

- **Nunca** capture o display da sessão do usuário. Ele contém janelas de outros projetos,
  notificações que surgem no meio da gravação, navegador pessoal, chat, terminal com credenciais e
  material de **outros clientes** — o isolamento entre clientes proíbe isso de forma absoluta.
- Ordem de preferência: display próprio do container/VM/emulador da rodada > display aninhado ou
  virtual criado para a gravação no host > nada.
- Sem display próprio disponível, **não grave**: diga ao usuário que a rodada não terá vídeo e por
  quê. Cair para a tela da sessão por conveniência não é uma opção.
- Gravar uma janela só não resolve: menu suspenso, modal e balão do navegador nascem como janela
  própria e ficam fora do quadro; janela ocluída rende quadros congelados.
- Prepare o ambiente para o vídeo: geometria escolhida para o texto ficar legível sem zoom, perfil
  de navegador novo e descartável, gerenciador de senhas desligado (senão o balão "salvar senha?"
  fica no canto do vídeo inteiro), e login e preparo de massa **fora** da gravação.
- A gravação é um efeito: registre em `effects` antes de iniciar, com a limpeza (encerrar o
  gravador, derrubar o display, apagar o arquivo do aparelho).

## 2. Roteiro (`work/video/roteiro.json`)

Escreva o roteiro **depois de executar os CTs**, a partir do que de fato aconteceu — não do que se
esperava que acontecesse.

```json
{
  "titulo": "Rodada de QA — cadastro de item",
  "pronuncia": {"CT-001": "C T zero zero um"},
  "cenas": [
    {"id": "abertura", "fala": "Rodada de QA do pedido de alteração. Ambiente local, build confirmada, persona de operador."},
    {"id": "ct-001-p01", "fala": "CT-001, passo um. Abrimos a tela de cadastro. O esperado é que o campo obrigatório apareça marcado."},
    {"id": "ct-001-p02", "fala": "Passo dois. Enviamos o formulário vazio. O esperado, pela regra R-03, é a recusa com mensagem no campo."},
    {"id": "fechamento", "fala": "Resultado: um caso aprovado, nenhum bloqueio. As provas por passo estão no relatório."}
  ]
}
```

- `id` começa com letra ou número e segue com letras, números, ponto, hífen ou sublinhado; nome
  reservado do Windows (`CON`, `COM1`…) é recusado, como em qualquer ID da rodada. Amarrar ao CT e ao
  passo (`ct-001-p02`) deixa a cena rastreável.
- **Abra dizendo o escopo e o contexto** (ambiente, build, persona, tenant) e **feche com o
  veredito e os números**, com denominador. Entre os dois, uma cena por passo verificável.
- Cada fala diz **o esperado, com a fonte da regra, antes** de mostrar o resultado. É isso que
  diferencia o vídeo de uma gravação de tela qualquer.
- Falha entra no vídeo: dizer o que se esperava, o que apareceu e que virou bug é o conteúdo mais
  útil que a gravação tem. Não maquie um CT que falhou nem omita um bloqueio.
- Frases curtas, uma ideia por ação, os rótulos da tela como eles aparecem. Nada de jargão interno
  nem de dado sensível: **o áudio não passa por saneamento** e a legenda repete a fala.
- `pronuncia` só muda o que a voz lê; a legenda mostra o texto original. Use apenas quando a
  transcrição acusar erro — grafia fonética inventada costuma piorar.
- Cena longa demais vira duas. Uma fala que não cabe na ação vira aviso na montagem.

## 3. Narração offline (`qa_video.py narrar`)

```bash
qv narrar --roteiro $V/roteiro.json --saida $V/narracao    # gera <cena>.wav + duracoes.json
```

- **A voz é sintetizada na própria máquina.** O texto da rodada não sai dela. Voz neural de serviço
  externo soa melhor, mas manda o roteiro — que descreve o sistema do cliente — para um terceiro:
  só com autorização explícita do usuário para aquela rodada.
- Padrão: motor `kokoro`, voz feminina `pf_dora+if_sara:0.5`. A sintaxe `VOZ+OUTRA:peso` **mistura o
  timbre** de duas vozes (peso da segunda depois do `:`, entre 0 e 1), que é como se chega a um
  timbre que nenhuma voz pronta tem; `--voz pf_dora` usa a voz pura. Peso fora da faixa não mistura:
  extrapola o vetor de voz e sintetiza ruído, por isso o comando recusa.
- O `kokoro` precisa do `uv` no PATH (roda num ambiente efêmero, sem instalar nada no projeto) e dos
  dois arquivos de modelo, `kokoro-v1.0.onnx` e `voices-v1.0.bin`, em `<dados-do-usuário>/kokoro`.
  `QA_BOT_VOZES` troca a **pasta de dados** (os modelos continuam em `<ela>/kokoro`) e `--modelos`
  aponta a pasta dos modelos diretamente. Faltando qualquer um, o comando diz o quê e onde.
- Alternativas: `--motor piper --modelo <voz.onnx>` (precisa de `uvx`), ou
  `--motor comando --comando "<sintetizador do hospedeiro> -f {wav}"`, que recebe o texto no stdin,
  grava onde `{wav}` indica e não baixa nada.
- `--ritmo` acima de 1.0 deixa a fala mais lenta.
- **Confira a fala antes de gravar a tela**: transcreva cada `.wav` de volta e compare com o texto.
  Palavra trocada se corrige em `pronuncia` e exige narrar de novo. Refazer a narração depois da
  gravação desalinha tudo, porque as durações mudam.
- O `narrar` grava, junto das falas, a assinatura do texto de cada cena. Mexer na fala ou na
  `pronuncia` sem narrar de novo é **recusado** na montagem: o id continuaria batendo, e o vídeo
  sairia com a legenda nova sobre o áudio velho.

## 4. Gravar a tela

Grave **sem áudio** (a narração entra na montagem) e **em uma tomada só**. Confirme as flags no
próprio host (`--help` do binário) antes de copiar qualquer comando daqui.

A coluna **origem** separa o que já foi executado numa máquina deste projeto do que vem da
documentação da ferramenta e nunca foi rodado aqui. Para o que é documentação, confirme a flag no
host antes de usar, e registre o que observou.

| Plataforma | Captura | Origem | A observar |
|---|---|---|---|
| Linux X11 | `ffmpeg -f x11grab -framerate 30 -video_size <LxA> -i <:display>` | medido | a geometria tem de bater com a do display; `-draw_mouse 1` é o padrão e é o que se quer |
| Linux Wayland | não há `x11grab`; o caminho é portal + PipeWire | documentação | o portal **abre diálogo de consentimento** e oferece a área de trabalho real: prefira um display próprio |
| macOS | `ffmpeg -f avfoundation -capture_cursor 1 -framerate 30 -i "<índice>:none"` | documentação | descubra o índice com `-list_devices true`; o cursor **não** é gravado por padrão; exige permissão de gravação de tela concedida ao terminal |
| Windows | `ffmpeg -f gdigrab -framerate 30 -i desktop` | documentação | recorte com `-offset_x/-offset_y/-video_size`; captura por título do app quebra quando o título muda e sai preta em janela acelerada por GPU |
| Android | `adb shell screenrecord --size <LxA> <arquivo>`, depois `adb pull` | documentação | **teto de 180 s**, sem áudio, não suporta girar a tela durante a gravação; o arquivo nasce com o relógio do **aparelho** |
| iOS | simulador: `xcrun simctl io booted recordVideo <arquivo>` | documentação | aparelho físico não tem caminho de gravação confiável: declare a rodada sem vídeo |

- **Pare sempre por SIGINT** (`kill -INT`), nunca `kill -9`: o índice do MP4 só é escrito no
  fechamento, e uma parada forçada perde a gravação inteira. Espere o processo sair antes de mover o
  arquivo, e confirme com `ffprobe` que ele abre.
- Um comando por vez no preparo e na gravação, sem encadear o resto com `&&`: um passo que falha no
  meio deixa a gravação rodando sem marcos, e ela vira lixo.
- No Android, cena longa obriga a quebrar em gravações de até 180 s; o limite dispara **sozinho**,
  sem o host mandar sinal.

### Marcos e ritmo

```bash
qv marco --log $V/marcos.jsonl --tipo inicio          # logo depois de a captura começar
# por cena, em volta das ações:
qv marco --log $V/marcos.jsonl --tipo cena --cena ct-001-p01 --narracao $V/narracao
#   ... o driver real (browser, adb, automação desktop) executa o passo ...
qv aguardar --log $V/marcos.jsonl --narracao $V/narracao --cena ct-001-p01
qv marco --log $V/marcos.jsonl --tipo parar           # no instante em que o sinal é enviado
```

`marco --tipo cena` abre a cena e `aguardar` completa o tempo da fala, de modo que a ação aconteça
**enquanto** a voz explica e a cena seguinte só comece quando a fala terminar. Funciona com qualquer
driver, porque são duas chamadas de shell em volta das ações que a rodada já faria. `excedeu_s` no
retorno diz que a ação durou mais que a fala — aceitável; o contrário é que deixaria silêncio.

Em Linux, uma rodada inteira em um display que ela mesma cria tem esta forma (um comando por linha,
nunca encadeados: um passo que falha no meio deixa a gravação rodando sem marcos):

```bash
Xephyr :<n> -screen 1280x720 -nolisten tcp -ac &          # display só da rodada; teardown no fim
xdpyinfo -display :<n> | grep dimensions                  # confirmar a geometria antes de gravar
# subir o alvo e preparar persona/massa NESTE display, fora da gravação
ffmpeg -y -loglevel error -f x11grab -framerate 30 -video_size 1280x720 -i :<n> \
  -c:v libx264 -preset ultrafast -pix_fmt yuv420p $V/bruto.mp4 & echo $! > $V/rec.pid
qv marco --log $V/marcos.jsonl --tipo inicio
# ... laço de cenas: marco --tipo cena, ações do driver, aguardar ...
qv marco --log $V/marcos.jsonl --tipo parar
kill -INT $(cat $V/rec.pid); wait                         # SIGINT, e esperar o processo sair
ffprobe -v error -show_entries format=duration -of csv=p=0 $V/bruto.mp4   # o arquivo abre?
```

Mova o ponteiro de verdade até o elemento antes de clicar, quando a ferramenta permitir: quem assiste
precisa ver para onde a ação foi. Um movimento que acelera e desacelera (em vez de saltar) é o que
torna o vídeo legível.

**Um log de marcos por tentativa de gravação.** O `montar` recusa um log com mais de um `inicio` ou
`parar`, justamente porque alinhar as falas pela gravação errada produz um vídeo plausível e falso.

## 5. Montar (`qa_video.py montar`)

```bash
qv montar --roteiro $V/roteiro.json --narracao $V/narracao --bruto $V/bruto.mp4 \
    --log $V/marcos.jsonl --saida <rodada>/cases/ct-001/attempt-01/jornada-narrada.mp4
```

Cada fala entra no instante do marco da sua cena; o vídeo começa `--margem` antes da primeira cena e
termina `--cauda` depois da última fala. Saída: vídeo H.264, áudio AAC estéreo 48 kHz e legenda
`mov_text` embutida, que o player liga e desliga (não fica queimada na imagem).

- **Nome do arquivo sem `:`** — o contrato recusa dois-pontos em caminho de prova — e com extensão
  real (`.mp4`, `.webm`), que é o que faz o relatório escolher o decodificador.
- Se o desfecho do passo aparece na tela **depois** da última palavra, aumente `--cauda`.
- **Avisos** no JSON são para resolver, não para ignorar: fala que invade a cena seguinte tem a
  legenda cortada nesse ponto; ordem de marcos diferente da do roteiro significa que a gravação não
  seguiu o plano.
- O `montar` recusa o resultado sem faixa de áudio ou com áudio mudo e, nesse caso, não apaga nada.
- Os insumos são **preservados por padrão**. A gravação bruta é o único insumo irrecuperável, e a
  revisão pode exigir remontar com outro corte ou outra âncora. Só depois de a prova estar revisada
  e registrada vale usar `--apagar-insumos`.
- Tentativa descartada é apagada, não guardada ao lado da prova.

### Âncora: amarrar o relógio dos marcos ao primeiro quadro

Os marcos são registrados com o relógio do **host**; a gravação pode ter sido feita noutro relógio.
O padrão `--ancora parar` assume origem = instante do `parar` menos a duração do arquivo.

- **Vale** para captura no próprio host, iniciada e encerrada por sinal. Mesmo aí sobra o atraso de
  partida da captura, da ordem de um décimo de segundo — tolerável para narração.
- **Não vale** quando o arquivo nasce no aparelho (`screenrecord`, espelhamento que grava com o
  timestamp do aparelho) nem quando a gravação termina sozinha por limite de tempo: aí não há
  relação conhecida entre os dois relógios.
- Nesses casos, use um **marco visível**: no começo da gravação, pinte na tela gravada algo
  inequívoco (tela de cor cheia, carimbo, contador) no mesmo instante em que registra um marco.
  Depois ache esse quadro na gravação bruta (`ffmpeg -ss <s> -i <bruto> -frames:v 1 q.png`, olhando
  as imagens; o `conferir` é para o vídeo já montado, porque exige faixa de áudio) e informe
  `--ancora cena --ancora-cena <id> --ancora-em <segundos no arquivo>`. A origem passa a ser medida
  **dentro do vídeo**, e o relógio do aparelho deixa de importar.

## 6. Revisar e registrar como prova

```bash
qv conferir --video <...>/jornada-narrada.mp4        # um quadro por cena + medida do áudio
```

O `conferir` lê os instantes das cenas da **própria legenda embutida**, extrai um quadro de cada uma
e devolve a fala correspondente. Então:

1. **Abra cada quadro como imagem** e confirme que a tela mostra o que a fala diz naquele ponto. Sem
   balão do navegador, sem tela de erro alheia, sem janela de terceiro, sem dado sensível.
2. **Transcreva o áudio de volta** e compare com o roteiro, na ordem e no tempo.
3. Confirme que nada no quadro ou no áudio pertence a outro cliente ou expõe credencial.

Só então registre, como qualquer outra prova:

```bash
python3 <caminho-da-skill>/scripts/qa_artifacts.py evidence --run <rodada>/run.json \
  --id EV-VID-001 --file cases/ct-001/attempt-01/jornada-narrada.mp4 --kind recording \
  --caption "Jornada narrada do CT-001, gravada após a execução que a documentou: esperado, ação e veredito" \
  --tool "<gravador e motor de voz usados>" --at <ISO com fuso> \
  --reviewed --review-note "quadros conferidos um a um e áudio transcrito; sem dado sensível"
```

- `kind: recording`. O hash é calculado no registro e reconferido em toda validação; `reviewed` e
  `review_note` são obrigatórios, e aqui significam **assisti ao vídeo inteiro e conferi o que ele
  mostra e diz**. Marcar o campo não executa a revisão.
- Vídeo da rodada inteira: registre **sem vincular a nada**. O `report` publica toda gravação não
  referenciada numa seção "Gravação da rodada" do relatório executivo. Vincular a gravação a um
  passo, a um bug ou a um reteste a tira do executivo e a põe na página daquele CT ou daquele bug —
  que é o que se quer quando o vídeo cobre um caso só.
- O `report` copia a gravação para `delivery/<snapshot>/evidence/` e a inclui no
  `manifest-sha256.json`. O HTML toca o vídeo com um player apontando para o arquivo irmão: mover o
  `.html` sozinho quebra a reprodução. **No PDF a gravação não vai** — fica a legenda com o nome do
  arquivo e o SHA-256; o vídeo é prova de HTML e Markdown.
- Pesa: uma cópia por snapshot. Deixar o vídeo fora do `run.json`, citado só pelo caminho no
  `summary`, evita a cópia — mas tira dele o hash e o gate de revisão, e o leitor fica sem link.
  Isso é exceção, não alternativa de gosto: só quando o destino exigir um arquivo único, dito no
  fechamento da rodada. O padrão é registrar.

## Variante: demonstração da funcionalidade ao usuário

A pedido, o mesmo mecanismo produz um vídeo de outra natureza: uma **demonstração** que apresenta a
funcionalidade a quem vai usá-la, em linguagem de produto. Muda o conteúdo, não as regras acima.

- Nada de "CT", "passo", "PASSOU" ou veredito: a fala diz o que é a novidade, como se faz, o que o
  sistema responde quando algo está errado e o que muda para o usuário.
- A fala vem da história, da nota de lançamento e do material de ajuda — não do diff nem dos nomes de
  CT. Segunda pessoa, presente.
- Só entra comportamento de CT **aprovado**: demonstrar o que falhou é mostrar ao usuário o que ele
  não vai encontrar. O que ficou de fora é dito no fechamento.
- Continua sendo execução real e gravada, não encenação — e continua passando pela revisão antes de
  ser distribuída.
