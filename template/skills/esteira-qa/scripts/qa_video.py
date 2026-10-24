#!/usr/bin/env python3
"""Narração e montagem do vídeo narrado da rodada de QA. Python 3.10+, só biblioteca padrão.

Depende de ferramentas externas do hospedeiro, como `export_pdf.py` depende de um navegador local:
`ffmpeg`/`ffprobe` para medir e montar, e um motor de voz para falar. Nada é instalado no projeto;
faltando o binário, o comando recusa dizendo o que falta.

  narrar    gera a fala de cada cena do roteiro e mede a duração de cada uma.
  marco     registra, com o relógio do host, o início/fim da gravação e o começo de cada cena.
  aguardar  dorme o que falta da fala da cena, para a ação ocorrer enquanto a voz explica.
  montar    junta a gravação da tela com as falas, cada uma no instante da sua cena, corta o tempo
            morto das pontas, embute a legenda como faixa do arquivo e confere que o vídeo final
            tem narração audível.
  conferir  extrai um quadro por cena e mede o áudio, insumo da revisão obrigatória da prova.

O script **não grava a tela e não executa o sistema sob teste**: a captura é feita pelas ferramentas
reais do hospedeiro, num display ou aparelho que a rodada controla. Nada aqui decide resultado de
teste nem julga uma prova.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid

TIPOS = {"inicio", "parar", "cena"}
# Container de vídeo de verdade: MP4/MOV trazem "ftyp" no início, Matroska/WebM o EBML.
VIDEO_MAGIC = (b"ftyp", b"\x1a\x45\xdf\xa3")
# Id de cena vira nome de arquivo .wav e rótulo de legenda: sem separador de caminho, sem surpresa.
ID_CENA = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}")
# Mesma regra do qa_artifacts.py: nome reservado no Windows impediria a rodada de ser aberta lá.
RESERVADOS = {"con", "prn", "aux", "nul"} | {f"{p}{i}" for p in ("com", "lpt") for i in range(1, 10)}
MUDO_DB = -45.0
LIMITE_TTS = 1800
LIMITE_FFMPEG = 3600


def id_valido(valor):
    return bool(ID_CENA.fullmatch(str(valor))) and str(valor).casefold() not in RESERVADOS


def dados_do_usuario():
    """Onde ficam os modelos de voz: variável explícita, depois o diretório de dados do usuário."""
    escolhido = os.environ.get("QA_BOT_VOZES")
    if escolhido:
        return Path(escolhido).expanduser()
    base = os.environ.get("XDG_DATA_HOME")
    return Path(base).expanduser() if base else Path.home() / ".local/share"


# Roda num ambiente efêmero do uv (kokoro-onnx já traz o espeak-ng): lê as cenas do stdin e grava um
# wav por cena. "pf_dora" usa a voz pura; "pf_dora+if_sara:0.5" mistura o timbre das duas (peso da
# segunda depois do ":"), que é como se obtém um timbre que nenhuma voz pronta tem.
KOKORO_SCRIPT = """
import json, sys, soundfile as sf
from kokoro_onnx import Kokoro
pedido = json.load(sys.stdin)
k = Kokoro(pedido["dir"] + "/kokoro-v1.0.onnx", pedido["dir"] + "/voices-v1.0.bin")
base, _, resto = pedido["voz"].partition("+")
voz = k.get_voice_style(base)
if resto:
    outra, _, peso = resto.partition(":")
    peso = float(peso or 0.5)
    voz = voz * (1 - peso) + k.get_voice_style(outra) * peso
for cena in pedido["cenas"]:
    audio, sr = k.create(cena["texto"], voice=voz, speed=pedido["velocidade"], lang=pedido["idioma"])
    sf.write(cena["wav"], audio, sr)
"""


def agora_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def exige(*binarios):
    faltando = [b for b in binarios if not shutil.which(b)]
    if faltando:
        raise ValueError(f"não encontrado no PATH: {', '.join(faltando)}")


def rodar(comando, **kwargs):
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("timeout", LIMITE_FFMPEG)
    return subprocess.run(comando, check=True, **kwargs)


def duracao(arquivo, fluxo=None):
    """Duração do contêiner ou, com `fluxo`, a de um fluxo específico (v:0 para a imagem).

    A diferença importa: o áudio é esticado até a janela pedida, então só a duração do fluxo de
    vídeo revela uma gravação cuja imagem acabou antes.
    """
    alvo = ["-select_streams", fluxo] if fluxo else []
    entrada = "stream=duration" if fluxo else "format=duration"
    saida = rodar(["ffprobe", "-v", "error", *alvo, "-show_entries", entrada, "-of", "csv=p=0",
                   str(arquivo)], timeout=120).stdout.strip().splitlines()
    try:
        return float(saida[0].rstrip(","))
    except (ValueError, IndexError):
        if fluxo:
            return None
        raise ValueError(f"{arquivo}: duração ilegível; gravação encerrada sem fechar o arquivo?")


def volume_medio(arquivo):
    """dB médios do arquivo. None quando a medida não pôde ser feita."""
    medida = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-i", str(arquivo), "-map", "0:a",
                             "-af", "volumedetect", "-f", "null", "-"],
                            capture_output=True, text=True, timeout=LIMITE_FFMPEG)
    if medida.returncode != 0 or "mean_volume:" not in medida.stderr:
        return None
    return float(medida.stderr.split("mean_volume:")[1].split("dB")[0])


def assinatura_da_fala(cena, pronuncia):
    """Identifica o que foi efetivamente sintetizado E o que vai na legenda."""
    dito = falado(cena["fala"], pronuncia)
    return hashlib.sha256(f"{cena['fala']}\x00{dito}".encode("utf-8")).hexdigest()


def ler_roteiro(caminho):
    roteiro = json.loads(Path(caminho).read_text(encoding="utf-8"))
    if not isinstance(roteiro, dict):
        raise ValueError("roteiro precisa ser um objeto JSON com 'cenas'")
    if roteiro.get("pronuncia") is not None and not isinstance(roteiro["pronuncia"], dict):
        raise ValueError("'pronuncia' precisa ser um objeto {escrito: dito}")
    cenas = roteiro.get("cenas")
    if not isinstance(cenas, list) or not cenas:
        raise ValueError("roteiro precisa de 'cenas' com ao menos uma cena")
    vistos = set()
    for cena in cenas:
        if not isinstance(cena, dict) or not id_valido(cena.get("id", "")):
            raise ValueError("cada cena precisa de 'id' com letras, números, ponto, hífen ou sublinhado")
        if not isinstance(cena.get("fala"), str) or not cena["fala"].strip():
            raise ValueError(f"cena {cena['id']} precisa de 'fala' em texto")
        if cena["id"].casefold() in vistos:
            raise ValueError(f"id de cena repetido no roteiro: {cena['id']}")
        vistos.add(cena["id"].casefold())
    return roteiro


def ler_duracoes(narracao, roteiro=None):
    arquivo = Path(narracao) / "duracoes.json"
    if not arquivo.is_file():
        raise ValueError(f"{arquivo} não existe; rode o `narrar` antes")
    duracoes = json.loads(arquivo.read_text(encoding="utf-8"))
    if roteiro is not None:
        # Roteiro editado depois do `narrar` é a causa silenciosa de vídeo fora de sincronia.
        faltando = [c["id"] for c in roteiro["cenas"] if c["id"] not in duracoes]
        if faltando:
            raise ValueError(f"cenas sem fala gerada: {', '.join(faltando)} — rode o `narrar` de novo")
    return duracoes


def ler_marcos(log, uma_gravacao=False):
    caminho = Path(log)
    if not caminho.is_file():
        raise ValueError(f"{caminho} não existe; nenhum marco foi registrado")
    eventos = []
    for numero, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1):
        if not linha.strip():
            continue
        try:
            evento = json.loads(linha)
            float(evento["t"])
            if evento["tipo"] not in TIPOS:
                raise ValueError("tipo desconhecido")
        except (ValueError, KeyError, TypeError):
            raise ValueError(f"{caminho}:{numero}: marco ilegível")
        eventos.append(evento)
    if not eventos:
        raise ValueError(f"{caminho} está vazio")
    if uma_gravacao:
        for tipo in ("inicio", "parar"):
            if sum(1 for e in eventos if e["tipo"] == tipo) > 1:
                raise ValueError(f"o log tem mais de um marco '{tipo}': use um log novo por tentativa "
                                 "de gravação, senão as falas alinham pela gravação errada")
    return sorted(eventos, key=lambda e: e["t"])


def falado(texto, pronuncia):
    # A pronúncia só muda o que a voz lê; a legenda mostra o texto original.
    for escrito, dito in (pronuncia or {}).items():
        texto = texto.replace(escrito, dito)
    return texto


def narrar(args):
    exige("ffprobe")
    if not 0.4 <= args.ritmo <= 3.0:
        raise ValueError("--ritmo fora de 0.4 a 3.0")
    roteiro = ler_roteiro(args.roteiro)
    destino = Path(args.saida)
    destino.mkdir(parents=True, exist_ok=True)
    textos = [(c["id"], falado(c["fala"], roteiro.get("pronuncia")).strip()) for c in roteiro["cenas"]]
    if args.motor == "kokoro":
        exige("uv")
        # Peso fora de 0..1 não mistura timbre: extrapola o vetor de voz e sintetiza ruído saturado,
        # que passaria pelas checagens seguintes por ser alto, e não mudo.
        _, _, mistura = args.voz.partition("+")
        if mistura:
            _, _, peso = mistura.partition(":")
            try:
                peso = float(peso) if peso else 0.5
            except ValueError:
                raise ValueError(f"peso de mistura de timbre não numérico em --voz {args.voz}")
            if not 0.0 <= peso <= 1.0:
                raise ValueError(f"peso de mistura de timbre fora de 0 a 1: {peso}")
        modelos = Path(args.modelos).expanduser() if args.modelos else dados_do_usuario() / "kokoro"
        for arquivo in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
            if not (modelos / arquivo).is_file():
                raise ValueError(f"{arquivo} não está em {modelos}: baixe os dois arquivos de modelo "
                                 "do kokoro-onnx (release de model-files) para essa pasta, ou aponte "
                                 "outra em QA_BOT_VOZES")
        pedido = {"dir": str(modelos), "voz": args.voz, "idioma": args.idioma,
                  "velocidade": round(1 / args.ritmo, 3),
                  "cenas": [{"texto": t, "wav": str((destino / f"{i}.wav").resolve())} for i, t in textos]}
        rodar(["uv", "run", "--quiet", "--with", "kokoro-onnx", "--with", "soundfile",
               "python", "-c", KOKORO_SCRIPT], input=json.dumps(pedido), timeout=LIMITE_TTS)
        voz = args.voz
    elif args.motor == "piper":
        exige("uvx")
        modelo = Path(args.modelo).expanduser() if args.modelo else dados_do_usuario() / "piper/voz.onnx"
        if not modelo.is_file():
            raise ValueError(f"modelo de voz {modelo} não encontrado: baixe uma voz do piper (os "
                             "arquivos .onnx e .onnx.json) e aponte com --modelo, ou use QA_BOT_VOZES")
        for identificador, texto in textos:
            rodar(["uvx", "--from", "piper-tts", "piper", "-m", str(modelo),
                   "-f", str(destino / f"{identificador}.wav"), "--length-scale", str(args.ritmo),
                   "--sentence-silence", "0.35"], input=texto, timeout=LIMITE_TTS)
        voz = modelo.stem
    else:
        # Escape para o hospedeiro que já tem um sintetizador: nada é baixado e nada sai da máquina
        # além do que o próprio comando fizer. O texto vai no stdin; {wav} é o arquivo de saída.
        if not args.comando or "{wav}" not in args.comando:
            raise ValueError("--motor comando precisa de --comando contendo {wav}")
        partes = shlex.split(args.comando)
        for identificador, texto in textos:
            alvo = str((destino / f"{identificador}.wav").resolve())
            rodar([p.replace("{wav}", alvo) for p in partes], input=texto, timeout=LIMITE_TTS)
        voz = partes[0]
    duracoes, mudas = {}, []
    for identificador, _ in textos:
        wav = destino / f"{identificador}.wav"
        if not wav.is_file():
            raise ValueError(f"{wav} não foi gerado pelo motor de voz")
        duracoes[identificador] = round(duracao(wav), 2)
        # Uma cena muda no meio das outras não move a média do vídeo inteiro: medir uma a uma.
        nivel = volume_medio(wav)
        if duracoes[identificador] <= 0.2 or nivel is None or nivel < MUDO_DB:
            mudas.append(identificador)
    if mudas:
        raise ValueError(f"fala sem áudio audível para: {', '.join(mudas)}")
    (destino / "duracoes.json").write_text(json.dumps(duracoes, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    # Guarda o que foi falado: reescrever a fala sem renarrar deixaria a legenda nova sobre o áudio
    # velho, e o id continuaria batendo.
    (destino / "falas.json").write_text(json.dumps(
        {c["id"]: assinatura_da_fala(c, roteiro.get("pronuncia")) for c in roteiro["cenas"]},
        ensure_ascii=False, indent=2), encoding="utf-8")
    return {"saida": str(destino), "motor": args.motor, "voz": voz, "cenas": len(duracoes),
            "fala_total_s": round(sum(duracoes.values()), 1), "duracoes": duracoes,
            "proximo": "conferir a fala transcrevendo cada .wav de volta antes de gravar a tela"}


def marco(args):
    if args.tipo == "cena" and not args.cena:
        raise ValueError("marco de cena precisa de --cena")
    if args.cena and not id_valido(args.cena):
        raise ValueError(f"id de cena inválido: {args.cena}")
    # Ler antes de escrever: um erro depois do append deixaria o marco gravado com rc=2, e a
    # repetição natural do comando duplicaria o marco, deslocando a fala da cena.
    fala = ler_duracoes(args.narracao).get(args.cena) if (args.narracao and args.tipo == "cena") else None
    registro = {"t": time.time(), "em": agora_iso(), "tipo": args.tipo, "cena": args.cena or ""}
    log = Path(args.log)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(registro, ensure_ascii=False) + "\n")
    saida = dict(registro)
    if fala is not None:
        saida["fala_s"] = fala
    return saida


def aguardar(args):
    """Completa o tempo da fala da cena: sem isso a ação acaba antes da voz e o corte fica torto."""
    if not 0.0 <= args.folga <= 30.0:
        raise ValueError("--folga fora de 0 a 30")
    fala = ler_duracoes(args.narracao).get(args.cena)
    if fala is None:
        raise ValueError(f"cena {args.cena} sem fala em duracoes.json")
    comeco = next((e["t"] for e in reversed(ler_marcos(args.log))
                   if e["tipo"] == "cena" and e["cena"] == args.cena), None)
    if comeco is None:
        raise ValueError(f"cena {args.cena} sem marco; chame `marco --tipo cena` antes de agir")
    restante = comeco + fala + args.folga - time.time()
    if restante > 0:
        time.sleep(restante)
    return {"cena": args.cena, "fala_s": fala, "esperou_s": round(max(0.0, restante), 2),
            "excedeu_s": round(max(0.0, -restante), 2)}


def conferir_audio(video):
    """O vídeo só vale com a narração dentro dele: faixa de áudio presente e com som."""
    faixas = json.loads(rodar(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                               "stream=codec_name,channels,sample_rate", "-of", "json",
                               str(video)], timeout=120).stdout).get("streams", [])
    if not faixas:
        raise ValueError(f"{video} saiu sem faixa de áudio")
    # Não confundir "não consegui medir" com "está mudo": o primeiro é erro de ferramenta.
    media = volume_medio(video)
    if media is None:
        raise ValueError(f"{video}: não foi possível medir o áudio")
    if media < MUDO_DB:
        raise ValueError(f"{video}: faixa de áudio muda (volume médio {media} dB)")
    return {"faixas": len(faixas), "canais": faixas[0].get("channels"), "volume_medio_db": media}


def tempo_srt(s):
    ms = max(0, round(s * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    seg, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{seg:02d},{ms:03d}"


def texto_srt(fala):
    # Linha em branco encerra a legenda e "-->" dentro dela quebra o parser: achatar antes de gravar.
    linhas = [l.strip().replace("-->", "→") for l in fala.strip().splitlines()]
    return "\n".join(l for l in linhas if l) or "…"


def origem_da_gravacao(args, eventos, dur_bruto):
    """Qual instante do relógio do host corresponde ao primeiro quadro da gravação.

    O padrão (`parar` menos a duração do arquivo) só vale quando o host controla início e fim e o
    eixo de tempo do arquivo é o do host — captura na própria máquina, encerrada por sinal. Mesmo
    ali sobra o atraso de partida da captura (décimos de segundo). Quando o arquivo nasce noutro
    relógio (gravação feita no aparelho, limite de tempo que dispara sozinho), mede-se nos quadros
    onde aparece um marco visível e informa-se o instante em --ancora-em.
    """
    tipo = args.ancora
    if tipo == "cena":
        if not args.ancora_cena:
            raise ValueError("--ancora cena precisa de --ancora-cena")
        if args.ancora_em is None:
            raise ValueError("--ancora cena precisa de --ancora-em: o segundo, dentro da gravação, "
                             "em que essa cena aparece")
        instante = next((e["t"] for e in reversed(eventos)
                         if e["tipo"] == "cena" and e["cena"] == args.ancora_cena), None)
    else:
        procura = eventos if tipo == "inicio" else list(reversed(eventos))
        instante = next((e["t"] for e in procura if e["tipo"] == tipo), None)
    if instante is None:
        alvo = args.ancora_cena if tipo == "cena" else tipo
        raise ValueError(f"log sem marco '{alvo}' — não dá para alinhar as falas")
    dentro = args.ancora_em if args.ancora_em is not None else (dur_bruto if tipo == "parar" else 0.0)
    if not -0.001 <= dentro <= dur_bruto + 0.001:
        raise ValueError(f"--ancora-em {dentro} fora da gravação (0 a {dur_bruto:.3f}s)")
    return instante - dentro, {"ancora": tipo, "ancora_em_s": round(dentro, 3)}


def montar(args):
    exige("ffmpeg", "ffprobe")
    for nome, valor, menor, maior in (("--fps", args.fps, 1, 120), ("--crf", args.crf, 0, 51),
                                      ("--margem", args.margem, 0.0, 30.0),
                                      ("--cauda", args.cauda, 0.0, 60.0)):
        if not menor <= valor <= maior:
            raise ValueError(f"{nome} fora de {menor} a {maior}")
    saida = Path(args.saida).resolve()
    if ":" in saida.name:
        raise ValueError("nome com ':' não é aceito como caminho de prova; use hífen no lugar")
    if saida.exists():
        raise FileExistsError(f"{saida} já existe; o vídeo montado não é sobrescrito")
    roteiro = ler_roteiro(args.roteiro)
    narracao = Path(args.narracao)
    duracoes = ler_duracoes(narracao, roteiro)
    bruto = Path(args.bruto).resolve()
    with bruto.open("rb") as stream:
        cabecalho = stream.read(16)
    if not any(assinatura in cabecalho for assinatura in VIDEO_MAGIC):
        raise ValueError(f"{bruto} não é MP4/Matroska legível: gravação encerrada à força perde o "
                         "índice e o arquivo inteiro")
    dur_bruto = duracao(bruto)
    eventos = ler_marcos(args.log, uma_gravacao=True)
    origem, ancoragem = origem_da_gravacao(args, eventos, dur_bruto)

    avisos = []
    marcos = {}
    for evento in eventos:
        if evento["tipo"] == "cena":
            if evento["cena"] in marcos:
                avisos.append(f"cena {evento['cena']} marcada mais de uma vez: vale a última")
            marcos[evento["cena"]] = evento["t"] - origem
    faltando = [c["id"] for c in roteiro["cenas"] if c["id"] not in marcos]
    if faltando:
        raise ValueError(f"cenas do roteiro sem marco na gravação: {', '.join(faltando)}")
    sobrando = sorted(set(marcos) - {c["id"] for c in roteiro["cenas"]})
    if sobrando:
        avisos.append(f"marco sem cena no roteiro, ignorado: {', '.join(sobrando)}")
    cenas = sorted(roteiro["cenas"], key=lambda c: marcos[c["id"]])
    if [c["id"] for c in cenas] != [c["id"] for c in roteiro["cenas"]]:
        avisos.append("a ordem dos marcos não é a do roteiro; vale a ordem em que foi gravado")
    for cena in cenas:
        if not 0 <= marcos[cena["id"]] <= dur_bruto:
            raise ValueError(f"a cena {cena['id']} cai fora da gravação ({marcos[cena['id']]:.1f}s de "
                             f"{dur_bruto:.1f}s): confira a âncora e se o log é desta gravação")
    for atual, seguinte in zip(cenas, cenas[1:]):
        sobra = marcos[seguinte["id"]] - (marcos[atual["id"]] + duracoes[atual["id"]])
        if sobra < 0:
            avisos.append(f"a fala de '{atual['id']}' invade {-sobra:.1f}s a cena '{seguinte['id']}'; "
                          "a legenda dela é cortada nesse ponto")

    # Fala reescrita depois do `narrar`: o id continua batendo, mas a legenda diria uma coisa e o
    # áudio outra. Narração antiga, sem falas.json, só gera aviso.
    assinaturas = narracao / "falas.json"
    if assinaturas.is_file():
        gravadas = json.loads(assinaturas.read_text(encoding="utf-8"))
        mudadas = [c["id"] for c in cenas
                   if gravadas.get(c["id"]) != assinatura_da_fala(c, roteiro.get("pronuncia"))]
        if mudadas:
            raise ValueError(f"a fala mudou depois do `narrar` em: {', '.join(mudadas)} — narre de novo")
    else:
        avisos.append("narração sem falas.json: não dá para conferir se o texto mudou depois do `narrar`")
    for cena in cenas:
        if not (narracao / f"{cena['id']}.wav").is_file():
            raise ValueError(f"{narracao / (cena['id'] + '.wav')} não existe; rode o `narrar` para o "
                             "roteiro inteiro")

    corte_ini = max(0.0, marcos[cenas[0]["id"]] - args.margem)
    ultima = cenas[-1]
    fim_fala = marcos[ultima["id"]] + duracoes[ultima["id"]]
    corte_fim = min(dur_bruto, fim_fala + args.cauda)
    if corte_fim < fim_fala - 0.05:
        avisos.append(f"a gravação acaba {fim_fala - dur_bruto:.1f}s antes do fim da última fala: "
                      "parte da narração final ficou de fora")
    if corte_fim - corte_ini <= 0.5:
        raise ValueError("janela de corte vazia: confira os marcos e a âncora")
    janela = corte_fim - corte_ini

    construcao = saida.parent / f".montando-{saida.stem}-{uuid.uuid4().hex[:8]}"
    construcao.mkdir(parents=True)
    try:
        entradas = ["-ss", f"{corte_ini:.3f}", "-to", f"{corte_fim:.3f}", "-i", str(bruto)]
        filtros, rotulos, srt = [], [], []
        for n, cena in enumerate(cenas, 1):
            entradas += ["-i", str((narracao / f"{cena['id']}.wav").resolve())]
            comeco = marcos[cena["id"]] - corte_ini
            atraso = round(comeco * 1000)
            if atraso < 0:
                raise ValueError(f"cena {cena['id']} começa antes do corte; reduza --margem")
            filtros.append(f"[{n}:a]aresample=48000,adelay={atraso}:all=1[a{n}]")
            rotulos.append(f"[a{n}]")
            # O mov_text trunca legenda sobreposta sem avisar: fechar a anterior onde a próxima abre.
            fim = comeco + duracoes[cena["id"]]
            if n < len(cenas):
                fim = min(fim, marcos[cenas[n]["id"]] - corte_ini)
            srt.append(f"{n}\n{tempo_srt(comeco)} --> {tempo_srt(max(comeco + 0.2, fim))}\n"
                       f"{texto_srt(cena['fala'])}\n")
        # Estéreo: a fala é mono e alguns players tocam faixa mono num canal só. O `apad` de duração
        # fechada define o fim do áudio; sem ele o `apad` cresce sem limite e o ffmpeg morre com
        # "No space left on device". E **não** se usa `-shortest`: com a faixa de legenda mapeada,
        # ele encerra o arquivo na última legenda e a cauda do vídeo desaparece (medido).
        filtros.append(f"{''.join(rotulos)}amix=inputs={len(cenas)}:normalize=0:dropout_transition=0,"
                       f"alimiter=limit=0.95,pan=stereo|c0=c0|c1=c0,apad=whole_dur={janela:.3f}[audio]")
        filtros.append(f"[0:v]fps={args.fps},scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p[video]")
        legenda = construcao / "legenda.srt"
        legenda.write_text("\n".join(srt), encoding="utf-8")
        entradas += ["-i", str(legenda)]
        temporario = construcao / ("final" + saida.suffix)
        rodar(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", *entradas,
               "-filter_complex", ";".join(filtros), "-map", "[video]", "-map", "[audio]",
               "-map", f"{len(cenas) + 1}:s", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", str(args.crf), "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
               "-c:s", "mov_text", "-metadata:s:a:0", f"language={args.lingua}",
               "-metadata:s:s:0", f"language={args.lingua}",
               "-movflags", "+faststart", str(temporario)])
        audio = conferir_audio(temporario)
        # A imagem pode acabar antes do áudio: `apad` estica a faixa de som até a janela inteira, e
        # uma gravação truncada (recorder morto no meio, índice declarando mais do que existe)
        # produziria cenas narrando sobre nada. Medir o fluxo de vídeo é o que revela isso.
        imagem = duracao(temporario, "v:0")
        if imagem is not None and imagem < fim_fala - corte_ini - 0.05:
            raise ValueError(f"a imagem acaba em {imagem:.1f}s, antes do fim da última fala "
                             f"({fim_fala - corte_ini:.1f}s): a gravação está truncada — regrave")
        if saida.exists():
            raise FileExistsError(f"{saida} criado durante a montagem; resultado em {construcao}")
        os.replace(temporario, saida)
    except BaseException:
        # Interrupção não pode destruir o trabalho; mas anunciar uma pasta vazia como "preservada"
        # mandaria o leitor procurar o que não existe.
        if any(construcao.rglob("*")):
            print(json.dumps({"montagem_preservada": str(construcao)}, ensure_ascii=False),
                  file=sys.stderr)
        else:
            shutil.rmtree(construcao, ignore_errors=True)
        raise
    shutil.rmtree(construcao, ignore_errors=True)
    final = duracao(saida)
    apagados = []
    if args.apagar_insumos:
        # Opcional e nunca o padrão: a gravação bruta é o único insumo que não se recupera, e a
        # revisão da prova ainda pode exigir remontar com outro corte.
        for cena in cenas:
            try:
                (narracao / f"{cena['id']}.wav").unlink(missing_ok=True)
                apagados.append(f"{cena['id']}.wav")
            except OSError as exc:
                avisos.append(f"não apagou {cena['id']}.wav: {exc}")
        try:
            bruto.unlink()
            apagados.append(bruto.name)
        except OSError as exc:
            avisos.append(f"não apagou {bruto.name}: {exc}")
    return {"saida": str(saida), "duracao_s": round(final, 1), "audio": audio, **ancoragem,
            "cortado_do_bruto_s": [round(corte_ini, 1), round(corte_fim, 1)], "cenas": len(cenas),
            "insumos_apagados": apagados, "avisos": avisos,
            "proximo": "rodar o `conferir` e revisar quadro e áudio antes de registrar a prova"}


def legendas_do_video(video):
    """As cenas do vídeo montado, lidas da própria faixa de legenda: não dependem de insumo externo."""
    saida = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                            "-i", str(video), "-map", "0:s:0", "-f", "srt", "-"],
                           capture_output=True, text=True, timeout=LIMITE_FFMPEG)
    if saida.returncode != 0:
        return []
    def segundos(marca):
        horas, minutos, resto = marca.split(":")
        return int(horas) * 3600 + int(minutos) * 60 + float(resto.replace(",", "."))
    cues = []
    for bloco in saida.stdout.strip().split("\n\n"):
        linhas = bloco.strip().splitlines()
        if len(linhas) >= 2 and "-->" in linhas[1]:
            comeco, _, fim = linhas[1].partition("-->")
            cues.append({"em_s": segundos(comeco.strip()), "ate_s": segundos(fim.strip()),
                         "fala": " ".join(l.strip() for l in linhas[2:])})
    return cues


def conferir(args):
    """Insumo da revisão obrigatória da prova: um quadro por cena e a medida do áudio."""
    exige("ffmpeg", "ffprobe")
    video = Path(args.video)
    destino = Path(args.saida) if args.saida else video.parent / f"revisao-{video.stem}"
    if destino.exists() and any(destino.iterdir()):
        raise FileExistsError(f"{destino} já tem arquivos; quadros de revisão não são sobrescritos")
    destino.mkdir(parents=True, exist_ok=True)
    total = duracao(video)
    # O instante de cada cena está na legenda embutida pelo `montar`; acumular durações de fala
    # erraria, porque entre duas cenas há o tempo da ação, que não é o tempo da voz.
    cues = legendas_do_video(video)
    if cues:
        instantes = [(f"cena-{n:02d}", min(c["em_s"] + 0.4, max(0.0, total - 0.05)), c["fala"])
                     for n, c in enumerate(cues, 1)]
    else:
        if not 1 <= args.quadros <= 60:
            raise ValueError("--quadros fora de 1 a 60")
        passo = total / (args.quadros + 1)
        instantes = [(f"t{n:02d}", round(passo * n, 2), "") for n in range(1, args.quadros + 1)]
    quadros = []
    for identificador, instante, fala in instantes:
        arquivo = destino / f"{identificador}.png"
        rodar(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
               "-ss", f"{max(0.0, instante):.3f}", "-i", str(video), "-frames:v", "1", str(arquivo)])
        # O ffmpeg sai com 0 e não grava nada quando o instante cai depois do fim da imagem.
        # Listar um quadro inexistente alimentaria a revisão da prova com um caminho vazio.
        if not arquivo.is_file() or not arquivo.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError(f"nenhum quadro em {instante:.2f}s: a imagem do vídeo acaba antes")
        quadros.append({"cena": identificador, "em_s": round(instante, 2), "fala": fala,
                        "arquivo": str(arquivo)})
    return {"video": str(video), "duracao_s": round(total, 1), "audio": conferir_audio(video),
            "cenas_na_legenda": len(cues), "quadros": quadros,
            "proximo": "abrir cada quadro como imagem e conferir que a tela corresponde à fala; "
                       "transcrever o áudio de volta; só então registrar a prova com reviewed e "
                       "review_note"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="subcomando", required=True)
    n = sub.add_parser("narrar", help="gera a fala de cada cena e duracoes.json")
    n.add_argument("--roteiro", required=True, help="roteiro.json com as cenas e as falas")
    n.add_argument("--saida", required=True, help="pasta das falas (insumo, fora da entrega)")
    n.add_argument("--motor", choices=["kokoro", "piper", "comando"], default="kokoro")
    n.add_argument("--voz", default="pf_dora+if_sara:0.5",
                   help="voz do kokoro; VOZ+OUTRA:peso mistura o timbre das duas (padrão: feminina)")
    n.add_argument("--idioma", default="pt-br", help="idioma da fala no kokoro")
    n.add_argument("--modelos", help="pasta dos modelos do kokoro (padrão: QA_BOT_VOZES ou XDG)")
    n.add_argument("--modelo", help="arquivo .onnx da voz do piper")
    n.add_argument("--comando", help="sintetizador do hospedeiro; recebe o texto no stdin e grava {wav}")
    n.add_argument("--ritmo", type=float, default=1.0, help="maior = mais devagar (1.0 = normal)")
    m = sub.add_parser("marco", help="registra um marco com o relógio do host")
    m.add_argument("--log", required=True)
    m.add_argument("--tipo", required=True, choices=sorted(TIPOS))
    m.add_argument("--cena", default="")
    m.add_argument("--narracao", help="pasta das falas, para devolver a duração da cena")
    a = sub.add_parser("aguardar", help="dorme o que falta da fala da cena")
    a.add_argument("--log", required=True)
    a.add_argument("--narracao", required=True)
    a.add_argument("--cena", required=True)
    a.add_argument("--folga", type=float, default=0.7, help="segundos de respiro depois da fala")
    v = sub.add_parser("montar", help="monta o vídeo narrado e confere o áudio")
    v.add_argument("--roteiro", required=True)
    v.add_argument("--narracao", required=True)
    v.add_argument("--bruto", required=True, help="gravação da tela, feita pelas ferramentas do host")
    v.add_argument("--log", required=True)
    v.add_argument("--saida", required=True)
    v.add_argument("--ancora", choices=["parar", "inicio", "cena"], default="parar",
                   help="marco que amarra o relógio dos marcos ao primeiro quadro da gravação")
    v.add_argument("--ancora-cena", help="id da cena usada como âncora")
    v.add_argument("--ancora-em", type=float,
                   help="segundo, dentro da gravação, em que a âncora aparece (medido nos quadros)")
    v.add_argument("--margem", type=float, default=1.0, help="segundos mantidos antes da 1ª cena")
    v.add_argument("--cauda", type=float, default=1.5,
                   help="segundos mantidos depois da última fala; aumente se o desfecho aparece depois")
    v.add_argument("--fps", type=int, default=30)
    v.add_argument("--crf", type=int, default=24)
    v.add_argument("--lingua", default="por", help="código ISO 639-2 das faixas de áudio e legenda")
    v.add_argument("--apagar-insumos", action="store_true",
                   help="apagar a gravação bruta e as falas depois de conferir o vídeo final")
    c = sub.add_parser("conferir", help="extrai um quadro por cena e mede o áudio, para a revisão")
    c.add_argument("--video", required=True)
    c.add_argument("--saida", help="pasta dos quadros (padrão: revisao-<vídeo> ao lado dele)")
    c.add_argument("--quadros", type=int, default=6,
                   help="quadros espaçados, quando o vídeo não tem faixa de legenda")
    args = parser.parse_args(argv)
    comandos = {"narrar": narrar, "marco": marco, "aguardar": aguardar, "montar": montar,
                "conferir": conferir}
    try:
        resultado = comandos[args.subcomando](args)
    except KeyboardInterrupt:
        print(json.dumps({"erro": "interrompido"}, ensure_ascii=False), file=sys.stderr)
        return 130
    except (ValueError, OSError, KeyError, TypeError, AttributeError,
            subprocess.SubprocessError, json.JSONDecodeError) as exc:
        detalhe = getattr(exc, "stderr", None)
        print(json.dumps({"erro": f"{type(exc).__name__}: {exc}",
                          "detalhe": detalhe[-500:] if detalhe else None}, ensure_ascii=False),
              file=sys.stderr)
        return 2
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
