import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pr_watch import icon


def alpha_at(img: Image.Image, fx: float, fy: float) -> int:
    px = img.getpixel((int(fx * img.width), int(fy * img.height)))
    assert isinstance(px, tuple)
    return int(px[3])


class IconTest(unittest.TestCase):
    def test_a_16_px_los_tres_nodos_se_distinguen(self) -> None:
        img = icon.glyph(16, icon.LIGHT_GLYPH)
        for fx, fy in [(0.27, 0.20), (0.27, 0.80), (0.73, 0.80)]:
            with self.subTest(nodo=(fx, fy)):
                self.assertGreater(alpha_at(img, fx, fy), 128)
        # Y entre las dos ramas, abajo, hay hueco: no es una mancha.
        self.assertLess(alpha_at(img, 0.5, 0.80), 64)

    def test_sin_fondo(self) -> None:
        img = icon.glyph(32, icon.LIGHT_GLYPH)
        self.assertEqual(alpha_at(img, 0.02, 0.98), 0)

    def test_con_y_sin_punto_difieren(self) -> None:
        a = icon.tray_image(32, dark_taskbar=True, unseen=False)
        b = icon.tray_image(32, dark_taskbar=True, unseen=True)
        self.assertNotEqual(a.tobytes(), b.tobytes())

    def test_color_segun_la_barra(self) -> None:
        dark = icon.tray_image(32, dark_taskbar=True, unseen=False)
        light = icon.tray_image(32, dark_taskbar=False, unseen=False)
        x, y = int(0.27 * 32), int(0.8 * 32)
        self.assertGreater(sum(dark.getpixel((x, y))[:3]), 600)  # type: ignore[index]
        self.assertLess(sum(light.getpixel((x, y))[:3]), 150)  # type: ignore[index]

    def test_no_se_regenera_si_no_cambia(self) -> None:
        r = icon.TrayRenderer(32)
        self.assertIsNotNone(r.render(dark_taskbar=True, unseen=False))
        self.assertIsNone(r.render(dark_taskbar=True, unseen=False))
        self.assertIsNotNone(r.render(dark_taskbar=True, unseen=True))
        self.assertIsNotNone(r.render(dark_taskbar=False, unseen=True))

    def test_ico_con_todos_los_tamanos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = icon.write_ico(Path(tmp) / "pr-watch.ico")
            with Image.open(path) as ico:
                sizes = ico.info.get("sizes") or set()
        self.assertTrue({(16, 16), (32, 32), (256, 256)} <= set(sizes))


if __name__ == "__main__":
    unittest.main()
