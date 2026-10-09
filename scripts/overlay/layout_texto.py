"""Onde o texto de tela pousa em cada layout (avatar cheio, tela dividida, insert).

É a FONTE ÚNICA das faixas de legenda e das regras de fronteira. Um quadro 1080x1920 tem três
posições de legenda, e a escolha depende do que está embaixo dela naquele instante:

    padrão   avatar cheio: cai no peito             y 1290 a 1500
    baixa    insert (de tela cheia ou com texto próprio): desce para o rodapé    y 1370 a 1520
    costura  tela dividida: a emenda entre os dois painéis, nem na testa nem na boca   y 963 a 1106

As faixas saem do CSS (`#caps .cgrp` bottom 475, `.cgrp-baixa` 330, `.cgrp-costura` 790) com folga
para os dois lados, e batem com as faixas que o gate de contraste mede no arquivo entregue. A costura é
a TINTA medida no render real (W4.D: `bottom:790px` com padding de 24 px pinta de y 963 a 1106); a faixa
antiga de 1000 a 1130 e o comentário do CSS diziam coisas diferentes, e o gate de geometria lia uma e o
render pintava a outra (pendência 12.3, unificada na W5.A).

REGRA DA FRONTEIRA. Um grupo de legenda que ATRAVESSA a troca de layout não tem posição boa: no
split só a costura escapa do rosto, e no avatar cheio é a costura que cai nele. Escolher um lado
sempre deixa o outro errado, e a medição provou nas duas pontas (por "meio" o "Code." pegou 3,90%
do rosto; por "60% dentro" a "pagina completamente diferente" pegou 4,2% do outro lado). Então o
grupo não atravessa: vira DOIS, um de cada lado, cada um com a classe do seu layout; se qualquer
fatia ficar curta demais (abaixo de PISO_FATIA), apara o grupo inteiro para o lado dominante.

O RELÓGIO é o da footage (28/08/2026). Os dois motores derivam os spans por caminhos diferentes e
não batem (o overlay fechava o split do bloco 2 em 14,37 e a footage só saía dele em 14,45, com
a deriva crescendo até 1,07 s no fim de um anúncio de 2 min). Toda decisão de POSIÇÃO de texto é
sobre o que está NA TELA, e quem põe na tela é a footage: quando o json dela existe, as janelas de
split vêm de lá. A W3.A troca isso por uma `timeline.json` única.
"""
import json

from caminhos import V1

# faixa (y0, y1) de cada classe de legenda no quadro 1080x1920
FAIXA_LEGENDA = {"costura": (963, 1106), "baixa": (1370, 1520), "padrao": (1290, 1500)}

GUARDA_MOTOR = 0.12       # banda de guarda na fronteira (resíduo de arredondamento entre os motores)
GUARDA_POS_SPLIT = 0.18   # grupo que nasce a menos disso do fim do split é empurrado para depois
PISO_FATIA = 0.30         # fatia de legenda abaixo disso não existe: apara tudo para um lado
PONTA_MIN = 0.12          # borda a menos disso da ponta do grupo: não dá para cortar em dois
MARGEM_SEM_LEAD = 0.35    # grupo que nasce a menos disso de uma borda não antecipa o fade-in
FRACAO_COSTURA = 0.60     # fração do grupo dentro do split que decide a costura
QUEIXO_FECHADO = 0.60     # queixo abaixo dessa fração da altura: não sobra peito para a legenda padrão
SOBREPOSICAO_RELOGIO = 0.05   # janela da footage só vale se encostar mais que isso numa do overlay
PLANO_FECHADO = "fechado"     # o `plano` de um look no looks.json do aluno (contratos/looks.schema.json)


def classe_do_grupo(g):
    """A classe de legenda do grupo: costura tem prioridade sobre baixa (no split a posição baixa cai
    na boca do apresentador, que é o defeito que ela deveria evitar)."""
    return "costura" if g.get("costura") else ("baixa" if g.get("baixa") else "padrao")


def janelas_por_visita(visitas):
    """(janelas_split, janelas_texto, mapa_insert) a partir das visitas de insert.

    - split: só as fatias que continuam em tela dividida (o resto do bloco voltou para o avatar e
      tem que ser tratado como avatar);
    - texto: insert de tela cheia, fatia `cheio` de um insert split, e insert com texto próprio. A
      posição padrão da legenda é calibrada para o AVATAR, onde cai no peito; sobre um insert cai no
      MEIO do conteúdo. Insert existe para ser visto, então a legenda desce para o rodapé;
    - mapa_insert: janela -> fonte, start e velocidade, para medir o fundo NO INSTANTE de cada grupo
      (um insert de gravação de tela que abre numa página branca rola para uma área escura no meio).
    """
    janelas_split, janelas_texto, mapa_insert = [], [], []
    for v in visitas:
        icfg = v.icfg
        if icfg.get("split"):
            for _a, _b2 in v.meus:
                _par = (round(_a, 2), round(min(_b2, v.e), 2))
                # fatia sem o apresentador embaixo se comporta como insert de tela cheia
                (janelas_texto if (round(_a, 2), round(_b2, 2)) in v.cheias
                 else janelas_split).append(_par)
        else:
            for _a, _b2 in v.meus:
                janelas_texto.append((round(_a, 2), round(min(_b2, v.e), 2)))
        if icfg.get("texto_proprio"):
            janelas_texto.append((round(v.s2, 2), round(v.s2 + v.dur, 2)))
        mapa_insert.extend(
            {"a": round(_a, 2), "b": round(min(_b2, v.e), 2), "file": icfg["file"],
             "start": float(icfg.get("start", 0) or 0), "speed": float(icfg.get("speed", 1.0)),
             "s2": float(v.s2)}
            for _a, _b2 in v.meus)
    return janelas_split, janelas_texto, mapa_insert


def aplicar_relogio_footage(ad, look, janelas_split):
    """As janelas de split de VERDADE, com o tempo da footage e o layout do overlay.

    Pegar as janelas da footage INTEIRAS trouxe junto o julgamento dela de layout, e o plano de
    ritmo marca `split` em TODA fatia de insert, inclusive nas que a footage renderiza em tela cheia
    (`cheio` e `pip`, o insert cheio com o apresentador num círculo). Quem sabe se há DOIS painéis é
    o overlay, que lê o config (`split: true`); da footage vem só o TEMPO. Então: janela da footage
    que não encosta em nenhuma do overlay não é split, e sai. Medido num anúncio longo: o insert
    `pip` de 24,48 a 30,40 entrou como split e a legenda foi para a costura de uma emenda que
    naquele layout não existe, pousando no meio de um mockup de página branca (contraste 1,52:1,
    contra 11,7 e 14,3 nos outros trechos).

    Primeira rodada de um anúncio novo (sem o json da footage): segue com o plano do overlay; o
    build seguinte converge.
    """
    try:
        _fj = V1 / "output" / f"{ad}_{look}_footage_1x_ritmo.json"
        if _fj.exists():
            _fsegs = json.loads(_fj.read_text(encoding="utf-8")).get("segs", [])
            _jf = [(round(x["s"], 2), round(x["e"], 2))
                   for x in _fsegs if x.get("layout") == "split"]
            if _jf and janelas_split:
                _int = [(a, b) for a, b in _jf
                        if any(min(b, d) - max(a, c) > SOBREPOSICAO_RELOGIO for c, d in janelas_split)]
                _fora = len(_jf) - len(_int)
                print(f"   [relogio] janelas de split da FOOTAGE ({_fj.name}): "
                      f"{len(_int)} no lugar das {len(janelas_split)} do overlay"
                      + (f"; {_fora} descartada(s): tela cheia (cheio/pip), nao split"
                         if _fora else ""), flush=True)
                if _int:
                    janelas_split = _int
            elif _jf:
                print(f"   [relogio] janelas de split da FOOTAGE ({_fj.name}): "
                      f"{len(_jf)} janelas (overlay nao marcou nenhuma)", flush=True)
                janelas_split = _jf
    except Exception as _e:
        print(f"   [relogio] footage json ilegivel ({_e}); seguindo com o do overlay",
              flush=True)
    return janelas_split


def descer_para_rodape_em_texto(groups, janelas_texto):
    """Insert que JÁ CARREGA TEXTO PRÓPRIO (card de depoimento, print de prova social) não leva a
    legenda por cima: ela desce para o rodapé em vez de pousar no parágrafo do card. Suprimir foi a
    primeira ideia e deu errado: sem legenda o anúncio ficou 6,0 s sem texto de tela e o gate
    reprovou (teto de 12%). Descer resolve os dois lados."""
    if janelas_texto:
        n = 0
        for g in groups:
            if any(a <= g["start"] < b for a, b in janelas_texto):
                g["baixa"] = True
                n += 1
        if n:
            print(f"   [texto_proprio] {n} grupo(s) de legenda descido(s) pro rodape "
                  f"sobre card com texto", flush=True)


def look_fechado(avatar, medir=None):
    """True quando o queixo do avatar cai abaixo de 60% da altura do quadro: não sobra peito para a
    posição padrão da legenda, que raspa o queixo.

    MEDIDO, NÃO PELO NOME DO LOOK (27/08/2026): a regra existia só para um look, escrita à mão, e
    outro look igualmente fechado teve a legenda pousando na barba (6,6% do rosto, queixo em y 1390
    e tinta em y 1275-1340). Nome de look não é critério: o enquadramento é. `medir` devolve
    (topo, altura) do rosto em pixels ou None; o padrão é o `medir_rosto.caixa_rosto`.
    """
    _fechado = False
    try:
        if medir is None:
            import medir_rosto as _mr
            medir = _mr.caixa_rosto
        _cx = medir(str(avatar))
        if _cx:
            _fim = (_cx[0] + _cx[1]) / 1920.0
            _fechado = _fim > QUEIXO_FECHADO
            print(f"   [look] queixo do avatar em {_fim:.0%} da altura -> "
                  f"{'FECHADO, legenda no rodape' if _fechado else 'aberto, legenda padrao'}",
                  flush=True)
    except Exception as _e:
        print(f"   [look] nao consegui medir o avatar ({_e}); caindo no plano declarado do look",
              flush=True)
    return _fechado


def baixar_no_look_fechado(groups, avatar, medir=None, plano_do_look=None):
    """Look fechado baixa a legenda do anúncio INTEIRO: no rodapé ela cai sobre a camiseta e nunca
    disputa com o rosto. A costura e o que já está embaixo ficam como estão.

    Fechado é o MEDIDO (queixo abaixo de QUEIXO_FECHADO) ou o DECLARADO pelo aluno: `plano_do_look` é o campo
    `plano` do look no looks.json dele (o overlay recebe em `look_plano` no config). Antes havia aqui nomes de
    look do dono escritos no código (W3.X L10): nome de arquivo não é critério e nome do dono não vai para o repo."""
    fechado = look_fechado(avatar, medir)
    if fechado or plano_do_look == PLANO_FECHADO:
        n = 0
        for g in groups:
            if not g.get("costura") and not g.get("baixa"):
                g["baixa"] = True
                n += 1
        if n:
            print(f"   [look fechado] {n} grupo(s) de legenda no rodape "
                  f"(look fechado nao tem peito pra legenda padrao)", flush=True)


def _aparar_no_lado_dominante(f, b):
    """(grupo, cortou). Apara o grupo INTEIRO para o lado da fronteira `b` onde ele vive mais, parando
    GUARDA_MOTOR antes da borda. Se nenhum lado chega ao piso, deixa como está.

    As duas posições machucam nesse caso (a costura cai no rosto do avatar cheio, a baixa cai no rosto
    do split), então a saída não é escolher: é a palavra ficar menos tempo na tela, inteira de um
    lado só. Medido num anúncio longo: "publicacao" sozinha, 108,40 a 109,20 s, ficava 57,5% dentro do
    split e levava a posição do avatar cheio para cima do rosto do painel de baixo (5,6% de
    cobertura em t=80,0 s).
    """
    _antes = b - f["start"]
    _depois = f["end"] - b
    if _antes >= _depois and _antes >= PISO_FATIA:
        return {**f, "end": round(b - GUARDA_MOTOR, 3)}, True
    if _depois > _antes and _depois >= PISO_FATIA:
        return {**f, "start": round(b + GUARDA_MOTOR, 3)}, True
    return f, False


def cortar_na_fronteira(groups, janelas_split):
    """Nenhum grupo atravessa a borda de uma janela de split.

    Cada borda parte o grupo em dois (um por lado) quando as duas fatias têm pelo menos PISO_FATIA;
    senão apara tudo para o lado dominante. A fatia para NA FRONTEIRA (menos a guarda), não no fim
    da palavra, que pode passar da borda. O piso vale nos DOIS ramos: "todo o processo" virava
    "todo o" por 0,178 s e "processo" por 0,185 s, dois flashes separados por 380 px de posição com
    apagão no meio, que no celular lê como falha de renderização.

    A ANTECIPAÇÃO DO FADE-IN TAMBÉM ATRAVESSA (27/08/2026): o grupo entra 0,12 s antes para cobrir
    a saída do anterior; se nasce logo depois de uma troca, esses 0,12 s aparecem ainda no layout
    antigo com a posição do novo. Grupo que nasce a menos de MARGEM_SEM_LEAD de uma borda ganha
    `sem_lead`. A guarda cobre GUARDA_MOTOR + o lead de 0,12 s.
    """
    if not janelas_split:
        return groups
    _bordas = sorted({round(x, 3) for jan in janelas_split for x in jan})
    _novos, _cortados = [], 0
    for g in groups:
        _fatias = [g]
        for _b in _bordas:
            _saida = []
            for _f in _fatias:
                if not (_f["start"] < _b < _f["end"]):
                    _saida.append(_f)
                    continue
                # BORDA PERTO DA PONTA: não dá para cortar em dois (um lado ficaria com menos de
                # 0,12 s), mas também não pode deixar atravessar. Apara.
                if not (_f["start"] + PONTA_MIN < _b < _f["end"] - PONTA_MIN):
                    peca, cortou = _aparar_no_lado_dominante(_f, _b)
                    _saida.append(peca)
                    _cortados += cortou
                    continue
                _ini = [w for w in _f["words"] if (w["start"] + w["end"]) / 2 < _b]
                _fim = [w for w in _f["words"] if (w["start"] + w["end"]) / 2 >= _b]
                if not _ini or not _fim:
                    # não dá para cortar: uma palavra só, ou todas do mesmo lado
                    peca, cortou = _aparar_no_lado_dominante(_f, _b)
                    _saida.append(peca)
                    _cortados += cortou
                    continue
                _fim_ini = round(min(_ini[-1]["end"], _b - GUARDA_MOTOR), 3)
                _ini_fim = round(max(_fim[0]["start"], _b + GUARDA_MOTOR), 3)
                if (_fim_ini - _f["start"] < PISO_FATIA) or (_f["end"] - _ini_fim < PISO_FATIA):
                    peca, cortou = _aparar_no_lado_dominante(_f, _b)
                    _saida.append(peca)
                    _cortados += cortou
                    continue
                _saida.append({**_f, "words": _ini, "start": _f["start"], "end": _fim_ini})
                _saida.append({**_f, "words": _fim, "start": _ini_fim, "end": _f["end"]})
                _cortados += 1
            _fatias = _saida
        _novos.extend(_fatias)
    if _cortados:
        print(f"   [split] {_cortados} grupo(s) de legenda cortado(s) na fronteira de "
              f"layout, pra nenhum atravessar o corte", flush=True)
    for g in _novos:
        if any(abs(g["start"] - x) < MARGEM_SEM_LEAD for jan in janelas_split for x in jan):
            g["sem_lead"] = True
    return _novos


def marcar_costura(groups, janelas_split):
    """Grupo com FRACAO_COSTURA ou mais do tempo dentro de um split vai para a costura, e perde o
    rodapé (no split a posição baixa cai na boca do apresentador).

    A pergunta não é "onde está o meio" (um grupo com o meio dentro vivia 0,3 a 0,9 s fora e cobriu
    3,84% e 3,90% do rosto) e sim "quanto desse grupo vive dentro do split". SÓ PRA FRENTE: a folga
    simétrica de antes deixava a legenda de 81,0 s herdar a costura de um split que acabou em 80,64
    (1,6% do rosto coberto, teto 1,5%), porque a costura subiu para y 967-1106, que só é segura
    DURANTE o split.
    """
    n = 0
    for g in groups:
        _dur_g = max(g["end"] - g["start"], 1e-6)
        _dentro = sum(max(0.0, min(g["end"], b) - max(g["start"], a))
                      for a, b in janelas_split)
        if _dentro / _dur_g >= FRACAO_COSTURA:
            g["costura"] = True
            g.pop("baixa", None)
            n += 1
    if n:
        print(f"   [split] {n} grupo(s) de legenda na COSTURA dos paineis "
              f"(nem na testa nem na boca dele)", flush=True)


def empurrar_pos_split(groups, janelas_split):
    """NASCER COLADO NO FIM DO SPLIT (31/08/2026). O grupo "profissionais." nascia 0,03 s depois de
    a janela fechar no relógio do overlay, mas o corte visual da footage vem até 0,1 s depois:
    legenda em posição de tela cheia sobre o rosto do painel de baixo, atravessando os OLHOS por 3
    quadros (gate: 7,6% e depois 9,8% do rosto). Grupo que nasce a menos de GUARDA_POS_SPLIT do fim
    de um split é empurrado para depois da guarda; palavra que ficaria antes do novo início cai fora.

    Empurrar pode deixar o grupo sem palavra, curto ou com o início depois do fim (quando o logo vem logo depois do
    split). Quem decide se ele fica é o `legendas.fechar_grupos`, que roda em seguida e aplica o piso depois de
    truncar no logo (W3.X A1).
    """
    for g in groups:
        for _a, _b in janelas_split:
            if 0 <= g["start"] - _b < GUARDA_POS_SPLIT:
                g["start"] = round(_b + GUARDA_POS_SPLIT, 3)
                g["words"] = [w for w in g["words"]
                              if (w["start"] + w["end"]) / 2 >= g["start"]]
