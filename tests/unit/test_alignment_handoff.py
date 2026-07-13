"""Montage must persist alignment.json in the shape captions consumes."""
import json
import os

from vam.captions import _alignment_tokens
from vam.montage import write_alignment


class _Cfg:
    def __init__(self, wd):
        self.workdir = wd


def test_write_alignment_roundtrips_into_captions(tmp_path):
    cfg = _Cfg(str(tmp_path))
    words = [(0.0, 0.4, "uma"), (0.5, 0.9, "skill")]
    path = write_alignment(words, cfg)
    assert os.path.basename(path) == "alignment.json"
    tokens = _alignment_tokens(path)
    assert [tuple(t) for t in tokens] == [
        (0.0, 0.4, "uma"), (0.5, 0.9, "skill")]


def test_write_alignment_is_valid_json(tmp_path):
    cfg = _Cfg(str(tmp_path))
    write_alignment([(1.0, 1.2, "ok")], cfg)
    with open(os.path.join(str(tmp_path), "alignment.json")) as fh:
        data = json.load(fh)
    assert data["tokens"][0]["text"] == " ok"
