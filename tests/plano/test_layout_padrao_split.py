"""W7.Z, item 6: o plano mostra o layout que o motor vai usar. Insert horizontal sem layout, no modo avatar, é `split`
(tratamento `split`); `cheio` escrito continua cheio (tratamento `moldura`); asset em pé sem layout segue cheio."""
from tests.plano.test_medir import ROTEIRO, medir_exemplo


def blocos_de_insert(plano):
    return {b["insert"]: b for b in plano["blocos"] if b["tipo"] == "insert"}


def tratamentos(plano):
    return {m["chave"]: m["tratamento"] for m in plano["mapa_inserts"]}


def test_horizontal_sem_layout_vira_split_no_plano(tmp_path):
    _, plano, _ = medir_exemplo(tmp_path)
    b = blocos_de_insert(plano)
    assert b["painel"]["layout"] == "split" and b["automacao"]["layout"] == "split"      # 1280x644 e 958x720
    assert b["planilha"]["layout"] == "split"                                              # já escrito
    assert tratamentos(plano) == {"painel": "split", "planilha": "split", "automacao": "split"}


def test_cheio_escrito_continua_cheio_e_em_moldura(tmp_path):
    roteiro = ROTEIRO.replace("[insert: painel |", "[insert: painel | cheio |")
    _, plano, _ = medir_exemplo(tmp_path, roteiro=roteiro)
    assert blocos_de_insert(plano)["painel"]["layout"] == "cheio"
    assert tratamentos(plano)["painel"] == "moldura"
    assert tratamentos(plano)["automacao"] == "split"


def test_asset_em_pe_sem_layout_segue_cheio(tmp_path):
    _, plano, _ = medir_exemplo(tmp_path, medidas={"painel": (720, 1280, 8.0)})
    assert blocos_de_insert(plano)["painel"]["layout"] == "cheio"
    assert tratamentos(plano)["painel"] == "cheio"


def test_o_split_do_padrao_conta_como_split_nos_cortes_previstos(tmp_path):
    """`cortes_previstos` não conta como corte a saída de um insert em split para o apresentador (ele já estava na tela):
    o layout resolvido tem que chegar lá, senão o plano prevê cortes que o render não entrega."""
    _, com_split, _ = medir_exemplo(tmp_path / "a")
    roteiro_cheio = (ROTEIRO.replace("[insert: painel |", "[insert: painel | cheio |")
                     .replace("[insert: automacao]", "[insert: automacao | cheio]"))
    _, com_cheio, _ = medir_exemplo(tmp_path / "b", roteiro=roteiro_cheio)
    assert com_split["ritmo"]["cortes_min"] <= com_cheio["ritmo"]["cortes_min"]


def test_imagem_estatica_horizontal_sem_layout_segue_como_imagem(tmp_path):
    _, plano, _ = medir_exemplo(tmp_path, medidas={"painel": (1200, 800, 0.0)})
    assert blocos_de_insert(plano)["painel"]["layout"] == "cheio"
    assert tratamentos(plano)["painel"] == "imagem"


def test_o_ritmo_do_plano_alterna_split_e_cheio_entre_os_blocos_sem_preferencia(tmp_path):
    """Os blocos 0 e 5 do exemplo ficaram sem layout: as visitas deles alternam, e o `planilha` (split escrito) não entra."""
    _, plano, _ = medir_exemplo(tmp_path)
    assert plano["ritmo"]["cortes_min"] > 0
    from tests.plano.test_medir import PADRAO_DO_EXEMPLO
    assert PADRAO_DO_EXEMPLO == {0, 5}
