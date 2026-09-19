# Dinámica de ingresos y desigualdad — EPH-INDEC

Dashboard interactivo que compara el **Coeficiente de Gini** y la **distribución
por deciles del Ingreso Per Cápita Familiar (IPCF)** entre el **4to Trimestre
2024** y el **4to Trimestre 2025**, a nivel **Nacional** y para el
**aglomerado Corrientes**, usando microdatos públicos de la Encuesta
Permanente de Hogares (EPH) del INDEC.

🔗 Fuente de datos: [INDEC - Bases de microdatos EPH](https://www.indec.gob.ar/indec/web/Institucional-Indec-BasesDeDatos)

## Resultados verificados

Antes de construir el pipeline, se recalculó el Gini de forma **independiente**
directamente desde los microdatos crudos (`usu_individual_T424.xlsx` /
`usu_individual_T425.xlsx`), replicando la metodología documentada. Los
valores coinciden exactamente con los de las planillas de trabajo originales:

| Recorte     | T4 2024   | T4 2025   | Variación |
|-------------|-----------|-----------|-----------|
| Nacional    | 0.428276  | 0.424758  | -0.0035   |
| Corrientes  | 0.330571  | 0.335805  | +0.0052   |

Los deciles locales de Corrientes también reproducen los valores
originales **de forma exacta**, decil por decil (ver "Historial de
correcciones" más abajo).

## Historial de correcciones

**Bug corregido (deciles locales):** la primera versión de `deciles_locales()`
en `src/etl.py` cortaba los 10 deciles persona por persona, sin agrupar
antes por valor de IPCF. Como el IPCF se repite para todos los
integrantes de un hogar y distintos hogares pueden compartir el mismo
valor exacto de IPCF, un grupo de personas con IPCF idéntico podía
quedar partido de forma arbitraria entre dos deciles vecinos, corriendo
levemente el límite de cada corte (esto afectaba solo a los deciles
intermedios 2-9; el decil 10 y el Gini ya daban exactos). La corrección
agrupa por valor de IPCF sumando `PONDIH` **antes** de acumular
población y cortar los deciles — el mismo criterio documentado en la
metodología original del proyecto. Con el fix, los 10 deciles y las
brechas D10/D1, D9/D1 y D10/D5 reproducen los valores de
`Gini_Deciles_Corrientes.xlsx` de forma exacta.

**Dato corregido (población ponderada de Corrientes):** un resumen de
avance del proyecto citaba una población ponderada de 392.042 (T4 2024)
y 395.306 (T4 2025), con una variación de +0,83%. Al sumar `PONDIH`
sobre el universo real filtrado (`DECCFR` 1-10, `AGLOMERADO` = 12) el
valor correcto es **392.641 → 395.388, variación de +0,70%**. El
pipeline ahora calcula y expone este dato en `data/processed/poblacion_corrientes.csv`,
y el dashboard lo muestra como caption bajo los KPIs de Corrientes.

## Metodología

- **Variable de ingreso:** `IPCF` (Ingreso Per Cápita Familiar) — variable
  estándar del INDEC para desigualdad entre personas, ya que compara
  bienestar entre hogares de distinto tamaño.
- **Ponderador:** `PONDIH` (ponderador de ingreso per cápita familiar,
  ajustado por no respuesta de ingresos). **No** se usa `PONDERA` (ponderador
  demográfico general), que sobrestimaría la muestra al ignorar la no
  respuesta específica de ingresos.
- **Filtro de calidad:** se conservan únicamente los casos con
  `DECCFR` entre 1 y 10 (se descartan 0 = sin ingreso declarado y
  12 = no responde), el mismo criterio que usa INDEC en sus publicaciones
  oficiales de deciles.
- **Recorte geográfico:** `AGLOMERADO == 12` para Corrientes.
- **Gini:** regla del trapecio sobre la curva de Lorenz (ingreso y
  población ordenados y acumulados, ponderados por `PONDIH`).
- **Deciles locales de Corrientes:** se recalculan sobre la distribución
  interna del aglomerado (no se reutiliza el `DECCFR` nacional), porque
  clasificar a Corrientes contra la distribución de todo el país generaría
  deciles desbalanceados para un aglomerado de tamaño intermedio.

> Nota: el cuaderno de investigación (NotebookLM) de referencia compartido
> por el usuario es privado y no pudo consultarse automáticamente en este
> proceso; toda la metodología aquí documentada fue validada directamente
> contra los archivos de trabajo (`Gini_EPH_2024_2025.xlsx`,
> `Gini_Deciles_Corrientes.xlsx`) y los microdatos crudos provistos.

## Estructura del repositorio

```
├── app.py                    # Dashboard Streamlit
├── src/etl.py                 # Pipeline ETL (microdatos crudos -> CSV procesados)
├── data/raw/                  # Bases EPH crudas (NO se versionan, ver abajo)
├── data/processed/            # CSV livianos ya calculados (sí se versionan)
├── requirements.txt
├── .streamlit/config.toml
└── README.md
```

## Cómo correrlo localmente

```bash
git clone <tu-repo>
cd <tu-repo>
pip install -r requirements.txt

# 1) (Opcional, ya viene con data/processed/ generado)
#    Descargar las bases individuales EPH del trimestre deseado desde INDEC
#    y colocarlas en data/raw/, luego:
python src/etl.py --t4_2024 data/raw/usu_individual_T424.xlsx \
                   --t4_2025 data/raw/usu_individual_T425.xlsx

# 2) Levantar el dashboard
streamlit run app.py
```

## Despliegue

### Streamlit Community Cloud (recomendado)
Streamlit necesita un proceso Python persistente, por eso **Streamlit
Community Cloud** (streamlit.io/cloud) es el destino natural:
1. Subí este repo a GitHub (asegurate de incluir `data/processed/*.csv`,
   que son livianos; `data/raw/` queda excluido por `.gitignore`).
2. En share.streamlit.io → "New app" → elegí el repo, la rama y `app.py`
   como archivo principal.
3. Listo — la URL pública queda lista para compartir con el público.

### Vercel
Vercel está pensado para funciones serverless / apps Next.js, **no** para
procesos persistentes como Streamlit, así que un `streamlit run` no
funciona ahí de forma nativa. Alternativas si el despliegue en Vercel es
un requisito estricto:
- Desplegar este mismo dashboard en **Streamlit Community Cloud** (gratis)
  y opcionalmente embeberlo dentro de una landing en Vercel con un
  `<iframe>`.
- Reescribir la capa de visualización como una app estática (Next.js +
  Plotly.js) que lea los CSV de `data/processed/` — posible pero implica
  otro proyecto (JS) aparte de este script Python.
- Usar un servicio con contenedores persistentes (Render, Railway,
  Fly.io) si se insiste en no usar Streamlit Cloud.

## Próximos pasos sugeridos
- Sumar más aglomerados para comparar Corrientes contra el resto del NEA.
- Incorporar series trimestrales completas (no solo T4) para ver la
  dinámica dentro del año.
- Agregar intervalos de confianza al Gini vía bootstrap sobre PONDIH.
