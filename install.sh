#!/usr/bin/env bash
# Copia as skills da esteira para o .claude/skills do projeto.
#
#   install.sh [--sobrescrever] [pasta-do-projeto]      padrão: a pasta atual
#
# A pasta do projeto é onde você abre o Claude Code para trabalhar: a raiz do
# repositório ou, num monorepo, a subpasta do projeto (ou a raiz do monorepo,
# se a esteira for cuidar dele inteiro). Só as pastas esteira-* são copiadas;
# nenhuma outra skill é tocada. O commit instalado fica em
# .claude/esteira-versao.json, que a skill esteira-atualizar usa como base.
#
# Com a esteira já instalada, nada é sobrescrito: só a skill esteira-atualizar
# é copiada, se faltar, e quem atualiza é ela (/esteira-atualizar), preservando
# as mudanças feitas no projeto. --sobrescrever troca tudo pelas skills novas,
# como numa instalação limpa (o config.json e os hooks de .claude/esteira/ ficam).
set -euo pipefail
force=0
[[ ${1:-} == --sobrescrever ]] && { force=1; shift; }
here=$(cd "$(dirname "$0")" && pwd)
dest=$(cd "${1:-.}" && pwd)
git -C "$dest" rev-parse --show-toplevel >/dev/null 2>&1 || { echo "$dest não está dentro de um repositório git" >&2; exit 1; }
[[ $dest == "$here" ]] && { echo "rode a partir da pasta do seu projeto, não do clone da esteira" >&2; exit 1; }
mkdir -p "$dest/.claude/skills"
if (( ! force )) && compgen -G "$dest/.claude/skills/esteira-*/SKILL.md" >/dev/null; then
  if [[ ! -d $dest/.claude/skills/esteira-atualizar ]]; then
    cp -r "$here/skills/esteira-atualizar" "$dest/.claude/skills/esteira-atualizar"
    echo "  .claude/skills/esteira-atualizar"
  fi
  echo
  echo "A esteira já está instalada aqui: nada foi sobrescrito. Para atualizar sem perder as suas"
  echo "mudanças, chame /esteira-atualizar no Claude (abra-o de novo se a skill acabou de chegar)."
  echo "Para trocar tudo pelas skills novas, rode de novo com --sobrescrever."
  exit 0
fi
for skill in "$here"/skills/esteira-*/; do
  name=$(basename "$skill")
  rm -rf "$dest/.claude/skills/$name"
  cp -r "$skill" "$dest/.claude/skills/$name"
  echo "  .claude/skills/$name"
done
commit=$(git -C "$here" rev-parse HEAD)
repo=$(git -C "$here" remote get-url origin 2>/dev/null || echo https://github.com/guilhermefeitosa66/esteira.git)
repo=$(sed -E 's#^git@github\.com:#https://github.com/#' <<<"$repo")   # https: quem atualiza não precisa de chave
printf '{\n "repositorio": "%s",\n "branch": "main",\n "commit": "%s",\n "atualizado_em": "%s"\n}\n' \
  "$repo" "$commit" "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)" > "$dest/.claude/esteira-versao.json"
echo "  .claude/esteira-versao.json (${commit:0:7})"
if [[ -f $dest/.claude/esteira/config.json ]]; then
  (cd "$dest" && python3 .claude/skills/esteira-bootstrap/scripts/esteira.py install >/dev/null) \
    && echo "  .claude/esteira/ atualizado (config.json preservado)"
  echo
  echo "Atualizado. Loops já de pé continuam com o código antigo até reiniciar: feche a aba 1 dos spaces e rode /esteira-up."
else
  echo
  echo "Pronto. Agora, dentro do Herdr, nesta pasta: rode 'claude' e chame /esteira-bootstrap"
fi
