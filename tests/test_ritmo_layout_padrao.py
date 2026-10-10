"""W7.Z: o ritmo com o split por padrão.

Com `insert horizontal sem layout = split`, todo insert sem preferência passou a nascer split, e a imagem só muda de verdade
na ENTRADA de cada insert (a saída de um split para o apresentador não é corte): o ritmo previsto caiu de 19,5 para 12,5
cortes/min e o medir_ritmo do render (piso de 16) reprovaria. O desenho do ritmo é alternar o LAYOUT entre as visitas (split e
tela cheia trocam ~60% dos pixels e REGISTRAM); com o padrão, essa alternância passa a valer também entre os BLOCOS de visita
única que o roteiro deixou sem preferência (`layout_padrao`). Layout escrito no roteiro nunca é trocado."""
import ritmo as R


def bloco(s, e, padrao=False, **kw):
    d = {"tipo": "insert", "s": s, "e": e, "texto": "x"}
    if padrao:
        d["layout_padrao"] = True
    d.update(kw)
    return d


def avatar(s, e):
    return {"tipo": "orig", "s": s, "e": e, "texto": "y"}


def layouts_dos_inserts(segs):
    return [sg.get("layout") for sg in segs if sg["tipo"] == "insert"]


def test_blocos_de_visita_unica_sem_preferencia_alternam_split_e_cheio():
    blocos = [avatar(0, 3), bloco(3, 7, True), avatar(7, 10), bloco(10, 14, True), avatar(14, 17), bloco(17, 21, True),
              avatar(21, 24), bloco(24, 28, True)]
    assert layouts_dos_inserts(R.plano_de_ritmo(blocos)) == ["split", "cheio", "split", "cheio"]


def test_layout_escrito_no_roteiro_nao_ganha_alternancia():
    blocos = [avatar(0, 3), bloco(3, 7), avatar(7, 10), bloco(10, 14), avatar(14, 17), bloco(17, 21)]
    assert layouts_dos_inserts(R.plano_de_ritmo(blocos)) == [None, None, None]


def test_bloco_escrito_entre_dois_sem_preferencia_nao_gasta_a_vez_de_ninguem():
    blocos = [avatar(0, 3), bloco(3, 7, True), avatar(7, 10), bloco(10, 14), avatar(14, 17), bloco(17, 21, True)]
    assert layouts_dos_inserts(R.plano_de_ritmo(blocos)) == ["split", None, "cheio"]


def test_a_alternancia_e_deterministica():
    blocos = [avatar(0, 3), bloco(3, 7, True), avatar(7, 10), bloco(10, 14, True)]
    assert R.plano_de_ritmo([dict(b) for b in blocos]) == R.plano_de_ritmo([dict(b) for b in blocos])


def test_bloco_com_teto_de_fonte_segue_a_vez_global():
    blocos = [avatar(0, 3), bloco(3, 7, True), avatar(7, 10), bloco(10, 18, True, dur_max=2.5)]
    segs = R.plano_de_ritmo(blocos)
    lays = [sg["layout"] for sg in segs if sg["tipo"] == "insert" and sg["bloco"] == 3]
    assert lays[0] == "cheio"            # a vez do 2º bloco sem preferência (o 1º foi split)


def test_o_gancho_continua_forcando_o_proprio_layout():
    blocos = [bloco(0, 9, True), avatar(9, 12)]
    segs = R.plano_de_ritmo(blocos)
    assert [sg["layout"] for sg in segs if sg["tipo"] == "insert"][0] == "split"


def test_bloco_com_teto_de_fonte_gasta_uma_vez_por_visita():
    """Duas visitas (split, cheio) gastam duas vezes: o bloco seguinte retoma o ciclo em split."""
    blocos = [avatar(0, 3), bloco(3, 15, True, dur_max=3.0), avatar(15, 18), bloco(18, 22, True)]
    segs = R.plano_de_ritmo(blocos)
    do_teto = [sg["layout"] for sg in segs if sg["tipo"] == "insert" and sg["bloco"] == 1]
    seguinte = [sg["layout"] for sg in segs if sg["tipo"] == "insert" and sg["bloco"] == 3]
    assert len(do_teto) == 2 and do_teto == ["split", "cheio"] and seguinte == ["split"]
