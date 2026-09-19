"""
Dashboard - Dinámica de ingresos y desigualdad (EPH-INDEC)
============================================================
4to Trimestre 2024 vs 4to Trimestre 2025 | Nacional y Aglomerado Corrientes

Ejecutar localmente:
    streamlit run app.py

Requiere que `src/etl.py` ya haya generado los CSV en data/processed/
(ver README.md para correr el ETL con las bases crudas de la EPH).
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DATA_DIR = Path(__file__).parent / "data" / "processed"

st.set_page_config(
    page_title="Desigualdad de ingresos | EPH-INDEC",
    page_icon="📊",
    layout="wide",
)

# ---------------------------------------------------------------
# Carga de datos (cacheada)
# ---------------------------------------------------------------
@st.cache_data
def cargar_datos():
    gini = pd.read_csv(DATA_DIR / "gini_resumen.csv")
    lorenz = pd.read_csv(DATA_DIR / "lorenz_curvas.csv")
    deciles = pd.read_csv(DATA_DIR / "deciles_corrientes.csv")
    brechas = pd.read_csv(DATA_DIR / "brechas_decilicas.csv")
    poblacion = pd.read_csv(DATA_DIR / "poblacion_corrientes.csv")
    return gini, lorenz, deciles, brechas, poblacion


try:
    gini_df, lorenz_df, deciles_df, brechas_df, poblacion_df = cargar_datos()
except FileNotFoundError:
    st.error(
        "No se encontraron los datos procesados. Corré primero el ETL:\n\n"
        "`python src/etl.py --t4_2024 data/raw/usu_individual_T424.xlsx "
        "--t4_2025 data/raw/usu_individual_T425.xlsx`"
    )
    st.stop()

# ---------------------------------------------------------------
# Encabezado
# ---------------------------------------------------------------
st.title("📊 Dinámica de ingresos y desigualdad")
st.caption(
    "Fuente: Encuesta Permanente de Hogares (EPH) - INDEC · "
    "4to Trimestre 2024 vs 4to Trimestre 2025 · "
    "Variable: IPCF (Ingreso Per Cápita Familiar) · Ponderador: PONDIH"
)

recorte = st.sidebar.radio("Recorte geográfico", ["Corrientes", "Nacional"], index=0)
st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Metodología**\n\n"
    "- Filtro de calidad: DECCFR entre 1 y 10 (se excluyen hogares sin "
    "ingreso declarado o sin respuesta).\n"
    "- Gini calculado con la regla del trapecio sobre la curva de Lorenz.\n"
    "- Deciles de Corrientes recalculados **localmente** (no se reutiliza "
    "el decil nacional DECCFR), para no distorsionar la distribución "
    "interna del aglomerado."
)

# ---------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------
g24 = gini_df.query("periodo == 'T4 2024' and recorte == @recorte")["gini"].iloc[0]
g25 = gini_df.query("periodo == 'T4 2025' and recorte == @recorte")["gini"].iloc[0]
delta_gini = g25 - g24

col1, col2, col3, col4 = st.columns(4)
col1.metric("Gini T4 2024", f"{g24:.4f}")
col2.metric("Gini T4 2025", f"{g25:.4f}", delta=f"{delta_gini:+.4f}",
            delta_color="inverse")

if recorte == "Corrientes":
    b24 = brechas_df.query("periodo == 'T4 2024'").iloc[0]
    b25 = brechas_df.query("periodo == 'T4 2025'").iloc[0]
    col3.metric("Brecha D10/D1 (2025)", f"{b25['D10_D1']:.2f}x",
                delta=f"{b25['D10_D1'] - b24['D10_D1']:+.2f}", delta_color="inverse")
    col4.metric("% ingreso del decil 10 (2025)", f"{b25['pct_ingreso_decil10']*100:.1f}%",
                delta=f"{(b25['pct_ingreso_decil10'] - b24['pct_ingreso_decil10'])*100:+.1f} p.p.",
                delta_color="inverse")

    p24 = poblacion_df.query("periodo == 'T4 2024'")["poblacion_ponderada"].iloc[0]
    p25 = poblacion_df.query("periodo == 'T4 2025'")["poblacion_ponderada"].iloc[0]
    var_pob = (p25 - p24) / p24 * 100
    st.caption(
        f"Población ponderada de Corrientes: {p24:,.0f} hab. (T4 2024) → "
        f"{p25:,.0f} hab. (T4 2025), variación de {var_pob:+.2f}% "
        "(muestra estable entre ambos trimestres)."
    )

st.markdown(
    "**Cómo leerlo:** un Gini más alto (más cerca de 1) indica mayor "
    "desigualdad; más cerca de 0 indica mayor igualdad en la distribución "
    "del ingreso per cápita familiar."
)

st.divider()

# ---------------------------------------------------------------
# Curva de Lorenz
# ---------------------------------------------------------------
st.subheader("Curva de Lorenz")
st.caption(
    "Compara la distribución real del ingreso (curva) contra la "
    "igualdad perfecta (diagonal). Cuanto más se aleja la curva de la "
    "diagonal, mayor es la desigualdad."
)

l_sub = lorenz_df.query("recorte == @recorte")
fig_lorenz = go.Figure()
fig_lorenz.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines",
                                 name="Igualdad perfecta", line=dict(dash="dash", color="gray")))
for periodo, color in [("T4 2024", "#1f77b4"), ("T4 2025", "#d62728")]:
    d = l_sub[l_sub["periodo"] == periodo]
    fig_lorenz.add_trace(go.Scatter(
        x=d["x_pob_acum_pct"], y=d["y_ing_acum_pct"], mode="lines",
        name=periodo, line=dict(color=color, width=3),
    ))
fig_lorenz.update_layout(
    xaxis_title="% de población acumulada",
    yaxis_title="% de ingreso acumulado",
    xaxis_tickformat=".0%", yaxis_tickformat=".0%",
    height=480, legend=dict(orientation="h", y=1.08),
)
st.plotly_chart(fig_lorenz, use_container_width=True)

st.divider()

# ---------------------------------------------------------------
# Deciles (solo tiene sentido con detalle de Corrientes; para
# Nacional se muestra un aviso ya que no se calcularon deciles
# locales nacionales en este ETL de referencia)
# ---------------------------------------------------------------
st.subheader("Distribución del ingreso por decil (aglomerado Corrientes)")
st.caption(
    "% del ingreso total que concentra cada decil de hogares, de menor "
    "(decil 1) a mayor (decil 10) ingreso per cápita familiar."
)

fig_dec = go.Figure()
for periodo, color in [("T4 2024", "#1f77b4"), ("T4 2025", "#d62728")]:
    d = deciles_df[deciles_df["periodo"] == periodo].sort_values("decil_local")
    fig_dec.add_trace(go.Bar(
        x=d["decil_local"], y=d["pct_ingreso_total"] * 100,
        name=periodo, marker_color=color,
    ))
fig_dec.update_layout(
    barmode="group",
    xaxis_title="Decil (1 = más pobre, 10 = más rico)",
    yaxis_title="% del ingreso total",
    xaxis=dict(tickmode="linear"),
    height=450, legend=dict(orientation="h", y=1.08),
)
st.plotly_chart(fig_dec, use_container_width=True)

col_a, col_b = st.columns(2)
with col_a:
    st.markdown("**Brechas entre deciles**")
    st.dataframe(
        brechas_df.set_index("periodo")[["D10_D1", "D9_D1", "D10_D5", "pct_ingreso_decil10"]]
        .rename(columns={
            "D10_D1": "D10 / D1", "D9_D1": "D9 / D1", "D10_D5": "D10 / D5",
            "pct_ingreso_decil10": "% ingreso decil 10",
        }),
        use_container_width=True,
    )
with col_b:
    st.markdown("**IPCF promedio por decil**")
    tabla = deciles_df.pivot(index="decil_local", columns="periodo", values="ipcf_promedio_decil")
    st.dataframe(tabla.style.format("${:,.0f}"), use_container_width=True)

st.divider()

# ---------------------------------------------------------------
# Hallazgos
# ---------------------------------------------------------------
st.subheader("Resumen de hallazgos")
tendencia = "aumentó" if delta_gini > 0 else "disminuyó"

if recorte == "Corrientes":
    d10d1_24 = brechas_df.query("periodo == 'T4 2024'")["D10_D1"].iloc[0]
    d10d1_25 = brechas_df.query("periodo == 'T4 2025'")["D10_D1"].iloc[0]
    linea_brecha = (
        f"- En Corrientes, la brecha D10/D1 pasó de **{d10d1_24:.2f}x** "
        f"a **{d10d1_25:.2f}x** entre ambos trimestres."
    )
else:
    linea_brecha = (
        "- Cambiá el recorte a **Corrientes** en la barra lateral para ver "
        "el detalle por deciles."
    )

st.markdown(f"""
- El coeficiente de Gini de **{recorte}** {tendencia} de **{g24:.4f}** (T4 2024)
  a **{g25:.4f}** (T4 2025), una variación de **{delta_gini:+.4f}** puntos.
{linea_brecha}
- Estos resultados están construidos exclusivamente con microdatos
  públicos de la EPH-INDEC y son reproducibles corriendo `src/etl.py`
  sobre las bases oficiales del trimestre correspondiente.
""")

st.caption("Fuente: INDEC, Encuesta Permanente de Hogares (EPH). Elaboración propia.")
