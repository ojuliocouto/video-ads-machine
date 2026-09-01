"""Gera as configs por (ad, look) pro gen_ad_v2.py. Autoria: hooks, letterings, kw, CTA."""
import json
from pathlib import Path

from caminhos import INPUTS as V1  # noqa: E402
from caminhos import V2L  # noqa: E402

LOOKS = {
    "espuma_roxa": "espuma",
    "selfie_neon": "neon",
    # estudio_claro (avatar 3eda6f0a...) foi ABANDONADO: a HeyGen entrega ele com o
    # conteudo em 16:9 e tarja branca no 9:16. Ver reference-avatares-heygen-thales.
    "estudio_verde": "estverde",
    "oficial_13": "of13",
    "dentro_carro": "carro",
    # leva Jheni 2 (18/08/2026): sem estes dois o gerador morria com KeyError depois de
    # escrever o config do jh14, e os builds do jh15 e do jh16 caiam em "config nao existe".
    "neon_branca": "neonbranca",
    "espuma_branca": "espbranca",
    # os 8 oficiais completos: o build_composite importa ESTE dicionario, entao look que
    # falta aqui derruba o build depois do avatar pronto (jh15, KeyError 'neon_creme').
    "neon_creme": "neoncreme",
    "estudio_claro": "estclaro",
    "espuma_fechado": "espfechado",
    "espuma_estampado": "espestampado",
}

ADS = {
    # Leva da Jheni (AD13..AD24). Os letterings vem do DOC dela: ele marca [lettering] em
    # blocos especificos. LEAD e KEY sao recorte CONTIGUO da propria fala daquele bloco,
    # nunca texto novo, e o `anchor` e a palavra onde o lettering pousa.
    # Sem esta entrada o config nascia com "letterings": [] e os tres sumiam calados: o
    # gate nao acusa, porque legenda tem, e o video sai parecendo certo.
    "jh13v2": {
        # D8 do diretor de arte: neste enquadramento nao cabe lead + pill + logo acima da
        # safe zone sem o "TOCA EM" pousar no queixo. O lettering do CTA ja diz "TOCA EM".
        "cta_sem_lead": True,
        # HOOK (17/08/2026): nascia VAZIO e por isso o anuncio abria sem nada escrito
        # na tela, que foi a segunda queixa da Jheni. As palavras sao recorte da fala
        # do bloco 0 ("É inadmissível ver infoprodutores... criando essas páginas
        # feias… com cara de I.A…"): nada de texto novo, ordem do Julio.
        # style "punch" (Jheni, 17/08/2026): sans pesado em caixa alta no lugar do serif
        # elegante, na linha da ref instagram.com/p/DZ-GKJ7u54z. O 🤡 foi pedido dela.
        "hook": {"eyebrow": "É INADMISSÍVEL", "l1": "essas páginas feias",
                 "accent": "COM CARA DE I.A", "style": "punch"},
        "cta_label": "saiba mais",
        "kw_phrases": ["com cara de I.A…", "skill", "completamente diferente.",
                        "sem pagar hospedagem.", "deixa de vender.", "algo concreto.",
                        "Operação Claude Code.", "dois dias", "saiba mais"],
        # O doc escreve o bloco da dor como LISTA de tres itens marcados com ❌
        # ("Enquanto isso:❌ a campanha não sobe❌o teste não acontece ❌ e você deixa
        # de vender"). Antes isso virava UM lettering so e a direcao visual sumia.
        # Agora sao tres, cada um pousando na palavra que a voz fala.
        "letterings": [
            # nth explicito: "sabe" aparece 3x na fala; o lettering e o do bloco 1.
            {"lead": "sabe", "key": "por quê?", "anchor": "sabe", "nth": 1, "dur": 1.8},
            # Dois KEYs no miolo: o diretor de arte mediu 49s (55% do anuncio) sem
            # nenhum lettering, e as duas afirmacoes mais fortes passavam sem pico.
            # "sem pagar hospedagem" e a promessa de custo e nao tinha nada na tela.
            # TIRADO: este cai num close em que o rosto ocupa de y1042 a y1702. Mesmo na
            # posicao baixa o texto encosta no queixo (gate de colisao: 2,4%). Nao ha
            # faixa livre nesse enquadramento; so entra se o bloco ganhar plano mais
            # aberto ou se a fala for coberta por insert.
            # ancora em "melhor" (nao em "hospedagem"): com a ancora na ultima palavra
            # da frase o card so subia depois dela terminar, e os 2,0s do "E o melhor:"
            # ficavam com a tela sem NENHUM texto (maior vao do anuncio, medido pelo
            # diretor de arte em 18/08/2026). "melhor" aparece 1x na fala inteira.
            {"lead": "e o melhor:", "key": "SEM PAGAR HOSPEDAGEM",
             "anchor": "melhor", "nth": 1, "dur": 3.4},
            # nth=2 OBRIGATORIO: "campanha" aparece duas vezes na fala (bloco 7, "uma
            # nova oferta, uma campanha ou uma ideia", e bloco 9, o da dor). Sem nth o
            # lettering pousou no bloco 7 e apareceu com a voz falando outra coisa
            # (visto na auditoria do build de 17/08/2026).
            # PILHA (18/08/2026): os tres entravam na MESMA posicao, cada um apagando o
            # anterior, com dois vaos em branco no meio (59,0s e 60,5s). A copy e um
            # tricolon que ACUMULA perda, entao a tela tem que acumular tambem: agora
            # cada linha pousa na propria palavra e as tres ficam ate o fim do trecho.
            {"lead": "enquanto isso:", "key": "❌ a campanha não sobe", "anchor": "campanha",
             "nth": 2, "dur": 1.4, "pilha": "dor"},
            {"lead": "", "key": "❌ o teste não acontece", "anchor": "teste",
             "dur": 1.4, "pilha": "dor"},
            {"lead": "", "key": "❌ e você deixa de vender", "anchor": "deixa",
             "dur": 2.2, "pilha": "dor"},
            # D9 do diretor de arte (18/08/2026): o bloco 7 roda 10,6s e o bloco 10
            # roda 4,6s sem NENHUM lettering. Todos os textos abaixo sao recorte literal
            # da fala, e as quatro ancoras aparecem 1x cada no anuncio inteiro.
            {"lead": "se você é do digital, sabe", "key": "O TAMANHO DO PROBLEMA",
             "anchor": "tamanho", "nth": 1, "dur": 2.2},
            {"lead": "toda vez que surge", "key": "UMA NOVA OFERTA",
             "anchor": "oferta", "nth": 1, "dur": 2.4},
            {"lead": "começa a", "key": "MESMA HISTÓRIA",
             "anchor": "mesma", "nth": 1, "dur": 1.4},
            {"lead": "não é a", "key": "FALTA DE IDEIAS",
             "anchor": "falta", "nth": 1, "dur": 2.2},
            # nth explicito: "transformar" aparece 2x (aqui e no bloco da imersao).
            {"lead": "para transformar uma ideia", "key": "em algo concreto",
             "anchor": "transformar", "nth": 1, "dur": 2.4},
            # BLOCO 14, o do CTA. Estava FALTANDO: o roteiro pede
            # "[thales de frente + lettering + logo da occ | LEAD: toca em | KEY: SAIBA MAIS]"
            # e eu escrevi so tres letterings aqui, esquecendo justamente o do pico de
            # intencao. O diretor de arte reprovou por isso (17/08/2026): a voz manda
            # tocar no botao e a tela nao reforcava nada.
            {"lead": "toca em", "key": "SAIBA MAIS", "anchor": "toca", "nth": 1, "dur": 2.6},
        ],
        "labels": {},
    },
    # ---------------- leva Jheni: 14, 15 e 16 (18/08/2026) ----------------
    # Bloco 1 dos tres e lettering de abertura: quem entrega ele e o HOOK, por isso ele
    # nao aparece de novo na lista de letterings.
    "jh14v2": {
        # D10: o lead "toca em" pousava no queixo, e a instrucao ja existe 3x
        # (lettering do CTA, pill e a propria fala). Fica pill + logo.
        "cta_sem_lead": True,
        "hook": {"eyebrow": "TEM MUITA GENTE", "l1": "que vive do digital",
                 "accent": "E NÃO SABE FAZER ISSO", "style": "punch"},
        "cta_label": "saiba mais",
        "kw_phrases": ["sem esperar", "executa sozinho", "já está pronto",
                       "dia, horário", "Operação Claude Code.", "dois dias"],
        "letterings": [
            # D12: com 1.8 o card ficava branco sobre a tela clara do insert nos ultimos 0,2s.
            {"lead": "olha", "key": "O QUE DÁ PRA FAZER", "anchor": "olha", "nth": 1, "dur": 1.4},
            {"lead": "trabalha sozinho?", "key": "ISSO MUDA SEU JOGO", "anchor": "muda",
             "nth": 1, "dur": 2.2},
            # D11 (20/08): os blocos 6 e 8 rodavam 20,3s sem nenhum card. Em pilha porque
            # a copy e um par de consequencia, e par que se substitui le como recarregar.
            {"lead": "se você não parar", "key": "NÃO TEM CONTEÚDO",
             "anchor": "produzir", "dur": 2.0, "pilha": "parada"},
            {"lead": "", "key": "A OPERAÇÃO TAMBÉM PARA",
             "anchor": "folga", "dur": 2.2, "pilha": "parada"},
            {"lead": "times de I.A. que executam", "key": "O TRABALHO OPERACIONAL",
             "anchor": "operacional", "dur": 2.2},
            {"lead": "toca em", "key": "SAIBA MAIS", "anchor": "toca", "nth": 1, "dur": 2.6},
        ],
        "labels": {},
    },
    "jh15v2": {
        # D10: o lead "toca em" pousava no queixo, e a instrucao ja existe 3x
        # (lettering do CTA, pill e a propria fala). Fica pill + logo.
        "cta_sem_lead": True,
        "hook": {"eyebrow": "O CLAUDE CODE", "l1": "é péssimo pra",
                 "accent": "CRIAR IMAGENS", "style": "punch"},
        "cta_label": "saiba mais",
        # "chave gratuita" saiu: virou card (D11) e como kw ficaria a mesma frase 2x na tela
        "kw_phrases": ["Nano Banana", "muito melhores",
                       "Operação Claude Code.", "dois dias"],
        "letterings": [
            # "pessimo" aparece 2x (bloco 1 e bloco 3); este e o do bloco 3.
            {"lead": "não preciso dizer", "key": "FICA PÉSSIMO, NÉ?", "anchor": "péssimo",
             "nth": 2, "dur": 1.8},
            {"lead": "pera aí", "key": "DÁ PRA MELHORAR", "anchor": "melhorar",
             "nth": 1, "dur": 1.8},
            # 2.4 fazia este lettering atravessar 0,53s por cima do lettering do CTA,
            # e os dois saiam impressos um sobre o outro no pico de intencao.
            # D11 (20/08): 11,52s e 17,6s de rosto sem nenhum card.
            {"lead": "usando uma chave", "key": "GRATUITA DO GOOGLE AI STUDIO",
             "anchor": "gratuita", "dur": 2.2},
            {"lead": "deixa de depender de", "key": "FREELANCER ENROLADO",
             "anchor": "freelancer", "dur": 2.2},
            {"lead": "e te dá a", "key": "LIBERDADE DE TESTAR MAIS",
             "anchor": "liberdade", "dur": 2.2},
            {"lead": "criar", "key": "SEUS PRÓPRIOS TIMES DE I.A", "anchor": "próprios",
             "nth": 1, "dur": 1.6},
            {"lead": "toca em", "key": "SAIBA MAIS", "anchor": "toca", "nth": 1, "dur": 2.6},
        ],
        "labels": {},
    },
    "jh16v2": {
        # D10: o lead "toca em" pousava no queixo, e a instrucao ja existe 3x
        # (lettering do CTA, pill e a propria fala). Fica pill + logo.
        "cta_sem_lead": True,
        "hook": {"eyebrow": "DEIXA EU ADIVINHAR", "l1": "você vive do digital",
                 "accent": "E TRABALHA SOZINHO", "style": "punch"},
        "cta_label": "saiba mais",
        "kw_phrases": ["cara de I.A.,", "não funciona.", "um único prompt.",
                       "Operação Claude Code.", "dois dias"],
        "letterings": [
            {"lead": "e te fez concluir", "key": "QUE NÃO FUNCIONA", "anchor": "concluir",
             "nth": 1, "dur": 2.0},
            # ancora em "partes": com "dividi" o card entrava 1,6s ANTES da voz dizer
            # "tres partes", e ja tinha saido quando ele falava.
            # D13 (20/08): o ASSET do bloco traz "DIVIDI EM / TRES PARTES" impresso, no
            # mesmo serif italico e na mesma altura. Com 1.8 ficavam 1,08s com o mesmo
            # texto duas vezes empilhado. Com 0.9 o card entrega a frase e o asset segue.
            {"lead": "dividi em", "key": "TRÊS PARTES", "anchor": "partes",
             "nth": 1, "dur": 0.9},
            # D11 (20/08): o bloco 9 roda 24,72s com ZERO card, e a copy ali e o tricolon
            # das tres skills. Mesmo caso do "❌" em pilha do AD13: acumula e fica.
            {"lead": "deixa eu te contar um segredo:", "key": "O PROBLEMA NÃO FOI O CLAUDE",
             "anchor": "segredo", "dur": 2.4},
            {"lead": "a primeira", "key": "PESQUISA OS TEMAS",
             "anchor": "relevantes", "dur": 1.6, "pilha": "time"},
            {"lead": "", "key": "A SEGUNDA VIRA GANCHO E ROTEIRO",
             "anchor": "gancho", "dur": 1.6, "pilha": "time"},
            {"lead": "", "key": "A TERCEIRA CRIA O DESIGN",
             "anchor": "design", "dur": 2.4, "pilha": "time"},
            {"lead": "sem depender de", "key": "FREELANCER QUE NÃO ENTREGA",
             "anchor": "entrega", "dur": 2.2},
            {"lead": "te convido pra", "key": "OPERAÇÃO CLAUDE CODE", "anchor": "convido",
             "nth": 1, "dur": 2.4},
        ],
        "labels": {},
    },

    "ad02": {
        "hook": {"eyebrow": "aqui tem", "l1": "editor, designer, webdesigner…", "accent": "tudo no Claude!"},
        "cta_label": "saiba mais",
        "kw_phrases": ["CLAUDE!", "prospecção", "no automático:", "Operação Claude Code.",
                        "2 dias", "saiba mais", "código."],
        "letterings": [
            {"lead": "e sim pelo", "key": "Claude!", "anchor": "CLAUDE!", "dur": 2.2},
            {"lead": "uma imersão de", "key": "2 dias", "anchor": "imersão", "dur": 2.4},
        ],
        "labels": {"4 abas": "claude com 4 abas trabalhando", "apify": "prospecção no automático",
                    "buscando as empresas": "busca no google", "extraindo o email": "e-mail · contato",
                    "abordagem personalizada": "abordagem personalizada",
                    "take 1": "montando um time de i.a", "take 2": "montando um time de i.a"},
    },
    "ad03": {
        "hook": {"eyebrow": "isso aqui é", "l1": "o Claude prospectando", "accent": "no automático"},
        "cta_label": "saiba mais",
        "kw_phrases": ["prospectando", "no automático.", "skills", "GASTANDO MAIS, LUCRANDO MENOS",
                        "times de I.A", "Operação Claude Code:", "2 dias", "saiba mais"],
        "letterings": [
            {"lead": "o mercado se dividiu", "key": "em dois", "anchor": "dividiu", "dur": 2.2},
            {"lead": "a escolha", "key": "é sua!", "anchor": "escolha", "dur": 2.2},
        ],
        "labels": {"apify": "prospecção no automático", "buscando as empresas": "busca no google",
                    "extraindo o email": "e-mail · contato", "abordagem personalizada": "abordagem personalizada",
                    "criando uma skill": "criando uma skill", "conectando o claude ao google": "mcp do google",
                    "take 1": "montando um time de i.a", "4 abas": "claude com 4 abas trabalhando",
                    "take 2": "montando um time de i.a", "skill de prospecção em ação": "skill de prospecção"},
    },
    "ad04": {
        "hook": {"eyebrow": "isso aqui é", "l1": "o Claude gerando vídeos", "accent": "por mim!"},
        "cta_label": "garanta sua vaga",
        "kw_phrases": ["Ads Machine,", "R$48 mil", "prospecção,", "30 mil reais",
                        "Operação Claude Code,", "2 dias", "vaga"],
        "letterings": [
            {"lead": "só esse time economiza", "key": "R$48 mil/ano", "anchor": "economiza", "dur": 2.4},
            {"lead": "nada disso é", "key": "exclusividade minha", "anchor": "exclusividade", "dur": 2.2},
        ],
        "labels": {"skill de criação de vídeos": "skill de vídeo no claude", "clonando": "clone de imagem e voz",
                    "cortando": "corte · legenda · efeitos", "apify": "prospecção no automático",
                    "economizando": "economia todo mês", "aula": "montando um time de i.a",
                    "construindo skills": "construindo skills"},
    },
    "ad05": {
        "hook": {"eyebrow": "você tá pagando", "l1": "salário, ferramenta, freelancer…", "accent": "pra quê?"},
        "cta_label": "saiba mais",
        "kw_phrases": ["PORQUE?", "CLAREZA", "distração!", "skills", "MCPs", "6 mil pessoas",
                        "Operação Claude Code.", "saiba mais"],
        "letterings": [
            {"lead": "a pergunta é", "key": "PORQUE?", "anchor": "PORQUE?", "dur": 2.2},
            {"lead": "chegou a hora de", "key": "dar um basta!", "anchor": "basta", "dur": 2.2},
        ],
        "labels": {"4 abas": "claude com 4 abas trabalhando", "take a": "montando um time de i.a",
                    "instagram": "só distração", "criando uma skill": "criando uma skill",
                    "mcp do google": "mcp do google", "claude code na tela": "claude code",
                    "take b": "montando um time de i.a", "take c": "montando um time de i.a",
                    "mcps, take 2": "mcps no claude", "páginas profissionais": "páginas do zero",
                    "apify": "prospecção no automático"},
    },
    "ad06": {
        "hook": {"eyebrow": "daqui a 1 ano", "l1": "não vai existir agência", "accent": "sem isso aqui!"},
        "cta_label": "garanta seu ingresso",
        "kw_phrases": ["agência", "departamento inteiro", "4, 5, 6 funcionários", "lucra muito mais",
                        "Operação Claude Code,", "2 dias", "ingresso"],
        "letterings": [
            {"lead": "tem agência pagando", "key": "4, 5, 6 funcionários", "anchor": "funcionários", "dur": 2.4},
            {"lead": "quem fica com", "key": "o cliente?", "anchor": "cliente", "dur": 2.2},
        ],
        "labels": {"4 abas": "claude com 4 abas trabalhando", "take a": "montando um time de i.a",
                    "take b": "montando um time de i.a", "apify": "prospecção no automático",
                    "páginas profissionais": "páginas do zero"},
    },
    "ad07": {
        "hook": {"eyebrow": "quer colocar o Claude", "l1": "pra trabalhar", "accent": "na sua empresa?"},
        "cta_label": "garanta seu ingresso",
        "kw_phrases": ["próprias soluções", "abordagem personalizada", "time humano",
                        "2 dias", "saiba mais"],
        "letterings": [
            {"lead": "sob medida", "key": "pro seu negócio", "anchor": "medida", "dur": 2.2},
            {"lead": "uma imersão de", "key": "2 dias", "anchor": "imersão", "dur": 2.4},
        ],
        "labels": {"apify": "prospecção no automático", "google": "busca no google",
                    "email": "e-mail · contato", "abordagem": "abordagem personalizada"},
    },
    "ad08": {
        "hook": {"eyebrow": "você paga pelo Claude", "l1": "e tá jogando", "accent": "dinheiro fora?"},
        "cta_label": "garanta seu ingresso",
        "kw_phrases": ["ponte", "de graça", "pulo do gato", "funcionário humano",
                        "2 dias", "saiba mais"],
        "letterings": [
            {"lead": "e aqui tá", "key": "o pulo do gato", "anchor": "gato", "dur": 2.2},
            {"lead": "uma imersão de", "key": "2 dias", "anchor": "imersão", "dur": 2.4},
        ],
        "labels": {"mcp do google": "mcp do google"},
    },
    "ad09": {
        "hook": {"eyebrow": "a Anthropic lançou", "l1": "o Fable 5", "accent": "o modelo mais poderoso"},
        "cta_label": "garanta seu ingresso",
        "kw_phrases": ["GASTAR MENOS", "pulo do gato", "92% da qualidade", "fração do preço",
                        "times de I.A", "2 dias"],
        "letterings": [
            {"lead": "usar ele pra", "key": "GASTAR MENOS", "anchor": "MENOS", "dur": 2.2},
            {"lead": "o Claude tivesse", "key": "92% da qualidade", "anchor": "92%", "dur": 2.2},
        ],
        "labels": {"trabalho_pesado_skill": "modelo barato faz o grosso", "gastando_menos": "economia real",
                    "times_ia_claude": "montando um time de i.a", "imersao_evento": "imersão de 2 dias"},
    },
    "ad10": {
        "hook": {"eyebrow": "esqueça o n8n", "l1": "o Claude agora faz", "accent": "sozinho!"},
        "cta_label": "garanta seu ingresso",
        "kw_phrases": ["n8n", "no automático", "VIROU COMPLETAMENTE", "times de IA",
                        "24 horas por dia", "2 dias"],
        "letterings": [
            {"lead": "conheça o", "key": "Claude Routines", "anchor": "Routines", "dur": 2.4},
            {"lead": "o jogo", "key": "VIROU COMPLETAMENTE", "anchor": "COMPLETAMENTE", "dur": 2.2},
        ],
        "labels": {"fluxo_make_n8n": "n8n cheio de nós", "times_ia_rh": "montando um time de i.a",
                    "imersao_evento": "imersão de 2 dias", "apify_minerar": "minerando anúncios",
                    "aluno_criando_skill": "criando uma skill", "prospeccao_google": "levantando dados",
                    "claude_trabalhando": "claude trabalhando"},
    },
    "ad12v2": {
        "hook": {"eyebrow": "ela criou tudo isso", "l1": "sem saber automação", "accent": ""},
        "cta_label": "saiba mais",
        "kw_phrases": ["sem entender nada de automação", "90 dias de post", "não é código",
                        "escrito em português", "todas as vezes.", "é genérica.",
                        "o seu jeito de fazer", "dois dias práticos"],
        "letterings": [
            {"lead": "skill não é código", "key": "É UM MANUAL", "anchor": "manual", "dur": 2.5},
            {"lead": "skill pronta", "key": "É GENÉRICA", "anchor": "genérica", "dur": 2.4},
        ],
        "labels": {"o que a empresaria criou": "o que ela construiu",
                    "a skill na tela": "isso é uma skill",
                    "skills prontas na internet": "skill pronta da internet",
                    "depoimentos de alunos": "quem já construiu",
                    "aula acelerada": "operação claude code"},
    },
    "ad11v2": {
        "hook": {"eyebrow": "psicóloga, advogado", "l1": "consultor comercial", "accent": ""},
        "cta_label": "saiba mais",
        "kw_phrases": ["sem nunca ter feito uma automação", "dois dias", "não precisa saber programar",
                        "um bloco de texto", "direto no seu WhatsApp", "roda sem você", "primeiro lote"],
        "letterings": [
            {"lead": "dois dias", "key": "CONSTRUINDO<br>COM VOCÊ", "anchor": "constrói", "dur": 2.5},
            {"lead": "não precisa", "key": "SABER<br>PROGRAMAR", "anchor": "programar", "dur": 2.5},
        ],
        "labels": {"depoimentos de alunos": "quem já construiu",
                    "criando a skill": "criando a skill",
                    "pagina com quiz": "página com qualificação de lead",
                    "prospeccao rodando": "prospecção rodando sozinha",
                    "squad rodando": "o squad rodando sozinho",
                    "aula acelerada": "operação claude code"},
    },
    "ad10v2": {
        "hook": {"eyebrow": "o que eu vou", "l1": "construir de verdade?", "accent": ""},
        "cta_label": "saiba mais",
        "kw_phrases": ["não vai só assistir.", "sem você pagar hospedagem", "já qualificado no seu WhatsApp",
                        "todo santo dia.", "um bloco de texto.", "8 mil pessoas", "outra edição."],
        "letterings": [
            {"lead": "no primeiro dia", "key": "VOCÊ NÃO VAI<br>SÓ ASSISTIR", "anchor": "assistir", "dur": 2.6},
            {"lead": "não precisa", "key": "PROGRAMAR", "anchor": "programar", "dur": 2.4},
        ],
        "labels": {"pergunta do aluno": "pergunta de aluno",
                    "pagina publicada": "página publicada pelo claude",
                    "quiz de qualificacao": "quiz que qualifica o lead",
                    "prospeccao automatica": "prospecção no automático",
                    "criando a skill": "criando a skill",
                    "squad rodando": "o squad rodando sozinho",
                    "aula acelerada": "operação claude code"},
    },
    "ad09v2": {
        "hook": {"eyebrow": "um time de I.A", "l1": "pra cada problema", "accent": ""},
        "cta_label": "saiba mais",
        "kw_phrases": ["só te enrola.", "domingo à noite", "os três níveis.", "no seu tom",
                        "sem mensalidade.", "todo dia no mesmo horário", "dois dias práticos"],
        "letterings": [
            {"lead": "um time de I.A", "key": "FAZ ISSO<br>POR VOCÊ", "anchor": "você", "dur": 2.5},
            {"lead": "três freelancers", "key": "QUE VOCÊ NÃO PRECISA<br>MAIS CHAMAR", "anchor": "chamar", "dur": 2.8},
        ],
        "labels": {"slide times de ia": "um time pra cada problema",
                    "skill de conteudo": "skill de conteúdo",
                    "skill de paginas": "skill de páginas",
                    "skill de prospeccao": "skill de prospecção",
                    "aula acelerada": "operação claude code"},
    },
    "ad08v2": {
        "hook": {"eyebrow": "o Claude", "l1": "fez isso", "accent": ""},
        "cta_label": "saiba mais",
        "kw_phrases": ["corte, legenda, trilha", "volta fora do que você pediu", "48 mil reais",
                        "100 vídeos prontos.", "um bloco de texto.", "dois dias"],
        "letterings": [
            {"lead": "o preço é o que", "key": "VOCÊ DEIXA<br>DE VENDER", "anchor": "vender", "dur": 2.6},
            {"lead": "eu gastava", "key": "R$ 48 MIL<br>POR ANO", "anchor": "mil", "dur": 2.6},
        ],
        "labels": {"videos prontos": "vídeos prontos e editados",
                    "skill de edicao": "skill de edição",
                    "paga caro espera volta errado": "paga caro, espera, volta errado",
                    "criando a skill": "criando a skill",
                    "skill publicando pagina": "página no ar sozinha",
                    "aula acelerada": "operação claude code"},
    },
    "ad07v2": {
        "hook": {"eyebrow": "troque o freelancer", "l1": "por uma skill", "accent": ""},
        "cta_label": "saiba mais",
        "kw_phrases": ["refém de freelancers.", "no prazo.", "em minutos.", "no ar automático.",
                        "ideia e execução.", "imersão prática", "do zero"],
        "letterings": [
            {"lead": "nunca te entrega", "key": "NO PRAZO", "anchor": "prazo", "dur": 2.4},
            {"lead": "o que trava é", "key": "O TEMPO ENTRE<br>IDEIA E EXECUÇÃO", "anchor": "execução", "dur": 2.8},
        ],
        "labels": {"freelancer vira skill": "freelancer vira skill",
                    "organograma geral": "o organograma da operação",
                    "organograma editor": "time de edição",
                    "organograma webdesigner": "time de web design",
                    "organograma desenvolvedor": "time de desenvolvimento",
                    "skill de edicao": "skill de edição",
                    "skill publicando pagina": "página no ar sozinha",
                    "aula acelerada": "operação claude code"},
    },
    "ad06v2": {
        "hook": {"eyebrow": "um time de I.A", "l1": "pra cada área", "accent": ""},
        "cta_label": "saiba mais",
        "kw_phrases": ["nenhuma automação.", "vídeo pronto.", "publica e ainda audita",
                        "um por um.", "uma contratação.", "uma skill no Cloud", "dois dias"],
        "letterings": [
            {"lead": "isso é possível", "key": "HOJE", "anchor": "possível", "dur": 2.2},
            {"lead": "cada área é", "key": "UMA<br>CONTRATAÇÃO", "anchor": "contratação", "dur": 2.6},
        ],
        "labels": {"organograma geral": "o organograma da operação",
                    "organograma editor": "time de edição",
                    "organograma webdesigner": "time de web design",
                    "organograma prospeccao": "time de prospecção",
                    "agentes no whatsapp": "agentes no whatsapp",
                    "criando a skill": "criando a skill",
                    "aula acelerada": "operação claude code"},
    },
    "ad05v2": {
        "hook": {"eyebrow": "digita", "l1": "/contratar", "accent": ""},
        "cta_label": "saiba mais",
        "kw_phrases": ["barra contratar", "24 horas por dia", "já é possível.", "uma skill,",
                        "em português", "100% um funcionário humano", "dois dias"],
        "letterings": [
            {"lead": "hoje isso", "key": "JÁ É POSSÍVEL", "anchor": "possível", "dur": 2.4},
            {"lead": "não escreve código", "key": "FALA EM<br>PORTUGUÊS", "anchor": "português", "dur": 2.6},
        ],
        "labels": {"barra contratar claude": "/contratar no claude",
                    "editor de video no claude": "o editor de vídeo",
                    "criando a skill": "criando a skill",
                    "aula acelerada": "operação claude code"},
    },
    "ad04v2": {
        "hook": {"eyebrow": "você contratou", "l1": "pra sair do operacional", "accent": ""},
        "cta_label": "saiba mais",
        "kw_phrases": ["segundo trabalho.", "uma única vez.", "em minutos.", "no centésimo.",
                        "no automático.", "em massa", "não sou eu", "nenhum real a mais."],
        "letterings": [
            {"lead": "contratou pra sair", "key": "GANHOU UM<br>SEGUNDO", "anchor": "segundo", "dur": 2.6},
            {"lead": "os processos que", "key": "JÁ ESTÃO NA<br>SUA CABEÇA", "anchor": "cabeça", "dur": 2.8},
        ],
        "labels": {"skills web video paginas": "skills: vídeo, página, prospecção",
                    "organograma geral": "o organograma da operação",
                    "organograma editor": "o editor de vídeo",
                    "skill gerando video": "skill de edição",
                    "organograma webdesigner": "o web designer",
                    "skill publicando pagina": "página no ar sozinha",
                    "organograma prospeccao": "a prospecção",
                    "aula acelerada": "operação claude code"},
    },
    "ad03v2": {
        # hook curto (2 linhas): no ad02v2 um hook de 3 linhas ficou congelado por 15s
        # tapando o payoff dos inserts de abertura.
        "hook": {"eyebrow": "era assim", "l1": "antes do Claude", "accent": ""},
        "cta_label": "saiba mais",
        "kw_phrases": ["em massa.", "um comercial na folha", "JSON.", "pagava alguém",
                        "uma skill", "dois dias práticos", "time de prospecção"],
        "letterings": [
            {"lead": "ou pagava alguém", "key": "OU NÃO FAZIA", "anchor": "pagava", "dur": 2.6},
            {"lead": "virou uma", "key": "SKILL", "anchor": "skill", "dur": 2.6},
        ],
        "labels": {"n8n fluxo gigante": "automação antiga: nó, webhook, json",
                    "claude prospectando skill": "prospecção por skill",
                    "tela do n8n complexa": "a barreira técnica",
                    "takes de prospecção": "prospecção rodando",
                    "aula acelerada": "operação claude code"},
    },
    "ad02v2": {
        # hook curto de proposito: o hook fica na tela ate o cap_gate, e no 1o corte
        # ele congelou 15.5s COBRINDO os tres inserts, ou seja, tapando exatamente o
        # payoff que o anuncio promete mostrar. Menos texto = menos area coberta.
        "hook": {"eyebrow": "o Claude", "l1": "por dentro", "accent": ""},
        # o roteiro pede KEY "SAIBA MAIS" no bloco final e a pill imita o botao do Meta:
        # apontar pra "garanta seu ingresso" enquanto o botao real diz "Saiba mais"
        # quebra a mecanica do dispositivo.
        "cta_label": "saiba mais",
        "kw_phrases": ["vídeos prontos", "sem pagar hospedagem", "folha de pagamento",
                        "uma skill", "todo santo dia", "2 dias práticos"],
        "letterings": [
            # LEAD+KEY juntos cobrindo o bloco inteiro (dur 4.2). Motivo: o motor
            # suprime toda legenda que coincide com a janela do lettering (eles ficam a
            # 25px um do outro no layout, entao empilhariam). Com o lettering curto,
            # sobrava tela muda em "é uma skill, um manual de instruções" e a palavra
            # SKILL, que e o mecanismo unico do produto, nunca aparecia escrita no
            # anuncio inteiro. Trazer ela pra KEY resolve o gap e o mecanismo de uma vez.
            {"lead": "aqui não é nenhum", "key": "É UMA SKILL", "anchor": "nenhum", "dur": 3.8},
            # dur 2.9 (nao 2.2): com 2.2 o lettering saia em 37.0s e a legenda seguinte
            # so entrava em 38.17s, deixando 1.17s de tela MUDA justo enquanto a voz diz
            # "garante o seu ingresso na Operação Claude Code", o nome do produto.
            {"lead": "toca no", "key": "BOTÃO ABAIXO", "anchor": "botão", "dur": 3.8},
        ],
        "labels": {"skill gerando vídeos prontos": "vídeo pronto e editado",
                    "skill gerando a página publicada": "página no ar, sem hospedagem",
                    "skill gerando dashboard de campanhas": "dashboard das campanhas",
                    "aula acelerada": "operação claude code"},
    },
    "ad01v2": {
        "hook": {"eyebrow": "você tem uma", "l1": "agência de", "accent": "marketing?"},
        "cta_label": "garanta seu ingresso",
        "kw_phrases": ["demitir metade", "sem precisar pagar por hospedagem",
                        "prospecta em massa", "fechar em 2027", "saiba mais",
                        "muito menos com pessoas"],
        "letterings": [
            # o total do custo entra exatamente quando ele pergunta "quanto isso
            # te custaria por mes?", respondendo a pergunta retorica na tela
            {"lead": "isso te custa", "key": "R$ 25 MIL", "anchor": "custaria", "dur": 2.4},
            {"lead": "ou a agência", "key": "FECHA EM 2027", "anchor": "2027", "dur": 2.2},
            # bloco 14 do leva.txt pede "avatar com lettering + logo" mas eu nao tinha
            # ancorado lettering nenhum ali: renderizou 3.7s de talking-head cru bem no
            # PRIMEIRO CTA do anuncio (achado na auditoria de 04/08).
            # dur 2.9 (nao 2.2): com 2.2 o lettering saia em 37.0s e a legenda seguinte
            # so entrava em 38.17s, deixando 1.17s de tela MUDA justo enquanto a voz diz
            # "garante o seu ingresso na Operação Claude Code", o nome do produto.
            {"lead": "toca no", "key": "BOTÃO ABAIXO", "anchor": "botão", "dur": 3.8},
        ],
        "labels": {"organograma geral dos times de i.a": "seu time de I.A",
                    "organograma destacando o editor de vídeo": "editor de vídeo",
                    "skill criadora de vídeos em ação": "skill de edição",
                    "organograma destacando o web designer": "web designer",
                    "skill criando e publicando a página": "página no ar sozinha",
                    "organograma destacando a prospecção": "prospecção",
                    "organograma destacando o desenvolvedor": "desenvolvedor",
                    "sistemas internos criados pipocando": "sistemas internos",
                    "motion de custo por cargo": "a conta da folha",
                    "aula acelerada montando time de i.a": "aula do thales",
                    "aula acelerada segundo take": "operação claude code"},
    },
    "ad11": {
        "hook": {"eyebrow": "isso aqui é o", "l1": "Claude construindo", "accent": "um dashboard sozinho"},
        "cta_label": "garanta seu ingresso",
        "kw_phrases": ["MENSALIDADE", "VAZANDO", "2 dias", "saiba mais",
                        "todo santo dia", "ouro"],
        "letterings": [
            {"lead": "sem mais uma", "key": "MENSALIDADE", "anchor": "MENSALIDADE", "dur": 2.2},
            {"lead": "o dinheiro tá", "key": "VAZANDO", "anchor": "VAZANDO", "dur": 2.2},
        ],
        "labels": {"skill de dashboard rodando": "construindo o dashboard",
                    "tela puxando dados de vendas": "puxando dados de vendas",
                    "gerenciador de anúncios": "custo dos anúncios",
                    "dashboard pronto": "dashboard pronto",
                    "pessoa perdida em planilhas": "decidindo no escuro",
                    "aula do thales acelerada": "aula do thales",
                    "segundo take da aula do thales acelerada": "operação claude code"},
    },
}

AVATARES = {
    ("ad02", "espuma_roxa"): V1 / "ad02_espuma_roxa_avatar.mp4",
    ("ad02", "selfie_neon"): V1 / "ad02_selfie_neon_avatar.mp4",
    ("ad03", "espuma_roxa"): V1 / "ad03_espuma_roxa_avatar.mp4",
    ("ad03", "selfie_neon"): V1 / "ad03_selfie_neon_avatar.mp4",
    ("ad04", "espuma_roxa"): V1 / "ad04_espuma_roxa_avatar.mp4",
    ("ad04", "selfie_neon"): V1 / "ad04_selfie_neon_avatar.mp4",
    ("ad05", "espuma_roxa"): V1 / "ad05_espuma_roxa_avatar.mp4",
    ("ad05", "selfie_neon"): V1 / "ad05_selfie_neon_avatar.mp4",
    ("ad06", "espuma_roxa"): V1 / "ad06_espuma_roxa_avatar.mp4",
    ("ad06", "selfie_neon"): V1 / "ad06_selfie_neon_avatar.mp4",
    ("ad07", "espuma_roxa"): V1 / "ad07_espuma_roxa_avatar.mp4",
    ("ad07", "selfie_neon"): V1 / "ad07_selfie_neon_avatar.mp4",
    ("ad08", "espuma_roxa"): V1 / "ad08_espuma_roxa_avatar.mp4",
    ("ad08", "selfie_neon"): V1 / "ad08_selfie_neon_avatar.mp4",
    ("ad09", "espuma_roxa"): V1 / "ad09_espuma_roxa_avatar.mp4",
    ("ad09", "selfie_neon"): V1 / "ad09_selfie_neon_avatar.mp4",
    ("ad10", "espuma_roxa"): V1 / "ad10_espuma_roxa_avatar.mp4",
    ("ad10", "selfie_neon"): V1 / "ad10_selfie_neon_avatar.mp4",
    ("ad11", "espuma_roxa"): V1 / "ad11_espuma_roxa_avatar.mp4",
    ("ad11", "selfie_neon"): V1 / "ad11_selfie_neon_avatar.mp4",
    ("ad01v2", "selfie_neon"): V1 / "ad01v2_selfie_neon_avatar.mp4",
    ("ad02v2", "estudio_verde"): V1 / "ad02v2_estudio_verde_avatar.mp4",
    ("ad03v2", "selfie_neon"): V1 / "ad03v2_selfie_neon_avatar.mp4",
    ("ad04v2", "estudio_verde"): V1 / "ad04v2_estudio_verde_avatar.mp4",
    ("ad05v2", "espuma_roxa"): V1 / "ad05v2_espuma_roxa_avatar.mp4",
    ("ad06v2", "estudio_verde"): V1 / "ad06v2_estudio_verde_avatar.mp4",
    ("ad07v2", "selfie_neon"): V1 / "ad07v2_selfie_neon_avatar.mp4",
    ("ad08v2", "estudio_verde"): V1 / "ad08v2_estudio_verde_avatar.mp4",
    ("ad09v2", "espuma_roxa"): V1 / "ad09v2_espuma_roxa_avatar.mp4",
    ("ad10v2", "estudio_verde"): V1 / "ad10v2_estudio_verde_avatar.mp4",
    ("ad11v2", "selfie_neon"): V1 / "ad11v2_selfie_neon_avatar.mp4",
    ("ad12v2", "espuma_roxa"): V1 / "ad12v2_espuma_roxa_avatar.mp4",
    ("ad01v2", "espuma_roxa"): V1 / "ad01v2_espuma_roxa_avatar.mp4",
    # Leva da Jheni: o jh13 nao estava aqui, entao rodar este arquivo NAO regerava o
    # config dele. Resultado (17/08/2026): editei o ADS["jh13v2"] com hook e os tres
    # letterings de ❌, o configs/jh13v2_espuma.json ficou VELHO, o build usou o velho
    # e o video saiu sem hook. Sem esta entrada a fonte de verdade nao chega no build.
    ("jh13v2", "espuma_roxa"): V1 / "jh13v2_espuma_roxa_avatar.mp4",
    ("jh14v2", "oficial_13"): V1 / "jh14v2_oficial_13_avatar.mp4",
    # neon_branca saiu: 27,1% de altura util (medido), o resto e barra branca.
    ("jh15v2", "neon_creme"): V1 / "jh15v2_neon_creme_avatar.mp4",
    # espuma_branca saiu: o conteudo dentro do arquivo ocupa 37,4% da altura
    # (medido), o resto e barra branca. Ver LOOKS_COM_TARJA no gerador.
    ("jh16v2", "espuma_roxa"): V1 / "jh16v2_espuma_roxa_avatar.mp4",
}

if __name__ == "__main__":
    outdir = V2L / "configs"
    outdir.mkdir(exist_ok=True)
    # SO 9x16. A Jhenifer definiu (04/08/2026) que a campanha produz apenas vertical,
    # entao gerar config 1x1 junto so criava arquivo morto. Pra voltar a produzir
    # quadrado, e so acrescentar ("1x1", "_1x1") na lista abaixo.
    FORMATOS = [("9x16", "")]
    for (ad, look), avatar in AVATARES.items():
        if not avatar.exists():
            print(f"AVISO: avatar faltando {avatar}")
            continue
        lk = LOOKS[look]
        for fmt, suffix in FORMATOS:
            cfg = dict(ADS[ad])
            cfg.update({"ad": ad, "look": look, "format": fmt, "avatar": str(avatar),
                        "out_dir": str(V2L / f"render-{ad}-{lk}{suffix}")})
            p = outdir / f"{ad}_{lk}{suffix}.json"
            p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))
            print("config:", p.name)
