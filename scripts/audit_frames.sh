#!/usr/bin/env bash
# scripts/audit_frames.sh <video.mp4> <outdir>
#
# Auditoria frame a frame (Task 1.5, ver PLAN.md e DESIGN.md seção 9 passo 9):
# NUNCA declarar um reel "pronto" só pelo preview. Gera um contact sheet do
# vídeo inteiro (fps=1, grade 5x11) + os frames-chave dos beats críticos
# (hook, "1%" e end card), pra o agente LER de verdade antes de aprovar.
#
# Uso: bash scripts/audit_frames.sh <video.mp4> <outdir>

VIDEO="$1"
OUTDIR="$2"

if [ -z "$VIDEO" ]; then
    echo "[audit_frames] ERRO: falta o argumento <video.mp4>."
    echo "Uso: bash scripts/audit_frames.sh <video.mp4> <outdir>"
    exit 1
fi

if [ ! -f "$VIDEO" ]; then
    echo "[audit_frames] ERRO: o vídeo '$VIDEO' não existe."
    exit 1
fi

if [ -z "$OUTDIR" ]; then
    echo "[audit_frames] ERRO: falta o argumento <outdir>."
    echo "Uso: bash scripts/audit_frames.sh <video.mp4> <outdir>"
    exit 1
fi

mkdir -p "$OUTDIR"
if [ $? -ne 0 ]; then
    echo "[audit_frames] ERRO: não consegui criar o diretório '$OUTDIR'."
    exit 1
fi

echo "[audit_frames] vídeo: $VIDEO"
echo "[audit_frames] saída: $OUTDIR"

# --- 1. contact sheet do vídeo inteiro (fps=1, grade 5x11) ---
SHEET="$OUTDIR/sheet.jpg"
echo "[audit_frames] gerando contact sheet completo em '$SHEET'..."
ffmpeg -hide_banner -loglevel error -y -i "$VIDEO" \
    -vf "fps=1,scale=210:-1,tile=5x11:margin=6:padding=4:color=0x222222" \
    -update 1 -frames:v 1 "$SHEET"
if [ $? -ne 0 ]; then
    echo "[audit_frames] ERRO: ffmpeg falhou gerando o contact sheet."
    exit 1
fi

# --- 2. frames-chave: hook (t=1.5), beat do "1%" (t=29), end card (t=52) ---
HOOK_FRAME="$OUTDIR/frame_hook_1.5s.jpg"
BEAT_FRAME="$OUTDIR/frame_beat1pct_29s.jpg"
ENDCARD_FRAME="$OUTDIR/frame_endcard_52s.jpg"

echo "[audit_frames] extraindo frame do hook (t=1.5s) em '$HOOK_FRAME'..."
ffmpeg -hide_banner -loglevel error -y -ss 1.5 -i "$VIDEO" -update 1 -frames:v 1 "$HOOK_FRAME"
if [ $? -ne 0 ]; then
    echo "[audit_frames] AVISO: falhou extraindo o frame do hook (t=1.5s)."
fi

echo "[audit_frames] extraindo frame do beat '1%' (t=29s) em '$BEAT_FRAME'..."
ffmpeg -hide_banner -loglevel error -y -ss 29 -i "$VIDEO" -update 1 -frames:v 1 "$BEAT_FRAME"
if [ $? -ne 0 ]; then
    echo "[audit_frames] AVISO: falhou extraindo o frame do beat '1%' (t=29s)."
fi

echo "[audit_frames] extraindo frame do end card (t=52s) em '$ENDCARD_FRAME'..."
ffmpeg -hide_banner -loglevel error -y -ss 52 -i "$VIDEO" -update 1 -frames:v 1 "$ENDCARD_FRAME"
if [ $? -ne 0 ]; then
    echo "[audit_frames] AVISO: falhou extraindo o frame do end card (t=52s)."
fi

echo "[audit_frames] concluído. Arquivos gerados:"
echo "  $SHEET"
echo "  $HOOK_FRAME"
echo "  $BEAT_FRAME"
echo "  $ENDCARD_FRAME"
