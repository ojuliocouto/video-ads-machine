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
# Python: o `.venv` do repo se existir; senão /usr/bin/python3 (o do macOS, 3.9) com o user
# site REAL, onde o pytest costuma morar. O user site é descoberto pelo HOME real (pwd), não
# pelo $HOME, então funciona até se quem chamou já exportou um HOME falso.
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
if [ -x "$RAIZ/.venv/bin/python" ]; then
    PY="$RAIZ/.venv/bin/python"; ORIGEM=".venv do repo"
elif [ -x /usr/bin/python3 ]; then
    PY=/usr/bin/python3; ORIGEM="sistema"
else
    PY="$(command -v python3)"; ORIGEM="PATH"
fi
if [ -z "$PY" ] || [ ! -x "$PY" ]; then
    echo "[testar_limpo] ERRO: nenhum python3 encontrado. Instale o Python 3.9 ou superior."
    exit 1
fi

# user site real, calculado ANTES de trocar o HOME e sem confiar no $HOME de quem chamou
if [ -z "${PYTHONUSERBASE:-}" ]; then
    HOME_REAL="$("$PY" -c 'import os, pwd; print(pwd.getpwuid(os.getuid()).pw_dir)' 2>/dev/null)"
    [ -z "$HOME_REAL" ] && HOME_REAL="$HOME"
    PYTHONUSERBASE="$(HOME="$HOME_REAL" "$PY" -m site --user-base 2>/dev/null)"
fi
export PYTHONUSERBASE

# --- 3. ambiente hermético ---------------------------------------------------------------
HOME_FALSO="$(mktemp -d "$(dirname "${TMPDIR:-/tmp}/x")/vam-home.XXXXXX")"
if [ -z "$HOME_FALSO" ] || [ ! -d "$HOME_FALSO" ]; then
    echo "[testar_limpo] ERRO: mktemp não criou o HOME temporário."
    exit 1
fi
trap 'rm -rf "$HOME_FALSO"' EXIT
export HOME="$HOME_FALSO"
export PYTHONDONTWRITEBYTECODE=1

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
echo "HOME=$HOME_FALSO"
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
