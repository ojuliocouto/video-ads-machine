#!/usr/bin/env bash
# scripts/setup.sh
#
# Bootstrap idempotente do HyperFrames para o video-ads-machine-2 (Task 1.5,
# ver PLAN.md e DESIGN.md seção 8). Cada passo só faz o que ainda falta:
# rodar de novo depois que tudo já está pronto é um no-op (além de reconferir).
#
# Compatível com macOS/bash 3.2: sem `declare -A`, sem `timeout`. NÃO usa
# `set -e`: cada passo trata o próprio erro e decide se aborta ou só avisa,
# nunca quebra o script inteiro no meio de um passo que não é crítico.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || { echo "[setup] ERRO: não consegui entrar em $REPO_ROOT"; exit 1; }

echo "[setup] iniciando bootstrap do HyperFrames em $REPO_ROOT"

# --- 1. CLI do hyperframes acessível? (local em ./node_modules/.bin ou global) ---
HF_BIN=""

if [ -x "./node_modules/.bin/hyperframes" ]; then
    HF_BIN="./node_modules/.bin/hyperframes"
    echo "[setup] hyperframes já instalado localmente (node_modules/.bin). Pulando npm i."
elif command -v hyperframes >/dev/null 2>&1; then
    HF_BIN="hyperframes"
    echo "[setup] hyperframes encontrado global no PATH. Pulando npm i."
else
    echo "[setup] hyperframes não encontrado (nem local, nem global)."
    echo "[setup] rodando 'npm i' (versão pinada em package.json)..."
    npm i
    if [ $? -ne 0 ]; then
        echo "[setup] ERRO: 'npm i' falhou. Abortando o restante do setup até isso ser corrigido."
        exit 1
    fi
    if [ -x "./node_modules/.bin/hyperframes" ]; then
        HF_BIN="./node_modules/.bin/hyperframes"
        echo "[setup] hyperframes instalado com sucesso em node_modules/.bin."
    else
        echo "[setup] ERRO: 'npm i' rodou sem erro mas node_modules/.bin/hyperframes não apareceu."
        exit 1
    fi
fi

# --- 2. hyperframes doctor (confere Node, ffmpeg, Chrome/Chromium) ---
echo "[setup] rodando '$HF_BIN doctor'..."
"$HF_BIN" doctor
if [ $? -ne 0 ]; then
    echo "[setup] AVISO: 'hyperframes doctor' voltou com erro. Revise a saída acima antes de renderizar."
else
    echo "[setup] doctor OK."
fi

# --- 3. Chromium do render, se faltar. ---
# Nota: o subcommand real desta versão pinada (0.7.56) é 'browser ensure'
# (encontra ou baixa o Chrome), não 'browser install'. 'ensure' já é
# idempotente por si: se o Chrome já estiver em cache, só confirma o path.
echo "[setup] checando/baixando o browser do render ('$HF_BIN browser ensure')..."
"$HF_BIN" browser ensure
if [ $? -ne 0 ]; then
    echo "[setup] AVISO: 'hyperframes browser ensure' voltou com erro. Render pode falhar sem o Chromium."
else
    echo "[setup] browser ensure OK."
fi

# --- 4. hyperframes skills (instala as skills de autoria pros agentes de IA) ---
echo "[setup] instalando as skills de autoria ('$HF_BIN skills')..."
"$HF_BIN" skills
if [ $? -ne 0 ]; then
    echo "[setup] AVISO: 'hyperframes skills' voltou com erro."
else
    echo "[setup] skills OK."
fi

echo "[setup] bootstrap concluído."
