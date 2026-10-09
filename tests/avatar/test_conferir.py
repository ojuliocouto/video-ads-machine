"""W2.C: conferência do avatar (dimensão, fração útil, duração, prancha da boca).

ffprobe e ffmpeg são mockados por argv; os quadros são PNGs sintéticos feitos com Pillow.
Zero chamada real, zero custo.
"""
import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from avatar import conferir as C
from projeto import looks, pastas

ID = "avatar_fake_0001"


def coluna(topo=0, base=0, n=1080):
    """Coluna de cinza 1xN: barra preta em cima e embaixo, conteúdo variável no meio."""
    meio = [60 + (i * 37) % 140 for i in range(n - topo - base)]
    return [0] * topo + meio + [0] * base


class Midia:
    """Executor falso: responde ffprobe por caminho e escreve PNGs sintéticos para o ffmpeg."""

    def __init__(self, arquivos, colunas=None):
        self.arquivos = arquivos          # caminho -> (largura, altura, duracao)  (largura None = só áudio)
        self.colunas = colunas            # função t -> coluna; None = sem barra
        self.chamadas = []

    def __call__(self, argv, **kw):
        argv = [str(a) for a in argv]
        self.chamadas.append(argv)
        if argv[0] == "ffprobe":
            alvo = argv[-1]
            if alvo not in self.arquivos:
                return 1, "No such file"
            w, h, d = self.arquivos[alvo]
            streams = [{"width": w, "height": h}] if w else []
            return 0, json.dumps({"streams": streams, "format": {"duration": "%.3f" % d}})
        if argv[0] == "ffmpeg":
            saida = Path(argv[-1])
            saida.parent.mkdir(parents=True, exist_ok=True)
            t = float(argv[argv.index("-ss") + 1])
            if any("scale=1:1080" in a for a in argv):
                col = self.colunas(t) if self.colunas else coluna()
                img = Image.new("L", (1, len(col)))
                img.putdata(col)
            else:
                img = Image.new("RGB", (270, 480), (int(t * 7) % 255, 90, 160))
            img.save(str(saida))
            return 0, ""
        raise AssertionError("comando inesperado: %r" % argv)


@pytest.fixture
def proj(tmp_path):
    p = pastas.projeto("tres-horas", tmp_path / "_local").criar()
    p.avatar_mp4.write_bytes(b"avatar-bytes")
    p.voz_limpo.write_bytes(b"voz-bytes")
    return p


def midia(proj, av=(1080, 1920, 55.0), voz=55.2, colunas=None):
    return Midia({str(proj.avatar_mp4): av, str(proj.voz_limpo): (None, None, voz)}, colunas)


# --- fração útil (função pura) ------------------------------------------------------------------

def test_fracao_util_sem_barra_e_1():
    f, topo, base = C.fracao_util(coluna())
    assert f == pytest.approx(1.0, abs=0.001) and topo == 0 and base == 0


def test_fracao_util_com_barras():
    f, topo, base = C.fracao_util(coluna(100, 100))
    assert (topo, base) == (100, 100)
    assert f == pytest.approx(880 / 1080, abs=0.002)


def test_fracao_util_quadro_todo_uniforme_e_zero():
    assert C.fracao_util([0] * 1080)[0] == 0.0


def test_limites_vem_do_plano():
    assert C.LIMITE_FRACAO_UTIL == 0.93 and C.LIMITE_DIFERENCA_S == 1.0


# --- conferir -----------------------------------------------------------------------------------

def test_avatar_bom_passa_e_escreve_conferencia_e_prancha(proj):
    m = midia(proj, colunas=lambda t: coluna(20, 20))
    r = C.conferir(proj, executar=m, agora="2026-10-09T10:00:00-03:00")
    assert r["resultado"] == "aprovada" and r["reprovacoes"] == []
    assert r["avatar"] == {"arquivo": "avatar/avatar.mp4", "sha256": hashlib.sha256(b"avatar-bytes").hexdigest(),
                           "largura": 1080, "altura": 1920, "duracao_s": 55.0}
    assert r["voz"] == {"arquivo": "voz/limpo.mp3", "duracao_s": 55.2}
    assert r["diferenca_duracao_s"] == pytest.approx(0.2, abs=1e-6)
    assert r["fracao_util"] == pytest.approx(1040 / 1080, abs=0.002)
    assert r["aspecto"] == "9:16" and r["versao"] == 1
    gravado = json.loads(proj.avatar_conferencia.read_text(encoding="utf-8"))
    assert gravado == r
    assert r["prancha"]["arquivo"] == "avatar/boca.png"
    assert r["prancha"]["sha256"] == hashlib.sha256(proj.avatar_boca.read_bytes()).hexdigest()
    assert len(r["prancha"]["quadros_s"]) == 3


def test_prancha_da_boca_tem_3_quadros_lado_a_lado(proj):
    m = midia(proj)
    C.conferir(proj, executar=m)
    img = Image.open(str(proj.avatar_boca))
    assert img.size == (3 * 270, 480)
    extracoes = [a for a in m.chamadas if a[0] == "ffmpeg" and not any("scale=1:1080" in x for x in a)]
    assert len(extracoes) == 3


def test_reprova_fracao_util_abaixo_de_093(proj):
    m = midia(proj, colunas=lambda t: coluna(60, 60))       # 0,889
    r = C.conferir(proj, executar=m)
    assert r["resultado"] == "reprovada"
    assert any("fração útil" in x for x in r["reprovacoes"])
    assert json.loads(proj.avatar_conferencia.read_text(encoding="utf-8"))["resultado"] == "reprovada"


def test_barra_em_um_so_quadro_basta_para_reprovar(proj):
    def col(t):
        return coluna(150, 150) if t > 40 else coluna(5, 5)   # só o último quadro tem barra
    r = C.conferir(proj, executar=midia(proj, colunas=col))
    assert r["resultado"] == "reprovada"
    assert r["fracao_util"] == pytest.approx(780 / 1080, abs=0.002)    # o pior quadro manda


def test_duracao_exatamente_1s_de_diferenca_passa_e_acima_reprova(proj):
    ok = C.conferir(proj, executar=midia(proj, av=(1080, 1920, 56.2), voz=55.2))
    assert ok["resultado"] == "aprovada"
    ruim = C.conferir(proj, executar=midia(proj, av=(1080, 1920, 56.3), voz=55.2))
    assert ruim["resultado"] == "reprovada"
    assert any("duração" in x for x in ruim["reprovacoes"])


def test_avatar_mais_curto_que_a_voz_tambem_reprova(proj):
    r = C.conferir(proj, executar=midia(proj, av=(1080, 1920, 53.0), voz=55.2))
    assert r["resultado"] == "reprovada"


def test_dimensao_errada_reprova(proj):
    r = C.conferir(proj, executar=midia(proj, av=(1920, 1080, 55.0)))
    assert r["resultado"] == "reprovada"
    assert any("1080x1920" in x for x in r["reprovacoes"])


def test_aspecto_quadrado_espera_1080x1080(proj):
    r = C.conferir(proj, aspecto="1:1", executar=midia(proj, av=(1080, 1080, 55.0)))
    assert r["resultado"] == "aprovada" and r["aspecto"] == "1:1"


def test_varias_reprovacoes_aparecem_todas(proj):
    r = C.conferir(proj, executar=midia(proj, av=(720, 1280, 50.0), colunas=lambda t: coluna(200, 200)))
    assert len(r["reprovacoes"]) == 3


def test_insumo_ausente_e_erro_de_insumo_e_nao_escreve_nada(proj):
    proj.avatar_mp4.unlink()
    with pytest.raises(C.InsumoInvalido):
        C.conferir(proj, executar=midia(proj))
    assert not proj.avatar_conferencia.exists()


def test_voz_ausente(proj):
    proj.voz_limpo.unlink()
    with pytest.raises(C.InsumoInvalido):
        C.conferir(proj, executar=midia(proj))


def test_ffprobe_que_falha_ou_devolve_lixo_e_insumo_invalido(proj):
    with pytest.raises(C.InsumoInvalido):
        C.conferir(proj, executar=lambda argv, **kw: (1, "Invalid data"))
    with pytest.raises(C.InsumoInvalido):
        C.conferir(proj, executar=lambda argv, **kw: (0, "não é json"))


def test_avatar_sem_trilha_de_video_e_insumo_invalido(proj):
    m = Midia({str(proj.avatar_mp4): (None, None, 55.0), str(proj.voz_limpo): (None, None, 55.2)})
    with pytest.raises(C.InsumoInvalido):
        C.conferir(proj, executar=m)


# --- amarração com looks.aprovar ----------------------------------------------------------------

def test_conferencia_e_aceita_por_looks_aprovar_e_vence_se_mudar(proj):
    C.conferir(proj, executar=midia(proj))
    estado = proj.estado
    looks.adicionar("laranja", ID, "medio", estado=estado)
    rel = proj.avatar_conferencia.relative_to(estado).as_posix()
    look = looks.aprovar("laranja", rel, estado=estado)
    assert look["conferencia"]["sha256"] == looks.sha256_arquivo(proj.avatar_conferencia)
    assert looks.verificar("laranja", estado).aprovado
    # reconferir com outro avatar muda o arquivo (sha do avatar e instante): a aprovação vence
    proj.avatar_mp4.write_bytes(b"outro-avatar")
    C.conferir(proj, executar=midia(proj), agora="2026-10-09T11:00:00-03:00")
    assert not looks.verificar("laranja", estado).aprovado


def test_so_conferencia_aprovada_pode_ser_aprovada_pelo_aluno(proj):
    C.conferir(proj, executar=midia(proj, colunas=lambda t: coluna(200, 200)))
    assert C.conferencia_passou(proj.avatar_conferencia) is False
    C.conferir(proj, executar=midia(proj))
    assert C.conferencia_passou(proj.avatar_conferencia) is True
    assert C.conferencia_passou(proj.avatar_conferencia.parent / "nao.json") is False


# --- CLI ----------------------------------------------------------------------------------------

def test_cli_exit_0_1_2(proj, capsys):
    estado = str(proj.estado)
    assert C.main(["tres-horas", "--estado", estado], executar=midia(proj)) == 0
    assert "OK" in capsys.readouterr().out
    assert C.main(["tres-horas", "--estado", estado],
                  executar=midia(proj, colunas=lambda t: coluna(300, 300))) == 1
    assert "REPROVADO" in capsys.readouterr().out
    proj.avatar_mp4.unlink()
    assert C.main(["tres-horas", "--estado", estado], executar=midia(proj)) == 2
    assert "avatar.mp4" in capsys.readouterr().err
