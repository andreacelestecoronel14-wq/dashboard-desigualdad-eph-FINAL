"""
ETL - Dinámica de ingresos y desigualdad (Gini y deciles), EPH-INDEC
=====================================================================

Compara el 4to trimestre de 2024 contra el 4to trimestre de 2025,
a nivel NACIONAL y para el aglomerado CORRIENTES (código 12).

Fuente de datos: microdatos individuales de la EPH (INDEC), bases
"usu_individual_T424" y "usu_individual_T425" (formato .xlsx o .txt).
https://www.indec.gob.ar/indec/web/Institucional-Indec-BasesDeDatos

--------------------------------------------------------------------
METODOLOGÍA (validada contra el cálculo de referencia del proyecto)
--------------------------------------------------------------------
Variable de ingreso : IPCF   (Ingreso Per Cápita Familiar)
Ponderador           : PONDIH (ponderador de ingreso per cápita
                        familiar, ajustado por no respuesta de
                        ingresos -- NO usar PONDERA para esto).
Filtro de calidad    : DECCFR entre 1 y 10 (se descartan 0 = hogar
                        sin ingreso declarado, y 12 = no responde).
                        Mismo criterio que usa INDEC para publicar
                        sus deciles de ingreso.
Recorte geográfico   : AGLOMERADO == 12 para el análisis de
                        Corrientes. Los deciles de Corrientes se
                        recalculan LOCALMENTE (no se reutiliza el
                        DECCFR nacional), porque DECCFR ubica a cada
                        hogar contra la distribución de TODO el país
                        y generaría deciles desbalanceados para un
                        aglomerado chico.

Gini (fórmula del trapecio sobre la curva de Lorenz):
    1) Ordenar personas por IPCF ascendente.
    2) x = población acumulada (ponderada por PONDIH) / población total
    3) y = ingreso acumulado (IPCF * PONDIH) / ingreso total
    4) Gini = 1 - 2 * área bajo la curva de Lorenz (regla del trapecio)

Deciles locales:
    Sobre la población ya ordenada por IPCF, se corta en 10 tramos
    de igual tamaño poblacional (ponderado), con
    decil = ceil(participación acumulada * 10), acotado a [1,10].
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------
AGLOMERADO_CORRIENTES = 12
COLS_NECESARIAS = [
    "CODUSU", "NRO_HOGAR", "COMPONENTE",
    "ANO4", "TRIMESTRE", "AGLOMERADO",
    "PONDERA", "PONDIH",
    "ITF", "IPCF", "DECCFR",
]


# ---------------------------------------------------------------
# Carga
# ---------------------------------------------------------------
def cargar_base_individual(path: str | Path) -> pd.DataFrame:
    """Lee la base individual de la EPH (.xlsx o .txt separado por ';')."""
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path, usecols=COLS_NECESARIAS)
    else:
        df = pd.read_csv(path, sep=";", usecols=COLS_NECESARIAS, encoding="latin1")
    return df


def filtrar_ingreso_valido(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica el filtro de calidad estándar de INDEC: DECCFR 1-10."""
    return df[(df["DECCFR"] >= 1) & (df["DECCFR"] <= 10)].copy()


# ---------------------------------------------------------------
# Cálculo del Gini y la curva de Lorenz
# ---------------------------------------------------------------
def curva_lorenz(df: pd.DataFrame, pond_col: str = "PONDIH",
                  ipcf_col: str = "IPCF") -> pd.DataFrame:
    """Devuelve la curva de Lorenz punto a punto (x=pob. acum., y=ingreso acum.)."""
    d = df[df[pond_col] > 0].copy()
    d = d.sort_values(ipcf_col)
    d["ingreso_total"] = d[ipcf_col] * d[pond_col]

    d["pob_acum"] = d[pond_col].cumsum()
    d["ing_acum"] = d["ingreso_total"].cumsum()

    pob_total = d["pob_acum"].iloc[-1]
    ing_total = d["ing_acum"].iloc[-1]

    d["x_pob_acum_pct"] = d["pob_acum"] / pob_total
    d["y_ing_acum_pct"] = d["ing_acum"] / ing_total
    return d


def gini(df: pd.DataFrame, pond_col: str = "PONDIH",
         ipcf_col: str = "IPCF") -> float:
    """Coeficiente de Gini a partir de IPCF y PONDIH (regla del trapecio)."""
    lorenz = curva_lorenz(df, pond_col, ipcf_col)
    x = np.concatenate([[0.0], lorenz["x_pob_acum_pct"].values])
    y = np.concatenate([[0.0], lorenz["y_ing_acum_pct"].values])
    area = np.trapezoid(y, x)
    return 1 - 2 * area


# ---------------------------------------------------------------
# Deciles locales
# ---------------------------------------------------------------
def deciles_locales(df: pd.DataFrame, pond_col: str = "PONDIH",
                     ipcf_col: str = "IPCF") -> pd.DataFrame:
    """Agrupa la población (ya filtrada a un recorte, ej. un aglomerado)
    en 10 deciles locales de igual tamaño poblacional ponderado.

    IMPORTANTE (fix): el IPCF se repite para todos los integrantes de un
    mismo hogar, y distintos hogares pueden compartir exactamente el
    mismo valor de IPCF. Antes de cortar los deciles hay que agrupar por
    valor de IPCF sumando el PONDIH correspondiente; si se corta persona
    por persona sin agrupar primero, un grupo de personas con IPCF
    idéntico puede quedar partido a la mitad entre dos deciles distintos
    de forma arbitraria (según el orden de las filas), lo que corre
    ligeramente los límites de cada decil. Agrupar por IPCF asegura que
    todas las personas con el mismo ingreso caigan siempre en el mismo
    decil, tal como hace INDEC.
    """
    d = df[df[pond_col] > 0].copy()
    agrupado = d.groupby(ipcf_col, as_index=False)[pond_col].sum()
    agrupado = agrupado.sort_values(ipcf_col)
    agrupado["ingreso_total"] = agrupado[ipcf_col] * agrupado[pond_col]

    agrupado["pob_acum"] = agrupado[pond_col].cumsum()
    pob_total = agrupado["pob_acum"].iloc[-1]
    agrupado["x_pob_acum_pct"] = agrupado["pob_acum"] / pob_total
    agrupado["decil_local"] = np.clip(
        np.ceil(agrupado["x_pob_acum_pct"] * 10).astype(int), 1, 10
    )

    resumen = (
        agrupado.groupby("decil_local")
        .agg(
            poblacion_ponderada=(pond_col, "sum"),
            ingreso_total_ponderado=("ingreso_total", "sum"),
        )
        .reset_index()
    )
    resumen["ipcf_promedio_decil"] = (
        resumen["ingreso_total_ponderado"] / resumen["poblacion_ponderada"]
    )
    resumen["pct_ingreso_total"] = (
        resumen["ingreso_total_ponderado"] / resumen["ingreso_total_ponderado"].sum()
    )
    return resumen


def brechas_decilicas(resumen_deciles: pd.DataFrame) -> dict:
    """D10/D1, D9/D1, D10/D5 y % de ingreso del decil más rico."""
    ipcf = resumen_deciles.set_index("decil_local")["ipcf_promedio_decil"]
    pct = resumen_deciles.set_index("decil_local")["pct_ingreso_total"]
    return {
        "D10_D1": ipcf[10] / ipcf[1],
        "D9_D1": ipcf[9] / ipcf[1],
        "D10_D5": ipcf[10] / ipcf[5],
        "pct_ingreso_decil10": pct[10],
    }


# ---------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------
def ejecutar_etl(path_t4_2024: str, path_t4_2025: str, out_dir: str = "data/processed"):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    periodos = {
        "T4 2024": path_t4_2024,
        "T4 2025": path_t4_2025,
    }

    resumen_gini_rows = []
    resumen_brechas_rows = []
    resumen_poblacion_rows = []

    for periodo, path in periodos.items():
        raw = cargar_base_individual(path)
        valido = filtrar_ingreso_valido(raw)

        # --- Nacional ---
        g_nac = gini(valido)
        lorenz_nac = curva_lorenz(valido)[["x_pob_acum_pct", "y_ing_acum_pct"]]
        lorenz_nac["periodo"] = periodo
        lorenz_nac["recorte"] = "Nacional"

        # --- Corrientes ---
        corrientes = valido[valido["AGLOMERADO"] == AGLOMERADO_CORRIENTES]
        g_corr = gini(corrientes)
        lorenz_corr = curva_lorenz(corrientes)[["x_pob_acum_pct", "y_ing_acum_pct"]]
        lorenz_corr["periodo"] = periodo
        lorenz_corr["recorte"] = "Corrientes"

        # Población ponderada total de Corrientes (para el KPI de estabilidad muestral)
        n_pob_corrientes = corrientes.loc[corrientes["PONDIH"] > 0, "PONDIH"].sum()
        resumen_poblacion_rows.append({"periodo": periodo, "poblacion_ponderada": n_pob_corrientes})

        deciles_corr = deciles_locales(corrientes)
        deciles_corr["periodo"] = periodo
        deciles_corr.to_csv(
            out_dir / f"deciles_corrientes_{periodo.replace(' ', '_')}.csv", index=False
        )

        brechas = brechas_decilicas(deciles_corr)
        brechas["periodo"] = periodo
        resumen_brechas_rows.append(brechas)

        resumen_gini_rows.append({"periodo": periodo, "recorte": "Nacional", "gini": g_nac})
        resumen_gini_rows.append({"periodo": periodo, "recorte": "Corrientes", "gini": g_corr})

        pd.concat([lorenz_nac, lorenz_corr]).to_csv(
            out_dir / f"lorenz_{periodo.replace(' ', '_')}.csv", index=False
        )

    pd.DataFrame(resumen_gini_rows).to_csv(out_dir / "gini_resumen.csv", index=False)
    pd.DataFrame(resumen_brechas_rows).to_csv(out_dir / "brechas_decilicas.csv", index=False)
    pd.DataFrame(resumen_poblacion_rows).to_csv(out_dir / "poblacion_corrientes.csv", index=False)

    # Deciles combinados en un solo archivo (más fácil de leer para el dashboard)
    deciles_all = pd.concat(
        [pd.read_csv(out_dir / f"deciles_corrientes_{p.replace(' ', '_')}.csv") for p in periodos]
    )
    deciles_all.to_csv(out_dir / "deciles_corrientes.csv", index=False)

    # Curvas de Lorenz combinadas
    lorenz_all = pd.concat(
        [pd.read_csv(out_dir / f"lorenz_{p.replace(' ', '_')}.csv") for p in periodos]
    )
    lorenz_all.to_csv(out_dir / "lorenz_curvas.csv", index=False)

    print("ETL finalizado. Archivos generados en", out_dir.resolve())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--t4_2024", default="data/raw/usu_individual_T424.xlsx")
    parser.add_argument("--t4_2025", default="data/raw/usu_individual_T425.xlsx")
    parser.add_argument("--out", default="data/processed")
    args = parser.parse_args()
    ejecutar_etl(args.t4_2024, args.t4_2025, args.out)
