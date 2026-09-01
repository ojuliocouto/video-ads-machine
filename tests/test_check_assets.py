"""Testes de check_assets.py (TDD, Task 1.4 do PLAN.md).

Cobre missing() (detecção de assets ausentes no disco) e
offer_avatar_generation() (mensagem/instrução, sem chamar API nenhuma).
"""
import os
import socket
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from check_assets import missing, offer_avatar_generation


def _make_file(path):
    """Cria um arquivo vazio de verdade no disco (fixture local, sem mocks)."""
    with open(path, "wb") as handle:
        handle.write(b"fake")
    return str(path)


def test_missing_returns_all_paths_when_nothing_exists(tmp_path):
    brief = {
        "assets": {
            "avatar": str(tmp_path / "avatar_nao_existe.mp4"),
            "voz": str(tmp_path / "voz_nao_existe.mp3"),
            "logo": str(tmp_path / "logo_nao_existe.png"),
            "brolls": [
                str(tmp_path / "broll1_nao_existe.mp4"),
                str(tmp_path / "broll2_nao_existe.mp4"),
            ],
        }
    }

    result = missing(brief)

    expected = {
        brief["assets"]["avatar"],
        brief["assets"]["voz"],
        brief["assets"]["logo"],
        *brief["assets"]["brolls"],
    }
    assert set(result) == expected
    assert len(result) == 5


def test_missing_returns_empty_when_all_files_exist(tmp_path):
    brief = {
        "assets": {
            "avatar": _make_file(tmp_path / "avatar.mp4"),
            "voz": _make_file(tmp_path / "voz.mp3"),
            "logo": _make_file(tmp_path / "logo.png"),
            "brolls": [_make_file(tmp_path / "broll01.mp4")],
        }
    }

    assert missing(brief) == []


def test_missing_flags_only_the_ones_that_dont_exist(tmp_path):
    voz_existente = _make_file(tmp_path / "voz.mp3")
    avatar_faltando = str(tmp_path / "avatar_falta.mp4")
    logo_faltando = str(tmp_path / "logo_falta.png")

    brief = {
        "assets": {
            "avatar": avatar_faltando,
            "voz": voz_existente,
            "logo": logo_faltando,
            "brolls": [],
        }
    }

    result = missing(brief)
    assert set(result) == {avatar_faltando, logo_faltando}


def test_missing_flags_only_the_brolls_that_dont_exist(tmp_path):
    broll_existente = _make_file(tmp_path / "broll_ok.mp4")
    broll_faltando = str(tmp_path / "broll_falta.mp4")

    brief = {
        "assets": {
            "brolls": [broll_existente, broll_faltando],
        }
    }

    assert missing(brief) == [broll_faltando]


def test_missing_skips_keys_not_declared_but_flags_declared_ones():
    """Chave ausente no brief (ex: sem b-roll neste reel) não conta como faltando."""
    brief = {"assets": {"voz": "algum_caminho_qualquer.mp3"}}
    # "voz" foi declarada mas não existe no disco: deve aparecer.
    assert missing(brief) == ["algum_caminho_qualquer.mp3"]


def test_missing_handles_brief_without_assets_key():
    assert missing({}) == []


def test_missing_handles_empty_brief_dict_variants():
    assert missing({"assets": {}}) == []
    assert missing({"assets": None}) == []


def test_offer_avatar_generation_mentions_heygen_and_avatar_v():
    msg = offer_avatar_generation("roteiro.txt", "voz.mp3")

    assert isinstance(msg, str)
    assert "HeyGen" in msg
    assert "Avatar V" in msg


def test_offer_avatar_generation_echoes_the_given_paths():
    msg = offer_avatar_generation("meu_roteiro.txt", "minha_voz.mp3")

    assert "meu_roteiro.txt" in msg
    assert "minha_voz.mp3" in msg


def test_offer_avatar_generation_instructs_saving_as_avatar_mp4():
    msg = offer_avatar_generation("roteiro.txt", "voz.mp3")

    assert "avatar.mp4" in msg


def test_offer_avatar_generation_never_opens_a_network_socket(monkeypatch):
    """Prova que a função só monta string: nenhuma chamada de API acontece aqui."""

    def blocked_connect(*args, **kwargs):
        raise AssertionError("offer_avatar_generation não deveria abrir socket")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)

    msg = offer_avatar_generation("roteiro.txt", "voz.mp3")
    assert "HeyGen" in msg
