"""Renderizadores de segmento (W2.B): o argv de cada ffmpeg tem que ser o do motor original.

Cada caso golden é um renderizador do `produzir_roteiro.py` ORIGINAL (commit 2ebd1cc) chamado
com as medições fixadas (aspecto, luminância, largura, foco, recorte de conteúdo, preto na
entrada) e o `run` trocado por um gravador. Aqui o mesmo bloco, as mesmas medições e o mesmo
`run` falso têm que dar exatamente o mesmo comando. Cobre os ramos que a fixture de paridade
não exercita: imagem estática (Ken Burns), vertical sem moldura, zoom, recorte declarado,
PiP, painel encaixado, offset de fundo sem medida.

Duas diferenças DECLARADAS em relação ao original, normalizadas em tokens:
  - `<MOLDURAS>`: a pasta dos PNG de moldura (aqui um tmp);
  - `<SOMBRA_PIP>`, `<LOGO>`, `<BRILHO>`, `<ANEL>`: os assets do PiP e do card de logo, que
    antes eram PNG externos de uma pasta cravada e agora vêm do projeto (o logo) ou são gerados
    por código (sombra, brilho e anel).
"""
import copy
import os
import time
from pathlib import Path

import pytest

import push_in
from footage import cadeia as CA
from footage import enquadramento as ENQ
from footage import exposicao as EX
from footage import filtros_insert as FI
from footage import render_segmentos as RS

AV = "/AV/avatar.mp4"
LOGO = "/L/logo.png"

# lista de {"nome","fn","cfg","s","e","out","idx","base","medidas","pip_crop","comandos"}
GOLDEN = [{'nome': 'split_h16_escuro_pushin',
  'fn': 'r_split_tela',
  's': 10.88,
  'e': 15.92,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-ss',
                '1.0',
                '-t',
                '5.4399999999999995',
                '-i',
                '/m/h16.mp4',
                '-ss',
                '10.88',
                '-t',
                '5.4399999999999995',
                '-i',
                '/AV/avatar.mp4',
                '-filter_complex',
                "[0:v]setpts=PTS/1.0,tpad=stop_mode=clone:stop_duration=4,split=2[t1][t2];[t1]scale=1080:1150:force_original_aspect_ratio=increase,crop=1080:1150,eq=brightness=0.176:contrast=1.106,boxblur=26:1,eq=brightness=-0.12,setsar=1[tbg];[t2]eq=brightness=0.176:contrast=1.106,scale=1008:566,setsar=1,zoompan=z='min(1+0.42857*on/150,1.42857)':x='iw*0.5000-(iw/zoom/2)':y='ih*0.5000-(ih/zoom/2)':d=1:s=1008x566:fps=30[tvid];color=black@0:s=1128x748:r=30,format=rgba,setsar=1[tcv];[tcv][tvid]overlay=60:122:shortest=1[tcard];movie=<MOLDURAS>/moldura_1_7778.png,format=rgba,setsar=1[tmold];[tcard][tmold]overlay=0:0[tfg];[tbg][tfg]overlay=(W-w)/2:(H-h)/2,setsar=1[top];[1:v]crop=1080:1600:0:100,scale=1080:1600,crop=1080:770:0:480,setsar=1[bot];color=0x141210:s=1080x1920:r=30[cv];[cv][top]overlay=0:0:shortest=1[c1];[c1][bot]overlay=0:1150[c2];color=black:s=1080x90:r=30,format=rgba,geq=r=0:g=0:b=0:a='255*0.62*pow(Y/89,1.6)'[grad];[c2][grad]overlay=0:1060:shortest=1,fps=30,trim=end_frame=151,setpts=N/30/TB[v]",
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'file': '/m/h16.mp4', 'speed': 1.0, 'split': True, 'start': 1.0},
  'medidas': {'asp': 1.7778,
              'foco': [0.5, 0.5],
              'larg': 1920,
              'lum': 60.0,
              'lum_med': 40,
              'preto': 1.0}},
 {'nome': 'split_h16_claro_teto',
  'fn': 'r_split_tela',
  's': 3.0,
  'e': 6.1,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-ss',
                '0.0',
                '-t',
                '5.05',
                '-i',
                '/m/h16.mp4',
                '-ss',
                '3.0',
                '-t',
                '3.4999999999999996',
                '-i',
                '/AV/avatar.mp4',
                '-filter_complex',
                "[0:v]setpts=PTS/1.5,tpad=stop_mode=clone:stop_duration=4,split=2[t1][t2];[t1]scale=1080:1150:force_original_aspect_ratio=increase,crop=1080:1150,boxblur=26:1,eq=brightness=-0.12,setsar=1[tbg];[t2]scale=1008:566,setsar=1[tvid];color=black@0:s=1128x748:r=30,format=rgba,setsar=1[tcv];[tcv][tvid]overlay=60:122:shortest=1[tcard];movie=<MOLDURAS>/moldura_1_7778.png,format=rgba,setsar=1[tmold];[tcard][tmold]overlay=0:0[tfg];[tbg][tfg]overlay=(W-w)/2:(H-h)/2,setsar=1[top];[1:v]crop=1080:1600:0:100,scale=1080:1600,crop=1080:770:0:480,setsar=1[bot];color=0x141210:s=1080x1920:r=30[cv];[cv][top]overlay=0:0:shortest=1[c1];[c1][bot]overlay=0:1150[c2];color=black:s=1080x90:r=30,format=rgba,geq=r=0:g=0:b=0:a='255*0.62*pow(Y/89,1.6)'[grad];[c2][grad]overlay=0:1060:shortest=1,fps=30,trim=end_frame=93,setpts=N/30/TB[v]",
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'exposicao': 0.1, 'file': '/m/h16.mp4', 'speed': 1.5, 'split': True, 'start': 0.0},
  'medidas': {'asp': 1.7778,
              'foco': [0.4, 0.62],
              'larg': 900,
              'lum': 244.0,
              'lum_med': 240,
              'preto': 0.0}},
 {'nome': 'split_ultrawide_exposicao_declarada',
  'fn': 'r_split_tela',
  's': 20.0,
  'e': 23.5,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-ss',
                '2.5',
                '-t',
                '3.9',
                '-i',
                '/m/uw.mp4',
                '-ss',
                '20.0',
                '-t',
                '3.9',
                '-i',
                '/AV/avatar.mp4',
                '-filter_complex',
                "[0:v]setpts=PTS/1.0,tpad=stop_mode=clone:stop_duration=4,split=2[t1][t2];[t1]scale=1080:1150:force_original_aspect_ratio=increase,crop=1080:1150,eq=brightness=-0.100:contrast=1.060,boxblur=26:1,eq=brightness=-0.12,setsar=1[tbg];[t2]eq=brightness=-0.100:contrast=1.060,scale=1008:420,setsar=1,zoompan=z='min(1+0.70000*on/104,1.70000)':x='iw*0.3000-(iw/zoom/2)':y='ih*0.3000-(ih/zoom/2)':d=1:s=1008x420:fps=30[tvid];color=black@0:s=1128x602:r=30,format=rgba,setsar=1[tcv];[tcv][tvid]overlay=60:122:shortest=1[tcard];movie=<MOLDURAS>/moldura_2_4000.png,format=rgba,setsar=1[tmold];[tcard][tmold]overlay=0:0[tfg];[tbg][tfg]overlay=(W-w)/2:(H-h)/2,setsar=1[top];[1:v]crop=1080:1600:0:100,scale=1080:1600,crop=1080:770:0:480,setsar=1[bot];color=0x141210:s=1080x1920:r=30[cv];[cv][top]overlay=0:0:shortest=1[c1];[c1][bot]overlay=0:1150[c2];color=black:s=1080x90:r=30,format=rgba,geq=r=0:g=0:b=0:a='255*0.62*pow(Y/89,1.6)'[grad];[c2][grad]overlay=0:1060:shortest=1,fps=30,trim=end_frame=105,setpts=N/30/TB[v]",
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'exposicao': -0.1, 'file': '/m/uw.mp4', 'speed': 1.0, 'split': True, 'start': 2.0},
  'medidas': {'asp': 2.4,
              'foco': [0.3, 0.3],
              'larg': 2560,
              'lum': 120.0,
              'lum_med': 100,
              'preto': 2.5}},
 {'nome': 'split_vertical_sem_moldura_preencher',
  'fn': 'r_split_tela',
  's': 1.0,
  'e': 4.0,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-ss',
                '0.0',
                '-t',
                '3.4',
                '-i',
                '/m/v.mp4',
                '-ss',
                '1.0',
                '-t',
                '3.4',
                '-i',
                '/AV/avatar.mp4',
                '-filter_complex',
                "[0:v]setpts=PTS/1.0,tpad=stop_mode=clone:stop_duration=4,split=2[t1][t2];[t1]scale=1080:1150:force_original_aspect_ratio=increase,crop=1080:1150,eq=brightness=0.059:contrast=1.035,boxblur=26:1,eq=brightness=-0.12,setsar=1[tbg];[t2]eq=brightness=0.059:contrast=1.035,scale=1080:1150:force_original_aspect_ratio=increase,crop=1080:1150:'clip((in_w*0.4200)-(out_w/2),0,in_w-out_w)':'clip((in_h*0.5500)-(out_h/2),0,in_h-out_h)',setsar=1[tfg];[tbg][tfg]overlay=(W-w)/2:(H-h)/2,setsar=1[top];[1:v]crop=1080:1600:0:100,scale=1080:1600,crop=1080:770:0:480,setsar=1[bot];color=0x141210:s=1080x1920:r=30[cv];[cv][top]overlay=0:0:shortest=1[c1];[c1][bot]overlay=0:1150[c2];color=black:s=1080x90:r=30,format=rgba,geq=r=0:g=0:b=0:a='255*0.62*pow(Y/89,1.6)'[grad];[c2][grad]overlay=0:1060:shortest=1,fps=30,trim=end_frame=90,setpts=N/30/TB[v]",
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'file': '/m/v.mp4', 'speed': 1.0, 'split': True, 'start': 0.0},
  'medidas': {'asp': 0.5625,
              'conteudo': [0.42, 0.55, 'preencher'],
              'larg': 1080,
              'lum': 90.0,
              'lum_med': 90,
              'preto': 0.0}},
 {'nome': 'split_vertical_sem_moldura_encaixar',
  'fn': 'r_split_tela',
  's': 1.0,
  'e': 4.0,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-ss',
                '0.5',
                '-t',
                '3.4',
                '-i',
                '/m/v2.mp4',
                '-ss',
                '1.0',
                '-t',
                '3.4',
                '-i',
                '/AV/avatar.mp4',
                '-filter_complex',
                "[0:v]setpts=PTS/1.0,tpad=stop_mode=clone:stop_duration=4,split=2[t1][t2];[t1]scale=1080:1150:force_original_aspect_ratio=increase,crop=1080:1150,eq=brightness=0.059:contrast=1.035,boxblur=26:1,eq=brightness=-0.12,setsar=1[tbg];[t2]eq=brightness=0.059:contrast=1.035,scale=1036:1150:force_original_aspect_ratio=decrease,setsar=1[tfg];[tbg][tfg]overlay=(W-w)/2:(H-h)/2,setsar=1[top];[1:v]crop=1080:1600:0:100,scale=1080:1600,crop=1080:770:0:480,setsar=1[bot];color=0x141210:s=1080x1920:r=30[cv];[cv][top]overlay=0:0:shortest=1[c1];[c1][bot]overlay=0:1150[c2];color=black:s=1080x90:r=30,format=rgba,geq=r=0:g=0:b=0:a='255*0.62*pow(Y/89,1.6)'[grad];[c2][grad]overlay=0:1060:shortest=1,fps=30,trim=end_frame=90,setpts=N/30/TB[v]",
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'file': '/m/v2.mp4', 'speed': 1.0, 'split': True, 'start': 0.5},
  'medidas': {'asp': 0.5625,
              'conteudo': [0.5, 0.5, 'encaixar'],
              'larg': 1080,
              'lum': 90.0,
              'lum_med': 90,
              'preto': 0.5}},
 {'nome': 'split_quadrado_asp_1_0',
  'fn': 'r_split_tela',
  's': 1.0,
  'e': 4.0,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-ss',
                '0.0',
                '-t',
                '3.4',
                '-i',
                '/m/q.mp4',
                '-ss',
                '1.0',
                '-t',
                '3.4',
                '-i',
                '/AV/avatar.mp4',
                '-filter_complex',
                "[0:v]setpts=PTS/1.0,tpad=stop_mode=clone:stop_duration=4,split=2[t1][t2];[t1]scale=1080:1150:force_original_aspect_ratio=increase,crop=1080:1150,boxblur=26:1,eq=brightness=-0.12,setsar=1[tbg];[t2]scale=1080:1150:force_original_aspect_ratio=increase,crop=1080:1150:'clip((in_w*0.5000)-(out_w/2),0,in_w-out_w)':'clip((in_h*0.5000)-(out_h/2),0,in_h-out_h)',setsar=1[tfg];[tbg][tfg]overlay=(W-w)/2:(H-h)/2,setsar=1[top];[1:v]crop=1080:1600:0:100,scale=1080:1600,crop=1080:770:0:480,setsar=1[bot];color=0x141210:s=1080x1920:r=30[cv];[cv][top]overlay=0:0:shortest=1[c1];[c1][bot]overlay=0:1150[c2];color=black:s=1080x90:r=30,format=rgba,geq=r=0:g=0:b=0:a='255*0.62*pow(Y/89,1.6)'[grad];[c2][grad]overlay=0:1060:shortest=1,fps=30,trim=end_frame=90,setpts=N/30/TB[v]",
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'crop': '800:800:10:20', 'file': '/m/q.mp4', 'speed': 1.0, 'split': True, 'start': 0.0},
  'medidas': {'asp': 1.0,
              'conteudo': [0.5, 0.5, 'preencher'],
              'larg': 800,
              'lum': 110.0,
              'lum_med': 110,
              'preto': 0.0}},
 {'nome': 'split_preto_deslocado',
  'fn': 'r_split_tela',
  's': 1.0,
  'e': 5.0,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-ss',
                '4.25',
                '-t',
                '4.4',
                '-i',
                '/m/p.mp4',
                '-ss',
                '1.0',
                '-t',
                '4.4',
                '-i',
                '/AV/avatar.mp4',
                '-filter_complex',
                "[0:v]setpts=PTS/1.0,tpad=stop_mode=clone:stop_duration=4,split=2[t1][t2];[t1]scale=1080:1150:force_original_aspect_ratio=increase,crop=1080:1150,eq=brightness=0.137:contrast=1.082,boxblur=26:1,eq=brightness=-0.12,setsar=1[tbg];[t2]eq=brightness=0.137:contrast=1.082,scale=1008:566,setsar=1,zoompan=z='min(1+0.42857*on/119,1.42857)':x='iw*0.5000-(iw/zoom/2)':y='ih*0.5000-(ih/zoom/2)':d=1:s=1008x566:fps=30[tvid];color=black@0:s=1128x748:r=30,format=rgba,setsar=1[tcv];[tcv][tvid]overlay=60:122:shortest=1[tcard];movie=<MOLDURAS>/moldura_1_7778.png,format=rgba,setsar=1[tmold];[tcard][tmold]overlay=0:0[tfg];[tbg][tfg]overlay=(W-w)/2:(H-h)/2,setsar=1[top];[1:v]crop=1080:1600:0:100,scale=1080:1600,crop=1080:770:0:480,setsar=1[bot];color=0x141210:s=1080x1920:r=30[cv];[cv][top]overlay=0:0:shortest=1[c1];[c1][bot]overlay=0:1150[c2];color=black:s=1080x90:r=30,format=rgba,geq=r=0:g=0:b=0:a='255*0.62*pow(Y/89,1.6)'[grad];[c2][grad]overlay=0:1060:shortest=1,fps=30,trim=end_frame=120,setpts=N/30/TB[v]",
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'file': '/m/p.mp4', 'speed': 1.0, 'split': True, 'start': 3.0},
  'medidas': {'asp': 1.7778, 'larg': 1920, 'lum': 70.0, 'lum_med': 70, 'preto': 4.25}},
 {'nome': 'cheio_h16_pushin',
  'fn': 'r_insert_moldura',
  's': 0.62,
  'e': 4.9,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-ss',
                '0.0',
                '-t',
                '4.680000000000001',
                '-i',
                '/m/h16.mp4',
                '-filter_complex',
                "[0:v]setpts=PTS/1.0,tpad=stop_mode=clone:stop_duration=4,split=2[t1][t2];[t1]trim=end_frame=1,loop=loop=-1:size=1:start=0,setpts=N/30/TB,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=60:2,eq=brightness=-0.039:saturation=0.7,setsar=1[bg];[t2]eq=brightness=0.176:contrast=1.106,scale=1036:582,setsar=1,zoompan=z='min(1+0.38996*on/127,1.38996)':x='iw*0.5000-(iw/zoom/2)':y='ih*0.5000-(ih/zoom/2)':d=1:s=1036x582:fps=30[vid];color=black@0:s=1156x764:r=30,format=rgba,setsar=1[cv];[cv][vid]overlay=60:122:shortest=1[card];movie=<MOLDURAS>/moldura_cheio_1_7778.png,format=rgba,setsar=1[mold];[card][mold]overlay=0:0[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,setsar=1,fps=30,trim=end_frame=128,setpts=N/30/TB[v]",
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'file': '/m/h16.mp4', 'speed': 1.0, 'split': True, 'start': 0.0},
  'medidas': {'asp': 1.7778,
              'foco': [0.5, 0.5],
              'larg': 1920,
              'lum': 60.0,
              'lum_med': 40,
              'preto': 0.0}},
 {'nome': 'cheio_h16_claro_largo',
  'fn': 'r_insert_moldura',
  's': 30.0,
  'e': 33.0,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-ss',
                '5.0',
                '-t',
                '6.4',
                '-i',
                '/m/c.mp4',
                '-filter_complex',
                '[0:v]setpts=PTS/2.0,tpad=stop_mode=clone:stop_duration=4,split=2[t1][t2];[t1]trim=end_frame=1,loop=loop=-1:size=1:start=0,setpts=N/30/TB,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=60:2,eq=brightness=-0.400:saturation=0.7,setsar=1[bg];[t2]scale=1036:582,setsar=1[vid];color=black@0:s=1156x764:r=30,format=rgba,setsar=1[cv];[cv][vid]overlay=60:122:shortest=1[card];movie=<MOLDURAS>/moldura_cheio_1_7778.png,format=rgba,setsar=1[mold];[card][mold]overlay=0:0[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,setsar=1,fps=30,trim=end_frame=90,setpts=N/30/TB[v]',
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'exposicao': 0.2, 'file': '/m/c.mp4', 'speed': 2.0, 'start': 5.0},
  'medidas': {'asp': 1.7778,
              'foco': [0.35, 0.65],
              'larg': 800,
              'lum': 230.0,
              'lum_med': 235,
              'preto': 5.0}},
 {'nome': 'cheio_ultrawide_preto',
  'fn': 'r_insert_moldura',
  's': 40.0,
  'e': 44.5,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-ss',
                '2.2',
                '-t',
                '4.9',
                '-i',
                '/m/cw.mp4',
                '-filter_complex',
                "[0:v]setpts=PTS/1.0,tpad=stop_mode=clone:stop_duration=4,split=2[t1][t2];[t1]trim=end_frame=1,loop=loop=-1:size=1:start=0,setpts=N/30/TB,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=60:2,eq=brightness=0.059:saturation=0.7,setsar=1[bg];[t2]eq=brightness=0.333:contrast=1.200,scale=1036:432,setsar=1,zoompan=z='min(1+0.70000*on/134,1.70000)':x='iw*0.5000-(iw/zoom/2)':y='ih*0.5000-(ih/zoom/2)':d=1:s=1036x432:fps=30[vid];color=black@0:s=1156x614:r=30,format=rgba,setsar=1[cv];[cv][vid]overlay=60:122:shortest=1[card];movie=<MOLDURAS>/moldura_cheio_2_4000.png,format=rgba,setsar=1[mold];[card][mold]overlay=0:0[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,setsar=1,fps=30,trim=end_frame=135,setpts=N/30/TB[v]",
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'file': '/m/cw.mp4', 'speed': 1.0, 'start': 1.0},
  'medidas': {'asp': 2.4,
              'foco': [0.5, 0.5],
              'larg': 3840,
              'lum': 20.0,
              'lum_med': 15,
              'preto': 2.2}},
 {'nome': 'cheio_lum_none',
  'fn': 'r_insert_moldura',
  's': 1.0,
  'e': 3.0,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-ss',
                '0.0',
                '-t',
                '2.4',
                '-i',
                '/m/ln.mp4',
                '-filter_complex',
                "[0:v]setpts=PTS/1.0,tpad=stop_mode=clone:stop_duration=4,split=2[t1][t2];[t1]trim=end_frame=1,loop=loop=-1:size=1:start=0,setpts=N/30/TB,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=60:2,eq=brightness=-0.200:saturation=0.7,setsar=1[bg];[t2]scale=1036:582,setsar=1,zoompan=z='min(1+0.38996*on/59,1.38996)':x='iw*0.5000-(iw/zoom/2)':y='ih*0.5000-(ih/zoom/2)':d=1:s=1036x582:fps=30[vid];color=black@0:s=1156x764:r=30,format=rgba,setsar=1[cv];[cv][vid]overlay=60:122:shortest=1[card];movie=<MOLDURAS>/moldura_cheio_1_7778.png,format=rgba,setsar=1[mold];[card][mold]overlay=0:0[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,setsar=1,fps=30,trim=end_frame=60,setpts=N/30/TB[v]",
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'file': '/m/ln.mp4', 'speed': 1.0, 'start': 0.0},
  'medidas': {'asp': 1.7778, 'larg': 1920, 'lum': None, 'lum_med': None, 'preto': 0.0}},
 {'nome': 'insert_imagem_ken_burns',
  'fn': 'r_insert',
  's': 2.0,
  'e': 5.5,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-loop',
                '1',
                '-t',
                '3.9',
                '-i',
                '/m/img.png',
                '-filter_complex',
                "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:1,setsar=1[bg];[0:v]scale=1166:-1,zoompan=z='min(zoom+0.0007,1.06)':d=117:s=1080x1920:fps=30,setsar=1[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,trim=end_frame=105,setpts=N/30/TB[v]",
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'file': '/m/img.png', 'speed': 1.0, 'start': 0},
  'medidas': {'asp': 1.7778, 'lum': 100.0, 'lum_med': 100, 'preto': 0}},
 {'nome': 'insert_imagem_jpg_com_split',
  'fn': 'r_insert',
  's': 2.0,
  'e': 5.5,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-ss',
                '0',
                '-t',
                '3.9',
                '-i',
                '/m/img.JPG',
                '-ss',
                '2.0',
                '-t',
                '3.9',
                '-i',
                '/AV/avatar.mp4',
                '-filter_complex',
                "[0:v]setpts=PTS/1.0,tpad=stop_mode=clone:stop_duration=4,split=2[t1][t2];[t1]scale=1080:1150:force_original_aspect_ratio=increase,crop=1080:1150,eq=brightness=0.020:contrast=1.012,boxblur=26:1,eq=brightness=-0.12,setsar=1[tbg];[t2]eq=brightness=0.020:contrast=1.012,scale=1080:1150:force_original_aspect_ratio=increase,crop=1080:1150:'clip((in_w*0.5000)-(out_w/2),0,in_w-out_w)':'clip((in_h*0.5000)-(out_h/2),0,in_h-out_h)',setsar=1[tfg];[tbg][tfg]overlay=(W-w)/2:(H-h)/2,setsar=1[top];[1:v]crop=1080:1600:0:100,scale=1080:1600,crop=1080:770:0:480,setsar=1[bot];color=0x141210:s=1080x1920:r=30[cv];[cv][top]overlay=0:0:shortest=1[c1];[c1][bot]overlay=0:1150[c2];color=black:s=1080x90:r=30,format=rgba,geq=r=0:g=0:b=0:a='255*0.62*pow(Y/89,1.6)'[grad];[c2][grad]overlay=0:1060:shortest=1,fps=30,trim=end_frame=105,setpts=N/30/TB[v]",
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'file': '/m/img.JPG', 'speed': 1.0, 'split': True, 'start': 0},
  'medidas': {'asp': 0.75,
              'conteudo': [0.5, 0.5, 'preencher'],
              'lum': 100.0,
              'lum_med': 100,
              'preto': 0}},
 {'nome': 'insert_vertical_plain',
  'fn': 'r_insert',
  's': 3.0,
  'e': 7.0,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-ss',
                '1.0',
                '-t',
                '4.4',
                '-i',
                '/m/vv.mp4',
                '-filter_complex',
                '[0:v]eq=brightness=0.098:contrast=1.059,setpts=PTS/1.0,tpad=stop_mode=clone:stop_duration=4,split=2[i1][i2];[i1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:1,setsar=1[bg];[i2]scale=1080:1920:force_original_aspect_ratio=decrease,setsar=1[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,trim=end_frame=120,setpts=N/30/TB[v]',
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'file': '/m/vv.mp4', 'speed': 1.0, 'start': 1.0},
  'medidas': {'asp': 0.5625, 'larg': 1080, 'lum': 80.0, 'lum_med': 80, 'preto': 1.0}},
 {'nome': 'insert_vertical_zoom',
  'fn': 'r_insert',
  's': 3.0,
  'e': 7.0,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-ss',
                '0.0',
                '-t',
                '6.4',
                '-i',
                '/m/vz.mp4',
                '-filter_complex',
                "[0:v]eq=brightness=0.098:contrast=1.059,setpts=PTS/1.5,tpad=stop_mode=clone:stop_duration=4,split=2[i1][i2];[i1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:1,setsar=1[bg];[i2]scale=1404:2496:force_original_aspect_ratio=decrease,crop='min(iw,1080)':'min(ih,1920)':'clip((in_w*0.4000)-(out_w/2),0,in_w-out_w)':'clip((in_h*0.6000)-(out_h/2),0,in_h-out_h)',setsar=1[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,trim=end_frame=120,setpts=N/30/TB[v]",
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'file': '/m/vz.mp4', 'speed': 1.5, 'start': 0.0, 'zoom': 1.3},
  'medidas': {'asp': 0.5625,
              'conteudo': [0.4, 0.6, 'preencher'],
              'larg': 1080,
              'lum': 80.0,
              'lum_med': 80,
              'preto': 0.0}},
 {'nome': 'insert_vertical_zoom_crop',
  'fn': 'r_insert',
  's': 3.0,
  'e': 7.0,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-ss',
                '0.0',
                '-t',
                '4.4',
                '-i',
                '/m/vc.mp4',
                '-filter_complex',
                "[0:v]crop=600:900:100:50,setpts=PTS/1.0,tpad=stop_mode=clone:stop_duration=4,split=2[i1][i2];[i1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:1,setsar=1[bg];[i2]scale=1296:2304:force_original_aspect_ratio=decrease,crop='min(iw,1080)':'min(ih,1920)':'(in_w-out_w)/2':'(in_h-out_h)/2',setsar=1[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,trim=end_frame=120,setpts=N/30/TB[v]",
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'crop': '600:900:100:50', 'file': '/m/vc.mp4', 'speed': 1.0, 'start': 0.0, 'zoom': 1.2},
  'medidas': {'asp': 0.5625, 'larg': 1080, 'lum': 140.0, 'lum_med': 140, 'preto': 0.0}},
 {'nome': 'insert_vertical_crop_sem_zoom',
  'fn': 'r_insert',
  's': 3.0,
  'e': 7.0,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-ss',
                '0.0',
                '-t',
                '4.4',
                '-i',
                '/m/vk.mp4',
                '-filter_complex',
                '[0:v]crop=600:900:100:50,eq=brightness=0.216:contrast=1.129,setpts=PTS/1.0,tpad=stop_mode=clone:stop_duration=4,split=2[i1][i2];[i1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:1,setsar=1[bg];[i2]scale=1080:1920:force_original_aspect_ratio=decrease,setsar=1[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,trim=end_frame=120,setpts=N/30/TB[v]',
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'crop': '600:900:100:50',
          'exposicao': 0.12,
          'file': '/m/vk.mp4',
          'speed': 1.0,
          'start': 0.0},
  'medidas': {'asp': 0.5625, 'larg': 1080, 'lum': 50.0, 'lum_med': 50, 'preto': 0.0}},
 {'nome': 'insert_vertical_pip',
  'fn': 'r_insert',
  's': 3.0,
  'e': 7.0,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-ss',
                '0.0',
                '-t',
                '4.4',
                '-i',
                '/m/vp.mp4',
                '-ss',
                '3.0',
                '-t',
                '4.4',
                '-i',
                '/AV/avatar.mp4',
                '-loop',
                '1',
                '-t',
                '4.4',
                '-i',
                '<SOMBRA_PIP>',
                '-filter_complex',
                "[0:v]eq=brightness=0.098:contrast=1.059,setpts=PTS/1.0,tpad=stop_mode=clone:stop_duration=4,split=2[i1][i2];[i1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:1,setsar=1[bg];[i2]scale=1080:1920:force_original_aspect_ratio=decrease,setsar=1[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,trim=end_frame=120,setpts=N/30/TB[base];[1:v]crop=720:720:180:640,scale=300:300,format=yuva420p,geq=lum='lum(X,Y)':cb='cb(X,Y)':cr='cr(X,Y)':a='if(lte(pow(X-150,2)+pow(Y-150,2),22500),255,0)'[pipv];[2:v]scale=420:420[sh];[base][sh]overlay=330:230:shortest=1[b1];[b1][pipv]overlay=390:290:shortest=1[v]",
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'file': '/m/vp.mp4', 'pip': True, 'speed': 1.0, 'start': 0.0},
  'medidas': {'asp': 0.5625,
              'larg': 1080,
              'lum': 80.0,
              'lum_med': 80,
              'preto': 0.0,
              'src': '/m/vp.mp4'},
  'pip_crop': '720:720:180:640'},
 {'nome': 'insert_split_layout_cheio_vertical',
  'fn': 'r_insert',
  's': 3.0,
  'e': 7.0,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-ss',
                '0.0',
                '-t',
                '4.4',
                '-i',
                '/m/vs.mp4',
                '-filter_complex',
                '[0:v]eq=brightness=0.098:contrast=1.059,setpts=PTS/1.0,tpad=stop_mode=clone:stop_duration=4,split=2[i1][i2];[i1]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:1,setsar=1[bg];[i2]scale=1080:1920:force_original_aspect_ratio=decrease,setsar=1[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30,trim=end_frame=120,setpts=N/30/TB[v]',
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'_layout': 'cheio', 'file': '/m/vs.mp4', 'speed': 1.0, 'split': True, 'start': 0.0},
  'medidas': {'asp': 0.5625, 'larg': 1080, 'lum': 80.0, 'lum_med': 80, 'preto': 0.0}},
 {'nome': 'insert_despacha_split',
  'fn': 'r_insert',
  's': 10.88,
  'e': 15.92,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-ss',
                '1.0',
                '-t',
                '5.4399999999999995',
                '-i',
                '/m/h16.mp4',
                '-ss',
                '10.88',
                '-t',
                '5.4399999999999995',
                '-i',
                '/AV/avatar.mp4',
                '-filter_complex',
                "[0:v]setpts=PTS/1.0,tpad=stop_mode=clone:stop_duration=4,split=2[t1][t2];[t1]scale=1080:1150:force_original_aspect_ratio=increase,crop=1080:1150,eq=brightness=0.176:contrast=1.106,boxblur=26:1,eq=brightness=-0.12,setsar=1[tbg];[t2]eq=brightness=0.176:contrast=1.106,scale=1008:566,setsar=1,zoompan=z='min(1+0.42857*on/150,1.42857)':x='iw*0.5000-(iw/zoom/2)':y='ih*0.5000-(ih/zoom/2)':d=1:s=1008x566:fps=30[tvid];color=black@0:s=1128x748:r=30,format=rgba,setsar=1[tcv];[tcv][tvid]overlay=60:122:shortest=1[tcard];movie=<MOLDURAS>/moldura_1_7778.png,format=rgba,setsar=1[tmold];[tcard][tmold]overlay=0:0[tfg];[tbg][tfg]overlay=(W-w)/2:(H-h)/2,setsar=1[top];[1:v]crop=1080:1600:0:100,scale=1080:1600,crop=1080:770:0:480,setsar=1[bot];color=0x141210:s=1080x1920:r=30[cv];[cv][top]overlay=0:0:shortest=1[c1];[c1][bot]overlay=0:1150[c2];color=black:s=1080x90:r=30,format=rgba,geq=r=0:g=0:b=0:a='255*0.62*pow(Y/89,1.6)'[grad];[c2][grad]overlay=0:1060:shortest=1,fps=30,trim=end_frame=151,setpts=N/30/TB[v]",
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'file': '/m/h16.mp4', 'speed': 1.0, 'split': True, 'start': 1.0},
  'medidas': {'asp': 1.7778,
              'foco': [0.5, 0.5],
              'larg': 1920,
              'lum': 60.0,
              'lum_med': 40,
              'preto': 1.0}},
 {'nome': 'insert_despacha_cheio_marcado',
  'fn': 'r_insert',
  's': 4.82,
  'e': 5.6,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-ss',
                '0.0',
                '-t',
                '1.1799999999999993',
                '-i',
                '/m/h16.mp4',
                '-filter_complex',
                "[0:v]setpts=PTS/1.0,tpad=stop_mode=clone:stop_duration=4,split=2[t1][t2];[t1]trim=end_frame=1,loop=loop=-1:size=1:start=0,setpts=N/30/TB,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=60:2,eq=brightness=-0.039:saturation=0.7,setsar=1[bg];[t2]eq=brightness=0.176:contrast=1.106,scale=1036:582,setsar=1,zoompan=z='min(1+0.38996*on/22,1.38996)':x='iw*0.5000-(iw/zoom/2)':y='ih*0.5000-(ih/zoom/2)':d=1:s=1036x582:fps=30[vid];color=black@0:s=1156x764:r=30,format=rgba,setsar=1[cv];[cv][vid]overlay=60:122:shortest=1[card];movie=<MOLDURAS>/moldura_cheio_1_7778.png,format=rgba,setsar=1[mold];[card][mold]overlay=0:0[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,setsar=1,fps=30,trim=end_frame=23,setpts=N/30/TB[v]",
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'_layout': 'cheio', 'file': '/m/h16.mp4', 'speed': 1.0, 'split': True, 'start': 0.0},
  'medidas': {'asp': 1.7778,
              'foco': [0.5, 0.5],
              'larg': 1920,
              'lum': 60.0,
              'lum_med': 40,
              'preto': 0.0}},
 {'nome': 'insert_despacha_horizontal_sem_split',
  'fn': 'r_insert',
  's': 0.62,
  'e': 4.82,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-ss',
                '0.0',
                '-t',
                '4.6000000000000005',
                '-i',
                '/m/h16.mp4',
                '-filter_complex',
                "[0:v]setpts=PTS/1.0,tpad=stop_mode=clone:stop_duration=4,split=2[t1][t2];[t1]trim=end_frame=1,loop=loop=-1:size=1:start=0,setpts=N/30/TB,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=60:2,eq=brightness=-0.039:saturation=0.7,setsar=1[bg];[t2]eq=brightness=0.176:contrast=1.106,scale=1036:582,setsar=1,zoompan=z='min(1+0.38996*on/125,1.38996)':x='iw*0.5000-(iw/zoom/2)':y='ih*0.5000-(ih/zoom/2)':d=1:s=1036x582:fps=30[vid];color=black@0:s=1156x764:r=30,format=rgba,setsar=1[cv];[cv][vid]overlay=60:122:shortest=1[card];movie=<MOLDURAS>/moldura_cheio_1_7778.png,format=rgba,setsar=1[mold];[card][mold]overlay=0:0[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,setsar=1,fps=30,trim=end_frame=126,setpts=N/30/TB[v]",
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'file': '/m/h16.mp4', 'speed': 1.0, 'start': 0.0},
  'medidas': {'asp': 1.7778,
              'foco': [0.5, 0.5],
              'larg': 1920,
              'lum': 60.0,
              'lum_med': 40,
              'preto': 0.0}},
 {'nome': 'insert_horizontal_pip_ignorado',
  'fn': 'r_insert',
  's': 0.62,
  'e': 4.82,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-ss',
                '0.0',
                '-t',
                '4.6000000000000005',
                '-i',
                '/m/h16.mp4',
                '-filter_complex',
                "[0:v]setpts=PTS/1.0,tpad=stop_mode=clone:stop_duration=4,split=2[t1][t2];[t1]trim=end_frame=1,loop=loop=-1:size=1:start=0,setpts=N/30/TB,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=60:2,eq=brightness=-0.039:saturation=0.7,setsar=1[bg];[t2]eq=brightness=0.176:contrast=1.106,scale=1036:582,setsar=1,zoompan=z='min(1+0.38996*on/125,1.38996)':x='iw*0.5000-(iw/zoom/2)':y='ih*0.5000-(ih/zoom/2)':d=1:s=1036x582:fps=30[vid];color=black@0:s=1156x764:r=30,format=rgba,setsar=1[cv];[cv][vid]overlay=60:122:shortest=1[card];movie=<MOLDURAS>/moldura_cheio_1_7778.png,format=rgba,setsar=1[mold];[card][mold]overlay=0:0[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,setsar=1,fps=30,trim=end_frame=126,setpts=N/30/TB[v]",
                '-r',
                '30',
                '-map',
                '[v]',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']],
  'cfg': {'file': '/m/h16.mp4', 'pip': True, 'speed': 1.0, 'start': 0.0},
  'medidas': {'asp': 1.7778,
              'foco': [0.5, 0.5],
              'larg': 1920,
              'lum': 60.0,
              'lum_med': 40,
              'preto': 0.0}},
 {'nome': 'r_logo',
  'fn': 'r_logo',
  's': 40.0,
  'e': 43.2,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-loop',
                '1',
                '-t',
                '3.6000000000000028',
                '-i',
                '<LOGO>',
                '-loop',
                '1',
                '-t',
                '3.6000000000000028',
                '-i',
                '<BRILHO>',
                '-loop',
                '1',
                '-t',
                '3.6000000000000028',
                '-i',
                '<ANEL>',
                '-filter_complex',
                "color=0x141210:s=1080x1920:r=30[bg0];[2:v]format=rgba,scale=1180:1180,rotate='0.3*t':c=none:ow=1180:oh=1180,colorchannelmixer=aa=0.28[rays];[bg0][rays]overlay=x=(W-1180)/2:y=660-590:format=auto[bg1];[1:v]format=rgba,fade=t=in:st=0:d=0.5:alpha=1[gl];[bg1][gl]overlay=0:0:format=auto[bg2];[0:v]fps=30,setpts=PTS-STARTPTS,format=yuva420p,scale=940:-1,scale=w='trunc(iw*(0.84+0.16*min(t/0.7,1))/2)*2':h='trunc(ih*(0.84+0.16*min(t/0.7,1))/2)*2':eval=frame,fade=t=in:st=0:d=0.5:alpha=1[lg];[bg2][lg]overlay=x='(W-w)/2':y='(H-h)/2-300':eval=frame,trim=end_frame=96,setpts=N/30/TB[v]",
                '-map',
                '[v]',
                '-r',
                '30',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']]},
 {'nome': 'r_logo_curto',
  'fn': 'r_logo',
  's': 40.0,
  'e': 40.9,
  'out': '/o/s.mp4',
  'comandos': [['ffmpeg',
                '-y',
                '-loop',
                '1',
                '-t',
                '1.2999999999999985',
                '-i',
                '<LOGO>',
                '-loop',
                '1',
                '-t',
                '1.2999999999999985',
                '-i',
                '<BRILHO>',
                '-loop',
                '1',
                '-t',
                '1.2999999999999985',
                '-i',
                '<ANEL>',
                '-filter_complex',
                "color=0x141210:s=1080x1920:r=30[bg0];[2:v]format=rgba,scale=1180:1180,rotate='0.3*t':c=none:ow=1180:oh=1180,colorchannelmixer=aa=0.28[rays];[bg0][rays]overlay=x=(W-1180)/2:y=660-590:format=auto[bg1];[1:v]format=rgba,fade=t=in:st=0:d=0.35999999999999943:alpha=1[gl];[bg1][gl]overlay=0:0:format=auto[bg2];[0:v]fps=30,setpts=PTS-STARTPTS,format=yuva420p,scale=940:-1,scale=w='trunc(iw*(0.84+0.16*min(t/0.4949999999999993,1))/2)*2':h='trunc(ih*(0.84+0.16*min(t/0.4949999999999993,1))/2)*2':eval=frame,fade=t=in:st=0:d=0.35999999999999943:alpha=1[lg];[bg2][lg]overlay=x='(W-w)/2':y='(H-h)/2-300':eval=frame,trim=end_frame=27,setpts=N/30/TB[v]",
                '-map',
                '[v]',
                '-r',
                '30',
                '-an',
                '-c:v',
                'libx264',
                '-pix_fmt',
                'yuv420p',
                '/o/s.mp4']]}]


def _sem_chaves_vazias(med):
    return {k: v for k, v in med.items() if k != "src"}


def fixar_medidas(mp, med):
    """Troca cada medição por um valor fixo. Medida que o caso não declarou e que o código pedir
    vira falha: a mesma mão que mede no original é a que mede aqui."""
    med = _sem_chaves_vazias(med or {})

    def pega(chave, nome):
        def f(*a, **k):
            if chave not in med:
                raise AssertionError(f"medição inesperada: {nome}{a}")
            return med[chave]
        return f

    mp.setattr(ENQ, "aspecto", pega("asp", "aspecto"))
    mp.setattr(ENQ, "largura_fonte", pega("larg", "largura_fonte"))
    mp.setattr(ENQ, "pular_preto", pega("preto", "pular_preto"))
    mp.setattr(ENQ, "medir_conteudo", pega("conteudo", "medir_conteudo"))
    mp.setattr(EX, "luminancia_fonte", pega("lum", "luminancia_fonte"))
    mp.setattr(EX, "luminancia_mediana_fonte", pega("lum_med", "luminancia_mediana_fonte"))
    foco = tuple(med.get("foco", (0.5, 0.5)))
    mp.setattr(push_in, "foco_do_conteudo", lambda src, start=0.0: foco)


def _normaliza(cmd, dirs):
    saida = []
    for a in cmd:
        a = a.replace(str(dirs["molduras"]), "<MOLDURAS>")
        a = a.replace(str(dirs["gerados"] / FI.SOMBRA_PIP), "<SOMBRA_PIP>")
        a = a.replace(str(dirs["gerados"] / FI.BRILHO_LOGO), "<BRILHO>")
        a = a.replace(str(dirs["gerados"] / FI.ANEL_LOGO), "<ANEL>")
        a = a.replace(LOGO, "<LOGO>")
        saida.append(a)
    return saida


@pytest.fixture
def dirs(tmp_path):
    return {"molduras": tmp_path / "molduras", "gerados": tmp_path / "gerados"}


@pytest.fixture
def gravador(monkeypatch):
    cmds = []
    monkeypatch.setattr(RS, "run", lambda c: cmds.append([str(x) for x in c]))
    monkeypatch.setenv("VAM_SPLIT_BIAS", "0.30")
    for nome in ("_CACHE_CONTEUDO", "_CACHE_ASPECTO", "_CACHE_LARG", "_PRETO_CACHE", "_PIP_CROP_CACHE"):
        getattr(ENQ, nome).clear()
    return cmds


def _chama(caso, dirs):
    cfg = copy.deepcopy(caso.get("cfg"))
    s, e, out = caso["s"], caso["e"], caso["out"]
    mold, ger = str(dirs["molduras"]), str(dirs["gerados"])
    fn = caso["fn"]
    if fn == "r_orig":
        kw = {} if caso["base"] is None else {"base": caso["base"]}
        return RS.r_orig(AV, s, e, out, idx=caso["idx"], **kw)
    if fn == "r_split_tela":
        return RS.r_split_tela(cfg, s, e, out, AV, mold)
    if fn == "r_insert_moldura":
        return RS.r_insert_moldura(cfg, s, e, out, mold)
    if fn == "r_insert":
        return RS.r_insert(cfg, s, e, out, AV, mold, ger)
    if fn == "r_logo":
        return RS.r_logo(s, e, out, LOGO, ger)
    raise AssertionError(fn)


@pytest.mark.parametrize("caso", GOLDEN, ids=lambda c: c["nome"])
def test_comando_bate_com_o_original(caso, gravador, dirs, monkeypatch):
    fixar_medidas(monkeypatch, caso.get("medidas"))
    if caso.get("pip_crop"):
        monkeypatch.setattr(ENQ, "pip_crop", lambda avatar, executar=None: caso["pip_crop"])
    _chama(caso, dirs)
    assert [_normaliza(c, dirs) for c in gravador] == caso["comandos"]


def test_a_cobertura_do_golden_inclui_cada_ramo_de_insert():
    nomes = {c["nome"] for c in GOLDEN}
    for esperado in ("insert_imagem_ken_burns", "insert_vertical_plain", "insert_vertical_zoom",
                     "insert_vertical_pip", "split_vertical_sem_moldura_encaixar",
                     "split_vertical_sem_moldura_preencher", "cheio_lum_none", "r_logo"):
        assert esperado in nomes


# ------------------------------------------------------------------ regras que os goldens mostram

def test_imagem_estatica_faz_ken_burns_ate_1_06(gravador, dirs, monkeypatch):
    caso = next(c for c in GOLDEN if c["nome"] == "insert_imagem_ken_burns")
    fixar_medidas(monkeypatch, caso["medidas"])
    _chama(caso, dirs)
    cmd = gravador[0]
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "zoompan=z='min(zoom+0.0007,1.06)'" in fc
    assert cmd[cmd.index("-loop") + 1] == "1"            # imagem vira fonte "infinita" pro ffmpeg


def test_vertical_abaixo_de_1_05_entra_sem_moldura_no_split(gravador, dirs, monkeypatch):
    caso = next(c for c in GOLDEN if c["nome"] == "split_vertical_sem_moldura_preencher")
    fixar_medidas(monkeypatch, caso["medidas"])
    _chama(caso, dirs)
    cmd = gravador[0]
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "movie=" not in fc and "moldura" not in fc
    assert not dirs["molduras"].exists() or not list(dirs["molduras"].glob("*.png"))


def test_horizontal_em_split_usa_a_moldura_no_aspecto_do_asset(gravador, dirs, monkeypatch):
    caso = next(c for c in GOLDEN if c["nome"] == "split_h16_escuro_pushin")
    fixar_medidas(monkeypatch, caso["medidas"])
    _chama(caso, dirs)
    fc = gravador[0][gravador[0].index("-filter_complex") + 1]
    assert f"movie={dirs['molduras']}/moldura_1_7778.png" in fc
    assert (dirs["molduras"] / "moldura_1_7778.png").is_file()


def test_degrade_da_emenda_tem_piso_0_62_e_painel_de_1150(gravador, dirs, monkeypatch):
    caso = next(c for c in GOLDEN if c["nome"] == "split_h16_escuro_pushin")
    fixar_medidas(monkeypatch, caso["medidas"])
    _chama(caso, dirs)
    fc = gravador[0][gravador[0].index("-filter_complex") + 1]
    assert "geq=r=0:g=0:b=0:a='255*0.62*pow(Y/89,1.6)'[grad]" in fc
    assert "[c1][bot]overlay=0:1150[c2]" in fc
    assert "[c2][grad]overlay=0:1060:shortest=1" in fc


def test_tela_cheia_congela_o_fundo_e_fecha_com_shortest(gravador, dirs, monkeypatch):
    caso = next(c for c in GOLDEN if c["nome"] == "cheio_h16_pushin")
    fixar_medidas(monkeypatch, caso["medidas"])
    _chama(caso, dirs)
    fc = gravador[0][gravador[0].index("-filter_complex") + 1]
    assert "trim=end_frame=1,loop=loop=-1:size=1:start=0" in fc          # fundo = UM quadro esticado
    assert "boxblur=60:2" in fc
    assert "[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1" in fc


def test_fundo_da_tela_cheia_sem_luminancia_medida_usa_o_offset_conhecido(gravador, dirs, monkeypatch):
    caso = next(c for c in GOLDEN if c["nome"] == "cheio_lum_none")
    fixar_medidas(monkeypatch, caso["medidas"])
    _chama(caso, dirs)
    fc = gravador[0][gravador[0].index("-filter_complex") + 1]
    assert "eq=brightness=-0.200:saturation=0.7" in fc


def test_fatia_de_horizontal_ganha_push_in_so_quando_o_asset_encolheu(gravador, dirs, monkeypatch):
    """Fonte de 1920 px encolhe a 0,54 da janela (avança até 1,39x); fonte de 800 px já entra grande."""
    pushin = next(c for c in GOLDEN if c["nome"] == "cheio_h16_pushin")
    largo = next(c for c in GOLDEN if c["nome"] == "cheio_h16_claro_largo")
    fixar_medidas(monkeypatch, pushin["medidas"])
    _chama(pushin, dirs)
    fixar_medidas(monkeypatch, largo["medidas"])
    _chama(largo, dirs)
    com, sem = (c[c.index("-filter_complex") + 1] for c in gravador[:2])
    assert "zoompan=z='min(1+0.38996*on/127,1.38996)'" in com
    assert "zoompan" not in sem


def test_lettering_logo_e_lettering_sao_apresentador_nao_ha_renderizador_proprio():
    """O serif baked (VAM_BAKE_LETTERING=1) e o foil foram removidos: lettering é o r_orig por baixo."""
    for nome in ("r_lettering_serif", "r_lettering", "r_split", "caption_ass", "hero_lettering_ass",
                 "serif_lettering_ass"):
        assert not hasattr(RS, nome), f"{nome} é renderizador morto e saiu"


# ------------------------------------------------------------------ logo e PiP sem assets externos

def test_logo_vem_do_projeto_nunca_de_um_arquivo_cravado(gravador, dirs):
    RS.r_logo(40.0, 43.2, "/o/s.mp4", "/projeto/marca/logo.png", str(dirs["gerados"]))
    cmd = gravador[0]
    entradas = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-i"]
    assert entradas[0] == "/projeto/marca/logo.png"
    assert all("sunburst.png" not in e and "circle_shadow" not in e and "logo_glow" not in e for e in entradas)
    assert all(Path(e).is_file() for e in entradas[1:])               # os outros dois foram gerados


def test_card_de_logo_sem_logo_do_projeto_da_erro_alto(dirs):
    with pytest.raises(CA.ErroFootage) as e:
        RS.r_logo(1.0, 3.0, "/o/s.mp4", None, str(dirs["gerados"]))
    assert "logo" in str(e.value).lower()


def test_pip_nao_depende_de_assets_externos(gravador, dirs, monkeypatch):
    caso = next(c for c in GOLDEN if c["nome"] == "insert_vertical_pip")
    fixar_medidas(monkeypatch, caso["medidas"])
    monkeypatch.setattr(ENQ, "pip_crop", lambda avatar, executar=None: caso["pip_crop"])
    _chama(caso, dirs)
    cmd = gravador[0]
    entradas = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-i"]
    assert entradas[2] == str(dirs["gerados"] / FI.SOMBRA_PIP)
    assert Path(entradas[2]).is_file()


# ------------------------------------------------------------------ pool e cache por segmento

def _ctx(tmp_path, **kw):
    base = dict(avatar=AV, tmp=str(tmp_path / "tmp"), tr=CA.Transicao.do_ambiente({}), inserts={"k": {"file": "/m/k.mp4"}},
                dir_molduras=str(tmp_path / "m"), dir_gerados=str(tmp_path / "g"), logo=LOGO, cache=True, paralelo=1)
    base.update(kw)
    os.makedirs(base["tmp"], exist_ok=True)
    return RS.Contexto(**base)


def _blocos():
    return [{"type": "insert", "narr": "a", "instr": "x k", "_layout": "split"},
            {"type": "orig", "narr": "b", "_base": 1.0},
            {"type": "lettering", "narr": "c", "_base": 1.14},
            {"type": "logo", "narr": "d"},
            {"type": "lettering_logo", "narr": "e"},
            {"type": "orig", "narr": "f", "_base": 1.0}]


SPANS = [(0.0, 2.0), (2.0, 4.0), (4.0, 5.0), (5.0, 6.0), (6.0, 7.0), (7.0, 8.0)]


@pytest.fixture
def falsos(monkeypatch):
    chamadas = []

    def r_orig(avatar, s, e, out, idx=0, base=1.0):
        chamadas.append(("orig", idx, round(s, 3), round(e, 3), base))
        Path(out).write_bytes(b"o")

    def r_insert(cfg, s, e, out, avatar, dir_molduras, dir_gerados):
        chamadas.append(("insert", cfg.get("_layout"), round(s, 3), round(e, 3)))
        Path(out).write_bytes(b"i")

    def r_logo(s, e, out, logo, dir_gerados):
        chamadas.append(("logo", round(s, 3), round(e, 3), logo))
        Path(out).write_bytes(b"l")

    monkeypatch.setattr(RS, "r_orig", r_orig)
    monkeypatch.setattr(RS, "r_insert", r_insert)
    monkeypatch.setattr(RS, "r_logo", r_logo)
    return chamadas


def test_cada_tipo_de_bloco_vai_pro_renderizador_certo_com_o_handle_da_transicao(tmp_path, falsos):
    """Insert -> orig leva whip de 0,08 s (o handle estende o fim do insert); orig -> lettering e
    qualquer entrada de insert/logo/lettering_logo são secas; lettering é r_orig com a base do
    bloco; lettering_logo é r_orig SEM base (o default do original); o último não tem cauda."""
    ctx = _ctx(tmp_path)
    segs = RS.renderizar_todos(_blocos(), SPANS, ctx)
    assert segs == [os.path.join(ctx.tmp, f"s{i:02d}.mp4") for i in range(6)]
    assert falsos == [("insert", "split", 0.0, 2.08),
                      ("orig", 1, 2.0, 4.0, 1.0),
                      ("orig", 2, 4.0, 5.0, 1.14),
                      ("logo", 5.0, 6.0, LOGO),
                      ("orig", 4, 6.0, 7.08, 1.0),
                      ("orig", 5, 7.0, 8.0, 1.0)]


def test_resultado_vem_na_ordem_dos_indices_mesmo_com_4_workers(tmp_path, falsos, monkeypatch):
    def lento(avatar, s, e, out, idx=0, base=1.0):
        time.sleep(0.05 if idx == 1 else 0.0)
        Path(out).write_bytes(b"o")

    monkeypatch.setattr(RS, "r_orig", lento)
    ctx = _ctx(tmp_path, paralelo=4)
    segs = RS.renderizar_todos(_blocos(), SPANS, ctx)
    assert [os.path.basename(p) for p in segs] == [f"s{i:02d}.mp4" for i in range(6)]


def test_segundo_build_com_a_mesma_entrada_vem_do_cache(tmp_path, falsos, capsys):
    ctx = _ctx(tmp_path)
    RS.renderizar_todos(_blocos(), SPANS, ctx)
    primeiro = len(falsos)
    RS.renderizar_todos(_blocos(), SPANS, ctx)
    assert len(falsos) == primeiro, "nada devia renderizar de novo"
    assert capsys.readouterr().out.count("cache") == 6


def test_cache_desligado_renderiza_sempre(tmp_path, falsos):
    ctx = _ctx(tmp_path, cache=False)
    RS.renderizar_todos(_blocos(), SPANS, ctx)
    RS.renderizar_todos(_blocos(), SPANS, ctx)
    assert len(falsos) == 12
    assert not os.path.exists(os.path.join(ctx.tmp, "cache"))


def test_trocar_o_conteudo_da_fonte_invalida_o_cache(tmp_path, falsos):
    avatar = tmp_path / "avatar.mp4"
    avatar.write_bytes(b"v1")
    ctx = _ctx(tmp_path, avatar=str(avatar))
    blocos = [{"type": "orig", "narr": "a", "_base": 1.0}, {"type": "orig", "narr": "b", "_base": 1.14}]
    RS.renderizar_todos(blocos, SPANS[:2], ctx)
    n = len(falsos)
    avatar.write_bytes(b"conteudo bem maior que o anterior")
    os.utime(str(avatar), (time.time() + 50, time.time() + 50))
    RS.renderizar_todos(blocos, SPANS[:2], ctx)
    assert len(falsos) == n + 2


def test_insert_que_nao_casa_aborta_com_erro_alto(tmp_path, falsos):
    ctx = _ctx(tmp_path, inserts={})
    with pytest.raises(CA.ErroFootage):
        RS.renderizar_todos(_blocos(), SPANS, ctx)


def test_card_de_logo_usa_o_logo_do_contexto_e_a_chave_de_cache_acompanha_o_arquivo(tmp_path, falsos):
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"png1")
    ctx = _ctx(tmp_path, logo=str(logo))
    blocos = [{"type": "logo", "narr": "x"}]
    RS.renderizar_todos(blocos, [(0.0, 2.0)], ctx)
    logo.write_bytes(b"png2 diferente")
    os.utime(str(logo), (time.time() + 50, time.time() + 50))
    RS.renderizar_todos(blocos, [(0.0, 2.0)], ctx)
    assert sum(1 for c in falsos if c[0] == "logo") == 2
