import unittest

from pr_watch.placement import MARGIN, Rect, place, taskbar_edge

SCREEN = Rect(0, 0, 1920, 1080)
SIZE = (340, 400)


class PlacementTest(unittest.TestCase):
    def test_barra_abajo_va_a_la_esquina_inferior_derecha(self) -> None:
        work = Rect(0, 0, 1920, 1032)
        x, y = place(SIZE, SCREEN, work)
        self.assertEqual(x, 1920 - 340 - MARGIN)
        self.assertEqual(y, 1032 - 400 - MARGIN)

    def test_la_posicion_no_depende_del_icono(self) -> None:
        """El panel va a la esquina este donde este el icono de bandeja."""
        work = Rect(0, 0, 1920, 1032)
        esquina = (1920 - 340 - MARGIN, 1032 - 400 - MARGIN)
        self.assertEqual(place(SIZE, SCREEN, work), esquina)

    def test_barra_arriba(self) -> None:
        work = Rect(0, 48, 1920, 1080)
        x, y = place(SIZE, SCREEN, work)
        self.assertEqual(x, 1920 - 340 - MARGIN)
        self.assertEqual(y, 48 + MARGIN)

    def test_barra_a_la_izquierda_y_a_la_derecha(self) -> None:
        # Con la barra en un lateral, la bandeja esta abajo: esquina inferior
        # del lado donde esta la barra.
        left_work = Rect(60, 0, 1920, 1080)
        x, y = place(SIZE, SCREEN, left_work)
        self.assertEqual(x, 60 + MARGIN)
        self.assertEqual(y, 1080 - 400 - MARGIN)

        right_work = Rect(0, 0, 1860, 1080)
        x, y = place(SIZE, SCREEN, right_work)
        self.assertEqual(x, 1860 - 340 - MARGIN)
        self.assertEqual(y, 1080 - 400 - MARGIN)

    def test_pantalla_secundaria_con_coordenadas_negativas(self) -> None:
        screen = Rect(-2560, 0, 0, 1440)
        work = Rect(-2560, 0, 0, 1392)
        x, y = place(SIZE, screen, work)
        self.assertEqual(x, 0 - 340 - MARGIN)
        self.assertEqual(y, 1392 - 400 - MARGIN)

    def test_panel_mas_ancho_que_la_pantalla_no_se_sale_por_la_izquierda(self) -> None:
        work = Rect(0, 0, 300, 1032)
        x, _ = place(SIZE, Rect(0, 0, 300, 1080), work)
        self.assertEqual(x, MARGIN)

    def test_lado_de_la_barra(self) -> None:
        self.assertEqual(taskbar_edge(SCREEN, Rect(0, 0, 1920, 1032)), "bottom")
        self.assertEqual(taskbar_edge(SCREEN, SCREEN), "bottom")


if __name__ == "__main__":
    unittest.main()
