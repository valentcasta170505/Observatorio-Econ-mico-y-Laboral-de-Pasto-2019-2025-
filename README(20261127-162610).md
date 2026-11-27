# TerritorioPulse · Pasto (2019–2025)

Observatorio económico y laboral en **Streamlit**. Explora tasas de desocupación de Pasto (GEIH-DANE) y la creación, renovación y cancelación de **sociedades registradas en el municipio de Pasto** (Cámara de Comercio de Pasto). Contiene interpretaciones de cada figura, discusión metodológica, modelos temporales cuando hay observaciones suficientes y conclusiones automáticas. No tiene módulo RAG ni solicita subir bases empresariales.

## Los únicos tres archivos

- `app.py`: interfaz, datos empresariales con fuente documental, descarga GEIH, análisis, gráficos y modelos.
- `requirements.txt`: dependencias Python.
- `README.md`: reproducibilidad, fuentes e instalación.

## Ejecutar localmente

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud

Subir los tres archivos a la **raíz** del repositorio GitHub. En https://share.streamlit.io elegir el repositorio, rama `main` y **Main file path: `app.py`**. Si hay una app anterior, sobrescribir los tres archivos y reiniciar. No copiar código viejo que use `from analitica import comparar`.

## Fuentes

### 1. Mercado laboral: DANE / GEIH
- Archivo: https://www.dane.gov.co/files/operaciones/GEIH/anex-GEIH-dic2025.xlsx
- Página de históricos: https://www.dane.gov.co/index.php/estadisticas-por-tema/mercado-laboral/empleo-y-desempleo/geih-historicos
- Hoja: `Total 23 ciudades A.M. Trim`.
- Extracción estricta: bloque `Pasto`, indicador `Tasa de Desocupación`, años 2019–2025, validaciones de formato y rango.
- Fuente de respaldo **no simulada**: seis medias descriptivas de cuatro trimestres publicadas en la salida del notebook Colab proporcionado (2019, 2021, 2022, 2023, 2024, 2025). En 2020 había solo un trimestre no solapado recuperado; por ello se omite la media anual descriptiva. Esta media simple **no equivale a tasa anual oficial**.
- El aplicativo intenta la descarga oficial al abrirse y puede actualizarla desde la barra lateral. Si el sitio DANE está temporalmente inaccesible, la app conserva gráficos descriptivos respaldados por el notebook y deshabilita cálculos econométricos que necesiten datos trimestrales completos. No inventa valores.

### 2. Registro de sociedades: Cámara de Comercio de Pasto
- Informe: https://ccpasto.org.co/2024/wp-content/uploads/2025/12/CAMARA-DE-COMERCIO-INFORME-FINAL-DEF.pdf
- Serie 2019–2025, sección **Número de sociedades canceladas, inscritas y renovadas 2017–2025 en Pasto**.
- **Población:** sociedades/personas jurídicas en **Pasto**, no todas las empresas, no personas naturales, no los 41 municipios de jurisdicción cameral.
- Datos del informe incorporados directamente en el código, no requieren archivos adicionales. Saldo registral = inscritas − canceladas; no equivale a empleo neto ni a stock empresarial.
- Informe para comparación de alcance: https://ccpasto.org.co/2024/wp-content/uploads/2026/01/Documento-3-Estudio-Economico-CCPasto-2025.pdf (jurisdicción de 41 municipios, NO usar como dato exclusivamente municipal).

## Enfoques analíticos

Con datos trimestrales DANE completos y consecutivos, la sección de modelos compara **tendencia lineal**, **tendencia y estacionalidad** y **AR(1) condicional** con una persistencia simple de referencia. Usa holdout cronológico de cuatro trimestres y MAE/RMSE en puntos porcentuales. AR(1) utiliza el valor del trimestre previo observado: es pronóstico a un paso, no predicción genuina de cuatro pasos. Estas especificaciones no prueban causalidad entre firmas y desempleo.

## Integridad metodológica

- No se generan cifras ficticias ni se rellenan trimestres ausentes.
- Las medias descriptivas no se presentan como tasas oficiales anuales.
- Las sociedades registradas no equivalen a la totalidad de establecimientos formales ni a empleos creados.
- Sin información espacial desagregada no se aplica Moran, LISA ni SpVAR a barrios o comunas.
- La disponibilidad del servidor DANE puede afectar la extracción en vivo; los datos empresariales verificables y las cifras históricas del Colab quedan visibles sin cargas manuales.
- La eliminación del RAG se hizo a petición del usuario, aunque la rúbrica del curso mencione este producto tecnológico.

## Licencia y atribución

Código académico de ejemplo. Se deben citar las fuentes originales al reutilizar tablas o figuras. La app no está afiliada a DANE ni a la Cámara de Comercio.
