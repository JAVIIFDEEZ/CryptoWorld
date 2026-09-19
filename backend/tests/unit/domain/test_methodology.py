"""
test_methodology.py — La nota tiene que envejecer mal a la vista, no en silencio.

Una nota metodológica en un documento suelto se queda obsoleta sin que nadie se
entere: el umbral se recalibra, la definición cambia y el texto sigue diciendo lo
de antes. Que viva en el código solo ayuda si algo se rompe cuando se desincroniza.

Eso es lo que hacen estos tests. No comprueban que el texto sea bonito:
comprueban que **cada métrica publica sus límites**, que los números citados en
ellos coinciden con los que el motor produce de verdad, y que las métricas que
esta plataforma muestra tienen entrada. Un campo «límites» vacío es el estado por
defecto de casi toda la industria y es exactamente lo que esta página existe para
no hacer.
"""

import pytest

from core.domain.services.methodology import (
    DISCLAIMERS, GOLDEN_RULE, METHODOLOGY_VERSION, NOTES, all_notes, note_for,
)


class TestCadaNotaEstaCompleta:

    @pytest.mark.unit
    def test_todas_traen_los_tres_campos(self):
        for note in NOTES:
            assert {"key", "title", "what", "assumptions", "limits"} <= set(note)

    @pytest.mark.unit
    def test_ninguna_deja_los_limites_en_blanco(self):
        """El campo que casi nadie publica y el único que distingue una nota
        metodológica de un folleto."""
        for note in NOTES:
            assert len(note["limits"]) > 60, f"{note['key']} no declara sus límites"

    @pytest.mark.unit
    def test_ninguna_deja_los_supuestos_en_blanco(self):
        for note in NOTES:
            assert len(note["assumptions"]) > 30, f"{note['key']} no declara supuestos"

    @pytest.mark.unit
    def test_las_claves_no_se_repiten(self):
        claves = [n["key"] for n in NOTES]
        assert len(claves) == len(set(claves))


class TestCubreLoQueLaPlataformaEnsena:
    """
    Una métrica visible sin nota es una cifra sin contrato. Estas claves son las
    que el producto muestra hoy; si se añade otra, este test obliga a
    documentarla antes de publicarla.
    """

    @pytest.mark.unit
    @pytest.mark.parametrize("clave", [
        "fitness", "deflated_sharpe", "pbo", "purged_cv", "edge_ml",
        "feature_importance", "execution_cost", "edge_test", "incubation",
        "risk_gate",
    ])
    def test_la_metrica_tiene_nota(self, clave):
        assert note_for(clave) is not None

    @pytest.mark.unit
    def test_una_clave_inexistente_devuelve_none_en_vez_de_reventar(self):
        assert note_for("no_existe") is None


class TestLosNumerosCitadosSonLosDelMotor:
    """
    Los límites citan cifras medidas durante el desarrollo. Si el motor cambia y
    la nota no, la nota miente — y miente con autoridad, que es peor.
    """

    @pytest.mark.unit
    def test_la_purga_cita_la_inflacion_que_se_midio(self):
        """0,76 puntos porcentuales sobre ocho series de ruido puro."""
        assert "0,76" in note_for("purged_cv")["limits"]

    @pytest.mark.unit
    def test_el_edge_cita_el_tamano_de_muestra_que_haria_falta(self):
        limites = note_for("edge_ml")["limits"]
        assert "4.000" in limites and "15.000" in limites

    @pytest.mark.unit
    def test_el_test_de_potencia_cita_el_criterio_descartado(self):
        """Que el criterio cambió después de calibrar es parte de la nota, no una
        nota al pie: ocultarlo sería el patrón que este motor critica."""
        limites = note_for("edge_test")["limits"]
        assert "+0,45" in limites and "7 de 9" in limites

    @pytest.mark.unit
    def test_la_importancia_dice_que_no_significa_no_significativo(self):
        limites = note_for("feature_importance")["limits"]
        assert "no se ha demostrado que aporte" in limites

    @pytest.mark.unit
    def test_el_control_de_riesgo_declara_que_falla_cerrado(self):
        limites = note_for("risk_gate")["limits"]
        assert "NO autoriza" in limites
        assert "ventas" in limites          # y que las ventas nunca se bloquean

    @pytest.mark.unit
    def test_el_coste_de_ejecucion_niega_ser_el_libro_de_ordenes(self):
        assert "libro de órdenes" in note_for("execution_cost")["limits"]


class TestLaReglaYLoQueNoSeAfirma:

    @pytest.mark.unit
    def test_la_regla_de_oro_nombra_las_tres_condiciones(self):
        for termino in ("dentro de muestra", "costes", "deflactar"):
            assert termino in GOLDEN_RULE

    @pytest.mark.unit
    def test_se_publica_que_no_se_predice_la_direccion(self):
        """La ausencia de una promesa es tan informativa como la promesa, y es lo
        que separa esta herramienta del resto del segmento."""
        assert any("dirección del precio" in d for d in DISCLAIMERS)

    @pytest.mark.unit
    def test_se_publica_que_el_rendimiento_es_simulado(self):
        assert any("simulado" in d for d in DISCLAIMERS)

    @pytest.mark.unit
    def test_se_publica_que_el_sharpe_va_con_su_numero_de_pruebas(self):
        assert any("configuraciones probadas" in d for d in DISCLAIMERS)


class TestLaVersion:

    @pytest.mark.unit
    def test_la_nota_esta_versionada(self):
        """Quien citó una cifra tiene que poder saber contra qué definición la
        citó."""
        assert METHODOLOGY_VERSION and "." in METHODOLOGY_VERSION

    @pytest.mark.unit
    def test_all_notes_devuelve_copias(self):
        """Si devolviera las mismas referencias, un consumidor podría mutar la
        nota publicada para todos los demás."""
        copia = all_notes()
        copia[0]["limits"] = "manipulado"
        assert NOTES[0]["limits"] != "manipulado"
