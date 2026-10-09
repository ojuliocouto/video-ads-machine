"""Pipeline de take gravado: edição de anúncio a partir de takes reais com retomada.

O núcleo (energia, segmentos, asr) fica em `gravado.nucleo`; os 11 gates são `gate_*.py`,
cada um função + CLI com saída 0 (passou), 1 (defeito medido) ou 2 (insumo inválido).
"""
