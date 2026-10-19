"""Um nome de arquivo que quebra o filtro do ffmpeg se o escape estiver errado (W1.D, port nativo para Windows).

Tem os especiais das duas camadas do filtro (`:` `=` `'` `,` `[` `]` `\\`), mais espaço. No Windows o disco recusa `:`
e `\\` no nome, então lá o nome perde só esses dois. Usar:

    from tests.fixtures.nome_esquisito import NOME_ESQUISITO
    pasta = tmp_path / NOME_ESQUISITO
"""
import plataforma

_BASE = "a'b,c[d]=e f"
NOME_ESQUISITO = _BASE if plataforma.eh_windows() else "a:b" + _BASE[1:] + "\\g"
