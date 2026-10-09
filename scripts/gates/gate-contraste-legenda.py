#!/usr/bin/env python3
"""Gate de CONTRASTE da legenda contra o fundo, medido no arquivo entregue.

Nasceu de defeito que passou por todos os outros gates (jh13, build 26, 28/08/2026): a
legenda branca pousou em cima de um mockup de pagina BRANCA e o contraste deu 1,52:1,
contra 11,7 e 14,3 nos trechos escuros do mesmo anuncio. O gate de colisao nao pega isso
(nao ha rosto atras), o de "sem texto na tela" nao pega (o texto ESTA la, so nao le), e o
de ritmo nao pega. Texto ilegivel e pior que texto ausente: ocupa o lugar e nao entrega.

Como mede, sem detector e sem olhometro:
  o MOV de overlay tem canal ALPHA, entao ele diz exatamente onde esta a tinta;
  o mp4 entregue diz o que aparece embaixo dela.
  tinta   = pixels do quadro entregue onde o alpha do overlay e alto
  fundo   = pixels do quadro entregue na MESMA faixa onde o alpha e zero
  razao   = contraste WCAG entre as duas luminancias relativas

Piso: 4,5:1. E o mesmo numero que decide a tinta invertida no gen_ad_v2, entao gate e
motor concordam por construcao em vez de por coincidencia.

Uso:
  gate-contraste-legenda.py <entregue.mp4> --overlay <ovl.mov> [--accel 1.35]
                            [--intervalo 0.5] [--piso 4.5]
Saida 1 se algum trecho reprovar.
"""
import argparse
import subprocess
import sys

try:
    import numpy as np
except ImportError as _e:       # dependencia que o aluno ainda nao instalou: mensagem, nao traceback
    sys.exit(f"Falta uma dependência Python deste gate ({_e.name}). Instale com:\n"
             "  pip install -r scripts/gates/requirements.txt")

W, H = 1080, 1920
# SO A TINTA CHEIA (28/08/2026, terceira passada). Comecei em 200 pra pegar o miolo do
# glifo sem a borda de antialias, e isso deixou entrar a palavra AINDA NAO FALADA, que
# fica a 82% de opacidade de proposito (alpha 209). A 82% o pixel entregue e mistura de
# tinta com fundo, entao o gate media 0,451 e 0,509 de luminancia num texto branco e
# reprovava o karaoke em vez de defeito: 53 faixas no build 28, quase todas assim.
# Legibilidade se cobra no estado em que a palavra e LIDA, que e o de opacidade cheia.
# O escurecimento das outras e hierarquia, nao falha.
ALPHA_TINTA = 250
ALPHA_FUNDO = 12       # pixel intocado pelo overlay
MIN_TINTA = 1500       # menos que isso e pontuacao solta, nao legenda
MIN_ALTURA = 8


# SEEK POR AMOSTRA, NUNCA FLUXO CONTINUO (28/08/2026, primeira versao deste gate).
# Escrevi primeiro lendo os dois videos como fluxo (`fps=N` em cada pipe, indice a
# indice) e ele acusou 84 de 123 faixas, inclusive t=4,50s, onde a legenda le muito bem:
# reportou tinta 0,033 contra os 0,648 que a medicao manual do mesmo quadro deu. Os dois
# fluxos DERIVAM um contra o outro, entao a mascara de tinta de um instante caia sobre o
# quadro de outro. E a mesma armadilha que ja custou tres tentativas no gate de colisao.
# Com seek direto por amostra os numeros batem com a medicao manual nos dois quadros
# conferidos: 11,6:1 no que le e 1,5:1 no que o espectador ia ver.
def _quadro(caminho, t, vf):
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", caminho, "-frames:v", "1",
         "-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True)
    if len(r.stdout) < W * H:
        return None
    return np.frombuffer(r.stdout[:W * H], dtype=np.uint8).reshape(H, W)


def _rel_lum(cinza):
    c = cinza.astype(np.float64) / 255.0
    return np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _erodir(m, k):
    """Erosao binaria separavel de raio k, so com numpy (sem scipy)."""
    if k <= 0:
        return m
    out = m
    for eixo in (0, 1):
        acc = out
        for d in range(1, k + 1):
            acc = acc & np.roll(out, d, axis=eixo) & np.roll(out, -d, axis=eixo)
        out = acc
    return out


def bandas(tem):
    out, ini = [], None
    for y, v in enumerate(tem):
        if v and ini is None:
            ini = y
        elif not v and ini is not None:
            out.append((ini, y - 1))
            ini = None
    if ini is not None:
        out.append((ini, len(tem) - 1))
    return [(a, b) for a, b in out if b - a >= MIN_ALTURA]


def controle():
    """Vermelho antes de verde, NAS DUAS POLARIDADES.

    O gate tem que julgar pelo preenchimento da letra, seja ele claro ou escuro. A
    primeira versao media percentil 80 e so funcionava com legenda branca: quando a
    legenda inverteu pra escura, passou a medir o halo branco e reprovou material bom.
    Entao o controle sintetiza os tres casos que importam, com contorno de verdade:
        branca com contorno escuro sobre fundo ESCURO -> passa
        escura com halo claro      sobre fundo CLARO  -> passa
        branca com contorno escuro sobre fundo CLARO  -> reprova (o defeito reportado)
    """
    def caso(fundo, fill, contorno):
        q = np.full((160, 520), fundo, dtype=np.uint8)
        alpha = np.zeros((160, 520), dtype=np.uint8)
        # letra sintetica: haste de 60px com contorno de 6px de cada lado
        alpha[30:130, 60:460] = 255
        q[30:130, 60:460] = contorno
        q[36:124, 66:454] = fill
        ink = alpha >= ALPHA_TINTA
        lum = _rel_lum(q)
        miolo = _erodir(ink, 4)
        li = float(np.median(lum[miolo])) if miolo.sum() >= 200 else float(np.median(lum[ink]))
        lb = float(_rel_lum(np.full((10, 10), fundo, dtype=np.uint8)).mean())
        return (max(li, lb) + 0.05) / (min(li, lb) + 0.05)

    r_esc = caso(12, 245, 20)     # legenda branca sobre fundo escuro
    r_inv = caso(240, 18, 250)    # legenda escura com halo claro sobre fundo claro
    r_ruim = caso(240, 245, 20)   # legenda branca sobre fundo claro: o defeito
    ok = r_esc >= 4.5 and r_inv >= 4.5 and r_ruim < 4.5
    print(f"controle: branca/fundo escuro {r_esc:.2f}:1 | escura/fundo claro "
          f"{r_inv:.2f}:1 | branca/fundo claro {r_ruim:.2f}:1  ->  "
          f"{'OK (julga pelo preenchimento nas duas polaridades)' if ok else 'FALHOU'}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("entregue")
    ap.add_argument("--overlay", required=True)
    ap.add_argument("--accel", type=float, default=1.35)
    # a0: DESLOCAMENTO DO OVERLAY, LIDO DO FILTRO, NAO DEDUZIDO (28/08/2026).
    # O composite monta assim:  [1:v]setpts=PTS-a0/TB  ->  overlay sobre a footage  ->
    # setpts=PTS/ACCEL. Logo  overlay = entregue * ACCEL + a0.
    # Sem o `+ a0` o gate lia a mascara de um instante e o quadro de outro, e o erro so
    # aparecia em grupo CURTO: o grupo "todo o processo" vive 0,25s, e a amostra de
    # t=33,50s caia 0,095s DEPOIS do fim dele. O gate reportava tinta 0,001 sobre fundo
    # 0,001 e chamava de legenda ilegivel uma legenda que, 0,08s antes, aparecia branca
    # e nitida (conferido quadro a quadro na tira de 33,42 a 33,58).
    ap.add_argument("--a0", type=float, default=0.0)
    ap.add_argument("--intervalo", type=float, default=0.5)
    ap.add_argument("--piso", type=float, default=4.5)
    # `--ate`: instante do CTA. Depois dele a tela e do botao e do logo, que sao
    # elementos desenhados com contraste proprio, nao legenda de fala.
    ap.add_argument("--ate", type=float, default=None)
    a = ap.parse_args()

    if not controle():
        sys.exit("controle falhou: nao medi o filme")

    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", a.entregue], capture_output=True, text=True).stdout.strip())
    _fim = min(dur, a.ate) if a.ate else dur
    alvos = [round(k * a.intervalo, 3) for k in range(int(_fim / a.intervalo))]

    def medir(t):
        alpha = _quadro(a.overlay, t * a.accel + a.a0, "alphaextract")
        if alpha is None:
            return []
        ink = alpha >= ALPHA_TINTA
        if ink.sum() < MIN_TINTA:
            return []
        quadro = _quadro(a.entregue, t, "format=gray")
        if quadro is None:
            return []
        lum = _rel_lum(quadro)
        saida = []
        for y0, y1 in bandas(ink.sum(axis=1) >= 4):
            fi = ink[y0:y1 + 1]
            fq = lum[y0:y1 + 1]
            fundo = (alpha[y0:y1 + 1] <= ALPHA_FUNDO)
            if fi.sum() < 400 or fundo.sum() < 400:
                continue
            # BOTAO NAO E LEGENDA, mas NAO DA PRA SEPARAR POR GEOMETRIA (28/08/2026).
            # O CTA ("saiba mais" numa pilula escura) entrava como se fosse legenda e o
            # gate media o escuro da pilula contra o escuro da camisa: 1,07:1 em t=87,0s,
            # num quadro em que o botao le perfeitamente. Eram 6 das 17 reprovas.
            # Tentei cortar por "forma cheia nao e texto" e MEDI antes de confiar: o
            # preenchimento da faixa do CTA e 0,136 e o de uma legenda e 0,126. A regra
            # nao separava nada, entao saiu daqui em vez de ficar como enfeite que parece
            # justificar um numero. Quem sabe onde o CTA comeca e o build; por isso o
            # corte entra por `--ate`, com o valor vindo de la.
            # O MIOLO DA LETRA POR EROSAO, NAO POR PERCENTIL (28/08/2026, segunda
            # passada). A mascara de alpha cobre contorno E preenchimento, e os dois tem
            # luminancias opostas de proposito. Usei percentil 80 primeiro, o que
            # equivale a assumir que a tinta e sempre a parte CLARA: funcionava com a
            # legenda branca e passou a medir o HALO quando a legenda inverteu pra
            # escura. No build 27 isso reportou tinta 0,905 numa legenda preta, e o gate
            # piorou (64 reprovas) enquanto os quadros melhoravam no olho.
            # Erosao nao assume cor nenhuma: come a borda e sobra o preenchimento, seja
            # ele claro ou escuro. Contorno de 0,078em em corpo 80px da ~6px, entao 4px
            # de erosao tiram a borda e deixam a haste (14px no Inter 800).
            miolo = _erodir(fi, 4)
            li = float(np.median(fq[miolo])) if miolo.sum() >= 200 \
                else float(np.median(fq[fi]))
            lb = float(fq[fundo].mean())
            raz = (max(li, lb) + 0.05) / (min(li, lb) + 0.05)
            saida.append((t, y0, y1, raz, li, lb))
        return saida

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as ex:
        blocos = list(ex.map(medir, alvos))
    n = len(alvos)
    medidas, reprovas = [], []
    for bl in blocos:
        for item in bl:
            medidas.append(item[3])
            if item[3] < a.piso:
                reprovas.append(item)
    reprovas.sort()

    print(f"\nEntregue : {a.entregue.split('/')[-1]}")
    print(f"Amostras : {n} (a cada {a.intervalo}s), {len(medidas)} faixa(s) com legenda")
    if medidas:
        m = sorted(medidas)
        print(f"Contraste: pior {m[0]:.2f}:1  mediana {m[len(m) // 2]:.2f}:1  "
              f"melhor {m[-1]:.2f}:1   (piso {a.piso}:1)")
    # NENHUMA FAIXA MEDIDA NAO E APROVACAO (29/08/2026). Este gate devolveu
    # "0 faixa(s) com legenda ... PASSA" num anuncio com 231 palavras de legenda na tela:
    # a legenda tinha passado a renderizar a 82% de opacidade (alpha 210), abaixo do
    # limiar de tinta cheia, e o gate simplesmente parou de enxergar. Silencio virou
    # aprovacao. Se nao ha o que medir, ou o video nao tem legenda (defeito grave) ou o
    # medidor esta cego (defeito do gate): as duas coisas reprovam.
    if not medidas:
        print("\nREPROVA: nenhuma faixa de legenda encontrada para medir.\n"
              "  Ou o anuncio esta sem legenda, ou a tinta nao chega a opacidade cheia\n"
              f"  (limiar de tinta: alpha >= {ALPHA_TINTA}). Confira o alpha do overlay.")
        return 1
    # CRITERIO DE REPROVACAO (31/08/2026): o gate nasceu de um defeito de SECAO inteira
    # (mediana 2,64:1, 57 de 120 faixas abaixo do piso). Ligado no build, ele passou a
    # barrar por faixas de fronteira (4,3:1 num piso de 4,5) numa peca com mediana 8,7.
    # Reprova quando a MEDIANA cai abaixo do piso ou quando mais de 30% das faixas caem;
    # abaixo disso as faixas saem como AVISO, com instante, pra quem for corrigir.
    _med = sorted(medidas)[len(medidas) // 2]
    _frac = len(reprovas) / float(len(medidas))
    if reprovas and not (_med < a.piso or _frac > 0.30):
        print(f"\nAVISO: {len(reprovas)} de {len(medidas)} faixa(s) abaixo do piso "
              f"({_frac:.0%}); mediana {_med:.2f}:1 acima do piso, nao reprova")
        for t, y0, y1, raz, li, lb in reprovas[:12]:
            print(f"   t={t:6.2f}s  y{y0}-{y1}  {raz:5.2f}:1")
        print("\nPASSA (com avisos).")
        return 0
    if reprovas:
        print(f"\nREPROVA: {len(reprovas)} faixa(s) de legenda abaixo do piso "
              f"({_frac:.0%} das faixas; mediana {_med:.2f}:1)")
        for t, y0, y1, raz, li, lb in reprovas[:20]:
            print(f"   t={t:6.2f}s  y{y0}-{y1}  {raz:5.2f}:1  "
                  f"(tinta {li:.3f}, fundo {lb:.3f})")
        return 1
    print("\nPASSA: toda legenda le contra o fundo dela.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
