#!/usr/bin/env bash
# scripts/dev/testar_limpo.sh
#
# Roda a suite como um clone limpo roda: HOME temporário e vazio, nenhuma variável VAM_*
# herdada, sem depender de nada que o `setup.sh` gera. É o comando de verificação de toda
# unidade de trabalho e do CI.
#
#   bash scripts/dev/testar_limpo.sh               testes rápidos (sem lento, midia_real, rede)
#   bash scripts/dev/testar_limpo.sh --lento       inclui os marcados `lento`
#   bash scripts/dev/testar_limpo.sh --paridade    só os `midia_real` (exige VAM_PARIDADE_MIDIA)
#   bash scripts/dev/testar_limpo.sh --tudo        tudo menos `rede` (exige VAM_PARIDADE_MIDIA)
#   bash scripts/dev/testar_limpo.sh --dry-run     mostra o ambiente e o comando, sem rodar
#   bash scripts/dev/testar_limpo.sh -k som -x     o que sobrar vai direto para o pytest
#
# `rede` (API paga ou rede) nunca roda por aqui: chame `python3 -m pytest -m rede` à mão.
#
# Python: o primeiro que roda E já tem o pytest e o numpy, nesta ordem: o `.venv` do repo (Scripts/python.exe no
# Windows, bin/python nos outros), o python3 e o python do PATH, o `py -3` e, fora do Windows, o /usr/bin/python3.
# Nenhum com as dependências: o primeiro que roda. `VAM_PYTHON_TESTE=<python>` força um Python. O user
# site REAL (onde o pytest costuma morar) é descoberto pela pasta pessoal real, não pelo $HOME, então funciona
# até se quem chamou já exportou um HOME falso.
#
# Windows (Git Bash, Python do Windows): o atalho do Python da Microsoft Store é recusado; HOME e USERPROFILE vão
# para a pasta temporária e o Python roda em UTF-8 (PYTHONUTF8=1).
# Sem pytest em lugar nenhum, cai no unittest e AVISA (os marcadores e as fixtures do
# conftest só existem no pytest).
#
# Compatível com macOS/bash 3.2: sem `declare -A`, sem `timeout`, sem `set -u` (array vazio).

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$RAIZ" || { echo "[testar_limpo] ERRO: não consegui entrar em $RAIZ"; exit 1; }

LENTO=0; PARIDADE=0; TUDO=0; DRY=0
EXTRAS=()
for arg in "$@"; do
    case "$arg" in
        --lento)    LENTO=1 ;;
        --paridade) PARIDADE=1 ;;
        --tudo)     TUDO=1 ;;
        --dry-run)  DRY=1 ;;
        -h|--ajuda|--help)
            sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *)          EXTRAS+=("$arg") ;;
    esac
done

# --- 1. qual marcador seleciona o quê ---------------------------------------------------
# MARCADOR_TXT é o que se mostra; MARCADOR é o argumento do pytest ("" = sem filtro).
PRECISA_MIDIA=0
if [ "$TUDO" = 1 ]; then
    MARCADOR="not rede"; PRECISA_MIDIA=1
elif [ "$PARIDADE" = 1 ]; then
    MARCADOR="midia_real"; PRECISA_MIDIA=1
elif [ "$LENTO" = 1 ]; then
    MARCADOR="not midia_real and not rede"
else
    MARCADOR="not lento and not midia_real and not rede"
fi

if [ "$PRECISA_MIDIA" = 1 ]; then
    if [ -z "${VAM_PARIDADE_MIDIA:-}" ] || [ ! -d "${VAM_PARIDADE_MIDIA:-}" ]; then
        echo "[testar_limpo] ERRO: --paridade e --tudo precisam de VAM_PARIDADE_MIDIA apontando"
        echo "[testar_limpo] para a pasta com a mídia de paridade (ela nunca entra no repo)."
        echo "[testar_limpo] Exemplo: VAM_PARIDADE_MIDIA=/caminho/da/pasta bash scripts/dev/testar_limpo.sh --paridade"
        exit 2
    fi
fi

# --- 2. qual Python ----------------------------------------------------------------------
eh_windows() {
    case "$(uname -s 2>/dev/null)" in
        MINGW*|MSYS*|CYGWIN*) return 0 ;;
    esac
    return 1
}

# O Python da Microsoft Store (WindowsApps\python3.exe) é um atalho que abre a Store em vez de rodar Python.
# Vale o comando que sai 0 em `-c "import sys"` e que não mora em WindowsApps.
python_de_verdade() {
    case "$1" in *[Ww]indows[Aa]pps*) return 1 ;; esac
    [ -n "$1" ] && "$1" -c 'import sys' >/dev/null 2>&1
}

# A pasta pessoal REAL, sem confiar no $HOME de quem chamou (pode já ser um HOME falso) e sem módulo de usuários do
# Python: no Windows é o USERPROFILE; nos outros, o `~usuário` que o bash resolve pelo cadastro do sistema.
home_real() {
    local usuario destino
    if eh_windows; then
        echo "${USERPROFILE:-$HOME}"
        return
    fi
    usuario="$(id -un 2>/dev/null)"
    case "$usuario" in
        ''|*[!A-Za-z0-9._-]*) echo "$HOME"; return ;;
    esac
    destino="$(eval echo "~$usuario" 2>/dev/null)"
    if [ -d "$destino" ]; then echo "$destino"; else echo "$HOME"; fi
}
HOME_REAL="$(home_real)"

# O `py -3` (launcher do Windows) devolve o caminho do Python real em sys.executable.
caminho_do_py_launcher() {
    local launcher caminho
    launcher="$(command -v py 2>/dev/null)"
    [ -n "$launcher" ] || return 1
    caminho="$("$launcher" -3 -c 'import sys; print(sys.executable)' 2>/dev/null | tr -d '\r')"
    [ -n "$caminho" ] && [ -e "$caminho" ] && echo "$caminho"
}

# Os candidatos, um por linha, na ordem de preferência: o .venv do repo, o python3 e o python do PATH, o `py -3`
# e, fora do Windows, o python3 do sistema como último recurso. Nunca um caminho fixo como única opção.
candidatos_python() {
    local c
    [ -f "$RAIZ/.venv/Scripts/python.exe" ] && echo "$RAIZ/.venv/Scripts/python.exe"
    [ -x "$RAIZ/.venv/bin/python" ] && echo "$RAIZ/.venv/bin/python"
    for c in python3 python; do
        command -v "$c" 2>/dev/null
    done
    caminho_do_py_launcher
    if ! eh_windows && [ -x /usr/bin/python3 ]; then echo /usr/bin/python3; fi
    return 0
}

# O escolhido é o primeiro candidato que roda E já tem o pytest e as dependências do motor (numpy). Nenhum tendo, fica o
# primeiro que roda (e o script avisa que cai no unittest). VAM_PYTHON_TESTE força um Python e dispensa a escolha.
# Imprime "caminho|origem"; sai 1 se nenhum roda.
escolher_python_de_teste() {
    local c primeiro=""
    if [ -n "${VAM_PYTHON_TESTE:-}" ]; then
        python_de_verdade "$VAM_PYTHON_TESTE" || return 1
        echo "$VAM_PYTHON_TESTE|VAM_PYTHON_TESTE"
        return 0
    fi
    while IFS= read -r c; do
        python_de_verdade "$c" || continue
        [ -z "$primeiro" ] && primeiro="$c"
        if HOME="$HOME_REAL" "$c" -c 'import pytest, numpy' >/dev/null 2>&1; then
            echo "$c|com pytest e dependências"
            return 0
        fi
    done < <(candidatos_python)
    [ -n "$primeiro" ] && { echo "$primeiro|sem pytest ou dependências"; return 0; }
    return 1
}

ESCOLHA="$(escolher_python_de_teste)"
PY="${ESCOLHA%%|*}"
ORIGEM="${ESCOLHA#*|}"
case "$PY" in
    "$RAIZ"/.venv/*) ORIGEM=".venv do repo" ;;
esac
if [ -z "$PY" ]; then
    if [ -n "${VAM_PYTHON_TESTE:-}" ]; then
        echo "[testar_limpo] ERRO: VAM_PYTHON_TESTE ($VAM_PYTHON_TESTE) não roda."
    elif eh_windows; then
        echo "[testar_limpo] ERRO: nenhum Python encontrado (o atalho da Microsoft Store não conta)."
        echo "[testar_limpo] Instale: winget install -e --id Python.Python.3.12 (e feche e abra o terminal)."
    else
        echo "[testar_limpo] ERRO: nenhum python3 encontrado. Instale o Python 3.9 ou superior."
    fi
    exit 1
fi

# user site real, calculado ANTES de trocar o HOME e sem confiar no $HOME de quem chamou
if [ -z "${PYTHONUSERBASE:-}" ]; then
    PYTHONUSERBASE="$(HOME="$HOME_REAL" USERPROFILE="$HOME_REAL" "$PY" -m site --user-base 2>/dev/null | tr -d '\r')"
fi
export PYTHONUSERBASE

# --- 3. ambiente hermético ---------------------------------------------------------------
# Pasta temporária: mktemp com o TMPDIR; se falhar, o mktemp -d puro; se falhar, o $TEMP (Windows).
HOME_FALSO="$(mktemp -d "$(dirname "${TMPDIR:-/tmp}/x")/vam-home.XXXXXX" 2>/dev/null)"
[ -d "$HOME_FALSO" ] || HOME_FALSO="$(mktemp -d 2>/dev/null)"
if [ ! -d "$HOME_FALSO" ] && [ -n "${TEMP:-}" ] && [ -d "$TEMP" ]; then
    HOME_FALSO="$(mktemp -d "$TEMP/vam-home.XXXXXX" 2>/dev/null)"
fi
if [ -z "$HOME_FALSO" ] || [ ! -d "$HOME_FALSO" ]; then
    echo "[testar_limpo] ERRO: mktemp não criou o HOME temporário."
    exit 1
fi
trap 'rm -rf "$HOME_FALSO"' EXIT
# No Windows o Python lê o USERPROFILE (o HOME ele ignora), então os dois apontam para a pasta temporária, no
# formato C:/pasta que o Git Bash e o Python entendem (cygpath existe só no Git Bash).
HOME_EXPORTADO="$HOME_FALSO"
if command -v cygpath >/dev/null 2>&1; then
    HOME_EXPORTADO="$(cygpath -m "$HOME_FALSO" 2>/dev/null || echo "$HOME_FALSO")"
fi
export HOME="$HOME_EXPORTADO"
export USERPROFILE="$HOME_EXPORTADO"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1

REMOVIDAS=""
for nome in $(env | cut -d= -f1 | grep '^VAM_'); do
    [ "$nome" = "VAM_PARIDADE_MIDIA" ] && continue
    REMOVIDAS="$REMOVIDAS $nome"
    unset "$nome"
done

# --- 4. pytest ou fallback ---------------------------------------------------------------
PY_VERSAO="$("$PY" --version 2>&1)"
if "$PY" -c 'import pytest' >/dev/null 2>&1; then
    RUNNER="pytest $("$PY" -c 'import pytest; print(pytest.__version__)')"
    USA_PYTEST=1
else
    RUNNER="unittest (FALLBACK: pytest indisponível em $PY; instale com: $PY -m pip install pytest)"
    USA_PYTEST=0
fi

echo "[testar_limpo] raiz:    $RAIZ"
echo "[testar_limpo] python:  $PY ($PY_VERSAO, origem: $ORIGEM)"
echo "[testar_limpo] runner:  $RUNNER"
echo "[testar_limpo] VAM_* herdadas e removidas:${REMOVIDAS:- nenhuma}"
echo "HOME=$HOME"
echo "USERPROFILE=$USERPROFILE"
echo "PYTHONUTF8=$PYTHONUTF8"
echo "PYTHONUSERBASE=$PYTHONUSERBASE"

if [ "$MARCADOR" = "midia_real" ]; then
    SELECAO="-m midia_real"
else
    SELECAO="-m \"$MARCADOR\""
fi
echo "seleção: $SELECAO"

if [ "$USA_PYTEST" = 1 ]; then
    echo "comando: $PY -m pytest $SELECAO ${EXTRAS[*]}"
else
    echo "AVISO: sem pytest, os marcadores (lento, midia_real, rede) e as fixtures do conftest"
    echo "AVISO: não existem; o unittest roda só as classes TestCase e ignora a seleção acima."
    echo "comando: $PY -m unittest discover -s scripts + -s tests"
fi

if [ "$DRY" = 1 ]; then
    exit 0
fi

if [ "$USA_PYTEST" != 1 ] && { [ "$PARIDADE" = 1 ] || [ "$TUDO" = 1 ]; }; then
    echo "[testar_limpo] ERRO: --paridade e --tudo exigem pytest."
    exit 2
fi

# --- 5. roda -----------------------------------------------------------------------------
if [ "$USA_PYTEST" = 1 ]; then
    "$PY" -m pytest -m "$MARCADOR" ${EXTRAS[@]+"${EXTRAS[@]}"}
    exit $?
fi

"$PY" -m unittest discover -s scripts -p 'test_*.py' -t scripts ${EXTRAS[@]+"${EXTRAS[@]}"}
RC1=$?
"$PY" -m unittest discover -s tests -p 'test_*.py' -t . ${EXTRAS[@]+"${EXTRAS[@]}"}
RC2=$?
if [ "$RC1" -ne 0 ] || [ "$RC2" -ne 0 ]; then
    exit 1
fi
exit 0
