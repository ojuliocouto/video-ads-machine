#!/usr/bin/env bash
# scripts/dev/como_aluno.sh
#
# Roda um comando COMO o aluno roda num clone limpo: ambiente vazio (env -i), HOME falso, PATH só do sistema e do
# Homebrew (sem ~/.local/bin, onde mora ferramenta do dono), sem CLAUDE_CONFIG_DIR. Repassa só as três variáveis que
# o aluno teria definido: HEYGEN_API_KEY, GROQ_API_KEY e HF_HOME (o cache do modelo público de transcrição, declarado no
# laudo para não baixar cerca de 1 GB de novo).
#
#   VAM_HOME_ALUNO=<pasta> bash scripts/dev/como_aluno.sh bash setup.sh
#   VAM_HOME_ALUNO=<pasta> bash scripts/dev/como_aluno.sh python3 scripts/vam.py doctor
#
# Sem VAM_HOME_ALUNO o script recusa (saída 2): HOME falso é o ponto do teste, e cair no HOME real esconderia
# exatamente o que ele existe para pegar. Compatível com o bash 3.2 do macOS.

if [ -z "${VAM_HOME_ALUNO:-}" ] || [ ! -d "${VAM_HOME_ALUNO}" ]; then
    echo "[como_aluno] ERRO: defina VAM_HOME_ALUNO apontando para uma pasta que existe (o HOME falso do aluno)."
    exit 2
fi
if [ "$#" = 0 ]; then
    echo "[como_aluno] uso: VAM_HOME_ALUNO=<pasta> bash scripts/dev/como_aluno.sh <comando> [argumentos]"
    exit 2
fi

REPASSA=()
for nome in HEYGEN_API_KEY GROQ_API_KEY HF_HOME; do
    valor="$(printenv "$nome")"
    [ -n "$valor" ] && REPASSA+=("$nome=$valor")
done

exec env -i \
    HOME="$VAM_HOME_ALUNO" \
    PATH="/opt/homebrew/bin:/usr/bin:/bin:/usr/local/bin" \
    LANG="${LANG:-pt_BR.UTF-8}" \
    TERM="${TERM:-xterm}" \
    TMPDIR="${TMPDIR:-/tmp}" \
    ${REPASSA[@]+"${REPASSA[@]}"} \
    "$@"
