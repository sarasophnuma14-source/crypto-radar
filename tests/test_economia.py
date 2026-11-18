"""Comprueba que las cifras de docs/UNIT_ECONOMICS.md salen de sus fórmulas (ARPU, comisiones, contribución, caja,
equilibrio, LTV) y que los documentos vigentes no se contradicen.

    python3 tests/test_economia.py

Solo usa las entradas que el documento declara: precios propuestos (decisión del propietario), tarifas públicas y
supuestos etiquetados. Si cambia una entrada, cambia el documento y esta prueba a la vez.
"""
import re
import unittest
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
UE = (DOCS / "UNIT_ECONOMICS.md").read_text("utf-8")

M, A = 15.0, 149.0            # propuesta Pro (decisión preliminar del propietario)
ANNUAL = 0.40                 # SUPUESTO base
COP = 4000.0                  # SUPUESTO para la parte fija de Wompi
CARD = 0.70                   # SUPUESTO: 70 % tarjeta, 30 % USDT
SUPPORT = 0.25 * 10           # SUPUESTO: 15 min por usuario y mes a US$10/h
FIXED = 7 + 35 + (0.25 * 730 * 0.106 + 0.35)   # Render + CoinGecko Basic + Neon Launch estimado


def wompi(usd):
    return (usd * COP * 0.0265 + 700) * 1.19 / COP


def nowp(usd):
    return usd * 0.01 + 0.5


def arpu(annual=ANNUAL):
    return (1 - annual) * M + annual * A / 12


def fees(annual=ANNUAL):
    fm = CARD * wompi(M) + (1 - CARD) * nowp(M)
    fa = (CARD * wompi(A) + (1 - CARD) * nowp(A)) / 12
    return (1 - annual) * fm + annual * fa


def contribution(iva=False):
    return (arpu() / 1.19 if iva else arpu()) - fees() - SUPPORT


def es(x, d=2):
    """Formato del documento: coma decimal y punto de miles."""
    s = f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


class Formulas(unittest.TestCase):
    def test_arpu_y_descuento_anual(self):
        self.assertAlmostEqual(arpu(), 13.97, places=2)
        self.assertAlmostEqual(arpu(0.2), 14.48, places=2)
        self.assertAlmostEqual(arpu(0.6), 13.45, places=2)
        self.assertEqual(round(A / 12, 2), 12.42)
        self.assertEqual(round((1 - A / (12 * M)) * 100, 1), 17.2)
        for v in ("13,97", "14,48", "13,45", "12,42", "17,2 %"):
            self.assertIn(v, UE)

    def test_comisiones_y_contribucion(self):
        self.assertEqual(round(wompi(M), 2), 0.68)
        self.assertEqual(round(wompi(A), 2), 4.91)
        self.assertEqual(round(fees(), 2), 0.54)
        self.assertEqual(round(contribution(), 2), 10.93)
        self.assertEqual(round(contribution(iva=True), 2), 8.70)
        for v in ("US$0,54", "3,8 %", "10,93", "8,70"):
            self.assertIn(v, UE)

    def test_costos_separados_por_etapa(self):
        """Auditoría correctiva H6: gasto actual, piloto, comercialización, variables y sin cotizar, por separado."""
        for h in ("### 6.1 Gasto actual", "### 6.2 Estimación del piloto", "### 6.3 Estimación de comercialización",
                  "### 6.4 Costos variables", "### 6.5 Costos de negocio sin cotizar"):
            self.assertIn(h, UE)
        actual = UE[UE.index("### 6.1"):UE.index("### 6.2")]
        self.assertIn("| **Total verificado** | **14,00** |", actual)
        self.assertEqual(7 + 7, 14)                                            # Render 2.1 + Render 2.0
        for k in ("Neon", "**PENDIENTE: costo real sin verificar**", "Sujeto a licencia y plan", "todavía activo"):
            self.assertIn(k, actual)
        pil = UE[UE.index("### 6.2"):UE.index("### 6.3")]
        self.assertIn("**7,00 a 49,00**", pil)
        self.assertEqual((7 + 0 + 0, 7 + 7 + 35), (7, 49))
        com = UE[UE.index("### 6.3"):UE.index("### 6.4")]
        self.assertIn("ESTIMACIÓN", com)
        self.assertIn("Contribución no es utilidad neta", UE)
        for pend in ("contador", "abogado", "licencias de datos de Binance y Bybit", "operación"):
            self.assertIn(pend, UE[UE.index("### 6.5"):])

    def test_costos_fijos(self):
        self.assertEqual(round(FIXED, 2), 61.70)
        self.assertIn("61,70", UE)

    def test_caja_frente_a_arr(self):
        months = sum(0.92 ** t for t in range(12))                      # t = 0 … 11
        self.assertAlmostEqual(months, (1 - 0.92 ** 12) / 0.08)
        self.assertEqual(round(months, 3), 7.904)
        cash = 60 * M * months + 40 * A
        self.assertEqual(round(cash), 13074)
        arr = 100 * arpu() * 12
        self.assertEqual(round(arr), 16760)
        self.assertEqual(round((1 - cash / arr) * 100), 22)
        self.assertEqual(round(sum(0.92 ** t for t in range(1, 13)), 2), 7.27)   # la variante que empieza en t = 1
        for v in ("7,904", "13.074", "16.760", "7,27", "22 %"):
            self.assertIn(v, UE)
        self.assertNotIn("13.090", UE.split("Cómo se cuenta")[0], "la cifra corregida no debe quedar como vigente")

    def test_equilibrio(self):
        for F, sin, con in ((0, 6, 8), (100, 15, 19), (250, 29, 36), (500, 52, 65)):
            self.assertEqual(round((FIXED + F) / contribution() + 0.4999), sin, F)
            self.assertEqual(round((FIXED + F) / contribution(True) + 0.4999), con, F)

    def test_ltv(self):
        for churn, ltv, cac in ((0.05, 219, 73), (0.08, 137, 46), (0.12, 91, 30), (0.15, 73, 24), (0.20, 55, 18)):
            self.assertEqual(round(contribution() / churn), ltv)
            self.assertEqual(round(contribution() / churn / 3), cac)
            self.assertIn(f"US${ltv}", UE)

    def test_escenarios(self):
        infra = {50: 27, 100: 27, 250: 62, 500: 120, 1000: 170}
        table = {int(m.group(1).replace(".", "")): m for m in
                 re.finditer(r"^\| ([\d.]+) \| ([\d.]+) \| ([\d.]+) \| [\d.]+ \| [\d.]+ \| 35 \| [\d.]+ \| ([\d.]+) \|", UE, re.M)}
        self.assertEqual(sorted(table), [50, 100, 250, 500, 1000])
        for n, inf in infra.items():
            mrr = n * arpu()
            contrib = mrr - n * fees() - inf - 35 - n * SUPPORT
            self.assertEqual(table[n].group(2), es(round(mrr), 0))
            self.assertEqual(table[n].group(3), es(round(mrr * 12), 0))
            self.assertEqual(table[n].group(4), es(round(contrib), 0))


class Coherencia(unittest.TestCase):
    """Las cifras sustituidas solo pueden aparecer marcadas como historial."""

    def test_documentos_antiguos_marcados(self):
        for name in ("ANALISIS_COSTOS_Y_RENTABILIDAD.md", "ESTRATEGIA_PRICING.md", "MATRIZ_FUNCIONALIDADES_PLANES.md"):
            self.assertIn("UNIT_ECONOMICS.md", (DOCS / name).read_text("utf-8")[:1500], name)
        old = (DOCS / "ANALISIS_COSTOS_Y_RENTABILIDAD.md").read_text("utf-8")
        for sec in re.split(r"\n## ", old)[1:]:
            if "17,99" in sec or "Élite mensual US$29" in sec:
                self.assertIn("SUSTITUIDO", sec, sec[:60])

    def test_vigentes_sin_cifras_de_la_mezcla_anterior(self):
        for name in ("UNIT_ECONOMICS.md", "MODELO_NEGOCIO_VALIDADO.md", "PLAN_PILOTO_90_DIAS.md",
                     "DECISION_COMERCIAL_GO_NO_GO.md", "REQUISITOS_LANZAMIENTO.md", "MASTER_EXECUTION_PLAN.md"):
            txt = (DOCS / name).read_text("utf-8")
            body = txt.split("## 1. Correcciones")[-1] if name == "UNIT_ECONOMICS.md" else txt
            if name == "UNIT_ECONOMICS.md":
                body = body.split("## 2.", 1)[-1]
            for bad in ("17,99", "US$29 al mes (Élite", "Élite US$299"):
                self.assertNotIn(bad, body, f"{name}: {bad}")


if __name__ == "__main__":
    unittest.main()
