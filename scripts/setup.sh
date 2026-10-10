#!/usr/bin/env bash
# scripts/setup.sh
#
# Prepara a máquina do aluno para o video-ads-machine. Idempotente: cada passo só faz o que
# ainda falta, então rodar de novo com tudo pronto não reinstala nada.
#
#   bash scripts/setup.sh                instala o que falta
#   bash scripts/setup.sh --checar       só relata o que falta; não instala nem cria nada
#   bash scripts/setup.sh --cinema-plus  reservado (ver passo_cinema_plus); hoje não faz nada
#
# O que ele faz, em ordem:
#   1. cria o .venv do repo (o Python do Homebrew recusa `pip install` fora de um ambiente
#      virtual, PEP 668, então NADA vai para o Python do sistema)
#   2. instala o requirements.txt no .venv
#   2b. instala o transcritor no .venv: parakeet-mlx no Apple Silicon, faster-whisper nos outros
#      (sem transcritor o `vam audio` não roda; o doctor dá FAIL)
#   3. confere o Node 22 ou superior
#   4. instala o HyperFrames na versão pinada no package.json (npm install)
#   5. garante o Chromium do render (hyperframes browser ensure)
#   6. guarda uma cópia local do GSAP em templates/_vendor (o render não depende da CDN)
#   7. cria o .env a partir do .env.example, se ainda não existe (nunca sobrescreve)
#   8. prepara a pasta _local/ (init_local.py)
#   9. gera os efeitos sonoros (som_cortes.py)
#  10. roda o `vam doctor`; o resumo só diz "tudo pronto" se ele sair com 0 FAIL
#
# NENHUM passo aborta os seguintes. O que falhar vira uma linha de aviso na hora e entra no
# resumo do fim, com o comando de conserto. Saída: 0 se tudo certo, 1 se algo obrigatório falhou
# (a cópia local do GSAP é opcional e só avisa).
#
# O doctor roda sozinho no fim (passo 10), só quando nenhum passo anterior falhou: com falha pendente
# ele reprovaria pelo mesmo motivo. Para conferir de novo à mão:  python3 scripts/vam.py doctor
#
# Compatível com macOS/bash 3.2: sem arrays associativos, sem mapfile, sem comando de timeout.
# NÃO usa a opção de abortar no primeiro erro: cada passo trata o próprio erro.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || { echo "[setup] ERRO: não consegui entrar em $REPO_ROOT"; exit 1; }

uso() {
    echo "uso: bash scripts/setup.sh [--checar] [--cinema-plus]"
    echo "  (sem argumento)  instala o que falta; rodar de novo não reinstala nada"
    echo "  --checar         só relata o que falta, sem instalar nem criar nada"
    echo "  --cinema-plus    reservado para a camada opcional de matting; hoje não faz nada"
}

CHECAR=0
CINEMA_PLUS=0
for arg in "$@"; do
    case "$arg" in
        --checar)      CHECAR=1 ;;
        --cinema-plus) CINEMA_PLUS=1 ;;
        -h|--ajuda|--help) uso; exit 0 ;;
        *) echo "[setup] argumento desconhecido: $arg"; uso; exit 2 ;;
    esac
done

# --- caminhos e estado -------------------------------------------------------------------------
VENV="$REPO_ROOT/.venv"
VENV_PY="$VENV/bin/python"
SELO="$VENV/.vam-requirements"
SELO_TRANSCRITOR="$VENV/.vam-transcritor"
HF_BIN="$REPO_ROOT/node_modules/.bin/hyperframes"
GSAP_DEST="$REPO_ROOT/templates/_vendor/gsap.min.js"
ESTADO_DIR="${VAM_ESTADO:-$REPO_ROOT/_local}"
SOM_DIR="${VAM_DADOS:-${VAM_V1_HOME:-$ESTADO_DIR/dados}}/assets/som"
PY_SISTEMA="$(command -v python3 2>/dev/null)"
PIN="$(sed -n 's/.*"hyperframes"[[:space:]]*:[[:space:]]*"[~^]*\([0-9][^"]*\)".*/\1/p' package.json 2>/dev/null | head -1)"
NODE_OK=0
HF_OK=0
FALHAS=()
AVISOS=()

nota() { echo "[setup] $*"; }

# problema "o que deu errado" "o comando que resolve". Obrigatório: entra no resumo e no exit 1.
problema() {
    local rotulo="FALHOU"
    [ "$CHECAR" = 1 ] && rotulo="FALTA"
    FALHAS[${#FALHAS[@]}]="$1|$2"
    echo "[setup] $rotulo: $1"
    echo "[setup]   conserto: $2"
}

# aviso "o que houve" "o comando que resolve". Opcional: entra no resumo, não muda o exit.
aviso() {
    AVISOS[${#AVISOS[@]}]="$1|$2"
    echo "[setup] AVISO: $1"
    echo "[setup]   conserto: $2"
}

venv_ok() { [ -x "$VENV_PY" ]; }

# Pasta gerada pelo setup que o git não pode enxergar. Um .gitignore com `*` dentro dela se
# ignora a si mesmo, então não sobra nada para um `git add` pegar (o .gitignore da raiz não
# cobre .venv nem templates/_vendor).
esconder_do_git() {
    [ -d "$1" ] && [ ! -f "$1/.gitignore" ] && echo '*' > "$1/.gitignore"
    return 0
}

# --- 1. .venv ------------------------------------------------------------------------------------
passo_venv() {
    if venv_ok; then
        nota ".venv já existe. Pulando."
        return 0
    fi
    if [ "$CHECAR" = 1 ]; then
        problema ".venv não existe (as dependências Python moram nele)" "bash scripts/setup.sh"
        return 1
    fi
    if [ -z "$PY_SISTEMA" ]; then
        problema "python3 não encontrado no PATH" "instale o Python 3.9 ou superior (macOS: brew install python@3.12) e rode bash scripts/setup.sh"
        return 1
    fi
    if ! "$PY_SISTEMA" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
        problema "o python3 do sistema é anterior ao 3.9 (o motor pede 3.9 ou superior)" "instale o Python 3.9 ou superior (macOS: brew install python@3.12) e rode bash scripts/setup.sh"
        return 1
    fi
    nota "criando o ambiente virtual .venv (o Python do sistema recusa pip install, PEP 668)..."
    if ! "$PY_SISTEMA" -m venv "$VENV"; then
        problema "não consegui criar o .venv" "python3 -m venv .venv (no Debian/Ubuntu: sudo apt install python3-venv)"
        return 1
    fi
    if ! venv_ok; then
        problema "o .venv foi criado sem o Python dentro (.venv/bin/python)" "apague a pasta .venv e rode bash scripts/setup.sh"
        return 1
    fi
    esconder_do_git "$VENV"
    nota ".venv criado."
}

# --- 2. requirements.txt no .venv ------------------------------------------------------------------
selo_atual() { cksum < requirements.txt | cut -d' ' -f1,2; }

requirements_ok() {
    [ -f "$SELO" ] && [ "$(cat "$SELO")" = "$(selo_atual)" ]
}

passo_requirements() {
    if [ ! -f requirements.txt ]; then
        problema "requirements.txt não encontrado na raiz do repo" "git checkout -- requirements.txt"
        return 1
    fi
    if requirements_ok; then
        nota "dependências Python já instaladas no .venv. Pulando o pip."
        return 0
    fi
    if [ "$CHECAR" = 1 ]; then
        problema "dependências Python não instaladas (ou o requirements.txt mudou)" "bash scripts/setup.sh"
        return 1
    fi
    if ! venv_ok; then
        problema "sem .venv não há onde instalar as dependências Python (requirements.txt)" "corrija o .venv e rode bash scripts/setup.sh"
        return 1
    fi
    nota "instalando o requirements.txt no .venv..."
    if "$VENV_PY" -m pip install --quiet --disable-pip-version-check -r requirements.txt; then
        selo_atual > "$SELO"
        nota "dependências Python OK."
    else
        problema "o pip falhou ao instalar o requirements.txt" ".venv/bin/python -m pip install -r requirements.txt"
        return 1
    fi
}

# --- 2b. transcritor ---------------------------------------------------------------------------------------
# O motor escolhe sozinho o primeiro que existir (parakeet, faster-whisper, Groq). Sem nenhum, o `vam audio`
# não roda e o doctor dá FAIL: por isso o setup instala UM, no .venv (nunca no Python do sistema).
# O selo guarda qual foi instalado; o pip já é idempotente, o selo só evita o gasto de rodá-lo à toa.
transcritor_alvo() {
    if [ "$(uname -s 2>/dev/null)" = "Darwin" ] && [ "$(uname -m 2>/dev/null)" = "arm64" ]; then
        echo "parakeet-mlx"
    else
        echo "faster-whisper"
    fi
}

instalar_transcritor() {
    "$VENV_PY" -m pip install --quiet --disable-pip-version-check "$1"
}

passo_transcritor() {
    local alvo
    alvo="$(transcritor_alvo)"
    if [ -f "$SELO_TRANSCRITOR" ] && [ -n "$(cat "$SELO_TRANSCRITOR" 2>/dev/null)" ]; then
        nota "transcritor ($(cat "$SELO_TRANSCRITOR")) já instalado no .venv. Pulando."
        return 0
    fi
    if [ "$CHECAR" = 1 ]; then
        aviso "transcritor local ($alvo) não instalado no .venv (sem ele só a Groq, com GROQ_API_KEY, transcreve)" "bash scripts/setup.sh"
        return 0
    fi
    if ! venv_ok; then
        problema "sem .venv não há onde instalar o transcritor ($alvo)" "corrija o .venv e rode bash scripts/setup.sh"
        return 1
    fi
    nota "instalando o transcritor $alvo no .venv (pode demorar: baixa bibliotecas pesadas)..."
    if instalar_transcritor "$alvo"; then
        echo "$alvo" > "$SELO_TRANSCRITOR"
        nota "transcritor $alvo OK."
        return 0
    fi
    if [ "$alvo" = "parakeet-mlx" ]; then
        aviso "o parakeet-mlx não instalou (ele pede Python 3.10 ou superior); tentando o faster-whisper" "$VENV_PY -m pip install parakeet-mlx"
        nota "instalando o faster-whisper no .venv..."
        if instalar_transcritor "faster-whisper"; then
            echo "faster-whisper" > "$SELO_TRANSCRITOR"
            nota "transcritor faster-whisper OK."
            return 0
        fi
    fi
    problema "nenhum transcritor instalou no .venv (o vam audio precisa de um)" ".venv/bin/python -m pip install $alvo (ou ponha GROQ_API_KEY no .env para usar a Groq)"
    return 1
}

# --- 3. Node 22 ou superior ------------------------------------------------------------------------
passo_node() {
    if ! command -v node >/dev/null 2>&1; then
        problema "Node não encontrado (o HyperFrames pede o 22 ou superior)" "instale o Node 22 (macOS: brew install node@22; outros: https://nodejs.org) e rode bash scripts/setup.sh"
        return 1
    fi
    local major
    major="$(node --version 2>/dev/null | tr -d 'v' | cut -d. -f1)"
    case "$major" in
        ''|*[!0-9]*)
            problema "não consegui ler a versão do Node" "reinstale o Node 22 (macOS: brew install node@22) e rode bash scripts/setup.sh"
            return 1 ;;
    esac
    if [ "$major" -lt 22 ]; then
        problema "Node $major: o HyperFrames pede o 22 ou superior" "atualize para o Node 22 (macOS: brew install node@22; outros: https://nodejs.org) e rode bash scripts/setup.sh"
        return 1
    fi
    NODE_OK=1
    nota "Node $major OK."
}

# --- 4. HyperFrames pinado -----------------------------------------------------------------------
hf_instalado_ok() {
    [ -x "$HF_BIN" ] || return 1
    local inst
    inst="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' node_modules/hyperframes/package.json 2>/dev/null | head -1)"
    [ -n "$PIN" ] && [ "$inst" = "$PIN" ]
}

passo_hyperframes() {
    if [ -z "$PIN" ]; then
        problema "o package.json não pina a dependência hyperframes" "git checkout -- package.json"
        return 1
    fi
    if hf_instalado_ok; then
        nota "HyperFrames $PIN já instalado em node_modules. Pulando o npm."
        HF_OK=1
        return 0
    fi
    if [ "$CHECAR" = 1 ]; then
        problema "HyperFrames $PIN não instalado em node_modules (o motor chama node_modules/.bin/hyperframes)" "bash scripts/setup.sh"
        return 1
    fi
    if [ "$NODE_OK" != 1 ]; then
        problema "HyperFrames $PIN não instalado: falta o Node 22 ou superior" "instale o Node 22 e rode bash scripts/setup.sh"
        return 1
    fi
    if ! command -v npm >/dev/null 2>&1; then
        problema "npm não encontrado (HyperFrames não instalado)" "reinstale o Node 22, que traz o npm, e rode bash scripts/setup.sh"
        return 1
    fi
    nota "instalando o HyperFrames $PIN (npm install, versão pinada no package.json)..."
    if npm install --no-audit --no-fund; then
        if hf_instalado_ok; then
            HF_OK=1
            nota "HyperFrames instalado."
        else
            problema "o npm terminou sem erro, mas node_modules/.bin/hyperframes não ficou na versão $PIN" "npm install (na raiz do repo)"
            return 1
        fi
    else
        problema "npm install falhou (HyperFrames não instalado)" "npm install (na raiz do repo; confira a internet)"
        return 1
    fi
}

# --- 5. Chromium do render ---------------------------------------------------------------------------
# `browser ensure` encontra o Chrome em cache ou baixa; já é idempotente por conta própria.
passo_browser() {
    if [ "$CHECAR" = 1 ]; then
        return 0
    fi
    if [ "$HF_OK" != 1 ]; then
        nota "pulando o Chromium do render: o HyperFrames não está instalado."
        return 0
    fi
    nota "garantindo o Chromium do render (hyperframes browser ensure)..."
    if "$HF_BIN" browser ensure; then
        nota "Chromium do render OK."
    else
        problema "hyperframes browser ensure falhou (o render pode falhar sem o Chromium)" "node_modules/.bin/hyperframes browser ensure"
        return 1
    fi
}

# --- 6. cópia local do GSAP -----------------------------------------------------------------------------
# Os templates carregam o GSAP por CDN. A cópia local deixa o render funcionar sem internet.
gsap_ok() {
    [ -f "$GSAP_DEST" ] || return 1
    local tam
    tam="$(wc -c < "$GSAP_DEST" | tr -d ' ')"
    [ "${tam:-0}" -ge 1000 ]
}

passo_gsap() {
    if gsap_ok; then
        nota "GSAP local já guardado em templates/_vendor. Pulando."
        return 0
    fi
    if [ "$CHECAR" = 1 ]; then
        aviso "sem cópia local do GSAP (o render depende da CDN)" "bash scripts/setup.sh"
        return 0
    fi
    local ref url tmp
    ref="$(grep -rho 'gsap@[0-9][0-9.]*' templates/*/index.html 2>/dev/null | head -1)"
    [ -z "$ref" ] && ref="gsap@3.14.2"
    url="https://cdn.jsdelivr.net/npm/$ref/dist/gsap.min.js"
    if ! command -v curl >/dev/null 2>&1; then
        aviso "curl não encontrado: não guardei o GSAP local (o render usa a CDN)" "instale o curl e rode bash scripts/setup.sh"
        return 0
    fi
    mkdir -p "$REPO_ROOT/templates/_vendor"
    esconder_do_git "$REPO_ROOT/templates/_vendor"
    tmp="$GSAP_DEST.baixando"
    nota "guardando o $ref em templates/_vendor..."
    if curl -fsSL --max-time 60 -o "$tmp" "$url" && [ "$(wc -c < "$tmp" | tr -d ' ')" -ge 1000 ] && grep -q gsap "$tmp"; then
        mv "$tmp" "$GSAP_DEST"
        nota "GSAP local OK."
    else
        rm -f "$tmp"
        aviso "não consegui baixar o GSAP para templates/_vendor (o render usa a CDN)" "bash scripts/setup.sh (com internet)"
    fi
}

# --- 7. .env -----------------------------------------------------------------------------------------------
passo_env() {
    if [ -f .env ]; then
        nota ".env já existe. Não toquei."
    elif [ "$CHECAR" = 1 ]; then
        nota "sem .env (opcional): copie o .env.example para .env e preencha as chaves que usa."
    elif [ -f .env.example ]; then
        cp .env.example .env && nota "criei o .env a partir do .env.example. Preencha as chaves que você usa."
    fi
}

# --- 8. _local e 9. sons ------------------------------------------------------------------------------------
python_de_trabalho() {
    if venv_ok; then echo "$VENV_PY"; else echo "$PY_SISTEMA"; fi
}

passo_local() {
    if [ "$CHECAR" = 1 ]; then
        if [ -d "$ESTADO_DIR" ]; then nota "_local OK."; else problema "a pasta _local/ não existe" "bash scripts/setup.sh"; return 1; fi
        return 0
    fi
    local py
    py="$(python_de_trabalho)"
    if [ -z "$py" ]; then
        problema "sem Python para preparar a pasta _local/" "instale o Python 3.9 ou superior e rode bash scripts/setup.sh"
        return 1
    fi
    if "$py" "$REPO_ROOT/scripts/init_local.py"; then
        nota "_local OK."
    else
        problema "init_local.py falhou (a pasta _local/ não foi preparada)" "python3 scripts/init_local.py"
        return 1
    fi
}

passo_sons() {
    if [ "$CHECAR" = 1 ]; then
        if ls "$SOM_DIR"/*.wav >/dev/null 2>&1; then nota "efeitos sonoros OK."; else problema "efeitos sonoros ausentes (assets/som)" "bash scripts/setup.sh"; return 1; fi
        return 0
    fi
    local py
    py="$(python_de_trabalho)"
    if [ -z "$py" ]; then
        problema "sem Python para gerar os efeitos sonoros" "instale o Python 3.9 ou superior e rode bash scripts/setup.sh"
        return 1
    fi
    nota "gerando os efeitos sonoros (riser, tick, boom)..."
    if "$py" "$REPO_ROOT/scripts/som_cortes.py"; then
        nota "efeitos sonoros OK."
    else
        problema "som_cortes.py falhou (os efeitos sonoros não foram gerados; ele precisa do ffmpeg)" "instale o ffmpeg (macOS: brew install ffmpeg) e rode python3 scripts/som_cortes.py"
        return 1
    fi
}

# --- cinema-plus ------------------------------------------------------------------------------------------------
# RESERVADO. A unidade da camada de matting (torch, opcional) altera SÓ esta função. Hoje
# --cinema-plus é um no-op documentado: nada é instalado, e o anúncio funciona sem ele.
passo_cinema_plus() {
    if [ "$CINEMA_PLUS" = 1 ]; then
        nota "--cinema-plus: reservado. Hoje não instala nada; a camada opcional de matting entra aqui numa versão futura."
    fi
}

# --- roda os passos, sem deixar um derrubar o outro -------------------------------------------------------------------
if [ "$CHECAR" = 1 ]; then
    nota "conferindo (--checar: nada será instalado nem criado) em $REPO_ROOT"
else
    nota "iniciando em $REPO_ROOT"
fi

passo_venv
passo_requirements
passo_transcritor
passo_node
passo_hyperframes
passo_browser
passo_gsap
passo_env
passo_local
passo_sons
passo_cinema_plus

# --- 10. doctor ---------------------------------------------------------------------------------------------------
# Só diz "pronto" quem passou pelo doctor. Com falha pendente ele é pulado: reprovaria pelo mesmo motivo.
passo_doctor() {
    if [ ${#FALHAS[@]} -gt 0 ]; then
        nota "doctor adiado: conserte as falhas acima e rode bash scripts/setup.sh de novo."
        return 0
    fi
    local py saida rc
    py="$(python_de_trabalho)"
    if [ -z "$py" ] || [ ! -f "$REPO_ROOT/scripts/vam.py" ]; then
        problema "não consegui rodar o doctor (sem Python ou sem scripts/vam.py)" "python3 scripts/vam.py doctor"
        return 1
    fi
    nota "rodando o doctor (python3 scripts/vam.py doctor)..."
    saida="$("$py" "$REPO_ROOT/scripts/vam.py" doctor 2>&1)"
    rc=$?
    echo "$saida" | sed 's/^/[setup]   /'
    if [ "$rc" -ne 0 ]; then
        local primeira
        primeira="$(echo "$saida" | grep '^\[FAIL\]' | head -1)"
        problema "o doctor reprovou o ambiente: ${primeira:-ver a saída acima}" "aplique o conserto de cada [FAIL] acima e rode bash scripts/setup.sh de novo"
        return 1
    fi
}

passo_doctor

# --- resumo -----------------------------------------------------------------------------------------------------------
echo "[setup] resumo"
if [ ${#FALHAS[@]} -eq 0 ] && [ ${#AVISOS[@]} -eq 0 ]; then
    nota "tudo pronto (o doctor passou sem nenhum FAIL)."
    exit 0
fi
if [ ${#FALHAS[@]} -gt 0 ]; then
    if [ "$CHECAR" = 1 ]; then
        nota "FALTA ${#FALHAS[@]} coisa(s):"
    else
        nota "FALHOU ${#FALHAS[@]} passo(s):"
    fi
    for item in "${FALHAS[@]}"; do
        nota "  - ${item%%|*}"
        nota "    conserto: ${item#*|}"
    done
fi
if [ ${#AVISOS[@]} -gt 0 ]; then
    nota "avisos (opcionais):"
    for item in "${AVISOS[@]}"; do
        nota "  - ${item%%|*}"
        nota "    conserto: ${item#*|}"
    done
fi
if [ ${#FALHAS[@]} -gt 0 ]; then
    nota "depois de aplicar os consertos, rode de novo: bash scripts/setup.sh"
    exit 1
fi
nota "o que ficou é opcional; o doctor passou sem nenhum FAIL."
exit 0
