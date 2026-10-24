#!/usr/bin/env bash
# Copia as skills da esteira para o .claude/skills do projeto.
#
#   install.sh [pasta-do-projeto]      padrão: a pasta atual
#
# A pasta do projeto é onde você abre o Claude Code para trabalhar: a raiz do
# repositório ou, num monorepo, a subpasta do projeto (ou a raiz do monorepo,
# se a esteira for cuidar dele inteiro). Só as pastas esteira-* são
# substituídas; nenhuma outra skill é tocada. Rodar de novo atualiza: as skills
# são trocadas pelas novas e, se a esteira já estiver configurada no projeto, os
# scripts de .claude/esteira/ também (o config.json e os hooks ficam).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
dest=$(cd "${1:-.}" && pwd)
git -C "$dest" rev-parse --show-toplevel >/dev/null 2>&1 || { echo "$dest não está dentro de um repositório git" >&2; exit 1; }
[[ $dest == "$here" ]] && { echo "rode a partir da pasta do seu projeto, não do clone da esteira" >&2; exit 1; }
mkdir -p "$dest/.claude/skills"
for skill in "$here"/skills/esteira-*/; do
  name=$(basename "$skill")
  rm -rf "$dest/.claude/skills/$name"
  cp -r "$skill" "$dest/.claude/skills/$name"
  echo "  .claude/skills/$name"
done
if [[ -f $dest/.claude/esteira/config.json ]]; then
  (cd "$dest" && python3 .claude/skills/esteira-bootstrap/scripts/esteira.py install >/dev/null) \
    && echo "  .claude/esteira/ atualizado (config.json preservado)"
  echo
  echo "Atualizado. Loops já de pé continuam com o código antigo até reiniciar: feche a aba 1 dos spaces e rode /esteira-up."
else
  echo
  echo "Pronto. Agora, dentro do Herdr, nesta pasta: rode 'claude' e chame /esteira-bootstrap"
fi
