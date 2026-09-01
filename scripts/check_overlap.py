"""Verifica sobreposicao temporal entre janelas de lettering e grupos de legenda
no index.html gerado. Uso: python3 check_overlap.py <render-dir-ou-index.html>
Sai com codigo != 0 e imprime as colisoes se houver (0 = limpo)."""
import re
import sys
from pathlib import Path


def main(target):
    p = Path(target)
    html_path = p / "index.html" if p.is_dir() else p
    html = html_path.read_text()
    grps = []
    for m in re.finditer(r'data-g-start="([0-9.]+)" data-g-end="([0-9.]+)">(.*?)</div>', html, re.S):
        txt = " ".join(re.sub(r"<[^>]+>", " ", m.group(3)).split())
        grps.append((float(m.group(1)), float(m.group(2)), txt))
    letts = []
    for m in re.finditer(r'class="lett clip"[^>]*data-start="([0-9.]+)" data-duration="([0-9.]+)"', html):
        s = float(m.group(1))
        letts.append((s, s + float(m.group(2))))
    bad = 0
    for ls, le in letts:
        for gs, ge, txt in grps:
            if gs < le and ge > ls:
                print(f"  COLISAO lettering[{ls:.2f}-{le:.2f}] x legenda[{gs:.2f}-{ge:.2f}]: {txt}")
                bad += 1
    print(f"sobreposicao legenda x lettering: {bad}")
    return bad


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    sys.exit(1 if main(target) else 0)
