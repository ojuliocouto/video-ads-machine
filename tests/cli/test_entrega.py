"""Entrega (W5.A): laudo, nota do auditor, gate_entrega, `vam auditar`, `vam entregar` e a versão de WhatsApp.

    vam auditar <slug>                      mostra o pacote da auditoria (o que o auditor lê)
    vam auditar <slug> --nota 8.5 [...]     o AUDITOR registra a nota, amarrada ao sha256 do final (só ele escreve)
    vam entregar <slug>                     gate_entrega e o pacote; nada sai se o gate reprova

gate_entrega (o passo 18 da seção 4): libera só com o laudo todo PASS amarrado ao sha256 do arquivo final, a
aprovação do plano ainda vigente e a nota do auditor de 8 ou mais amarrada ao MESMO sha256.
"""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

import vam
from contratos.validar import validar
from entrega import laudo as LD
from entrega import pacote, whatsapp_versao
from gates import gate_entrega
from plano import aprovacao
from projeto import novo, pastas, status

AGORA = "2026-10-09T10:00:00-03:00"


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _gates_pass():
    return [{"nome": n, "etapa": e, "resultado": "PASS", "saida": 0}
            for n, e in (("gate_aprovacao", "antes"), ("gate_relogio", "durante"), ("gate-ad", "depois"),
                         ("gate_cor", "depois"))]


@pytest.fixture
def pj(estado_vazio, monkeypatch):
    novo.criar("entrega", "avatar", look="estudio", sem_trilha="teste da entrega", estado=estado_vazio)
    p = pastas.projeto("entrega", estado_vazio)
    p.final_9x16.parent.mkdir(parents=True, exist_ok=True)
    p.final_9x16.write_bytes(b"o final de verdade")
    # a aprovação do plano é conferida pelo gate_entrega; aqui ela é simulada como vigente
    monkeypatch.setattr(aprovacao, "verificar", lambda _pj: aprovacao.Situacao(True, "", [], {}))
    return p


def _laudo(pj, veredito="PASS", sha=None, gates=None):
    gates = gates or _gates_pass()
    if veredito == "REPROVA":
        gates = gates + [{"nome": "gate_mix", "etapa": "depois", "resultado": "REPROVA", "saida": 1,
                          "motivo": "cama sobe sob a fala"}]
    d = LD.montar(pj, gates, final=pj.final_9x16, previa=None, agora=AGORA,
                  medidas={"duracao_s": 20.0, "largura": 1080, "altura": 1920, "lufs": -14.0,
                           "true_peak_dbtp": -1.7})
    if sha:
        d["sha256"] = sha
    LD.gravar(pj, d)
    return d


def _nota(pj, nota=8.0, sha=None, arquivo="entrega/final_9x16.mp4"):
    d = {"versao": 1, "projeto": pj.slug, "arquivo": arquivo, "sha256": sha or _sha(pj.final_9x16),
         "nota": nota, "rodada": 1, "auditado_em": AGORA, "achados": [], "emissor": "auditor"}
    pj.nota.write_text(json.dumps(d), encoding="utf-8")
    return d


# --- o laudo ---------------------------------------------------------------------------------------------

def test_laudo_valida_no_contrato_com_as_14_capacidades(pj):
    d = _laudo(pj)
    assert validar("laudo", d) == []
    assert d["sha256"] == _sha(pj.final_9x16) and d["arquivo"] == "entrega/final_9x16.mp4"
    assert set(d["capacidades"]) == {"C%d" % i for i in range(1, 15)}


def test_capacidade_cujo_gate_nao_rodou_nao_vira_pass(pj):
    d = _laudo(pj)
    assert d["capacidades"]["C3"]["status"] != "PASS"                 # gate_camera não estava no laudo
    assert d["veredito"] == "REPROVA"


def test_laudo_com_gate_reprovado_sai_reprovado_e_valida(pj):
    d = _laudo(pj, veredito="REPROVA")
    assert validar("laudo", d) == [] and d["veredito"] == "REPROVA"
    assert d["capacidades"]["C10"]["status"] == "REPROVA"


def test_capacidades_apontam_os_gates_que_as_provam():
    mapa = LD.CAPACIDADES
    assert mapa["C1"] == ("gate_hook_visual", "gate-ad") and mapa["C14"] == ("gate_relogio",)
    assert "gate_safezone" in mapa["C6"] and "gate_lettering" in mapa["C7"] and "gate_mix" in mapa["C10"]


def test_gravar_recusa_laudo_fora_do_contrato(pj):
    d = _laudo(pj)
    d["veredito"] = "TALVEZ"
    with pytest.raises(LD.LaudoInvalido):
        LD.gravar(pj, d)


# --- gate_entrega ----------------------------------------------------------------------------------------

def _laudo_completo(pj):
    """Laudo com todos os gates que as 14 capacidades citam, todos PASS."""
    nomes = []
    for gs in LD.CAPACIDADES.values():
        for n in gs:
            if n not in nomes:
                nomes.append(n)
    gates = [{"nome": n, "etapa": "depois", "resultado": "PASS", "saida": 0} for n in nomes]
    return _laudo(pj, gates=gates)


def test_gate_entrega_bloqueia_nota_7_9(pj):
    _laudo_completo(pj)
    _nota(pj, 7.9)
    g = gate_entrega.rodar(pj)
    assert g["resultado"] == "REPROVA" and g["saida"] == 1 and "7,9" in g["motivo"]


def test_gate_entrega_bloqueia_nota_8_com_sha_diferente_do_arquivo(pj):
    _laudo_completo(pj)
    _nota(pj, 8.0, sha="0" * 64)
    g = gate_entrega.rodar(pj)
    assert g["resultado"] == "REPROVA" and "sha256" in g["motivo"]


def test_gate_entrega_libera_nota_8_com_sha_igual(pj):
    _laudo_completo(pj)
    _nota(pj, 8.0)
    g = gate_entrega.rodar(pj)
    assert g["resultado"] == "PASS" and g["saida"] == 0
    assert g["medido"]["nota"] == 8.0 and g["medido"]["sha256"] == _sha(pj.final_9x16)


def test_a_nota_minima_e_a_da_casa():
    import fase_gate
    assert gate_entrega.NOTA_MINIMA == fase_gate.NOTA_MINIMA == 8


def test_gate_entrega_bloqueia_laudo_reprovado_ou_de_outro_arquivo(pj):
    _laudo(pj, veredito="REPROVA")
    _nota(pj, 9.0)
    assert gate_entrega.rodar(pj)["resultado"] == "REPROVA"
    _laudo_completo(pj)
    pj.final_9x16.write_bytes(b"outro final, depois do laudo")
    _nota(pj, 9.0)
    g = gate_entrega.rodar(pj)
    assert g["resultado"] == "REPROVA" and "laudo" in g["motivo"]


def test_gate_entrega_sem_nota_aponta_o_vam_auditar(pj):
    _laudo_completo(pj)
    g = gate_entrega.rodar(pj)
    assert g["resultado"] == "REPROVA" and "vam auditar" in g["motivo"]


def test_gate_entrega_com_nota_fora_do_contrato_reprova(pj):
    _laudo_completo(pj)
    d = _nota(pj, 9.0)
    d["emissor"] = "montador"
    pj.nota.write_text(json.dumps(d), encoding="utf-8")
    g = gate_entrega.rodar(pj)
    assert g["resultado"] == "REPROVA" and "emissor" in g["motivo"]


def test_gate_entrega_com_aprovacao_vencida_reprova(pj, monkeypatch):
    _laudo_completo(pj)
    _nota(pj, 9.0)
    monkeypatch.setattr(aprovacao, "verificar",
                        lambda _pj: aprovacao.Situacao(False, "aprovação vencida: roteiro.md mudou", ["roteiro.md"], {}))
    g = gate_entrega.rodar(pj)
    assert g["resultado"] == "REPROVA" and "vencida" in g["motivo"]


def test_gate_entrega_sem_final_e_erro_de_insumo(pj):
    pj.final_9x16.unlink()
    g = gate_entrega.rodar(pj)
    assert g["resultado"] == "ERRO" and g["saida"] == 2


# --- vam auditar e vam entregar -----------------------------------------------------------------------

def _vam(pj, *argv):
    return vam.main([argv[0], pj.slug, "--estado", str(pj.estado)] + list(argv[1:]))


def test_vam_auditar_sem_nota_mostra_o_pacote_e_nao_escreve_nada(pj, capsys):
    _laudo_completo(pj)
    assert _vam(pj, "auditar") == 0
    out = capsys.readouterr().out
    assert "final_9x16.mp4" in out and _sha(pj.final_9x16) in out and "auditoria.md" in out
    assert not pj.nota.exists()


def test_vam_auditar_registra_a_nota_amarrada_ao_sha_do_final(pj, tmp_path):
    achados = tmp_path / "achados.json"
    achados.write_text(json.dumps([{"id": "A1", "gravidade": "leve", "descricao": "lettering entra um pouco cedo",
                                    "status": "aceito", "instante_s": 4.2}]), encoding="utf-8")
    assert _vam(pj, "auditar", "--nota", "8.5", "--achados", str(achados), "--modelo", "auditor-teste") == 0
    d = json.loads(pj.nota.read_text(encoding="utf-8"))
    assert validar("nota", d) == []
    assert d["emissor"] == "auditor" and d["nota"] == 8.5 and d["sha256"] == _sha(pj.final_9x16)
    assert d["arquivo"] == "entrega/final_9x16.mp4" and d["achados"][0]["id"] == "A1"


def test_vam_auditar_recusa_nota_fora_da_escala_e_rodada_2_sem_reconferir(pj):
    assert _vam(pj, "auditar", "--nota", "11") == 2
    assert _vam(pj, "auditar", "--nota", "8", "--rodada", "2") == 2           # rodada 2 reconfere os mesmos achados
    assert not pj.nota.exists()


def test_vam_entregar_bloqueado_sai_com_um_e_nao_monta_o_pacote(pj, capsys):
    _laudo_completo(pj)
    _nota(pj, 7.9)
    assert _vam(pj, "entregar") == 1
    assert not (pj.entrega_dir / "entrega.json").exists()
    assert status.ler(pj)["atual"]["estado"] == "falhou"
    assert "7,9" in capsys.readouterr().err


def test_vam_entregar_liberado_monta_o_pacote_com_os_sha(pj, capsys):
    _laudo_completo(pj)
    _nota(pj, 8.0)
    pj.final_whatsapp.write_bytes(b"previa")
    assert _vam(pj, "entregar") == 0
    m = json.loads((pj.entrega_dir / "entrega.json").read_text(encoding="utf-8"))
    assert m["final"]["sha256"] == _sha(pj.final_9x16) and m["nota"]["nota"] == 8.0
    assert m["previa"]["arquivo"] == "entrega/final_whatsapp.mp4"
    assert m["laudo"]["sha256"] == _sha(pj.laudo)
    out = capsys.readouterr().out
    assert "final_9x16.mp4" in out
    assert status.ler(pj)["atual"]["etapa"] == "entregar" and status.ler(pj)["atual"]["estado"] == "ok"


def test_pacote_nao_monta_sem_o_gate_passar(pj):
    with pytest.raises(pacote.EntregaBloqueada):
        pacote.montar(pj, {"nome": "gate_entrega", "etapa": "entrega", "resultado": "REPROVA", "saida": 1,
                           "motivo": "nota 7,9"})


# --- versão de WhatsApp ----------------------------------------------------------------------------------

def test_comando_da_versao_whatsapp_reencoda_leve():
    cmd = whatsapp_versao.comando("final.mp4", "final_whatsapp.mp4")
    texto = " ".join(cmd)
    assert "-crf 26" in texto and "-maxrate 3M" in texto and "scale=720:1280" in texto
    assert "+faststart" in texto and "-ar 48000" in texto and cmd[-1] == "final_whatsapp.mp4"


@pytest.mark.lento
def test_versao_whatsapp_de_um_video_granulado_sai_leve_e_em_720(tmp_path):
    src = tmp_path / "granulado.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=30:d=3",
                    "-f", "lavfi", "-i", "sine=f=440:d=3", "-vf", "noise=alls=40:allf=t", "-c:v", "libx264",
                    "-crf", "12", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src)], check=True)
    saida = whatsapp_versao.gerar(src, tmp_path / "w.mp4")
    o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(saida)], capture_output=True, text=True).stdout.strip()
    assert o == "720,1280"
    assert saida.stat().st_size < src.stat().st_size / 3
