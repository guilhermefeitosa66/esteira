#!/usr/bin/env bash
# Ferramentas do vídeo narrado do QA (display próprio, navegador limpo, voz offline, palco de API).
#   preparar-video.sh verificar              o que falta na máquina (sai 1 se faltar algo obrigatório)
#   preparar-video.sh instalar               baixa o que não pede sudo (modelos de voz) e mostra o resto
#   preparar-video.sh pasta <gravação>/work  instala o playwright-core da gravação
#   preparar-video.sh teste                  ensaio do palco de API com o exemplo da skill, sem câmera
set -uo pipefail

SK=$(cd "$(dirname "$0")/.." && pwd)
VOZES=${QA_BOT_VOZES:-${XDG_DATA_HOME:-$HOME/.local/share}}/kokoro
KOKORO_URL=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
APT="sudo apt install -y ffmpeg xserver-xephyr x11-utils xdotool nodejs npm python3"
DNF="sudo dnf install -y ffmpeg xorg-x11-server-Xephyr xdpyinfo xdotool nodejs npm python3"

tem () { command -v "$1" > /dev/null 2>&1; }
falta=0
linha () { printf '%-5s %-18s %s\n' "$1" "$2" "$3"; }
obrigatorio () { if tem "$1"; then linha ok "$1" "$(command -v "$1")"; else linha FALTA "$1" "$2"; falta=1; fi; }
opcional () { if tem "$1"; then linha ok "$1" "$(command -v "$1")"; else linha --  "$1" "opcional: $2"; fi; }

verificar () {
  obrigatorio ffmpeg "grava e monta o vídeo"
  obrigatorio ffprobe "vem com o ffmpeg"
  obrigatorio Xephyr "display próprio da gravação (xserver-xephyr)"
  obrigatorio xdpyinfo "confere o display (x11-utils)"
  obrigatorio xdotool "move o cursor de verdade"
  obrigatorio node "Node 18+ (palco de API, demo-lib)"
  obrigatorio npm "instala o playwright-core da gravação"
  obrigatorio python3 "Python 3.10+ (qa_video.py)"
  obrigatorio uv "roda o Kokoro sem instalar nada no projeto (curl -LsSf https://astral.sh/uv/install.sh | sh)"
  if tem google-chrome || tem chromium || tem chromium-browser || [[ -n ${CHROME:-} ]]; then
    linha ok chrome "${CHROME:-$(command -v google-chrome || command -v chromium || command -v chromium-browser)}"
  else
    linha FALTA chrome "google-chrome ou chromium (ou CHROME=<binário>)"; falta=1
  fi
  if tem node && (( $(node -p 'process.versions.node.split(".")[0]') < 18 )); then linha FALTA node "versão $(node -v): precisa 18+"; falta=1; fi
  for f in kokoro-v1.0.onnx voices-v1.0.bin; do
    if [[ -s $VOZES/$f ]]; then linha ok "$f" "$VOZES"; else linha FALTA "$f" "voz offline: preparar-video.sh instalar"; falta=1; fi
  done
  opcional adb "cenário Android (platform-tools)"
  return $falta
}

case ${1:-verificar} in
  verificar) verificar; exit $? ;;
  instalar)
    mkdir -p "$VOZES"
    for f in kokoro-v1.0.onnx voices-v1.0.bin; do
      [[ -s $VOZES/$f ]] && continue
      echo "baixando $f para $VOZES"
      curl -fL --retry 3 -o "$VOZES/$f.part" "$KOKORO_URL/$f" && mv "$VOZES/$f.part" "$VOZES/$f"
    done
    tem uv && uv run --quiet --with kokoro-onnx --with soundfile python -c 'import kokoro_onnx' && echo "ambiente do Kokoro em cache"
    echo
    verificar || echo -e "\nO que falta pede sudo; rode você mesmo:\n  Debian/Ubuntu: $APT\n  Fedora:        $DNF\n  (Chrome: https://www.google.com/chrome/ ou o pacote chromium da distro)"
    ;;
  pasta)
    destino=${2:?informe a pasta work da gravação}
    mkdir -p "$destino" && cd "$destino" && npm i --silent --no-audit --no-fund playwright-core@1 && echo "playwright-core em $destino/node_modules"
    ;;
  teste)
    tmp=$(mktemp -d)
    porta=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
    export SENHA_ALVO=senha-de-teste
    node "$SK/assets/exemplo-api/alvo.js" "$porta" "$tmp/alvo.log" > /dev/null &
    alvo=$!
    sleep 0.5
    ALVO=http://127.0.0.1:$porta ALVO_LOG=$tmp/alvo.log node "$SK/scripts/palco-api/servidor.js" ensaio --cenario "$SK/assets/exemplo-api/cenario.json" --pasta "$tmp/api"
    r=$?
    grep -q "$SENHA_ALVO" "$tmp/api/trocas.jsonl" && { echo "VAZOU a senha no trocas.jsonl" >&2; r=1; }
    kill $alvo
    rm -rf "$tmp"
    exit $r
    ;;
  *) sed -n '2,6p' "$0"; exit 2 ;;
esac
