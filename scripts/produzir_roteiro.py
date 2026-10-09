#!/usr/bin/env python3
"""Produz a footage de um reel: avatar + inserts, cortes e transições pelo plano de ritmo.

Wrapper fino. A lógica mora em scripts/footage/ (blocos, filtros_avatar, filtros_insert, exposicao,
enquadramento, cadeia, render_segmentos, grade_final, timing_export e montar). Nada executa no import.

Mesma CLI de sempre, só por variáveis de ambiente:
  VAM_AVATAR, VAM_ROTEIRO        mp4 do avatar e roteiro anotado (obrigatórias)
  VAM_INSERTS_JSON               mapa {palavra-chave: {file, start, speed, ...}}
  VAM_OUT                        nome do mp4 em DADOS/output (ou caminho absoluto)
  VAM_XF, VAM_XF_SECO, VAM_XF_TIPO                      transições
  VAM_SPLIT_TOP_H, VAM_SPLIT_GRAD, VAM_SPLIT_BIAS       tela dividida
  VAM_CACHE_SEG, VAM_PARALELO                           cache e pool
  CAP=0 e VAM_BAKE_LETTERING=0   únicos valores aceitos: legenda e lettering são do overlay
Escreve DADOS/output/<VAM_OUT>, <nome>_ritmo.json e timing.json.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from footage.montar import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
