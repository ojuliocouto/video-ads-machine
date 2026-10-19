#!/usr/bin/env bash
# scripts/dev/como_aluno.sh
#
# Roda um comando COMO o aluno roda num clone limpo: ambiente vazio (env -i), HOME falso, PATH só do sistema e do
# Homebrew (sem ~/.local/bin, onde mora ferramenta do dono), sem CLAUDE_CONFIG_DIR. Repassa só as três variáveis que
# o aluno teria definido: HEYGEN_API_KEY, GROQ_API_KEY e HF_HOME (o cache do modelo público de transcrição, declarado no
# laudo para não baixar cerca de 1 GB de novo).
#
# No Git Bash do Windows o `env -i` quebraria tudo (sem SystemRoot, TEMP e PATH o Python e o Node nem sobem) e o PATH do
# Homebrew não existe. Lá o ambiente é mantido, com HOME e USERPROFILE no HOME falso e sem o que é do dono: variáveis
# VAM_*, CLAUDE*, ANTHROPIC*, chaves e tokens de API (menos as três do aluno), PYTHONPATH/VIRTUAL_ENV e as pastas
# `.local/bin` do PATH.
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

eh_windows() {
    case "$(uname -s 2>/dev/null)" in
        MINGW*|MSYS*|CYGWIN*) return 0 ;;
    esac
    return 1
}

if eh_windows; then
    # Quais variáveis saem do ambiente: as do dono, nunca as três que o aluno teria.
    REMOVER=()
    while IFS= read -r nome; do
        case "$nome" in
            HEYGEN_API_KEY|GROQ_API_KEY|HF_HOME|VAM_HOME_ALUNO) continue ;;
            VAM_*|CLAUDE*|ANTHROPIC*|PYTHONPATH|PYTHONHOME|VIRTUAL_ENV|*_API_KEY|*_TOKEN|*_SECRET)
                REMOVER+=("-u" "$nome") ;;
        esac
    done < <(env | cut -d= -f1)
    # PATH sem as pastas .local/bin (ferramenta do dono), separador ':' do Git Bash.
    PATH_ALUNO=""
    IFS=':' read -r -a PARTES <<< "$PATH"
    for parte in "${PARTES[@]}"; do
        case "$parte" in */.local/bin|*/.local/bin/) continue ;; esac
        PATH_ALUNO="${PATH_ALUNO:+$PATH_ALUNO:}$parte"
    done
    # O Python do Windows lê o USERPROFILE, no formato C:/pasta (cygpath existe só no Git Bash).
    PERFIL="$VAM_HOME_ALUNO"
    if command -v cygpath >/dev/null 2>&1; then PERFIL="$(cygpath -m "$VAM_HOME_ALUNO" 2>/dev/null || echo "$VAM_HOME_ALUNO")"; fi
    exec env ${REMOVER[@]+"${REMOVER[@]}"} \
        HOME="$PERFIL" \
        USERPROFILE="$PERFIL" \
        PATH="$PATH_ALUNO" \
        "$@"
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
