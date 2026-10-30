import unittest

from pr_watch.placement import MARGIN, Rect, place, taskbar_edge

SCREEN = Rect(0, 0, 1920, 1080)
SIZE = (340, 400)


class PlacementTest(unittest.TestCase):
    def test_barra_abajo_icono_a_la_derecha(self) -> None:
        work = Rect(0, 0, 1920, 1032)
        icon = Rect(1700, 1040, 1724, 1064)
        x, y = place(SIZE, SCREEN, work, icon)
        self.assertEqual(y, 1032 - 400 - MARGIN)
        self.assertEqual(x, 1712 - 170)

    def test_no_se_sale_por_la_derecha(self) -> None:
        work = Rect(0, 0, 1920, 1032)
        icon = Rect(1890, 1040, 1914, 1064)
        x, _ = place(SIZE, SCREEN, work, icon)
        self.assertEqual(x + 340, 1920 - MARGIN)

    def test_barra_arriba(self) -> None:
        work = Rect(0, 48, 1920, 1080)
        icon = Rect(1700, 12, 1724, 36)
        _, y = place(SIZE, SCREEN, work, icon)
        self.assertEqual(y, 48 + MARGIN)

    def test_barra_a_la_izquierda_y_a_la_derecha(self) -> None:
        left_work = Rect(60, 0, 1920, 1080)
        x, y = place(SIZE, SCREEN, left_work, Rect(18, 900, 42, 924))
        self.assertEqual(x, 60 + MARGIN)
        # Centrado en el icono se saldria por abajo: se ajusta al borde.
        self.assertEqual(y, 1080 - 400 - MARGIN)
        right_work = Rect(0, 0, 1860, 1080)
        x, _ = place(SIZE, SCREEN, right_work, Rect(1878, 900, 1902, 924))
        self.assertEqual(x, 1860 - 340 - MARGIN)

    def test_sin_posicion_del_icono_va_a_la_esquina_junto_a_la_barra(self) -> None:
        work = Rect(0, 0, 1920, 1032)
        self.assertEqual(
            place(SIZE, SCREEN, work, None), (1920 - 340 - MARGIN, 1032 - 400 - MARGIN)
        )

    def test_pantalla_secundaria_con_coordenadas_negativas(self) -> None:
        screen = Rect(-2560, 0, 0, 1440)
        work = Rect(-2560, 0, 0, 1392)
        x, y = place(SIZE, screen, work, Rect(-200, 1400, -176, 1424))
        self.assertTrue(x >= -2560 and x + 340 <= 0)
        self.assertEqual(y, 1392 - 400 - MARGIN)

    def test_lado_de_la_barra(self) -> None:
        self.assertEqual(taskbar_edge(SCREEN, Rect(0, 0, 1920, 1032)), "bottom")
        self.assertEqual(taskbar_edge(SCREEN, SCREEN), "bottom")


if __name__ == "__main__":
    unittest.main()
