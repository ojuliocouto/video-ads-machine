#!/usr/bin/env bash
# scripts/dev/e2e_local.sh
#
# O fluxo do aluno no modo avatar, PONTA A PONTA, pela CLI `vam`, sobre a mídia de um fixture que NUNCA entra no
# repo. É o critério de pronto da orquestração (W5.A): sai 0 só com o laudo PASS e a entrega liberada.
#
#   VAM_E2E_MIDIA=<pasta> bash scripts/dev/e2e_local.sh
#
# A pasta da mídia tem: avatar_18s.mp4 (um avatar 1080x1920 JÁ gerado de uma voz higienizada), broll01.mp4,
# broll02.mp4 (gravações de tela) e logo.png. Sem VAM_E2E_MIDIA, usa $VAM_PARIDADE_MIDIA/fixture/midia.
#
# Os passos, todos pelo vam (o fluxo do aluno, na ordem):
#   doctor -> novo -> roteiro -> audio (a voz do próprio avatar como gravação) -> avatar --existente (custo zero, sem
#   HeyGen) -> plano -> aprovar -> montar -> auditar (pacote) -> auditar --nota (um comando SEPARADO, o do auditor:
#   quem é medido não assina) -> entregar
#
# A trilha é sintetizada (acordes de senoide com tremolo): o repo não embarca música e a de teste não pode ter licença.
# O _local do teste fica em VAM_E2E_SAIDA (padrão: uma pasta nova em $TMPDIR); nada é escrito no _local do repo.
# Cada passo tem o tempo medido; o laudo e o tempo de build vão para o resumo no fim.
#
# Compatível com o bash 3.2 do macOS.

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MIDIA="${VAM_E2E_MIDIA:-${VAM_PARIDADE_MIDIA:-}/fixture/midia}"
SLUG="${VAM_E2E_SLUG:-e2e}"
NOTA="${VAM_E2E_NOTA:-8.5}"
PY="${VAM_E2E_PYTHON:-python3}"

falhar() { echo "[e2e] FALHOU: $*"; exit 1; }

for f in avatar_18s.mp4 broll01.mp4 broll02.mp4 logo.png; do
    [ -f "$MIDIA/$f" ] || { echo "[e2e] ERRO: falta $MIDIA/$f (defina VAM_E2E_MIDIA)"; exit 2; }
done

SAIDA="${VAM_E2E_SAIDA:-$(mktemp -d "${TMPDIR:-/tmp}/vam-e2e.XXXXXX")}"
mkdir -p "$SAIDA"
export VAM_ESTADO="$SAIDA/_local"
unset VAM_DADOS VAM_V1_HOME VAM_INPUTS VAM_OUTPUT VAM_ASSETS VAM_ROTEIROS
TMP="$SAIDA/_insumos"
mkdir -p "$TMP"
echo "[e2e] raiz:  $RAIZ"
echo "[e2e] mídia: $MIDIA"
echo "[e2e] _local do teste: $VAM_ESTADO"

agora() { "$PY" -c 'import time; print("%.1f" % time.time())'; }
TEMPOS="$SAIDA/tempos.txt"
: > "$TEMPOS"
passo() {
    local nome="$1"; shift
    echo
    echo "[e2e] ===== $nome: vam $* ====="
    local t0; t0="$(agora)"
    "$PY" "$RAIZ/scripts/vam.py" "$@"
    local rc=$?
    local t1; t1="$(agora)"
    "$PY" -c "print('%-12s rc=%d %7.1f s' % ('$nome', $rc, $t1 - $t0))" >> "$TEMPOS"
    return $rc
}

# --- insumos do aluno -------------------------------------------------------------------------------------
cat > "$TMP/roteiro.md" <<'ROTEIRO'
[insert: demo-a | hook: MEU CLAUDE | virou um web designer | PROFISSIONAL] Minha skill de criação de páginas transformou meu Claude em um web designer profissional.
[apresentador] Agora eu construo minhas páginas em minutos, sem precisar pagar nada mais por isso.
[apresentador | LEAD: sabe qual é | KEY: O MELHOR] Sabe qual é o melhor?
[insert: demo-b | split] Se eu usar um conector que é disponibilizado gratuitamente dentro do Claude,
[cta | LEAD: eu consigo não só | KEY: PRODUZIR AS PÁGINAS | logo] eu consigo não só produzir as páginas
ROTEIRO
ffmpeg -y -v error -i "$MIDIA/avatar_18s.mp4" -vn -ac 1 -ar 48000 "$TMP/bruto.wav" || falhar "extrair a voz do avatar"
ffmpeg -y -v error -f lavfi -i "aevalsrc=0.20*sin(2*PI*220*t)*(0.6+0.4*sin(2*PI*0.5*t))+0.14*sin(2*PI*277.18*t)+0.11*sin(2*PI*329.63*t):s=48000:d=40" \
    -c:a aac -b:a 160k "$TMP/trilha_sintetica.m4a" || falhar "sintetizar a trilha"

# --- o fluxo ------------------------------------------------------------------------------------------------
passo doctor doctor || echo "[e2e] AVISO: o doctor apontou FAIL (o build diz se faz falta)"

passo novo novo "$SLUG" --look fixture --trilha trilha_sintetica.m4a || falhar "vam novo"
cp "$TMP/trilha_sintetica.m4a" "$VAM_ESTADO/trilhas/" || falhar "copiar a trilha"
cp "$MIDIA/logo.png" "$VAM_ESTADO/marca/logo.png" || falhar "copiar o logo"
PROJ="$VAM_ESTADO/projetos/$SLUG"
cp "$MIDIA/broll01.mp4" "$PROJ/inserts/demo-a.mp4" && cp "$MIDIA/broll02.mp4" "$PROJ/inserts/demo-b.mp4" \
    || falhar "copiar os inserts"
# O que o ALUNO declara (é dele): a grafia da marca que o ASR erra, e as exceções de lettering com motivo (um anúncio
# de 18 s não comporta 2 KEYs no meio a 8 s uma da outra).
"$PY" - "$VAM_ESTADO" "$PROJ" <<'PYEOF' || falhar "declarar glossário e exceções"
import json, sys
from pathlib import Path
estado, proj = Path(sys.argv[1]), Path(sys.argv[2])
(estado / "glossario.json").write_text(json.dumps({"versao": 1, "termos": [
    {"grafia": "Claude", "variantes": ["Cloud", "Clode", "Claud", "Cláudio"]}]}, ensure_ascii=False, indent=2) + "\n")
p = json.loads((proj / "projeto.json").read_text())
p["excecoes"] = [
    {"regra": "lettering.contagem", "motivo": "anúncio de teste de 18 s: cabe uma KEY no meio e a do CTA"},
    {"regra": "lettering.intervalo", "motivo": "anúncio de teste de 18 s: a KEY e o CTA ficam a menos de 8 s"}]
(proj / "projeto.json").write_text(json.dumps(p, ensure_ascii=False, indent=2) + "\n")
PYEOF

passo roteiro roteiro "$SLUG" --de "$TMP/roteiro.md" || falhar "vam roteiro"
passo audio audio "$SLUG" --bruto "$TMP/bruto.wav" || falhar "vam audio"
passo avatar avatar "$SLUG" --existente "$MIDIA/avatar_18s.mp4" --avatar-id fixture_sem_heygen --plano medio \
    --aprovar-look || falhar "vam avatar"
passo plano plano "$SLUG" || falhar "vam plano"
passo aprovar aprovar "$SLUG" --ok "aprovado no teste ponta a ponta (e2e_local)" || falhar "vam aprovar"
passo montar montar "$SLUG" --paralelo "${VAM_E2E_PARALELO:-2}"
RC_MONTAR=$?
if [ "$RC_MONTAR" != 0 ]; then
    passo status status "$SLUG"
    falhar "vam montar saiu com $RC_MONTAR (laudo em $PROJ/entrega/laudo.json)"
fi
passo pacote auditar "$SLUG" || falhar "vam auditar (pacote)"
cat > "$TMP/achados.json" <<'ACHADOS'
[{"id": "A1", "gravidade": "leve", "descricao": "nota de TESTE escrita pelo e2e_local: não substitui a auditoria de verdade", "status": "aceito"}]
ACHADOS
passo auditor auditar "$SLUG" --nota "$NOTA" --achados "$TMP/achados.json" --modelo e2e-teste || falhar "vam auditar --nota"
passo entregar entregar "$SLUG" || falhar "vam entregar"

# --- resumo ---------------------------------------------------------------------------------------------------
echo
echo "[e2e] ===== laudo ====="
"$PY" - "$PROJ/entrega/laudo.json" <<'PYEOF'
import json, sys
d = json.load(open(sys.argv[1]))
for g in d["gates"]:
    print("  %-24s %-8s %-7s %s" % (g["nome"], g["etapa"], g["resultado"], (g.get("motivo") or "")[:110]))
print("  capacidades: " + ", ".join("%s %s" % (c, v["status"]) for c, v in d["capacidades"].items()))
print("  medidas: %(duracao_s)s s, %(largura)sx%(altura)s, %(lufs)s LUFS, pico %(true_peak_dbtp)s dBTP" % d["medidas"])
print("  tempos: %s" % d.get("tempos"))
print("  sha256 do final: %s" % d["sha256"])
print("  VEREDITO: %s" % d["veredito"])
nao_pass = [g["nome"] for g in d["gates"] if g["resultado"] not in ("PASS",) and g["nome"] != "gate_texto_atras"]
sys.exit(0 if d["veredito"] == "PASS" and not nao_pass else 1)
PYEOF
RC_LAUDO=$?
echo
echo "[e2e] tempos por passo:"
cat "$TEMPOS"
echo "[e2e] final: $PROJ/entrega/final_9x16.mp4"
echo "[e2e] prévia: $PROJ/entrega/final_whatsapp.mp4"
[ "$RC_LAUDO" = 0 ] || falhar "o laudo não está todo PASS"
echo "[e2e] OK: laudo PASS e entrega liberada"
exit 0
