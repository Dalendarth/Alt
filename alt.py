# -*- coding: utf-8 -*-
"""Alt — ferramenta de print anotado.

Quatro formas: seta, callout redondo com rotulo dentro, marcador retangular de
cantos arredondados, e etiqueta de texto com fundo preenchido. As cores sao as
mesmas do manual do Fieldly.

Atalho global: Ctrl + Shift esquerdo + Print Screen.

Uso:
    pythonw alt.py              fica na bandeja do sistema esperando o atalho
    pythonw alt.py --painel     tambem mostra o painelzinho, para depurar
    python  alt.py --capturar   abre a selecao de area agora, sem atalho
    python  alt.py --autoteste  verifica captura, area de transferencia,
                                registro do atalho, e salva uma amostra das
                                quatro formas para conferencia visual
"""

import ctypes
import io
import json
import math
import os
import queue
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, font as tkfont

from PIL import Image, ImageDraw, ImageFont, ImageGrab, ImageTk

# ---------------------------------------------------------------------------
# CONSCIENCIA DE DPI
# Tem de vir antes de qualquer janela: sem isso, num monitor escalado as
# coordenadas do mouse e as do print nao batem, e o recorte sai deslocado.
# ---------------------------------------------------------------------------


def preparar_dpi():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # por monitor
        return 'por monitor'
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        return 'do sistema'
    except Exception:
        return 'nenhuma'


DPI = preparar_dpi()

# ---------------------------------------------------------------------------
# PALETA — as mesmas cores do manual
# ---------------------------------------------------------------------------

MAGENTA = '#C93466'   # o vermelho suave, cor padrao
LARANJA = '#F8A113'
VERDE = '#7EBE1A'
NAVY = '#475279'
BRANCO = '#FFFFFF'

CORES = [MAGENTA, LARANJA, VERDE, NAVY]

# Cinzas da propria ferramenta.
FUNDO = '#1B2029'
FUNDO_BARRA = '#232A36'
BORDA = '#3A4351'
TEXTO = '#E7EBF3'
TEXTO_FRACO = '#98A1B2'

ESPESSURAS = [2, 3, 5]
RAIO_CALLOUT = 17
RAIO_CANTO = 10

# Do prototipo que gerou os prints do manual: contorno branco de 3 px e fonte
# a 1,25 do raio. Com 2 px o anel quase desaparecia no papel.
CONTORNO_CALLOUT = 3
FONTE_SOBRE_RAIO = 1.25
FOLGA_CALLOUT = 7

# Etiqueta de texto: folga interna generosa, para o texto nunca encostar na
# borda arredondada, e os tres tamanhos oferecidos na barra.
FOLGA_TEXTO_X = 14
FOLGA_TEXTO_Y = 9
RAIO_TEXTO = 8
TAMANHOS_TEXTO = [16, 22, 30]

def pasta_do_programa():
    """Onde estao os recursos que vieram junto com o programa.

    Dentro de um executavel do PyInstaller isso e a pasta temporaria de
    descompactacao, que e somente leitura.
    """
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def pasta_de_dados():
    """Onde o programa pode gravar: config e icone gerado.

    Compilado, escrever ao lado do executavel falha em Program Files e some a
    cada atualizacao; o lugar certo e o LOCALAPPDATA.
    """
    if getattr(sys, 'frozen', False):
        base = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'Alt')
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        base = os.path.expanduser('~')
    return base


CONFIG = os.path.join(pasta_de_dados(), 'alt-config.json')

# ---------------------------------------------------------------------------
# CAPTURA
# ---------------------------------------------------------------------------

SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79


def area_virtual():
    """Origem e tamanho do desktop virtual, somando todos os monitores."""
    m = ctypes.windll.user32.GetSystemMetrics
    return (m(SM_XVIRTUALSCREEN), m(SM_YVIRTUALSCREEN),
            m(SM_CXVIRTUALSCREEN), m(SM_CYVIRTUALSCREEN))


def capturar_tudo():
    """Print de todos os monitores, mais a origem do desktop virtual."""
    x, y, _, _ = area_virtual()
    try:
        imagem = ImageGrab.grab(all_screens=True)
    except TypeError:
        imagem = ImageGrab.grab()
        x, y = 0, 0
    return imagem.convert('RGB'), x, y


# ---------------------------------------------------------------------------
# AREA DE TRANSFERENCIA
# ---------------------------------------------------------------------------


def copiar_imagem(imagem):
    """Poe a imagem na area de transferencia como CF_DIB.

    O BMP do Pillow vem com 14 bytes de cabecalho de arquivo que o CF_DIB nao
    quer; o corte e proposital.
    """
    import win32clipboard

    saida = io.BytesIO()
    imagem.convert('RGB').save(saida, 'BMP')
    dados = saida.getvalue()[14:]

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, dados)
    finally:
        win32clipboard.CloseClipboard()


# ---------------------------------------------------------------------------
# GEOMETRIA
# ---------------------------------------------------------------------------


def pontos_arredondados(x1, y1, x2, y2, raio, passos=8):
    """Contorno de um retangulo de cantos arredondados, para o canvas.

    O tkinter nao tem retangulo arredondado; o caminho e gerar o poligono.
    """
    x1, x2 = min(x1, x2), max(x1, x2)
    y1, y2 = min(y1, y2), max(y1, y2)
    raio = max(0.0, min(raio, (x2 - x1) / 2, (y2 - y1) / 2))

    cantos = (
        (x2 - raio, y1 + raio, -90, 0),
        (x2 - raio, y2 - raio, 0, 90),
        (x1 + raio, y2 - raio, 90, 180),
        (x1 + raio, y1 + raio, 180, 270),
    )
    pontos = []
    for cx, cy, a0, a1 in cantos:
        for i in range(passos + 1):
            a = math.radians(a0 + (a1 - a0) * i / passos)
            pontos.extend((cx + raio * math.cos(a), cy + raio * math.sin(a)))
    return pontos


def cabeca_de_seta(x1, y1, x2, y2, espessura):
    """Triangulo da ponta da seta, em coordenadas de imagem."""
    comprimento = max(16.0, espessura * 5.2)
    largura = max(13.0, espessura * 4.2)

    dx, dy = x2 - x1, y2 - y1
    distancia = math.hypot(dx, dy) or 1.0
    ux, uy = dx / distancia, dy / distancia
    px, py = -uy, ux

    base_x, base_y = x2 - ux * comprimento, y2 - uy * comprimento
    return [
        (x2, y2),
        (base_x + px * largura / 2, base_y + py * largura / 2),
        (base_x - px * largura / 2, base_y - py * largura / 2),
    ]


def encurtar(x1, y1, x2, y2, quanto):
    """Recua a ponta da linha para ela nao aparecer por dentro da cabeca."""
    dx, dy = x2 - x1, y2 - y1
    distancia = math.hypot(dx, dy) or 1.0
    if distancia <= quanto:
        return x1, y1, x1, y1
    return x1, y1, x2 - dx / distancia * quanto, y2 - dy / distancia * quanto


# ---------------------------------------------------------------------------
# FONTE PARA O ROTULO DO CALLOUT
# ---------------------------------------------------------------------------


TINTA_ESCURA = '#1C2231'


def tinta_sobre(cor):
    """Cor legivel para o rotulo, escolhida pela luminosidade do fundo.

    Branco sobre o verde e o laranja da paleta tem contraste baixo demais para
    um numero pequeno.
    """
    r, g, b = (int(cor[i:i + 2], 16) / 255 for i in (1, 3, 5))
    luminancia = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return TINTA_ESCURA if luminancia > 0.55 else BRANCO


def fonte_negrito(tamanho):
    for nome in ('segoeuib.ttf', 'arialbd.ttf', 'calibrib.ttf', 'seguisb.ttf'):
        caminho = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts', nome)
        if os.path.exists(caminho):
            try:
                return ImageFont.truetype(caminho, tamanho)
            except Exception:
                continue
    return ImageFont.load_default()


def raio_do_callout(forma):
    """Raio efetivo do callout: nunca menor do que o rotulo precisa.

    O tamanho da fonte vem do raio **da alca**, nao do raio efetivo. Se viesse
    do efetivo, crescer o circulo cresceria a letra, que cresceria o circulo de
    novo — realimentacao sem fim.
    """
    base = float(forma.get('r', RAIO_CALLOUT))
    rotulo = str(forma.get('rotulo', '') or '')
    if not rotulo:
        return base

    fonte = fonte_negrito(max(8, int(base * FONTE_SOBRE_RAIO)))
    pincel = ImageDraw.Draw(Image.new('RGB', (4, 4)))
    try:
        caixa = pincel.textbbox((0, 0), rotulo, font=fonte)
        largura, altura = caixa[2] - caixa[0], caixa[3] - caixa[1]
    except Exception:
        largura, altura = len(rotulo) * base, base

    # Circulo que comporta a caixa do texto: metade da diagonal, mais folga.
    necessario = math.hypot(largura, altura) / 2 + FOLGA_CALLOUT
    return max(base, necessario)


def medir_texto_pil(texto, tamanho):
    """Tamanho da etiqueta pelas metricas do Pillow.

    O Pillow e a autoridade porque e ele que desenha o arquivo final. A altura
    da linha vem de getmetrics, e nao do bbox do texto: bbox varia com as
    letras da linha, e isso faria a caixa pular de tamanho conforme se digita.
    """
    fonte = fonte_negrito(tamanho)
    linhas = texto.split('\n') or ['']
    pincel = ImageDraw.Draw(Image.new('RGB', (4, 4)))

    try:
        subida, descida = fonte.getmetrics()
        altura_linha = subida + descida
    except Exception:
        altura_linha = int(tamanho * 1.3)

    larguras = []
    for linha in linhas:
        try:
            larguras.append(pincel.textlength(linha, font=fonte))
        except Exception:
            larguras.append(len(linha) * tamanho * 0.6)

    largura = max(larguras) + FOLGA_TEXTO_X * 2
    altura = altura_linha * len(linhas) + FOLGA_TEXTO_Y * 2
    # Piso: uma etiqueta vazia ainda tem de ser visivel e clicavel.
    return max(largura, tamanho * 2.2), max(altura, altura_linha + FOLGA_TEXTO_Y * 2), altura_linha


# ---------------------------------------------------------------------------
# DESENHO NA IMAGEM FINAL (Pillow) — e o que sai no arquivo, em resolucao cheia
# ---------------------------------------------------------------------------


SUPERAMOSTRAGEM = 4
TETO_DA_CAMADA = 120_000_000   # pixels da camada ampliada


def caixa_da_forma(forma):
    """Retangulo que envolve a forma, com folga para contorno e suavizacao."""
    tipo = forma['tipo']
    esp = forma.get('esp', 3)

    if tipo == 'seta':
        cabeca = cabeca_de_seta(forma['x1'], forma['y1'], forma['x2'], forma['y2'], esp)
        xs = [forma['x1'], forma['x2']] + [c[0] for c in cabeca]
        ys = [forma['y1'], forma['y2']] + [c[1] for c in cabeca]
        folga = esp * 2 + 6

    elif tipo == 'marcador':
        xs = [forma['x1'], forma['x2']]
        ys = [forma['y1'], forma['y2']]
        folga = esp + 6

    elif tipo == 'callout':
        r = raio_do_callout(forma)
        xs = [forma['x'] - r, forma['x'] + r]
        ys = [forma['y'] - r, forma['y'] + r]
        folga = CONTORNO_CALLOUT + 5

    elif tipo == 'texto':
        largura, altura, _ = medir_texto_pil(forma.get('texto', ''), forma.get('tamanho', 22))
        largura = max(largura, forma.get('largura', 0))
        altura = max(altura, forma.get('altura', 0))
        xs = [forma['x'], forma['x'] + largura]
        ys = [forma['y'], forma['y'] + altura]
        folga = 4

    else:
        return None

    return (int(math.floor(min(xs) - folga)), int(math.floor(min(ys) - folga)),
            int(math.ceil(max(xs) + folga)), int(math.ceil(max(ys) + folga)))


def pintar_forma(pincel, forma, levar, escala):
    """Desenha uma forma em coordenadas de camada.

    `levar` converte coordenada de imagem em coordenada de camada; `escala` e o
    fator de ampliacao, para espessura e raio acompanharem.
    """
    cor = forma['cor']
    tipo = forma['tipo']

    if tipo == 'marcador':
        x1, y1 = levar(min(forma['x1'], forma['x2']), min(forma['y1'], forma['y2']))
        x2, y2 = levar(max(forma['x1'], forma['x2']), max(forma['y1'], forma['y2']))
        pincel.rounded_rectangle(
            (x1, y1, x2, y2),
            radius=forma.get('raio', RAIO_CANTO) * escala,
            outline=cor, width=max(1, int(round(forma.get('esp', 3) * escala))))

    elif tipo == 'seta':
        esp = forma.get('esp', 3)
        cabeca = cabeca_de_seta(forma['x1'], forma['y1'], forma['x2'], forma['y2'], esp)
        recuo = max(16.0, esp * 5.2) * 0.78
        ax1, ay1, ax2, ay2 = encurtar(forma['x1'], forma['y1'], forma['x2'], forma['y2'], recuo)
        largura_da_linha = max(1, int(round(esp * escala)))
        pincel.line((*levar(ax1, ay1), *levar(ax2, ay2)), fill=cor, width=largura_da_linha)
        # Ponta arredondada no rabo, como o capstyle do editor.
        raio = largura_da_linha / 2
        tx, ty = levar(ax1, ay1)
        pincel.ellipse((tx - raio, ty - raio, tx + raio, ty + raio), fill=cor)
        pincel.polygon([levar(cx, cy) for cx, cy in cabeca], fill=cor)

    elif tipo == 'callout':
        r = raio_do_callout(forma) * escala
        cx, cy = levar(forma['x'], forma['y'])
        tinta = tinta_sobre(cor)
        # O anel e sempre branco, como no prototipo: e ele que solta o callout
        # de qualquer fundo. Com tinta escura o anel continua branco.
        pincel.ellipse((cx - r, cy - r, cx + r, cy + r), fill=cor,
                       outline=BRANCO,
                       width=max(1, int(round(CONTORNO_CALLOUT * escala))))
        rotulo = str(forma.get('rotulo', '') or '')
        if rotulo:
            base = float(forma.get('r', RAIO_CALLOUT))
            fonte = fonte_negrito(max(8, int(base * FONTE_SOBRE_RAIO * escala)))
            caixa = pincel.textbbox((0, 0), rotulo, font=fonte)
            pincel.text((cx - (caixa[2] - caixa[0]) / 2 - caixa[0],
                         cy - (caixa[3] - caixa[1]) / 2 - caixa[1]),
                        rotulo, font=fonte, fill=tinta)

    elif tipo == 'texto':
        tamanho = forma.get('tamanho', 22)
        largura, altura, altura_linha = medir_texto_pil(forma.get('texto', ''), tamanho)
        largura = max(largura, forma.get('largura', 0))
        altura = max(altura, forma.get('altura', 0))
        x1, y1 = levar(forma['x'], forma['y'])
        x2, y2 = levar(forma['x'] + largura, forma['y'] + altura)
        pincel.rounded_rectangle((x1, y1, x2, y2),
                                 radius=forma.get('raio', RAIO_TEXTO) * escala,
                                 fill=cor)
        tinta = tinta_sobre(cor)
        fonte = fonte_negrito(max(6, int(tamanho * escala)))
        for numero, linha in enumerate((forma.get('texto', '') or '').split('\n')):
            if not linha:
                continue
            px, py = levar(forma['x'] + FOLGA_TEXTO_X,
                           forma['y'] + FOLGA_TEXTO_Y + numero * altura_linha)
            pincel.text((px, py), linha, font=fonte, fill=tinta, anchor='la')


CAMPOS_DE_ESCALA = ('x', 'y', 'x1', 'y1', 'x2', 'y2', 'r', 'esp', 'raio',
                    'tamanho', 'largura', 'altura', 'entrelinha')


def escalar_forma(forma, fator):
    """Copia da forma com toda medida multiplicada.

    Serve para desenhar a previa reduzida com o mesmo codigo do arquivo: em vez
    de um caminho de desenho separado para a tela, a forma e reescalada e passa
    pelo mesmo pincel.
    """
    if fator == 1.0:
        return forma
    copia = dict(forma)
    for campo in CAMPOS_DE_ESCALA:
        if campo in copia and isinstance(copia[campo], (int, float)):
            copia[campo] = copia[campo] * fator
    return copia


def renderizar_anotacoes(tamanho, formas, fator=1.0):
    """Camada transparente com as formas, para sobrepor a previa."""
    camada = Image.new('RGBA', tamanho, (0, 0, 0, 0))
    pincel = ImageDraw.Draw(camada)
    for forma in formas:
        escalada = escalar_forma(forma, fator)
        if desenhar_forma_suave(camada, escalada):
            continue
        pintar_forma(pincel, escalada, lambda px, py: (px, py), 1)
    return camada


def desenhar_forma_suave(imagem, forma):
    """Desenha a forma numa camada ampliada e reduz, para suavizar a borda.

    O ImageDraw nao faz antisserrilhamento: circulo e diagonal saem em escada, e
    o anel branco de 3 px do callout praticamente desaparece. A camada e do
    tamanho da forma, nao da imagem, para nao estourar memoria.
    """
    caixa = caixa_da_forma(forma)
    if not caixa:
        return False
    x0, y0, x1, y1 = caixa

    largura, altura = x1 - x0, y1 - y0
    if largura < 2 or altura < 2:
        return False
    if largura * altura * SUPERAMOSTRAGEM ** 2 > TETO_DA_CAMADA:
        return False

    escala = SUPERAMOSTRAGEM
    camada = Image.new('RGBA', (largura * escala, altura * escala), (0, 0, 0, 0))
    pincel = ImageDraw.Draw(camada)

    def levar(px, py):
        return ((px - x0) * escala, (py - y0) * escala)

    pintar_forma(pincel, forma, levar, escala)

    reduzida = camada.resize((largura, altura), Image.LANCZOS)
    if imagem.mode == 'RGBA':
        # Numa camada transparente a colagem com mascara zeraria o alfa em volta
        # e recortaria a forma anterior; a composicao respeita as duas.
        imagem.alpha_composite(reduzida, dest=(max(0, x0), max(0, y0)))
    else:
        imagem.paste(reduzida, (x0, y0), reduzida)
    return True


def desenhar_em_imagem(imagem, formas):
    """Aplica as formas sobre uma copia da imagem e devolve o resultado.

    Toda forma passa pela camada ampliada. A reserva sem suavizacao existe para
    o caso de a caixa ser degenerada ou grande demais.
    """
    saida = imagem.convert('RGB').copy()
    pincel = ImageDraw.Draw(saida)

    for forma in formas:
        if desenhar_forma_suave(saida, forma):
            continue
        # Reserva: desenha direto, sem suavizar.
        pintar_forma(pincel, forma, lambda px, py: (px, py), 1)

    return saida


# ---------------------------------------------------------------------------
# SELECAO DE AREA
# ---------------------------------------------------------------------------


def monitor_do_cursor():
    """Retangulo do monitor onde o cursor esta, em coordenadas de tela.

    A dica era centrada no meio do desktop virtual. Com dois monitores isso cai
    na juncao, e o texto sai partido entre as duas telas.
    """
    class PONTO(ctypes.Structure):
        _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]

    class RETANGULO(ctypes.Structure):
        _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long),
                    ('right', ctypes.c_long), ('bottom', ctypes.c_long)]

    class INFO(ctypes.Structure):
        _fields_ = [('cbSize', ctypes.c_ulong), ('rcMonitor', RETANGULO),
                    ('rcWork', RETANGULO), ('dwFlags', ctypes.c_ulong)]

    usuario = ctypes.windll.user32
    ponto = PONTO()
    usuario.GetCursorPos(ctypes.byref(ponto))

    usuario.MonitorFromPoint.restype = ctypes.c_void_p
    monitor = usuario.MonitorFromPoint(ponto, 2)  # MONITOR_DEFAULTTONEAREST

    info = INFO()
    info.cbSize = ctypes.sizeof(INFO)
    if not usuario.GetMonitorInfoW(ctypes.c_void_p(monitor), ctypes.byref(info)):
        return None
    r = info.rcMonitor
    return (r.left, r.top, r.right, r.bottom)


class SelecaoDeArea:
    """Tela cheia com o print congelado; arrastar escolhe o recorte.

    O escurecimento e feito pelo Pillow, e nao por retangulo com stipple no
    canvas: o stipple e um xadrez de meio pixel, que na tela aparece como risco
    microscopico e faz tudo parecer embacado.

    A area escolhida mostra o print em brilho cheio, recortado do original.
    """

    ESCURECIMENTO = 0.58
    INTERVALO_DE_REDESENHO = 0.025   # segundos, para o arrasto nao afogar

    def __init__(self, mestre, imagem, origem_x, origem_y, ao_confirmar):
        self.imagem = imagem
        self.ox, self.oy = origem_x, origem_y
        self.ao_confirmar = ao_confirmar
        self.inicio = None
        self.item_claro = None
        self.retangulo = None
        self.rotulo = None
        self.ultimo_desenho = 0.0

        largura, altura = imagem.size

        self.janela = tk.Toplevel(mestre)
        self.janela.overrideredirect(True)
        self.janela.geometry(f'{largura}x{altura}+{origem_x}+{origem_y}')
        self.janela.attributes('-topmost', True)
        self.janela.configure(bg='black')
        aplicar_icone(self.janela)

        self.canvas = tk.Canvas(self.janela, width=largura, height=altura,
                                highlightthickness=0, bd=0, bg='black')
        self.canvas.pack(fill='both', expand=True)

        # Fundo escurecido de uma vez, sem trama.
        escura = Image.blend(imagem, Image.new('RGB', imagem.size, (8, 10, 14)),
                             self.ESCURECIMENTO)
        self.foto_escura = ImageTk.PhotoImage(escura)
        self.canvas.create_image(0, 0, image=self.foto_escura, anchor='nw')

        # Guias que acompanham o cursor: o cursor de cruz do Windows e preto e
        # desaparece sobre o fundo escuro.
        self.guia_x = self.canvas.create_line(0, 0, 0, altura, fill=MAGENTA,
                                              width=1, dash=(4, 4))
        self.guia_y = self.canvas.create_line(0, 0, largura, 0, fill=MAGENTA,
                                              width=1, dash=(4, 4))

        self.montar_dica(largura, altura)

        self.canvas.bind('<ButtonPress-1>', self.pressionou)
        self.canvas.bind('<B1-Motion>', self.arrastou)
        self.canvas.bind('<ButtonRelease-1>', self.soltou)
        self.canvas.bind('<Motion>', self.moveu)
        self.janela.bind('<Escape>', lambda _e: self.cancelar())
        self.janela.bind('<Button-3>', lambda _e: self.cancelar())
        self.janela.bind('<Return>', lambda _e: self.tela_inteira())
        self.janela.focus_force()
        self.canvas.configure(cursor='crosshair')

    # -- dica --------------------------------------------------------------

    def montar_dica(self, largura, altura):
        """Caixa de instrucao centrada no monitor onde o cursor esta."""
        area = monitor_do_cursor()
        if area:
            centro_x = (area[0] + area[2]) / 2 - self.ox
            topo = area[1] - self.oy + 30
        else:
            centro_x, topo = largura / 2, 30

        # Da mais curta se a tela for estreita: deslocar nao resolve texto mais
        # largo do que a propria tela.
        VERSOES = (
            'Arraste para escolher a área      Enter tela inteira      Esc cancela',
            'Arraste  ·  Enter tela inteira  ·  Esc cancela',
            'Arraste  ·  Esc cancela',
        )
        self.dica_texto = self.canvas.create_text(
            centro_x, topo + 20, text=VERSOES[0], fill=BRANCO,
            font=('Segoe UI', 12, 'bold'), anchor='center')

        # A folga considera os 18 px que o fundo acrescenta de cada lado, senao
        # a moldura estoura a borda mesmo com o texto dentro.
        FOLGA = 36
        for versao in VERSOES:
            self.canvas.itemconfigure(self.dica_texto, text=versao)
            caixa = self.canvas.bbox(self.dica_texto)
            if not caixa or (caixa[2] - caixa[0]) + FOLGA * 2 <= largura:
                break
        caixa = self.canvas.bbox(self.dica_texto)
        if caixa:
            deslocar_x = deslocar_y = 0
            if caixa[0] < FOLGA:
                deslocar_x = FOLGA - caixa[0]
            elif caixa[2] > largura - FOLGA:
                deslocar_x = (largura - FOLGA) - caixa[2]
            if caixa[1] < FOLGA:
                deslocar_y = FOLGA - caixa[1]
            elif caixa[3] > altura - FOLGA:
                deslocar_y = (altura - FOLGA) - caixa[3]
            if deslocar_x or deslocar_y:
                self.canvas.move(self.dica_texto, deslocar_x, deslocar_y)

        # Fundo da dica, do tamanho do texto, desenhado atras dele.
        caixa = self.canvas.bbox(self.dica_texto)
        if caixa:
            self.dica_fundo = self.canvas.create_rectangle(
                caixa[0] - 18, caixa[1] - 11, caixa[2] + 18, caixa[3] + 11,
                fill='#11151C', outline=MAGENTA, width=1)
            self.canvas.tag_raise(self.dica_texto)

    def sumir_dica(self):
        for item in ('dica_texto', 'dica_fundo'):
            alvo = getattr(self, item, None)
            if alvo is not None:
                self.canvas.delete(alvo)
                setattr(self, item, None)

    # -- interacao ---------------------------------------------------------

    def moveu(self, evento):
        self.canvas.coords(self.guia_x, evento.x, 0, evento.x, self.imagem.size[1])
        self.canvas.coords(self.guia_y, 0, evento.y, self.imagem.size[0], evento.y)

    def pressionou(self, evento):
        self.inicio = (evento.x, evento.y)
        self.sumir_dica()

    def arrastou(self, evento):
        if not self.inicio:
            return
        self.moveu(evento)

        agora = time.time()
        if agora - self.ultimo_desenho < self.INTERVALO_DE_REDESENHO:
            return
        self.ultimo_desenho = agora
        self.mostrar(self.inicio[0], self.inicio[1], evento.x, evento.y)

    def mostrar(self, x1, y1, x2, y2):
        """Mostra a area escolhida em brilho cheio, com moldura e medida."""
        ex, dx = int(min(x1, x2)), int(max(x1, x2))
        cy, by = int(min(y1, y2)), int(max(y1, y2))

        if self.item_claro is not None:
            self.canvas.delete(self.item_claro)
            self.item_claro = None

        if dx - ex >= 1 and by - cy >= 1:
            recorte = self.imagem.crop((ex, cy, dx, by))
            self.foto_clara = ImageTk.PhotoImage(recorte)  # nao deixar coletar
            self.item_claro = self.canvas.create_image(ex, cy, image=self.foto_clara,
                                                       anchor='nw')

        if self.retangulo:
            self.canvas.coords(self.retangulo, ex, cy, dx, by)
        else:
            self.retangulo = self.canvas.create_rectangle(ex, cy, dx, by,
                                                          outline=MAGENTA, width=2)

        texto = f'{dx - ex} × {by - cy}'
        tx, ty = dx, cy - 16
        ancora = 'se'
        if ty < 14:
            ty, ancora = by + 16, 'ne'
        if self.rotulo:
            self.canvas.coords(self.rotulo, tx, ty)
            self.canvas.itemconfigure(self.rotulo, text=texto, anchor=ancora)
        else:
            self.rotulo = self.canvas.create_text(
                tx, ty, text=texto, fill=BRANCO, anchor=ancora,
                font=('Consolas', 12, 'bold'))

        self.canvas.tag_raise(self.retangulo)
        self.canvas.tag_raise(self.rotulo)
        self.canvas.tag_raise(self.guia_x)
        self.canvas.tag_raise(self.guia_y)

    def soltou(self, evento):
        if not self.inicio:
            return
        x1, y1 = self.inicio
        x2, y2 = evento.x, evento.y
        if abs(x2 - x1) < 8 or abs(y2 - y1) < 8:
            return  # clique solto: nao e recorte, deixa continuar
        recorte = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        self.fechar()
        self.ao_confirmar(self.imagem.crop(recorte))

    def tela_inteira(self):
        self.fechar()
        self.ao_confirmar(self.imagem.copy())

    def cancelar(self):
        self.fechar()

    def fechar(self):
        try:
            self.janela.destroy()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# EDITOR
# ---------------------------------------------------------------------------


class Editor:
    """Janela de anotacao. As formas vivem em coordenadas de imagem.

    O canvas pode estar reduzido para caber na tela, mas o arquivo final sai
    em resolucao cheia: por isso as formas nao guardam coordenada de tela.
    """

    FERRAMENTAS = (
        ('seta', 'Seta', 'A'),
        ('callout', 'Callout', 'C'),
        ('marcador', 'Marcador', 'R'),
        ('texto', 'Texto', 'T'),
        ('selecionar', 'Selecionar', 'V'),
    )

    def __init__(self, mestre, imagem):
        self.mestre = mestre
        self.imagem = imagem
        self.formas = []
        self.desfeitas = []
        self.selecionada = None
        self.arrastando = None
        self.previa = None

        self.ferramenta = tk.StringVar(value='callout')
        self.cor = tk.StringVar(value=MAGENTA)
        self.espessura = tk.IntVar(value=3)
        self.modo_rotulo = tk.StringVar(value='123')
        self.tamanho_texto = tk.IntVar(value=22)
        self.proximo = 1
        self.editando = None      # indice da etiqueta em digitacao
        self.cursor_visivel = True

        self.janela = tk.Toplevel(mestre)
        self.janela.title('Alt')
        self.janela.configure(bg=FUNDO)
        self.janela.attributes('-topmost', True)
        aplicar_icone(self.janela)

        self.escala = self.calcular_escala()
        self.montar_barra()
        self.montar_canvas()
        self.montar_rodape()
        self.ligar_teclas()

        self.janela.protocol('WM_DELETE_WINDOW', self.fechar)
        self.janela.update_idletasks()
        self.centralizar()
        self.janela.focus_force()
        self.redesenhar()

    # -- montagem ----------------------------------------------------------

    def calcular_escala(self):
        largura, altura = self.imagem.size
        tela_l = self.janela.winfo_screenwidth() - 80
        tela_a = self.janela.winfo_screenheight() - 220
        return min(1.0, tela_l / largura, tela_a / altura)

    def montar_barra(self):
        barra = tk.Frame(self.janela, bg=FUNDO_BARRA, pady=8, padx=10)
        barra.pack(fill='x')

        for chave, rotulo, tecla in self.FERRAMENTAS:
            tk.Radiobutton(
                barra, text=f'{rotulo}  ({tecla})', value=chave, variable=self.ferramenta,
                indicatoron=False, width=11, bg=FUNDO_BARRA, fg=TEXTO,
                selectcolor=MAGENTA, activebackground=BORDA, activeforeground=BRANCO,
                bd=0, highlightthickness=0, padx=6, pady=5,
                font=('Segoe UI', 9, 'bold'), cursor='hand2',
                command=self.trocou_ferramenta,
            ).pack(side='left', padx=(0, 4))

        tk.Frame(barra, bg=BORDA, width=1, height=26).pack(side='left', padx=10, fill='y')

        for cor in CORES:
            tk.Radiobutton(
                barra, value=cor, variable=self.cor, indicatoron=False,
                bg=cor, activebackground=cor, selectcolor=cor,
                width=3, bd=2, highlightthickness=2,
                highlightbackground=FUNDO_BARRA, highlightcolor=BRANCO,
                cursor='hand2', command=self.aplicar_na_selecionada,
            ).pack(side='left', padx=2)

        tk.Frame(barra, bg=BORDA, width=1, height=26).pack(side='left', padx=10, fill='y')

        for esp in ESPESSURAS:
            tk.Radiobutton(
                barra, text=f'{esp}px', value=esp, variable=self.espessura,
                indicatoron=False, width=5, bg=FUNDO_BARRA, fg=TEXTO,
                selectcolor=NAVY, activebackground=BORDA, bd=0, highlightthickness=0,
                pady=5, font=('Consolas', 9), cursor='hand2',
                command=self.aplicar_na_selecionada,
            ).pack(side='left', padx=2)

        tk.Frame(barra, bg=BORDA, width=1, height=26).pack(side='left', padx=10, fill='y')

        for valor, rotulo in (('123', '1 2 3'), ('ABC', 'A B C')):
            tk.Radiobutton(
                barra, text=rotulo, value=valor, variable=self.modo_rotulo,
                indicatoron=False, width=7, bg=FUNDO_BARRA, fg=TEXTO,
                selectcolor=NAVY, activebackground=BORDA, bd=0, highlightthickness=0,
                pady=5, font=('Consolas', 9, 'bold'), cursor='hand2',
                command=self.reiniciar_contador,
            ).pack(side='left', padx=2)

        tk.Frame(barra, bg=BORDA, width=1, height=26).pack(side='left', padx=10, fill='y')

        for tamanho in TAMANHOS_TEXTO:
            tk.Radiobutton(
                barra, text=f'T{tamanho}', value=tamanho, variable=self.tamanho_texto,
                indicatoron=False, width=5, bg=FUNDO_BARRA, fg=TEXTO,
                selectcolor=NAVY, activebackground=BORDA, bd=0, highlightthickness=0,
                pady=5, font=('Consolas', 9), cursor='hand2',
                command=self.aplicar_na_selecionada,
            ).pack(side='left', padx=2)

        direita = tk.Frame(barra, bg=FUNDO_BARRA)
        direita.pack(side='right')
        acoes = (
            ('Copiar  Ctrl+C', self.copiar, MAGENTA),
            ('Salvar  Ctrl+S', self.salvar, NAVY),
            ('Desfazer  Ctrl+Z', self.desfazer, FUNDO_BARRA),
            ('Limpar', self.limpar, FUNDO_BARRA),
        )
        for rotulo, acao, fundo in reversed(acoes):
            tk.Button(
                direita, text=rotulo, command=acao,
                bg=fundo, fg=BRANCO if fundo != FUNDO_BARRA else TEXTO,
                activebackground=BORDA, activeforeground=BRANCO,
                bd=0, highlightthickness=0, padx=12, pady=6,
                font=('Segoe UI', 9, 'bold'), cursor='hand2',
            ).pack(side='right', padx=3)

    def montar_canvas(self):
        largura, altura = self.imagem.size
        self.largura_tela = max(1, int(largura * self.escala))
        self.altura_tela = max(1, int(altura * self.escala))

        exibida = self.imagem if self.escala == 1.0 else self.imagem.resize(
            (self.largura_tela, self.altura_tela), Image.LANCZOS)
        self.foto = ImageTk.PhotoImage(exibida)

        moldura = tk.Frame(self.janela, bg=FUNDO, padx=12, pady=12)
        moldura.pack()
        self.canvas = tk.Canvas(moldura, width=self.largura_tela, height=self.altura_tela,
                                highlightthickness=1, highlightbackground=BORDA,
                                bd=0, bg=FUNDO, cursor='crosshair')
        self.canvas.pack()
        self.canvas.create_image(0, 0, image=self.foto, anchor='nw', tags='fundo')

        self.canvas.bind('<ButtonPress-1>', self.pressionou)
        self.canvas.bind('<B1-Motion>', self.arrastou)
        self.canvas.bind('<ButtonRelease-1>', self.soltou)
        self.canvas.bind('<Motion>', self.moveu)

    def montar_rodape(self):
        self.rodape = tk.Label(
            self.janela, bg=FUNDO, fg=TEXTO_FRACO, anchor='w', padx=14, pady=6,
            font=('Segoe UI', 9),
        )
        self.rodape.pack(fill='x')
        self.dizer()

    def ligar_teclas(self):
        j = self.janela
        j.bind('<Control-c>', lambda _e: self.copiar())
        j.bind('<Control-C>', lambda _e: self.copiar())
        j.bind('<Control-s>', lambda _e: self.salvar())
        j.bind('<Control-S>', lambda _e: self.salvar())
        j.bind('<Control-z>', lambda _e: self.desfazer())
        j.bind('<Control-Z>', lambda _e: self.desfazer())
        j.bind('<Delete>', lambda _e: self.apagar_selecionada())
        j.bind('<BackSpace>', lambda _e: None if self.editando is not None
               else self.apagar_selecionada())
        j.bind('<Escape>', lambda _e: self.encerrar_edicao() if self.editando is not None
               else self.fechar())
        for chave, _rotulo, tecla in self.FERRAMENTAS:
            for variante in (tecla.lower(), tecla.upper()):
                j.bind(f'<KeyPress-{variante}>', lambda _e, c=chave: self.escolher(c))
        j.bind('<Key>', self.digitou)

    def centralizar(self):
        l, a = self.janela.winfo_width(), self.janela.winfo_height()
        x = (self.janela.winfo_screenwidth() - l) // 2
        y = max(0, (self.janela.winfo_screenheight() - a) // 2 - 20)
        self.janela.geometry(f'+{x}+{y}')

    # -- estado ------------------------------------------------------------

    def dizer(self, mensagem=None):
        if mensagem is None:
            mensagem = (f'{len(self.formas)} forma(s)   ·   '
                        f'próximo rótulo: {self.rotulo_atual()}   ·   '
                        f'A seta · C callout · R marcador · T texto · V selecionar   ·   '
                        f'Ctrl+C copia · Ctrl+S salva · Ctrl+Z desfaz · Del apaga')
            if self.escala < 1.0:
                mensagem += f'   ·   exibindo a {self.escala * 100:.0f}%, salva em tamanho real'
        self.rodape.configure(text=mensagem)

    def escolher(self, chave):
        # Durante a digitacao as letras sao texto, nao atalho de ferramenta.
        if self.editando is not None:
            return
        self.ferramenta.set(chave)
        self.trocou_ferramenta()

    def trocou_ferramenta(self):
        self.encerrar_edicao()
        if self.ferramenta.get() != 'selecionar':
            self.selecionada = None
        ferramenta = self.ferramenta.get()
        self.canvas.configure(
            cursor='arrow' if ferramenta == 'selecionar'
            else 'xterm' if ferramenta == 'texto' else 'crosshair')
        self.redesenhar()

    def rotulo_atual(self):
        if self.modo_rotulo.get() == 'ABC':
            indice = self.proximo - 1
            letras = ''
            while True:
                letras = chr(ord('A') + indice % 26) + letras
                indice = indice // 26 - 1
                if indice < 0:
                    break
            return letras
        return str(self.proximo)

    def reiniciar_contador(self):
        self.proximo = 1
        self.dizer()

    def medir(self, forma):
        """Recalcula a caixa da etiqueta e guarda na propria forma.

        Toma o maior entre a metrica do Pillow e a do tkinter: o Pillow desenha
        o arquivo e o tkinter desenha o editor, e a caixa tem de comportar o
        texto nos dois, senao corta em um deles.
        """
        tamanho = forma.get('tamanho', 22)
        texto = forma.get('texto', '') or ''
        largura, altura, altura_linha = medir_texto_pil(texto, tamanho)

        try:
            fonte = tkfont.Font(family='Segoe UI', size=tamanho, weight='bold')
            linhas = texto.split('\n') or ['']
            largura_tk = max(fonte.measure(linha) for linha in linhas) + FOLGA_TEXTO_X * 2
            altura_tk = fonte.metrics('linespace') * len(linhas) + FOLGA_TEXTO_Y * 2
            largura = max(largura, largura_tk)
            altura = max(altura, altura_tk)
            altura_linha = max(altura_linha, fonte.metrics('linespace'))
        except Exception:
            pass

        forma['largura'] = largura
        forma['altura'] = altura
        forma['entrelinha'] = altura_linha
        return forma

    # -- conversao de coordenadas -----------------------------------------

    def para_imagem(self, x, y):
        return x / self.escala, y / self.escala

    def para_tela(self, x, y):
        return x * self.escala, y * self.escala

    # -- interacao ---------------------------------------------------------

    def pressionou(self, evento):
        x, y = self.para_imagem(evento.x, evento.y)
        ferramenta = self.ferramenta.get()

        if ferramenta == 'selecionar':
            alvo = self.forma_em(x, y)
            if self.editando is not None and alvo != self.editando:
                self.encerrar_edicao()
            self.selecionada = alvo
            if self.selecionada is not None:
                alca = self.alca_em(self.selecionada, x, y)
                self.arrastando = {'modo': 'alca' if alca else 'mover', 'alca': alca,
                                   'x': x, 'y': y}
            self.redesenhar()
            return

        if ferramenta == 'texto':
            self.encerrar_edicao()
            self.registrar()
            forma = self.medir({
                'tipo': 'texto', 'x': x, 'y': y, 'texto': '',
                'tamanho': self.tamanho_texto.get(), 'raio': RAIO_TEXTO,
                'cor': self.cor.get(),
            })
            self.formas.append(forma)
            self.selecionada = len(self.formas) - 1
            self.editando = self.selecionada
            self.piscar()
            self.redesenhar()
            self.dizer('digite o texto — Enter quebra linha, Esc termina')
            return

        if ferramenta == 'callout':
            self.encerrar_edicao()
            self.registrar()
            self.formas.append({
                'tipo': 'callout', 'x': x, 'y': y, 'r': RAIO_CALLOUT,
                'rotulo': self.rotulo_atual(), 'cor': self.cor.get(),
            })
            self.proximo += 1
            self.selecionada = len(self.formas) - 1
            self.redesenhar()
            self.dizer()
            return

        self.encerrar_edicao()
        self.arrastando = {'modo': 'novo', 'x': x, 'y': y}

    def arrastou(self, evento):
        if not self.arrastando:
            return
        x, y = self.para_imagem(evento.x, evento.y)
        modo = self.arrastando['modo']

        if modo == 'novo':
            self.previa = self.forma_nova(self.arrastando['x'], self.arrastando['y'], x, y)
            self.redesenhar()
            return

        forma = self.formas[self.selecionada]
        dx = x - self.arrastando['x']
        dy = y - self.arrastando['y']
        self.arrastando['x'], self.arrastando['y'] = x, y

        if modo == 'mover':
            if forma['tipo'] in ('callout', 'texto'):
                forma['x'] += dx
                forma['y'] += dy
            else:
                forma['x1'] += dx
                forma['y1'] += dy
                forma['x2'] += dx
                forma['y2'] += dy
        else:
            alca = self.arrastando['alca']
            if forma['tipo'] == 'texto':
                # A alca muda o tamanho da fonte; a caixa acompanha sozinha.
                alcance = max(x - forma['x'], (y - forma['y']) * 2.4)
                forma['tamanho'] = int(max(10, min(96, alcance / 2.2)))
                self.medir(forma)
            elif forma['tipo'] == 'callout':
                forma['r'] = max(8.0, math.hypot(x - forma['x'], y - forma['y']))
            elif forma['tipo'] == 'seta':
                if alca == 0:
                    forma['x1'], forma['y1'] = x, y
                else:
                    forma['x2'], forma['y2'] = x, y
            else:
                if alca in (0, 3):
                    forma['x1'] = x
                else:
                    forma['x2'] = x
                if alca in (0, 1):
                    forma['y1'] = y
                else:
                    forma['y2'] = y
        self.redesenhar()

    def soltou(self, _evento):
        if self.arrastando and self.arrastando['modo'] == 'novo' and self.previa:
            forma = self.previa
            if forma['tipo'] == 'seta':
                grande = math.hypot(forma['x2'] - forma['x1'], forma['y2'] - forma['y1']) > 12
            else:
                grande = abs(forma['x2'] - forma['x1']) > 10 and abs(forma['y2'] - forma['y1']) > 10
            if grande:
                self.registrar()
                self.formas.append(forma)
                self.selecionada = len(self.formas) - 1
        self.arrastando = None
        self.previa = None
        self.redesenhar()
        self.dizer()

    def moveu(self, evento):
        if self.ferramenta.get() != 'selecionar' or self.arrastando:
            return
        x, y = self.para_imagem(evento.x, evento.y)
        indice = self.forma_em(x, y)
        if indice is not None and self.alca_em(indice, x, y) is not None:
            self.canvas.configure(cursor='sizing')
        else:
            self.canvas.configure(cursor='hand2' if indice is not None else 'arrow')

    def digitou(self, evento):
        """Roteia a tecla: etiqueta em digitacao, ou rotulo do callout."""
        if evento.state & 0x0004:   # com Ctrl, e atalho, nao texto
            return

        if self.editando is not None:
            forma = self.formas[self.editando]
            if evento.keysym == 'BackSpace':
                forma['texto'] = forma['texto'][:-1]
            elif evento.keysym in ('Return', 'KP_Enter'):
                forma['texto'] += '\n'
            elif evento.char and (evento.char.isprintable() or evento.char == ' '):
                forma['texto'] += evento.char
            else:
                return
            self.medir(forma)
            self.redesenhar()
            self.dizer('digite o texto — Enter quebra linha, Esc termina')
            return 'break'

        if self.selecionada is None:
            return
        forma = self.formas[self.selecionada]
        if forma['tipo'] == 'texto':
            # Selecionada mas sem estar em digitacao: a primeira tecla reabre.
            self.editando = self.selecionada
            self.piscar()
            return self.digitou(evento)
        if forma['tipo'] != 'callout':
            return
        if evento.keysym == 'BackSpace':
            forma['rotulo'] = forma['rotulo'][:-1]
        elif evento.char and evento.char.isprintable() and len(forma['rotulo']) < 3:
            forma['rotulo'] += evento.char
        else:
            return
        self.redesenhar()

    def encerrar_edicao(self):
        """Fecha a digitacao. Etiqueta vazia nao fica no desenho."""
        if self.editando is None:
            return
        indice = self.editando
        self.editando = None
        if not (self.formas[indice].get('texto') or '').strip():
            del self.formas[indice]
            if self.selecionada == indice:
                self.selecionada = None
            elif self.selecionada is not None and self.selecionada > indice:
                self.selecionada -= 1
        self.redesenhar()
        self.dizer()

    def piscar(self):
        """Cursor piscando, para deixar claro que da para digitar."""
        if self.editando is None:
            self.cursor_visivel = True
            return
        self.cursor_visivel = not self.cursor_visivel
        self.redesenhar()
        try:
            self.janela.after(480, self.piscar)
        except Exception:
            pass

    def forma_nova(self, x1, y1, x2, y2):
        tipo = self.ferramenta.get()
        base = {'tipo': tipo, 'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2,
                'cor': self.cor.get(), 'esp': self.espessura.get()}
        if tipo == 'marcador':
            base['raio'] = RAIO_CANTO
        return base

    # -- acerto e alcas ----------------------------------------------------

    def forma_em(self, x, y):
        """Indice da forma sob o ponto, de cima para baixo."""
        for indice in range(len(self.formas) - 1, -1, -1):
            forma = self.formas[indice]
            if forma['tipo'] == 'texto':
                if (forma['x'] - 4 <= x <= forma['x'] + forma.get('largura', 0) + 4 and
                        forma['y'] - 4 <= y <= forma['y'] + forma.get('altura', 0) + 4):
                    return indice
            elif forma['tipo'] == 'callout':
                if math.hypot(x - forma['x'], y - forma['y']) <= raio_do_callout(forma) + 4:
                    return indice
            elif forma['tipo'] == 'seta':
                if self.perto_da_linha(x, y, forma['x1'], forma['y1'], forma['x2'], forma['y2'], 8):
                    return indice
            else:
                x1, x2 = sorted((forma['x1'], forma['x2']))
                y1, y2 = sorted((forma['y1'], forma['y2']))
                perto_borda = (
                    (x1 - 8 <= x <= x2 + 8 and (abs(y - y1) <= 8 or abs(y - y2) <= 8)) or
                    (y1 - 8 <= y <= y2 + 8 and (abs(x - x1) <= 8 or abs(x - x2) <= 8))
                )
                if perto_borda:
                    return indice
        return None

    @staticmethod
    def perto_da_linha(px, py, x1, y1, x2, y2, tolerancia):
        dx, dy = x2 - x1, y2 - y1
        comprimento = math.hypot(dx, dy)
        if comprimento < 1:
            return math.hypot(px - x1, py - y1) <= tolerancia
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (comprimento ** 2)))
        return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy)) <= tolerancia

    def alcas_de(self, indice):
        forma = self.formas[indice]
        if forma['tipo'] == 'texto':
            return [(forma['x'] + forma.get('largura', 0), forma['y'] + forma.get('altura', 0))]
        if forma['tipo'] == 'callout':
            return [(forma['x'] + raio_do_callout(forma), forma['y'])]
        if forma['tipo'] == 'seta':
            return [(forma['x1'], forma['y1']), (forma['x2'], forma['y2'])]
        x1, x2 = sorted((forma['x1'], forma['x2']))
        y1, y2 = sorted((forma['y1'], forma['y2']))
        # ordem: 0 superior-esquerda, 1 superior-direita, 2 inferior-direita, 3 inferior-esquerda
        return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]

    def alca_em(self, indice, x, y):
        for numero, (ax, ay) in enumerate(self.alcas_de(indice)):
            if math.hypot(x - ax, y - ay) <= 9 / max(self.escala, 0.2):
                return numero
        return None

    # -- desenho no canvas -------------------------------------------------

    def redesenhar(self):
        """Redesenha a previa com o mesmo pincel que gera o arquivo.

        O canvas do Tk nao suaviza borda, entao desenhar as formas nele daria
        uma previa diferente do resultado. Aqui a camada e do Pillow, reduzida
        para a escala de exibicao, e o canvas so a exibe. Custa mais por quadro,
        e e uma troca deliberada: a ferramenta e para tirar print, e o que
        importa e a previa bater com o que sai.
        """
        self.canvas.delete('anotacao')
        self.canvas.delete('camada')

        formas = list(self.formas)
        if self.previa:
            formas.append(self.previa)

        if formas:
            camada = renderizar_anotacoes(
                (self.largura_tela, self.altura_tela), formas, self.escala)
            self.foto_da_camada = ImageTk.PhotoImage(camada)  # nao deixar coletar
            self.canvas.create_image(0, 0, image=self.foto_da_camada, anchor='nw',
                                     tags='camada')
        else:
            self.foto_da_camada = None

        # Alcas e cursor sao controle da interface, nao anotacao: seguem no
        # canvas, por cima da camada, e nao entram no arquivo.
        if self.selecionada is not None and self.ferramenta.get() == 'selecionar':
            self.desenhar_alcas(self.selecionada)
        self.desenhar_cursor()

    def desenhar_cursor(self):
        """Cursor piscando no fim do texto da etiqueta em digitacao."""
        if self.editando is None or not self.cursor_visivel:
            return
        forma = self.formas[self.editando]
        if forma['tipo'] != 'texto':
            return

        entrelinha = forma.get('entrelinha', forma.get('tamanho', 22) * 1.3)
        linhas = (forma.get('texto', '') or '').split('\n')
        tamanho_na_tela = max(6, int(forma.get('tamanho', 22) * self.escala))
        try:
            fonte = tkfont.Font(family='Segoe UI', size=tamanho_na_tela, weight='bold')
            deslocamento = fonte.measure(linhas[-1])
        except Exception:
            deslocamento = 0

        x1, y1 = self.para_tela(forma['x'], forma['y'])
        cx = x1 + FOLGA_TEXTO_X * self.escala + deslocamento
        cy = y1 + (FOLGA_TEXTO_Y + (len(linhas) - 1) * entrelinha) * self.escala
        self.canvas.create_line(cx, cy, cx, cy + tamanho_na_tela * 1.25,
                                fill=tinta_sobre(forma['cor']), width=2,
                                tags='anotacao')

    def desenhar_alcas(self, indice):
        for ax, ay in self.alcas_de(indice):
            x, y = self.para_tela(ax, ay)
            self.canvas.create_rectangle(x - 4, y - 4, x + 4, y + 4, fill=BRANCO,
                                         outline=NAVY, width=1, tags='anotacao')

    # -- acoes -------------------------------------------------------------

    def registrar(self):
        self.desfeitas.append([dict(f) for f in self.formas])
        del self.desfeitas[:-40]

    def desfazer(self):
        if not self.desfeitas:
            self.dizer('nada para desfazer')
            return
        self.formas = self.desfeitas.pop()
        self.selecionada = None
        self.proximo = 1 + sum(1 for f in self.formas if f['tipo'] == 'callout')
        self.redesenhar()
        self.dizer()

    def limpar(self):
        if self.formas:
            self.registrar()
        self.formas = []
        self.selecionada = None
        self.proximo = 1
        self.redesenhar()
        self.dizer()

    def apagar_selecionada(self):
        if self.editando is not None:
            return
        if self.selecionada is None:
            return
        self.registrar()
        del self.formas[self.selecionada]
        self.selecionada = None
        self.redesenhar()
        self.dizer()

    def aplicar_na_selecionada(self):
        if self.selecionada is None:
            return
        forma = self.formas[self.selecionada]
        forma['cor'] = self.cor.get()
        if 'esp' in forma:
            forma['esp'] = self.espessura.get()
        if forma['tipo'] == 'texto':
            forma['tamanho'] = self.tamanho_texto.get()
            self.medir(forma)
        self.redesenhar()

    def resultado(self):
        self.encerrar_edicao()
        return desenhar_em_imagem(self.imagem, self.formas)

    def copiar(self):
        try:
            copiar_imagem(self.resultado())
            self.dizer('copiado para a área de transferência — pode colar no documento')
        except Exception as erro:
            self.dizer(f'falhou ao copiar: {erro}')

    def salvar(self):
        pasta = ler_config().get('pasta') or os.path.join(
            os.path.expanduser('~'), 'Pictures', 'Alt')
        os.makedirs(pasta, exist_ok=True)
        sugestao = f'alt-{datetime.now():%Y%m%d-%H%M%S}.png'

        caminho = filedialog.asksaveasfilename(
            parent=self.janela, initialdir=pasta, initialfile=sugestao,
            defaultextension='.png',
            filetypes=[('PNG', '*.png'), ('JPEG', '*.jpg')],
        )
        if not caminho:
            return
        imagem = self.resultado()
        if caminho.lower().endswith(('.jpg', '.jpeg')):
            imagem.save(caminho, quality=95)
        else:
            imagem.save(caminho)
        gravar_config({'pasta': os.path.dirname(caminho)})
        self.dizer(f'salvo em {caminho}')

    def fechar(self):
        try:
            self.janela.destroy()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------


def ler_config():
    try:
        with open(CONFIG, encoding='utf-8') as arquivo:
            return json.load(arquivo)
    except Exception:
        return {}


def gravar_config(novos):
    dados = ler_config()
    dados.update(novos)
    try:
        with open(CONFIG, 'w', encoding='utf-8') as arquivo:
            json.dump(dados, arquivo, ensure_ascii=False, indent=1)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# ICONE DA BANDEJA
# ---------------------------------------------------------------------------

ICONE = os.path.join(pasta_de_dados(), 'alt.ico')
ICONE_EMBUTIDO = os.path.join(pasta_do_programa(), 'alt.ico')


def gerar_icone():
    """Desenha o icone: um callout magenta com um A branco dentro.

    E o mesmo desenho que a ferramenta produz, o que faz o icone na bandeja
    dizer o que ela faz.
    """
    if os.path.exists(ICONE_EMBUTIDO):
        return ICONE_EMBUTIDO
    if os.path.exists(ICONE):
        return ICONE

    lado = 256
    imagem = Image.new('RGBA', (lado, lado), (0, 0, 0, 0))
    pincel = ImageDraw.Draw(imagem)
    folga = 10
    pincel.ellipse((folga, folga, lado - folga, lado - folga), fill=MAGENTA)
    pincel.ellipse((folga, folga, lado - folga, lado - folga), outline=BRANCO, width=14)

    fonte = fonte_negrito(150)
    caixa = pincel.textbbox((0, 0), 'A', font=fonte)
    pincel.text(
        (lado / 2 - (caixa[2] - caixa[0]) / 2 - caixa[0],
         lado / 2 - (caixa[3] - caixa[1]) / 2 - caixa[1]),
        'A', font=fonte, fill=BRANCO,
    )
    try:
        imagem.save(ICONE, sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (48, 48), (64, 64)])
    except Exception:
        imagem.resize((32, 32), Image.LANCZOS).save(ICONE)
    return ICONE


WM_SETICON = 0x0080
ICONE_GRANDE, ICONE_PEQUENO = 1, 0


def aplicar_icone(janela):
    """Poe o icone do Alt na janela, no lugar da pena do Tk.

    Toda janela tkinter nasce com o logo do Tcl/Tk — uma pena — no canto e na
    barra de tarefas.

    Dois caminhos, de proposito. O `default=` do iconbitmap vale para toda
    Toplevel criada depois, mas o Tk o aplica na classe da janela, e nao da para
    ler de volta nem garantir que pegou. O WM_SETICON e direto no identificador
    da janela: e o que se pode conferir depois.
    """
    caminho = gerar_icone()
    aplicou = False

    try:
        janela.iconbitmap(default=caminho)
        aplicou = True
    except Exception:
        try:
            janela.iconphoto(True, ImageTk.PhotoImage(Image.open(caminho)))
            aplicou = True
        except Exception:
            pass

    try:
        janela.update_idletasks()
        usuario = ctypes.windll.user32
        usuario.GetAncestor.restype = ctypes.c_void_p
        usuario.SendMessageW.restype = ctypes.c_void_p
        usuario.LoadImageW.restype = ctypes.c_void_p

        # GA_ROOT: o winfo_id pode devolver um filho, e o icone vive no topo.
        hwnd = usuario.GetAncestor(ctypes.c_void_p(janela.winfo_id()), 2)
        for qual, lado in ((ICONE_GRANDE, 32), (ICONE_PEQUENO, 16)):
            hicone = usuario.LoadImageW(None, caminho, 1, lado, lado, 0x0010)
            if hicone:
                usuario.SendMessageW(ctypes.c_void_p(hwnd), WM_SETICON,
                                     qual, ctypes.c_void_p(hicone))
                aplicou = True
    except Exception:
        pass

    return aplicou


# ---------------------------------------------------------------------------
# GANCHO DE TECLADO DE BAIXO NIVEL
#
# O RegisterHotKey nao serve para o Print Screen: ele aceita o registro e
# devolve sucesso, mas o evento nunca chega, porque outro programa com gancho
# de baixo nivel (antivirus, OneDrive, a captura do proprio Windows) consome a
# tecla antes do despachante de atalhos. Registro nao e entrega.
#
# O WH_KEYBOARD_LL ve a tecla antes disso, e e o que as ferramentas do genero
# usam. O gancho tambem devolve 1 para a combinacao nossa, engolindo a tecla,
# de modo que a captura do Windows nao dispare junto.
# ---------------------------------------------------------------------------

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

VK_SNAPSHOT = 0x2C
VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_MENU = 0x12

# A combinacao que dispara a captura. O gancho de baixo nivel distingue o Shift
# esquerdo do direito, o que o RegisterHotKey nao faz — por isso a reserva
# aceita qualquer Shift.
TECLAS_EXIGIDAS = (VK_CONTROL, VK_LSHIFT)
NOME_DO_ATALHO = 'Ctrl + Shift esquerdo + Print Screen'


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ('vkCode', ctypes.c_ulong),
        ('scanCode', ctypes.c_ulong),
        ('flags', ctypes.c_ulong),
        ('time', ctypes.c_ulong),
        ('dwExtraInfo', ctypes.c_void_p),
    ]


PROC_DO_GANCHO = ctypes.WINFUNCTYPE(
    ctypes.c_long, ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(KBDLLHOOKSTRUCT))


def pressionada(tecla):
    return bool(ctypes.windll.user32.GetAsyncKeyState(tecla) & 0x8000)


class GanchoDeTeclado:
    """Escuta Ctrl + Print Screen por gancho de baixo nivel.

    Tem de ser instalado no fio que roda o laco de mensagens, e a referencia do
    callback precisa ficar viva: se o Python coletar o objeto, o Windows chama
    memoria liberada e o processo morre.
    """

    def __init__(self, ao_disparar, espiar=None):
        self.ao_disparar = ao_disparar
        self.espiar = espiar
        self.identificador = None
        self.ultimo = 0.0
        self._callback = PROC_DO_GANCHO(self._tratar)  # nao deixar coletar

    def instalar(self):
        usuario = ctypes.windll.user32
        usuario.SetWindowsHookExW.restype = ctypes.c_void_p
        usuario.SetWindowsHookExW.argtypes = [
            ctypes.c_int, PROC_DO_GANCHO, ctypes.c_void_p, ctypes.c_ulong]
        self.identificador = usuario.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._callback, None, 0)
        return bool(self.identificador)

    def remover(self):
        if self.identificador:
            try:
                ctypes.windll.user32.UnhookWindowsHookEx(self.identificador)
            except Exception:
                pass
            self.identificador = None

    def _tratar(self, codigo, wparam, lparam):
        seguir = lambda: ctypes.windll.user32.CallNextHookEx(
            None, codigo, wparam, lparam)

        if codigo != 0 or not lparam:
            return seguir()

        try:
            tecla = lparam.contents.vkCode
        except Exception:
            return seguir()

        mensagem = wparam if isinstance(wparam, int) else 0
        descendo = mensagem in (WM_KEYDOWN, WM_SYSKEYDOWN)
        subindo = mensagem in (WM_KEYUP, WM_SYSKEYUP)

        if self.espiar and (descendo or subindo):
            self.espiar(tecla, 'desce' if descendo else 'sobe',
                        pressionada(VK_CONTROL), pressionada(VK_SHIFT),
                        pressionada(VK_MENU))

        # O Print Screen, em varias configuracoes, so gera o evento de subida.
        # Por isso tratamos as duas bordas, com um travao de tempo para nao
        # disparar duas vezes na mesma batida de tecla.
        if tecla == VK_SNAPSHOT and (descendo or subindo):
            if all(pressionada(exigida) for exigida in TECLAS_EXIGIDAS):
                agora = time.time()
                if agora - self.ultimo > 0.45:
                    self.ultimo = agora
                    try:
                        self.ao_disparar()
                    except Exception:
                        pass
                return 1  # engole: a captura do Windows nao dispara junto

        return seguir()


# ---------------------------------------------------------------------------
# BANDEJA E ATALHO GLOBAL
# ---------------------------------------------------------------------------

MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_ALT = 0x0001
MOD_NOREPEAT = 0x4000

# Reserva, para o caso raro de o gancho nao poder ser instalado.
COMBINACOES = (
    ('Ctrl + Shift + Print Screen', MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, VK_SNAPSHOT),
    ('Ctrl + Alt + A', MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord('A')),
)

ID_CAPTURAR = 1001
ID_PASTA = 1002
ID_SAIR = 1009


class Bandeja(threading.Thread):
    """Icone na bandeja e atalho global, num fio proprio.

    Os dois moram aqui porque os dois dependem do mesmo laco de mensagens do
    Windows: RegisterHotKey entrega WM_HOTKEY na janela que registrou, e o
    Shell_NotifyIcon entrega o clique do icone na mesma janela.

    Nada de tkinter acontece neste fio. Os avisos vao para a fila e o fio
    principal os consome.
    """

    def __init__(self, fila, espiar=None):
        super().__init__(daemon=True)
        self.fila = fila
        self.espiar = espiar
        self.registrado = None
        self.mecanismo = None
        self.gancho = None
        self.hwnd = None
        self.pronto = threading.Event()
        self.falha = None

    # -- ciclo de vida -----------------------------------------------------

    def run(self):
        try:
            import win32api
            import win32con
            import win32gui
        except Exception as erro:
            self.falha = f'pywin32 ausente: {erro}'
            self.pronto.set()
            return

        self.win32api, self.win32con, self.win32gui = win32api, win32con, win32gui
        self.WM_BANDEJA = win32con.WM_USER + 20
        self.WM_TASKBAR_CRIADA = win32gui.RegisterWindowMessage('TaskbarCreated')

        try:
            self.criar_janela()
            self.registrar_atalho()
            self.criar_icone()
        except Exception as erro:
            self.falha = str(erro)
            self.pronto.set()
            return

        self.pronto.set()
        win32gui.PumpMessages()

    def criar_janela(self):
        wg, wa, wc = self.win32gui, self.win32api, self.win32con
        classe = wg.WNDCLASS()
        classe.hInstance = wa.GetModuleHandle(None)
        classe.lpszClassName = 'AltBandeja'
        classe.lpfnWndProc = {
            wc.WM_COMMAND: self.no_comando,
            wc.WM_DESTROY: self.no_destruir,
            wc.WM_HOTKEY: self.no_atalho,
            self.WM_BANDEJA: self.no_icone,
            self.WM_TASKBAR_CRIADA: self.na_barra_recriada,
        }
        atomo = wg.RegisterClass(classe)
        # Janela sem area util: existe so para receber mensagem.
        self.hwnd = wg.CreateWindow(atomo, 'Alt', wc.WS_OVERLAPPED, 0, 0, 0, 0,
                                    0, 0, classe.hInstance, None)
        wg.UpdateWindow(self.hwnd)

    def registrar_atalho(self):
        # Gancho de baixo nivel primeiro: e o unico jeito confiavel de ouvir o
        # Print Screen, que outros programas interceptam antes do despachante
        # de atalhos do Windows.
        self.gancho = GanchoDeTeclado(lambda: self.fila.put('capturar'),
                                      espiar=self.espiar)
        if self.gancho.instalar():
            self.registrado = NOME_DO_ATALHO
            self.mecanismo = 'gancho de teclado'
            return

        self.gancho = None
        usuario = ctypes.windll.user32
        for numero, (nome, modificadores, tecla) in enumerate(COMBINACOES, start=1):
            if usuario.RegisterHotKey(self.hwnd, numero, modificadores, tecla):
                self.registrado = nome
                self.mecanismo = 'atalho do sistema'
                return
        # Sem atalho a ferramenta ainda serve pelo menu da bandeja.

    def criar_icone(self):
        wg, wc = self.win32gui, self.win32con
        try:
            self.hicon = wg.LoadImage(0, gerar_icone(), wc.IMAGE_ICON, 0, 0,
                                      wc.LR_LOADFROMFILE)
        except Exception:
            self.hicon = wg.LoadIcon(0, wc.IDI_APPLICATION)

        dica = f'Alt — {self.registrado}' if self.registrado else 'Alt — sem atalho'
        wg.Shell_NotifyIcon(wg.NIM_ADD, (
            self.hwnd, 0,
            wg.NIF_ICON | wg.NIF_MESSAGE | wg.NIF_TIP,
            self.WM_BANDEJA, self.hicon, dica,
        ))
        self.avisar()

    def avisar(self):
        """Balao de aviso ao subir, dizendo qual atalho ficou valendo."""
        wg = self.win32gui
        if self.registrado == NOME_DO_ATALHO:
            titulo = 'Alt ativo'
            texto = 'Ctrl + Shift esquerdo + Print Screen para capturar.'
        elif self.registrado:
            titulo = 'Alt ativo com outro atalho'
            texto = (f'{self.registrado}.\nO gancho de teclado nao pode ser '
                     'instalado, entao esta reserva aceita qualquer Shift.')
        else:
            titulo = 'Alt sem atalho'
            texto = 'Nenhuma combinação ficou livre. Use o menu do ícone.'
        try:
            wg.Shell_NotifyIcon(wg.NIM_MODIFY, (
                self.hwnd, 0, wg.NIF_INFO, self.WM_BANDEJA, self.hicon,
                'Alt', texto, 200, titulo,
            ))
        except Exception:
            pass

    # -- mensagens ---------------------------------------------------------

    def no_icone(self, hwnd, mensagem, wparam, lparam):
        wc = self.win32con
        if lparam in (wc.WM_LBUTTONUP, wc.WM_LBUTTONDBLCLK):
            self.fila.put('capturar')
        elif lparam in (wc.WM_RBUTTONUP, wc.WM_CONTEXTMENU):
            self.abrir_menu()
        return True

    def abrir_menu(self):
        wg, wc = self.win32gui, self.win32con
        menu = wg.CreatePopupMenu()
        rotulo = f'Capturar agora\t{self.registrado}' if self.registrado else 'Capturar agora'
        wg.AppendMenu(menu, wc.MF_STRING, ID_CAPTURAR, rotulo)
        wg.AppendMenu(menu, wc.MF_SEPARATOR, 0, '')
        wg.AppendMenu(menu, wc.MF_STRING, ID_PASTA, 'Abrir pasta dos prints')
        wg.AppendMenu(menu, wc.MF_SEPARATOR, 0, '')
        wg.AppendMenu(menu, wc.MF_STRING, ID_SAIR, 'Sair')

        x, y = wg.GetCursorPos()
        # Sem trazer a janela para a frente, o menu nao fecha ao clicar fora.
        wg.SetForegroundWindow(self.hwnd)
        wg.TrackPopupMenu(menu, wc.TPM_LEFTALIGN | wc.TPM_BOTTOMALIGN | wc.TPM_RIGHTBUTTON,
                          x, y, 0, self.hwnd, None)
        wg.PostMessage(self.hwnd, wc.WM_NULL, 0, 0)
        wg.DestroyMenu(menu)

    def no_comando(self, hwnd, mensagem, wparam, lparam):
        escolha = self.win32api.LOWORD(wparam)
        if escolha == ID_CAPTURAR:
            self.fila.put('capturar')
        elif escolha == ID_PASTA:
            self.fila.put('pasta')
        elif escolha == ID_SAIR:
            self.fila.put('sair')
        return True

    def no_atalho(self, hwnd, mensagem, wparam, lparam):
        self.fila.put('capturar')
        return True

    def na_barra_recriada(self, hwnd, mensagem, wparam, lparam):
        """O explorer.exe reiniciou e levou o icone embora; recoloca."""
        try:
            self.criar_icone()
        except Exception:
            pass
        return True

    def no_destruir(self, hwnd, mensagem, wparam, lparam):
        self.remover_icone()
        self.win32gui.PostQuitMessage(0)
        return True

    def remover_icone(self):
        if self.gancho:
            self.gancho.remover()
        try:
            self.win32gui.Shell_NotifyIcon(self.win32gui.NIM_DELETE, (self.hwnd, 0))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# APLICACAO
# ---------------------------------------------------------------------------


class Alt:
    """Fica na bandeja. Nenhuma janela visivel ate a captura comecar."""

    def __init__(self, mostrar_painel=False, espiar=None):
        self.raiz = tk.Tk()
        self.raiz.withdraw()
        aplicar_icone(self.raiz)
        self.ocupado = False
        self.fila = queue.Queue()

        self.bandeja = Bandeja(self.fila, espiar=espiar)
        self.bandeja.start()
        self.bandeja.pronto.wait(timeout=4)

        self.painel = None
        # Se a bandeja nao subiu, o painel e a unica forma de saber que a
        # ferramenta esta viva e de conseguir encerra-la.
        if mostrar_painel or self.bandeja.falha or not self.bandeja.hwnd:
            self.painel = self.montar_painel()

        self.raiz.after(120, self.olhar_fila)

    def montar_painel(self):
        painel = tk.Toplevel(self.raiz)
        painel.title('Alt')
        painel.configure(bg=FUNDO)
        painel.resizable(False, False)
        painel.attributes('-topmost', True)

        tk.Label(painel, text='Alt', bg=FUNDO, fg=BRANCO,
                 font=('Segoe UI', 20, 'bold')).pack(padx=26, pady=(18, 0))

        if self.bandeja.falha:
            recado, cor = f'bandeja indisponível\n{self.bandeja.falha}', LARANJA
        elif self.bandeja.registrado:
            recado, cor = f'ativo  ·  {self.bandeja.registrado}', VERDE
        else:
            recado, cor = ('nenhum atalho pôde ser registrado\n'
                           'outro programa está usando essas teclas'), LARANJA
        tk.Label(painel, text=recado, bg=FUNDO, fg=cor, justify='center',
                 font=('Segoe UI', 10)).pack(padx=26, pady=(2, 12))

        linha = tk.Frame(painel, bg=FUNDO)
        linha.pack(padx=26, pady=(0, 18))
        tk.Button(linha, text='Capturar agora', command=self.capturar,
                  bg=MAGENTA, fg=BRANCO, activebackground=MAGENTA,
                  bd=0, padx=16, pady=8, font=('Segoe UI', 10, 'bold'),
                  cursor='hand2').pack(side='left', padx=(0, 6))
        tk.Button(linha, text='Sair', command=self.sair,
                  bg=FUNDO_BARRA, fg=TEXTO, activebackground=BORDA,
                  bd=0, padx=16, pady=8, font=('Segoe UI', 10),
                  cursor='hand2').pack(side='left')

        painel.protocol('WM_DELETE_WINDOW', self.sair)
        painel.update_idletasks()
        painel.geometry(f'+{painel.winfo_screenwidth() - painel.winfo_width() - 40}+60')
        return painel

    def olhar_fila(self):
        try:
            while True:
                aviso = self.fila.get_nowait()
                if aviso == 'capturar':
                    self.capturar()
                elif aviso == 'pasta':
                    self.abrir_pasta()
                elif aviso == 'sair':
                    self.sair()
        except queue.Empty:
            pass
        self.raiz.after(120, self.olhar_fila)

    def capturar(self):
        if self.ocupado:
            return
        self.ocupado = True
        try:
            if self.painel:
                self.painel.withdraw()
            self.raiz.update()
            time.sleep(0.18)  # deixa a janela sair da tela antes do print
            imagem, ox, oy = capturar_tudo()
            SelecaoDeArea(self.raiz, imagem, ox, oy, self.abrir_editor)
        finally:
            if self.painel:
                self.painel.deiconify()
            self.ocupado = False

    def abrir_editor(self, recorte):
        Editor(self.raiz, recorte)

    def abrir_pasta(self):
        pasta = ler_config().get('pasta') or os.path.join(
            os.path.expanduser('~'), 'Pictures', 'Alt')
        os.makedirs(pasta, exist_ok=True)
        os.startfile(pasta)

    def sair(self):
        self.bandeja.remover_icone()
        try:
            self.raiz.destroy()
        except Exception:
            pass
        os._exit(0)

    def rodar(self):
        self.raiz.mainloop()


# ---------------------------------------------------------------------------
# AUTOTESTE — o que da para verificar sem clicar em nada
# ---------------------------------------------------------------------------


def autoteste():
    print(f'Alt — autoteste')
    print(f'  python              {sys.version.split()[0]}')
    print(f'  consciencia de dpi  {DPI}')

    x, y, largura, altura = area_virtual()
    print(f'  desktop virtual     origem ({x}, {y})  tamanho {largura}x{altura}')

    imagem, ox, oy = capturar_tudo()
    print(f'  captura             {imagem.size[0]}x{imagem.size[1]} a partir de ({ox}, {oy})')
    coerente = imagem.size == (largura, altura)
    print(f'  captura coerente    {"sim" if coerente else "NAO — o recorte sairia deslocado"}')

    # O que importa nao e se o atalho registra, e se o evento chega. Aqui o
    # gancho e instalado de verdade e uma tecla sintetica e disparada, para o
    # teste responder "entrega" e nao "registro".
    recebidos = []
    gancho = GanchoDeTeclado(lambda: recebidos.append(time.time()))
    instalou = gancho.instalar()
    print(f'  gancho de teclado   {"instalado" if instalou else "NAO INSTALOU"}')

    if instalou:
        usuario = ctypes.windll.user32
        KEYUP = 0x0002
        for exigida in TECLAS_EXIGIDAS:
            usuario.keybd_event(exigida, 0, 0, 0)
            time.sleep(0.03)
        usuario.keybd_event(VK_SNAPSHOT, 0, 0, 0)
        time.sleep(0.04)
        usuario.keybd_event(VK_SNAPSHOT, 0, KEYUP, 0)
        time.sleep(0.03)
        for exigida in reversed(TECLAS_EXIGIDAS):
            usuario.keybd_event(exigida, 0, KEYUP, 0)
            time.sleep(0.02)

        # O gancho e chamado pelo Windows durante o bombeamento de mensagens.
        classe = ctypes.Structure
        fim = time.time() + 2
        while time.time() < fim and not recebidos:
            ctypes.windll.user32.PeekMessageW(None, None, 0, 0, 1)
            time.sleep(0.03)

        entregou = bool(recebidos)
        print(f'  atalho              {NOME_DO_ATALHO}')
        print(f'  entrega             {"CONFIRMADA" if entregou else "NAO CHEGOU"}')
        if not entregou:
            print('                      outro programa esta consumindo a tecla antes;')
            print('                      o Alt cai nas reservas abaixo')
        gancho.remover()

    usuario = ctypes.windll.user32
    for nome, modificadores, tecla in COMBINACOES:
        if usuario.RegisterHotKey(None, 90, modificadores, tecla):
            usuario.UnregisterHotKey(None, 90)
            print(f'  reserva             {nome}: LIVRE')
        else:
            print(f'  reserva             {nome}: ocupada')

    try:
        copiar_imagem(imagem.crop((0, 0, 40, 40)))
        print('  area de transf.     ok')
    except Exception as erro:
        print(f'  area de transf.     FALHOU: {erro}')

    # Amostra visual das tres formas, para conferir a aparencia.
    amostra = Image.new('RGB', (860, 450), '#F6F7FB')
    pincel = ImageDraw.Draw(amostra)
    fonte = fonte_negrito(15)
    for i in range(4):
        pincel.rounded_rectangle((60, 70 + i * 70, 470, 115 + i * 70), radius=6,
                                 outline='#C8CFDD', width=2)
        pincel.text((78, 84 + i * 70), f'Campo de exemplo {i + 1}', font=fonte, fill='#4B5468')
    pincel.text((60, 28), 'Alt — amostra das quatro formas', font=fonte_negrito(20), fill='#1C2231')

    formas = [
        {'tipo': 'marcador', 'x1': 55, 'y1': 65, 'x2': 475, 'y2': 120,
         'raio': RAIO_CANTO, 'cor': MAGENTA, 'esp': 3},
        {'tipo': 'seta', 'x1': 640, 'y1': 92, 'x2': 495, 'y2': 92,
         'cor': MAGENTA, 'esp': 3},
        {'tipo': 'callout', 'x': 672, 'y': 92, 'r': RAIO_CALLOUT, 'rotulo': '1',
         'cor': MAGENTA},
        {'tipo': 'seta', 'x1': 640, 'y1': 162, 'x2': 495, 'y2': 162,
         'cor': LARANJA, 'esp': 3},
        {'tipo': 'callout', 'x': 672, 'y': 162, 'r': RAIO_CALLOUT, 'rotulo': '2',
         'cor': LARANJA},
        {'tipo': 'seta', 'x1': 640, 'y1': 232, 'x2': 495, 'y2': 232,
         'cor': VERDE, 'esp': 3},
        {'tipo': 'callout', 'x': 672, 'y': 232, 'r': RAIO_CALLOUT, 'rotulo': 'A',
         'cor': VERDE},
        {'tipo': 'seta', 'x1': 640, 'y1': 302, 'x2': 495, 'y2': 302,
         'cor': NAVY, 'esp': 5},
        {'tipo': 'callout', 'x': 672, 'y': 302, 'r': 22, 'rotulo': '12',
         'cor': NAVY},
        {'tipo': 'marcador', 'x1': 720, 'y1': 40, 'x2': 830, 'y2': 340,
         'raio': 18, 'cor': NAVY, 'esp': 2},
    ]

    # Etiquetas de texto, com a caixa medida pelo mesmo caminho do editor.
    etiquetas = [
        {'tipo': 'texto', 'x': 60, 'y': 350, 'texto': 'Campo obrigatório',
         'tamanho': 22, 'raio': RAIO_TEXTO, 'cor': MAGENTA},
        {'tipo': 'texto', 'x': 330, 'y': 350, 'texto': 'Atenção',
         'tamanho': 22, 'raio': RAIO_TEXTO, 'cor': LARANJA},
        {'tipo': 'texto', 'x': 505, 'y': 350, 'texto': 'duas' + chr(10) + 'linhas',
         'tamanho': 16, 'raio': RAIO_TEXTO, 'cor': VERDE},
        {'tipo': 'texto', 'x': 630, 'y': 350, 'texto': 'Aqui',
         'tamanho': 30, 'raio': RAIO_TEXTO, 'cor': NAVY},
    ]
    for etiqueta in etiquetas:
        largura, altura, entrelinha = medir_texto_pil(etiqueta['texto'], etiqueta['tamanho'])
        etiqueta.update(largura=largura, altura=altura, entrelinha=entrelinha)
    formas.extend(etiquetas)
    saida = desenhar_em_imagem(amostra, formas)
    destino = os.path.join(pasta_de_dados(), 'amostra.png')
    saida.save(destino)
    print(f'  amostra salva em    {destino}')


# ---------------------------------------------------------------------------


def main():
    argumentos = set(sys.argv[1:])

    if '--autoteste' in argumentos:
        autoteste()
        return

    aplicacao = Alt(mostrar_painel='--painel' in argumentos)
    if '--capturar' in argumentos:
        aplicacao.raiz.after(250, aplicacao.capturar)
    aplicacao.rodar()


if __name__ == '__main__':
    main()
