#!/usr/bin/env bash
# Deixa a skill /esteira-bootstrap disponível em qualquer projeto: liga
# .claude/skills/esteira-bootstrap deste repositório em ~/.claude/skills/.
# É um link: um `git pull` aqui atualiza a skill, e rodar o bootstrap de novo
# num projeto atualiza o que foi instalado nele.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
dest=${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills
mkdir -p "$dest"
if [[ -e $dest/esteira-bootstrap && ! -L $dest/esteira-bootstrap ]]; then
  echo "já existe $dest/esteira-bootstrap e não é um link desta instalação; remova-o antes" >&2
  exit 1
fi
ln -sfn "$here/.claude/skills/esteira-bootstrap" "$dest/esteira-bootstrap"
echo "ok: /esteira-bootstrap disponível ($dest/esteira-bootstrap -> $here/.claude/skills/esteira-bootstrap)"
echo
echo "Próximo passo: abra o Herdr, entre na pasta do seu projeto, rode 'claude' e chame /esteira-bootstrap."
