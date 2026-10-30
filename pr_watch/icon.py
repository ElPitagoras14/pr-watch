"""La marca de pr-watch: el glifo de un pull request, dibujado por codigo.

Un solo dibujo para la bandeja, las ventanas y el ejecutable (D10). Se traza a
4x y se reduce, para que a 16 px los nodos sigan siendo nodos. Las medidas son
fracciones del lado, asi que vale para cualquier tamano.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

type RGBA = tuple[int, int, int, int]

LIGHT_GLYPH: RGBA = (255, 255, 255, 255)  # sobre barra oscura
DARK_GLYPH: RGBA = (31, 31, 31, 255)  # sobre barra clara
BRAND: RGBA = (47, 129, 247, 255)  # ejecutable y ventanas
DOT: RGBA = (47, 129, 247, 255)

ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
_SS = 4  # sobremuestreo


def glyph(size: int, color: RGBA) -> Image.Image:
    """El simbolo: dos nodos unidos a la izquierda y la rama que vuelve a la derecha."""
    s = size * _SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def px(v: float) -> float:
        return v * s

    stroke = max(1, round(px(0.10)))
    r = px(0.125)

    def node(cx: float, cy: float) -> None:
        d.ellipse((px(cx) - r, px(cy) - r, px(cx) + r, px(cy) + r), fill=color)

    # Rama izquierda: base y cabeza unidas.
    d.line((px(0.27), px(0.20), px(0.27), px(0.80)), fill=color, width=stroke)
    node(0.27, 0.20)
    node(0.27, 0.80)

    # Rama derecha: sube desde su nodo, dobla y vuelve hacia la izquierda.
    d.line((px(0.73), px(0.80), px(0.73), px(0.42)), fill=color, width=stroke)
    bend = px(0.18)
    d.arc(
        (px(0.73) - 2 * bend, px(0.24), px(0.73), px(0.24) + 2 * bend),
        start=270,
        end=360,
        fill=color,
        width=stroke,
    )
    d.line((px(0.73) - bend, px(0.24), px(0.55), px(0.24)), fill=color, width=stroke)
    # Punta de flecha hacia la rama izquierda.
    d.polygon(
        [(px(0.43), px(0.24)), (px(0.58), px(0.10)), (px(0.58), px(0.38))],
        fill=color,
    )
    node(0.73, 0.80)

    return img.resize((size, size), Image.Resampling.LANCZOS)


def with_dot(base: Image.Image) -> Image.Image:
    """Anade el punto de novedades arriba a la derecha.

    Alrededor del punto se recorta un aro transparente: lo separa del glifo
    sobre cualquier color de barra, sin tener que adivinar cual es.
    """
    size = base.width
    s = size * _SS
    big = base.resize((s, s), Image.Resampling.LANCZOS)
    cx, cy, r = s * 0.81, s * 0.19, s * 0.17
    gap = s * 0.07
    mask = Image.new("L", (s, s), 255)
    ImageDraw.Draw(mask).ellipse((cx - r - gap, cy - r - gap, cx + r + gap, cy + r + gap), fill=0)
    alpha = Image.composite(big.getchannel("A"), Image.new("L", (s, s), 0), mask)
    big.putalpha(alpha)
    ImageDraw.Draw(big).ellipse((cx - r, cy - r, cx + r, cy + r), fill=DOT)
    return big.resize((size, size), Image.Resampling.LANCZOS)


def tray_image(size: int, *, dark_taskbar: bool, unseen: bool) -> Image.Image:
    color = LIGHT_GLYPH if dark_taskbar else DARK_GLYPH
    img = glyph(size, color)
    if unseen:
        img = with_dot(img)
    return img


class TrayRenderer:
    """Solo produce imagen nueva cuando cambia lo que se ve: (tema, hay novedades)."""

    def __init__(self, size: int = 64) -> None:
        self.size = size
        self._last: tuple[bool, bool] | None = None

    def render(self, *, dark_taskbar: bool, unseen: bool) -> Image.Image | None:
        key = (dark_taskbar, unseen)
        if key == self._last:
            return None
        self._last = key
        return tray_image(self.size, dark_taskbar=dark_taskbar, unseen=unseen)


def window_icon(size: int = 256) -> Image.Image:
    return glyph(size, BRAND)


def write_ico(path: Path) -> Path:
    """El icono del ejecutable, con una imagen trazada para cada tamano."""
    images = [glyph(n, BRAND) for n in ICO_SIZES]
    path.parent.mkdir(parents=True, exist_ok=True)
    images[-1].save(
        path, format="ICO", sizes=[(n, n) for n in ICO_SIZES], append_images=images[:-1]
    )
    return path
