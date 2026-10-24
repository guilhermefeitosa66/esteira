#!/usr/bin/env bash
# Sobe o display próprio da rodada (Xephyr) e, nele, um Chrome LIMPO controlado por CDP: perfil novo e
# descartável, sem extensões, sem tradução, sem "salvar senha", sem notificação, sem restaurar sessão,
# sem chaveiro do sistema. Nada pode surgir por cima dos componentes durante os CTs ou o vídeo.
#
#   chrome-limpo.sh subir  <pasta-da-rodada> <url-inicial> [LARGURAxALTURA]
#   chrome-limpo.sh descer <pasta-da-rodada>
#
# `subir` escolhe display e porta livres, grava tudo em <rodada>/work/navegador.env (QA_DISPLAY, CDP,
# PIDs) e só retorna depois de o CDP responder. `descer` mata só o que este script subiu e apaga o perfil.
set -euo pipefail

acao=${1:?uso: chrome-limpo.sh subir|descer <pasta-da-rodada> [url] [geometria]}
run=$(realpath "${2:?informe a pasta da rodada}")
w=$run/work
envf=$w/navegador.env

if [[ $acao == descer ]]; then
  [[ -f $envf ]] || { echo "nada a descer: $envf não existe"; exit 0; }
  source "$envf"
  kill "$CHROME_PID" 2>/dev/null || true
  sleep 1
  kill "$XEPHYR_PID" 2>/dev/null || true
  rm -rf "$w/chrome" "$envf"
  echo "{\"descido\": \"$QA_DISPLAY\", \"cdp\": \"$CDP\"}"
  exit 0
fi

url=${3:?informe a URL inicial}
chrome=${CHROME:-$(command -v google-chrome || command -v chromium || command -v chromium-browser || true)}
[[ -n $chrome ]] || { echo "nem google-chrome nem chromium no PATH (ou defina CHROME)" >&2; exit 1; }
geo=${4:-1440x900}
[[ -f $envf ]] && { echo "já existe navegador desta rodada ($envf): rode 'descer' antes" >&2; exit 1; }
mkdir -p "$w"

n=90; while [[ -e /tmp/.X11-unix/X$n || -e /tmp/.X$n-lock ]]; do n=$((n + 1)); done
porta=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')

Xephyr ":$n" -screen "$geo" -nolisten tcp -ac -title "QA BOT :$n" > "$w/xephyr.log" 2>&1 &
xephyr_pid=$!
for _ in $(seq 50); do xdpyinfo -display ":$n" > /dev/null 2>&1 && break; sleep 0.1; done

# Preferências do perfil novo: tradução, senhas, autofill, notificações e restauração desligadas;
# português como idioma aceito (a página em pt-BR não "parece estrangeira" ao Chrome).
mkdir -p "$w/chrome/Default"
cat > "$w/chrome/Default/Preferences" <<'JSON'
{
  "translate": {"enabled": false},
  "translate_blocked_languages": ["pt", "pt-BR", "en"],
  "intl": {"accept_languages": "pt-BR,pt"},
  "credentials_enable_service": false,
  "credentials_enable_autosignin": false,
  "profile": {
    "password_manager_enabled": false,
    "default_content_setting_values": {"notifications": 2, "geolocation": 2},
    "exit_type": "Normal",
    "exited_cleanly": true
  },
  "autofill": {"profile_enabled": false, "credit_card_enabled": false},
  "browser": {"check_default_browser": false},
  "session": {"restore_on_startup": 1}
}
JSON

DISPLAY=":$n" "$chrome" \
  --user-data-dir="$w/chrome" --remote-debugging-port="$porta" \
  --kiosk --window-position=0,0 --window-size="${geo/x/,}" \
  --lang=pt-BR --accept-lang=pt-BR,pt \
  --disable-extensions --disable-component-extensions-with-background-pages \
  --disable-features=Translate,TranslateUI,PasswordManagerOnboarding,AutofillServerCommunication,MediaRouter,OptimizationHints \
  --disable-translate --disable-notifications --deny-permission-prompts \
  --disable-sync --disable-default-apps --disable-background-networking \
  --disable-session-crashed-bubble --hide-crash-restore-bubble --noerrdialogs \
  --disable-search-engine-choice-screen --no-first-run --no-default-browser-check \
  --password-store=basic --test-type \
  "$url" > "$w/chrome.log" 2>&1 &
chrome_pid=$!

for _ in $(seq 100); do curl -sf "http://127.0.0.1:$porta/json/version" > /dev/null && break; sleep 0.1; done
curl -sf "http://127.0.0.1:$porta/json/version" > /dev/null || { kill $chrome_pid $xephyr_pid 2>/dev/null; echo "Chrome não respondeu no CDP; veja $w/chrome.log" >&2; exit 1; }

cat > "$envf" <<EOF
QA_DISPLAY=:$n
CDP=http://127.0.0.1:$porta
CHROME_PID=$chrome_pid
XEPHYR_PID=$xephyr_pid
GEOMETRIA=$geo
EOF
echo "{\"display\": \":$n\", \"cdp\": \"http://127.0.0.1:$porta\", \"geometria\": \"$geo\", \"env\": \"$envf\"}"
