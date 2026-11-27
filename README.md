# TerritorioPulse | Pasto 2019–2025

Observatorio interactivo de dinámica laboral de **San Juan de Pasto**, adaptado del cuaderno de Google Colab **“Dinámica empresarial y desempleo local: creación y destrucción de empresas formales en Pasto (2019–2025)”**.

## Alcance real de los datos

El cuaderno original obtiene la **tasa de desocupación de Pasto** de los anexos históricos de la **GEIH del DANE**, en particular de la hoja `Total 23 ciudades A.M. Trim` del anexo de diciembre de 2025. El notebook recuperó **82 períodos móviles**, 2019–2025; los períodos de 2025 pueden ser incompletos. La aplicación vuelve a recuperar y validar el archivo al ejecutarse: no trae valores de desempleo incrustados.

El notebook original **no contiene una serie municipal verificada de aperturas y cierres de empresas**. Por eso el módulo empresarial es opcional y exige datos externos documentados. Tampoco hay observaciones submunicipales para construir mapas de desempleo por comuna.

## Funcionalidades

- Descarga automática del anexo GEIH; validación del archivo Excel y de la estructura del bloque Pasto.
- Carga manual alternativa del Excel oficial si el servidor DANE impide la descarga.
- Gráficos de series trimestrales, tendencias, medias descriptivas, calor, cambios trimestrales e interanuales, rangos y distribuciones.
- Comparación de sensibilidad al excluir 2020 y 2021 (descriptiva, no causal).
- Mapa del **límite administrativo municipal** de Pasto mediante geoBoundaries (no simula datos por barrios).
- Panel empresarial opcional: permite cargar un CSV/XLSX con `anio,creaciones,cierres`, comprueba la estructura y presenta flujos, **sin certificar automáticamente la procedencia**.
- Informe ejecutivo generado a partir de datos realmente cargados y sección de auditoría metodológica.

## Instalación

Requiere Python 3.10 o superior.

```bash
pip install -r requirements.txt
python app.py
```

La aplicación no descarga datos durante la instalación; usa el botón **Cargar datos oficiales**. Si falla la descarga, abra la página de GEIH históricos del DANE, descargue el anexo pertinente y cárguelo manualmente.

## Estructura

```text
TerritorioPulse_Pasto/
├── app.py
├── requirements.txt
├── README.md
└── notebook_original.ipynb
```

La carpeta `cache/` se crea automáticamente y no debe subirse como datos oficiales sin revisión.

## Fuentes

- [DANE – GEIH históricos](https://www.dane.gov.co/index.php/estadisticas-por-tema/mercado-laboral/empleo-y-desempleo/geih-historicos)
- [Anexo GEIH diciembre 2025 (URL usada por el notebook)](https://www.dane.gov.co/files/operaciones/GEIH/anex-GEIH-dic2025.xlsx)
- [geoBoundaries](https://www.geoboundaries.org/)

## Advertencias metodológicas

1. Los **trimestres móviles** no son 12 trimestres independientes por año.
2. Para resúmenes descriptivos se usan **Ene–Mar, Abr–Jun, Jul–Sep, Oct–Dic**. Si faltan datos de un año, no se calcula una media de cuatro trimestres.
3. La media simple de cuatro tasas trimestrales **no equivale a la tasa anual oficial**, que requiere denominadores y ponderaciones apropiados.
4. Se analiza un solo municipio. **Moran, LISA y SpVAR no son estimables de forma justificada con esta estructura**; se necesitaría un panel espacial de varias unidades con datos comparables.
5. El análisis de sensibilidad a la pandemia **no es una identificación causal**.
6. Una serie empresarial cargada por el usuario no se debe presentar como oficial sin trazabilidad documental.

## Publicación en GitHub y Hugging Face Spaces

Suba `app.py`, `requirements.txt` y `README.md` a la raíz. Para Hugging Face Spaces, seleccione **Gradio** como SDK y `app.py` como archivo principal. El acceso a sitios web externos puede verse limitado por las políticas del proveedor de alojamiento; la carga manual es una alternativa reproducible.

## Licencia y atribución

Añada una licencia de software de su elección si desea permitir reutilización. Cite a DANE para los indicadores GEIH y a geoBoundaries para la geometría; estos datos mantienen sus condiciones de uso originales.

## Mejoras para la rúbrica de Seminario de Investigación Regional 2 (27/11/2026)

### Contraste de enfoques y resultados

La pestaña **Metodologías comparadas** calcula **tres especificaciones exploratorias** con una misma prueba cronológica (últimos cuatro trimestres disponibles): (1) tendencia lineal; (2) tendencia lineal con indicadores estacionales; (3) modelo autorregresivo AR(1) condicional, además de una referencia de persistencia. Reporta MAE/RMSE fuera de muestra, R² de entrenamiento y diagnósticos Durbin-Watson y Ljung-Box. La estimación utiliza únicamente tasas trimestrales no solapadas válidas y rechaza secuencias con periodos faltantes. El AR(1) evalúa pronósticos de **un paso utilizando el valor previo observado**, por lo que sus errores no son comparables con un pronóstico dinámico real a varios pasos. Estos modelos **no identifican relaciones causales ni sustituyen una comparación sustantiva de tres enfoques de identificación** exigida en el artículo.

### RAG documental verificable

La pestaña **RAG documental** permite cargar un artículo en español o inglés y un corpus de hasta 15 archivos TXT/MD/PDF/DOCX (12 MB y 150 páginas por PDF). Extrae fragmentos, recupera los tres más relevantes por similitud TF-IDF y muestra nombre del documento y ordinal de fragmento. Es **recuperación aumentada extractiva**, no generación de respuestas mediante modelo de lenguaje. No se incluyen fuentes externas que no hayan sido cargadas; los PDF escaneados sin texto pueden exigir OCR y las citas del artículo deben revisarse en el original. El índice permanece en la sesión de Gradio; no se guarda como base documental permanente.

### Auditoría y criterios para entrega

| Exigencia de la rúbrica | Estado y evidencia |
|---|---|
| Código reproducible y comentado | `app.py`, `analitica.py`, `rag_documental.py`, `requirements.txt`, pruebas en `tests/` |
| Rastreabilidad oficial | Descarga/validación GEIH, URL y SHA256 en el panel |
| RAG sobre corpus y artículo | Funcional al cargar documentos; **el artículo no está integrado por defecto** |
| Tres enfoques metodológicos confrontados | Tres modelos temporales exploratorios + referente ingenuo; **no sustituye tres enfoques de identificación causal ni la justificación metodológica del manuscrito** |
| Resultados coherentes | Datos de prueba cronológicos y diagnósticos en panel, a recalcular con GEIH real |
| Artículo bilingüe, APA 7 y formato | **Pendiente en el documento**, no verificable desde esta aplicación |
| Datos empresariales 2019–2025 | Requiere CSV/XLSX trazable de Cámara de Comercio u otra fuente oficial pertinente |

### Ejecución y pruebas

```bash
python -m pip install -r requirements.txt
python -m pip install pytest
python -m pytest -q
python app.py
```

**Nota de despliegue:** en Hugging Face Spaces, es recomendable montar el repositorio como Gradio Space. La descarga del DANE requiere conexión exterior; si el sitio impide la solicitud, use el Excel oficial cargado manualmente. No se necesita una llave API para RAG.

**Límite interpretativo:** la visualización territorial es solo un límite municipal y no deben publicarse estimaciones ESDA, Moran, LISA o SpVAR en Pasto sin observaciones comparables de varias unidades espaciales.
