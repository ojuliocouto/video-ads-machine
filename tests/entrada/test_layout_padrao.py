"""W7.Z, item 6: insert HORIZONTAL sem layout declarado, no modo avatar, vira SPLIT (insert em cima, rosto embaixo).

Antes, "sem preferência" caía em tela cheia: o card de um 16:9 ficava pequeno no meio do quadro e metade da tela era vazia
e escura (regra do dono: insert ocupa a tela). Agora a preferência de layout só decide quando o roteiro a escreve:
  - `split`, `cheio` e `pip` escritos valem como sempre;
  - sem preferência, asset horizontal (aspecto a partir de 1,05) no modo avatar: `split`;
  - sem preferência e asset em pé, imagem ou sem medida do arquivo: o padrão de antes (nada no config)."""
import pytest

from entrada import para_motor
from tests.entrada.test_para_motor import Base, projeto_base


def sondar(largura, altura):
    return lambda arquivo: {"largura": largura, "altura": altura, "duracao_s": 5.0}


ROTEIRO = ("[insert: demo | hook: VOCÊ PERDE | 3 horas por dia | NISSO AQUI] Você perde três horas por dia nisso aqui.\n"
           "[apresentador] E eu sei porque eu fazia igual.\n"
           "[cta | KEY: SAIBA MAIS] Toque em saiba mais.\n")


@pytest.mark.parametrize("declarado,modo,aspecto,esperado", [
    (None, "avatar", 1280 / 644.0, "split"),
    (None, "avatar", 958 / 720.0, "split"),
    (None, "avatar", 1.05, "split"),
    (None, "avatar", 1.04, None),
    (None, "avatar", 0.5625, None),
    (None, "avatar", 1.0, None),
    (None, "avatar", None, None),
    (None, "gravado", 1.78, None),
    ("cheio", "avatar", 1.78, "cheio"),
    ("split", "avatar", 0.56, "split"),
    ("pip", "avatar", 1.78, "pip"),
])
def test_layout_efetivo(declarado, modo, aspecto, esperado):
    assert para_motor.layout_efetivo(declarado, modo, aspecto) == esperado


class TestLayoutPadraoNoMotor(Base):

    def entrada(self, roteiro, largura, altura):
        motor = self.gerar(roteiro, sondar=sondar(largura, altura))
        return next(iter(motor.inserts.values()))

    def test_horizontal_sem_layout_vira_split_no_inserts_json(self):
        assert self.entrada(ROTEIRO, 1280, 644).get("split") is True

    def test_cheio_escrito_no_roteiro_nao_vira_split(self):
        e = self.entrada(ROTEIRO.replace("[insert: demo |", "[insert: demo | cheio |"), 1280, 644)
        assert "split" not in e and "pip" not in e

    def test_split_escrito_continua_split_em_asset_em_pe(self):
        e = self.entrada(ROTEIRO.replace("[insert: demo |", "[insert: demo | split |"), 720, 1280)
        assert e.get("split") is True

    def test_asset_em_pe_sem_layout_segue_sem_preferencia(self):
        assert "split" not in self.entrada(ROTEIRO, 720, 1280)

    def test_arquivo_que_nao_da_para_medir_segue_sem_preferencia(self):
        # o `sondar` padrão (ffprobe) não lê o arquivo vazio do teste: sem medida, o padrão de antes
        motor = self.gerar(ROTEIRO)
        assert "split" not in next(iter(motor.inserts.values()))

    def test_sondar_que_levanta_nao_derruba_o_motor(self):
        def quebra(arquivo):
            raise OSError("ffprobe sumiu")
        motor = self.gerar(ROTEIRO, sondar=quebra)
        assert "split" not in next(iter(motor.inserts.values()))


def test_imagem_estatica_horizontal_sem_layout_nao_vai_para_o_split():
    """Imagem tem Ken Burns próprio (`fc_imagem`); mandá-la ao split quebraria o insert de uma imagem só."""
    class Imagem(Base):
        def runTest(self):
            pass
    caso = Imagem()
    caso.setUp()
    try:
        motor = caso.gerar(ROTEIRO, sondar=lambda arquivo: {"largura": 1200, "altura": 800, "duracao_s": 0.0})
        assert "split" not in next(iter(motor.inserts.values()))
    finally:
        caso.tearDown()
