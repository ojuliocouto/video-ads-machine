"""W3.C: gate_fala_roteiro. A fala (ASR do áudio limpo) tem que cobrir o roteiro.md.

O ASR é simulado (uma função que devolve palavras); o áudio é só um arquivo que existe. Nada de
mídia, nada de rede. A regra de equivalência é o glossário do aluno: o gate nunca troca uma
palavra por conta própria (o revisor antigo trocava "cloud" por "Claude" em qualquer anúncio).
"""
import subprocess
import sys
from pathlib import Path

import pytest

from gates import gate_fala_roteiro as G
from projeto import glossario, modelo, pastas, status

RAIZ = Path(__file__).resolve().parents[2]
SLUG = "anuncio"


def palavras_do_texto(texto):
    return [{"text": p, "start": i * 0.3, "end": i * 0.3 + 0.25} for i, p in enumerate(texto.split())]


def roteiro_de(fala_por_bloco):
    """Roteiro dirigido: o primeiro bloco é apresentador, o último é o cta."""
    linhas = []
    for i, fala in enumerate(fala_por_bloco):
        if i == len(fala_por_bloco) - 1:
            linhas.append("[cta | KEY: SAIBA MAIS] " + fala)
        else:
            linhas.append("[apresentador] " + fala)
    return "\n".join(linhas) + "\n"


def montar(tmp_path, fala_por_bloco, modo="gravado"):
    estado = tmp_path / "_local"
    pj = pastas.projeto(SLUG, estado).criar()
    modelo.escrever(pj.projeto_json, modelo.minimo(SLUG, modo, sem_trilha="sem trilha no teste")
                    if modo != "avatar" else modelo.minimo(SLUG, modo, look="meu-look", sem_trilha="sem trilha no teste"))
    pj.roteiro.write_text(roteiro_de(fala_por_bloco), encoding="utf-8")
    pj.voz_dir.mkdir(parents=True, exist_ok=True)
    pj.voz_limpo.write_bytes(b"audio-qualquer")
    return estado, pj


def asr_com(texto):
    """Um ASR que diz `texto` para o áudio limpo, sempre."""
    chamadas = []

    def asr(caminho):
        chamadas.append(Path(caminho))
        return palavras_do_texto(texto)
    asr.chamadas = chamadas
    return asr


# Um roteiro de 64 palavras distintas o bastante para o alinhamento não se confundir.
BASE = ("Você perde três horas por dia nisso aqui e eu sei porque eu fazia igual todo santo dia "
        "O problema não é falta de tempo é que cada tarefa repetida come um pedaço da sua agenda "
        "Enquanto isso a proposta atrasa o cliente esfria e a venda escapa pela porta dos fundos "
        "Com uma automação simples tudo roda sozinho enquanto você atende quem importa de verdade "
        "Toque em saiba mais")


def em_blocos(texto):
    """O texto em 3 blocos de fala (sem cortar palavra): o roteiro dirigido mínimo."""
    ws = texto.split()
    a, b = len(ws) // 3, 2 * len(ws) // 3
    return [" ".join(ws[:a]), " ".join(ws[a:b]), " ".join(ws[b:])]


BASE_BLOCOS = em_blocos(BASE)


def sem_palavras(texto, indices):
    ws = texto.split()
    return " ".join(w for i, w in enumerate(ws) if i not in set(indices))


def test_fala_igual_ao_roteiro_passa(tmp_path):
    estado, pj = montar(tmp_path, BASE_BLOCOS)
    r = G.rodar(pj, asr=asr_com(BASE))
    assert r.ok, r.motivo
    assert r.detalhes["estado"] == "PASS"
    assert r.detalhes["palavras_roteiro"] == len(BASE.split())
    assert r.detalhes["faltando"] == 0


def test_acento_maiuscula_e_pontuacao_nao_contam(tmp_path):
    estado, pj = montar(tmp_path, BASE_BLOCOS)
    fala = BASE.lower().replace("você", "voce").replace("três", "tres").replace("aqui", "aqui,")
    r = G.rodar(pj, asr=asr_com(fala))
    assert r.ok, r.motivo


def test_uma_palavra_faltando_em_64_passa_abaixo_de_2_por_cento(tmp_path):
    """1 de 64 palavras é 1,6%: abaixo do limite de 2%."""
    assert len(BASE.split()) >= 51      # 1 palavra tem que valer 2% ou menos
    estado, pj = montar(tmp_path, BASE_BLOCOS)
    r = G.rodar(pj, asr=asr_com(sem_palavras(BASE, [10])))
    assert r.ok, r.motivo
    assert r.detalhes["faltando"] == 1


def test_duas_palavras_soltas_em_64_reprovam_acima_de_2_por_cento(tmp_path):
    estado, pj = montar(tmp_path, BASE_BLOCOS)
    r = G.rodar(pj, asr=asr_com(sem_palavras(BASE, [10, 30])))
    assert not r.ok
    assert "2%" in r.motivo
    assert r.detalhes["faltando"] == 2


def test_sequencia_de_3_palavras_sumida_reprova_mesmo_abaixo_de_2_por_cento(tmp_path):
    """3 palavras seguidas em 200 são 1,5%, mas a fala perdeu um pedaço de frase."""
    roteiro = " ".join("p%03d" % i for i in range(200))
    estado, pj = montar(tmp_path, em_blocos(roteiro))
    fala = sem_palavras(roteiro, [50, 51, 52])
    r = G.rodar(pj, asr=asr_com(fala))
    assert not r.ok
    assert r.detalhes["maior_sequencia"] == 3
    assert "3 palavras seguidas" in r.motivo


def test_duas_palavras_seguidas_em_200_passam(tmp_path):
    roteiro = " ".join("p%03d" % i for i in range(200))
    estado, pj = montar(tmp_path, em_blocos(roteiro))
    r = G.rodar(pj, asr=asr_com(sem_palavras(roteiro, [50, 51])))
    assert r.ok, r.motivo
    assert r.detalhes["maior_sequencia"] == 2


def test_palavra_a_mais_na_fala_nao_reprova(tmp_path):
    """O gate cobra o que SUMIU do roteiro; improviso a mais fica no relatório."""
    estado, pj = montar(tmp_path, BASE_BLOCOS)
    fala = BASE.replace("Com uma automação", "Olha, com uma automação")
    r = G.rodar(pj, asr=asr_com(fala))
    assert r.ok, r.motivo
    assert r.detalhes["extras"] >= 1


# --- troca de palavra: só o glossário do aluno autoriza -----------------------------------------

TEXTO_CLAUDE = ("Eu uso o Claude todo dia para montar propostas e o Claude ainda revisa o texto "
                "enquanto o Claude Code escreve a automação inteira que roda sozinha no servidor "
                "da empresa sem ninguém precisar abrir uma planilha ou mandar mensagem manual hoje")


def test_nunca_troca_cravada_cloud_nao_vira_claude(tmp_path):
    """O ASR ouviu 'cloud'. Sem o glossário declarar, é palavra faltando, não correção automática."""
    estado, pj = montar(tmp_path, em_blocos(TEXTO_CLAUDE))
    fala = TEXTO_CLAUDE.replace("Claude", "cloud")
    r = G.rodar(pj, asr=asr_com(fala))
    assert not r.ok
    assert r.detalhes["faltando"] == 3        # os três "Claude"
    assert "Claude" in r.motivo or "claude" in r.motivo


def test_cloud_no_roteiro_e_cloud_na_fala_passa_sem_reescrever_nada(tmp_path):
    """Aluno que fala de computação em nuvem: 'cloud' é o certo, e o arquivo fica como está."""
    texto = TEXTO_CLAUDE.replace("Claude", "cloud")
    estado, pj = montar(tmp_path, em_blocos(texto))
    antes = pj.roteiro.read_bytes()
    r = G.rodar(pj, asr=asr_com(texto))
    assert r.ok, r.motivo
    assert pj.roteiro.read_bytes() == antes


def test_variante_declarada_no_glossario_conserta_o_asr(tmp_path):
    estado, pj = montar(tmp_path, em_blocos(TEXTO_CLAUDE))
    glossario.adicionar_termo("Claude", variantes=["cloud"], estado=estado)
    r = G.rodar(pj, asr=asr_com(TEXTO_CLAUDE.replace("Claude", "cloud")))
    assert r.ok, r.motivo


TEXTO_PARA = ("Eu chamo para ver o que tem para hoje e depois eu volto para casa porque o dia foi longo "
              "e a gente ainda precisa decidir como vai fazer com o resto do trabalho que ficou pela metade "
              "na sexta passada sem que ninguém reclamasse de nada no grupo")


def test_equivalencia_so_vale_se_o_glossario_declarou(tmp_path):
    estado, pj = montar(tmp_path, em_blocos(TEXTO_PARA))
    fala = TEXTO_PARA.replace("para", "pra")
    sem = G.rodar(pj, asr=asr_com(fala))
    assert not sem.ok
    assert sem.detalhes["faltando"] == 3
    glossario.adicionar_equivalencia("para", "pra", estado=estado)
    com = G.rodar(pj, asr=asr_com(fala))
    assert com.ok, com.motivo


def test_equivalencia_vale_do_roteiro_para_a_fala_nunca_ao_contrario(tmp_path):
    """Declarado: roteiro 'para' pode ser falado 'pra'. Roteiro 'pra' e fala 'para' não está declarado."""
    texto = TEXTO_PARA.replace("para", "pra")
    estado, pj = montar(tmp_path, em_blocos(texto))
    glossario.adicionar_equivalencia("para", "pra", estado=estado)
    r = G.rodar(pj, asr=asr_com(TEXTO_PARA))
    assert not r.ok
    assert r.detalhes["faltando"] == 3


# --- função pura: o alinhamento ------------------------------------------------------------------

def test_comparar_conta_faltando_e_maior_sequencia():
    roteiro = "a b c d e f g h".split()
    fala = "a b e f h".split()
    r = G.comparar(roteiro, fala, equivalencias=[])
    assert r.faltando_idx == [2, 3, 6]
    assert r.maior_sequencia == 2


def test_comparar_equivalencia_de_varias_palavras():
    roteiro = "eu vou para o mercado".split()
    fala = "eu vou pro mercado".split()
    assert G.comparar(roteiro, fala, equivalencias=[(["para", "o"], ["pro"])]).faltando_idx == []
    assert G.comparar(roteiro, fala, equivalencias=[]).faltando_idx == [2, 3]


def test_limiares_vem_de_constantes_com_o_numero_do_plano():
    assert G.FALTANDO_MAX == 0.02
    assert G.SEQUENCIA_MAX == 3        # 3 palavras ou mais sumidas reprova


# --- insumos -------------------------------------------------------------------------------------

def test_sem_roteiro_e_insumo_invalido(tmp_path):
    estado, pj = montar(tmp_path, BASE_BLOCOS)
    pj.roteiro.unlink()
    with pytest.raises(G.InsumoInvalido):
        G.rodar(pj, asr=asr_com(BASE))


def test_roteiro_fora_da_convencao_e_insumo_invalido(tmp_path):
    estado, pj = montar(tmp_path, BASE_BLOCOS)
    pj.roteiro.write_text("[desenhar bonito] Isso não é um tipo de bloco.\n", encoding="utf-8")
    with pytest.raises(G.InsumoInvalido) as e:
        G.rodar(pj, asr=asr_com(BASE))
    assert "roteiro" in str(e.value)


def test_sem_audio_limpo_e_insumo_invalido(tmp_path):
    estado, pj = montar(tmp_path, BASE_BLOCOS)
    pj.voz_limpo.unlink()
    with pytest.raises(G.InsumoInvalido) as e:
        G.rodar(pj, asr=asr_com(BASE))
    assert "limpo.mp3" in str(e.value)


def test_transcricao_vazia_e_insumo_invalido_nao_reprovacao(tmp_path):
    """ASR que devolve nada é ferramenta quebrada (ou áudio mudo), não 'faltou 100% da fala'."""
    estado, pj = montar(tmp_path, BASE_BLOCOS)
    with pytest.raises(G.InsumoInvalido) as e:
        G.rodar(pj, asr=asr_com(""))
    assert "transcrição vazia" in str(e.value)


# --- CLI -----------------------------------------------------------------------------------------

def test_cli_passa_exit_0_e_registra(tmp_path, capsys):
    estado, pj = montar(tmp_path, BASE_BLOCOS)
    assert G.main([SLUG, "--estado", str(estado)], asr=asr_com(BASE)) == 0
    atual = status.ler(pj)["atual"]
    assert (atual["etapa"], atual["estado"]) == ("gate_fala_roteiro", "ok")
    assert atual["detalhes"]["faltando"] == 0


def test_cli_reprova_exit_1_e_registra(tmp_path, capsys):
    estado, pj = montar(tmp_path, BASE_BLOCOS)
    assert G.main([SLUG, "--estado", str(estado)], asr=asr_com(sem_palavras(BASE, [10, 30]))) == 1
    atual = status.ler(pj)["atual"]
    assert (atual["etapa"], atual["estado"]) == ("gate_fala_roteiro", "falhou")
    assert "2%" in atual["motivo"]


def test_cli_insumo_invalido_exit_2_e_registra(tmp_path, capsys):
    estado, pj = montar(tmp_path, BASE_BLOCOS)
    pj.voz_limpo.unlink()
    assert G.main([SLUG, "--estado", str(estado)], asr=asr_com(BASE)) == 2
    atual = status.ler(pj)["atual"]
    assert (atual["etapa"], atual["estado"]) == ("gate_fala_roteiro", "bloqueado")


def test_roda_como_script_e_sai_2_sem_projeto(tmp_path):
    estado = tmp_path / "_local"
    estado.mkdir()
    p = subprocess.run([sys.executable, str(RAIZ / "scripts" / "gates" / "gate_fala_roteiro.py"),
                        "nao-existe", "--estado", str(estado)], capture_output=True, text=True)
    assert p.returncode == 2, p.stdout + p.stderr


def test_o_gate_nao_tem_troca_cravada_no_codigo():
    """Varredura estática: o gate novo não carrega a troca do revisor antigo."""
    fonte = (RAIZ / "scripts" / "gates" / "gate_fala_roteiro.py").read_text(encoding="utf-8").lower()
    assert "cloud" not in fonte
