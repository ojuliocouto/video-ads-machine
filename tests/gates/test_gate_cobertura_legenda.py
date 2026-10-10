"""W7.W (A2): gate_cobertura_legenda. Toda palavra falada FORA das janelas de lettering, gancho e CTA tem texto na tela.

O defeito que o gate existe para pegar (anúncio da prova, v2): o CTA entrou ~3 s antes de a voz dizer o botão e levou junto a
legenda do bloco anterior: 24 palavras faladas sem texto nenhum, 6,6 s, e ninguém notou porque cada janela olhada sozinha
estava "dentro do limite". O gate lê a timeline (o que está declarado na tela, no relógio da footage a 1x) e as palavras do
alinhamento, e reprova quando mais de 3% das palavras que NÃO estão em lettering, gancho ou CTA ficam sem texto, ou quando o
CTA entra antes do início do bloco cta.

10/10/2026 (decisão do dono): durante o CTA NÃO há legenda. O CTA é lettering ("lettering e legenda nunca juntos"), então a
janela do CTA é isenta como a do lettering: a palavra falada sob o CTA não é contada nem penalizada. Uma versão com a legenda
acima da pílula foi desfeita (empilhava texto no peito e lia 3:1 no gate de contraste).
"""
import json
import pytest

from gates import gate_cobertura_legenda as G


def palavras(*tempos):
    """[(início, fim)] -> palavras do alinhamento ({t, s, e})."""
    return [{"t": "p%d" % i, "s": s, "e": e} for i, (s, e) in enumerate(tempos)]


def fala(ini, fim, passo=0.4):
    n = int(round((fim - ini) / passo))
    return [(round(ini + k * passo, 3), round(ini + (k + 1) * passo - 0.05, 3)) for k in range(n)]


def legenda(s, e, suprimida=False):
    return {"s": s, "e": e, "texto": "x", "palavras": [], "posicao": "base", "suprimida": suprimida}


def timeline(legendas, cta_inicio=18.0, cta_bloco=18.0, dur=22.0, hook=(0.0, 2.0), letterings=()):
    return {"relogio": {"a0": 0.0, "aceleracao": 1.0, "fps": 30}, "duracao_s": dur,
            "hook": {"s": hook[0], "e": hook[1]},
            "letterings": [{"s": s, "d": d, "cta": False} for s, d in letterings],
            "legendas": legendas,
            "blocos": [{"i": 0, "tipo": "apresentador", "s": 0.0, "e": cta_bloco},
                       {"i": 1, "tipo": "cta", "s": cta_bloco, "e": dur}],
            "cta": {"inicio": cta_inicio, "logo": cta_inicio, "label": "x", "sem_lead": False}}


def cobertura_total():
    """Legenda contínua de 2 a 18 s, gancho de 0 a 2 s e CTA de 18 s ao fim."""
    return timeline([legenda(2.0 + k, 3.0 + k) for k in range(16)])


def test_legenda_continua_com_gancho_e_cta_passa():
    g = G.rodar(cobertura_total(), palavras(*fala(0.0, 22.0)))
    assert g["resultado"] == "PASS" and g["saida"] == 0, g
    assert g["medido"]["sem_texto"] == 0


def test_o_fecho_sem_legenda_porque_o_cta_entrou_cedo_reprova():
    """O caso da v2: o CTA declarado em 12 s (a volta ao avatar), o bloco cta só em 18 s, a legenda corta em 12 s e as
    palavras de 12 a 18 s ficam sem texto. A janela do CTA para o gate começa no BLOCO cta, não no `cta.inicio` declarado."""
    leg = [legenda(2.0 + k, 3.0 + k) for k in range(10)]            # legenda de 2 a 12 s
    g = G.rodar(timeline(leg, cta_inicio=12.0, cta_bloco=18.0), palavras(*fala(0.0, 22.0)))
    assert g["resultado"] == "REPROVA" and g["saida"] == 1
    assert g["medido"]["percentual"] > 3.0
    assert g["medido"]["sem_texto"] >= 10
    assert "sem texto" in g["motivo"]


def test_cta_antes_do_bloco_cta_reprova_mesmo_com_a_legenda_em_dia():
    leg = [legenda(2.0 + k, 3.0 + k) for k in range(16)]
    g = G.rodar(timeline(leg, cta_inicio=16.0, cta_bloco=18.0), palavras(*fala(0.0, 22.0)))
    assert g["resultado"] == "REPROVA"
    assert "antes do bloco cta" in g["motivo"] and g["medido"]["cta_antes_do_bloco_s"] == pytest.approx(2.0)


def test_cta_na_ancora_depois_do_inicio_do_bloco_passa():
    leg = [legenda(2.0 + k, 3.0 + k) for k in range(16)] + [legenda(18.0, 18.6)]
    g = G.rodar(timeline(leg, cta_inicio=18.6, cta_bloco=18.0), palavras(*fala(0.0, 22.0)))
    assert g["resultado"] == "PASS", g


def test_legenda_suprimida_nao_conta_como_texto_na_tela():
    leg = [legenda(2.0 + k, 3.0 + k, suprimida=(5 <= k <= 9)) for k in range(16)]
    g = G.rodar(timeline(leg), palavras(*fala(0.0, 22.0)))
    assert g["resultado"] == "REPROVA" and g["medido"]["sem_texto"] >= 8


def test_palavra_dentro_de_lettering_ou_gancho_ou_cta_nao_precisa_de_legenda():
    # nenhuma legenda: a fala toda cai no gancho (0 a 2), num lettering (2 a 16) e no CTA (a partir de 16)
    t = timeline([], cta_inicio=16.0, cta_bloco=16.0, letterings=[(2.35, 13.3)])
    g = G.rodar(t, palavras(*fala(0.0, 22.0)))
    assert g["resultado"] == "PASS", g
    assert g["medido"]["palavras_avaliadas"] < g["medido"]["palavras"]


def test_a_folga_do_lettering_tambem_e_isenta_a_legenda_sai_de_proposito():
    """A legenda e o lettering não dividem a tela: a legenda sai FOLGA_LETT antes e volta FOLGA_LETT depois. Palavra nessa
    folga não é buraco."""
    from overlay import legendas
    assert G.FOLGA_LETTERING_S == legendas.FOLGA_LETT
    leg = [legenda(2.0, 6.0), legenda(11.6, 18.0)]                    # buraco de 6 a 11,6 s
    t = timeline(leg, letterings=[(6.35, 4.9)])                       # lettering de 6,35 a 11,25 s (folga: 6 a 11,6)
    g = G.rodar(t, palavras(*fala(0.0, 22.0)))
    assert g["resultado"] == "PASS", g


def test_vao_curto_entre_dois_grupos_de_legenda_nao_e_palavra_perdida():
    """Entre um grupo e o seguinte há um piscar de até 0,5 s (a troca de layout, o piso de 0,2 s do grupo): a palavra que
    cai nele tem texto logo antes e logo depois."""
    leg = [legenda(2.0, 6.0), legenda(6.4, 18.0)]                     # vão de 0,4 s
    g = G.rodar(timeline(leg), palavras((6.1, 6.3), *fala(7.0, 22.0)))
    assert g["resultado"] == "PASS", g
    leg_longo = [legenda(2.0, 6.0), legenda(6.9, 18.0)]               # vão de 0,9 s: a palavra de 6,1 a 6,3 fica sem texto
    g2 = G.rodar(timeline(leg_longo), palavras((6.1, 6.3), (6.4, 6.6), (6.6, 6.8)))
    assert g2["medido"]["sem_texto"] == 3


def test_ate_3_por_cento_sem_texto_passa_e_acima_reprova():
    leg = [legenda(2.0, 11.0), legenda(12.0, 18.0)]                   # 1 s sem texto: 2 palavras de 0,4 s em ~40
    pal = palavras(*fala(2.0, 18.0))
    g = G.rodar(timeline(leg), pal)
    assert g["medido"]["sem_texto"] == 2
    esperado = 100.0 * 2 / g["medido"]["palavras_avaliadas"]
    assert g["medido"]["percentual"] == pytest.approx(esperado, abs=0.05)
    assert (g["resultado"] == "PASS") == (esperado <= G.MAX_SEM_TEXTO_PCT)


def test_sem_palavras_ou_timeline_ruim_e_erro_de_insumo_nao_pass():
    assert G.rodar(cobertura_total(), [])["resultado"] == "ERRO"
    assert G.rodar({"duracao_s": 3}, palavras((0, 1)))["resultado"] == "ERRO"
    assert G.rodar("lixo", palavras((0, 1)))["saida"] == 2


def test_o_gate_vem_no_formato_do_laudo():
    g = G.rodar(cobertura_total(), palavras(*fala(0.0, 22.0)))
    assert g["nome"] == "gate_cobertura_legenda" and g["etapa"] == "depois"
    assert G.MAX_SEM_TEXTO_PCT == 3.0 and set(g["limiar"]) >= {"max_sem_texto_pct", "vao_ponte_s"}
    json.dumps(g)


def test_cli_le_a_timeline_e_o_alinhamento_e_sai_com_o_codigo_do_gate(tmp_path, capsys):
    tl = tmp_path / "timeline.json"
    al = tmp_path / "alinhamento.json"
    tl.write_text(json.dumps(timeline([legenda(2.0, 6.0)], cta_inicio=12.0, cta_bloco=18.0)), encoding="utf-8")
    al.write_text(json.dumps({"palavras": palavras(*fala(0.0, 22.0))}), encoding="utf-8")
    assert G.main(["--timeline", str(tl), "--alinhamento", str(al)]) == 1
    assert "REPROVA" in capsys.readouterr().out
