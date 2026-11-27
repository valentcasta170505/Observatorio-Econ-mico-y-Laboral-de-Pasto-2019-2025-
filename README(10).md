# 🌐 TerritorioPulse | Pasto (2019–2025)

**Observatorio económico y laboral de San Juan de Pasto, Colombia.** Aplicación interactiva en **Streamlit** para analizar la tasa de desocupación publicada en anexos de la Gran Encuesta Integrada de Hogares (GEIH) del DANE, comparar modelos temporales exploratorios y explorar archivos empresariales y bibliografía.

> **Integridad de datos.** La aplicación NO simula datos ni usa cifras empresariales sin carga explícita del usuario. Si el anexo oficial GEIH no puede descargarse, ofrece carga manual de `.xlsx`. Los promedios de cuatro trimestres son descriptivos, NO tasas anuales oficiales. La comparación de modelos no identifica causalidad.

## 📁 Estructura para GitHub (solo 3 archivos)

```text
TerritorioPulse-Pasto/
├── app.py
├── requirements.txt
└── README.md
```

**Importante:** `app.py` contiene **todos los módulos**. No debes importar `analitica`, `core`, `streamlit_app` ni `rag_documental` desde archivos externos. Esto corrige el error de `ModuleNotFoundError` de despliegues anteriores.

## 🚀 Publicación en Streamlit Community Cloud

1. Crea un repositorio de GitHub, o abre el existente.
2. Sube los **tres archivos** a la raíz, respetando mayúsculas y nombres exactos. No subas únicamente `app.py`.
3. En [Streamlit Community Cloud](https://share.streamlit.io/), selecciona el repositorio, rama (`main`) y **Main file path = `app.py`**.
4. Haz clic en **Deploy**. En una app existente usa **Manage app → Reboot** si queda la caché de una versión anterior.
5. Dentro del observatorio, haz clic en **Cargar / actualizar datos**. Si el enlace oficial no responde, descarga el anexo del DANE y súbelo con la opción de carga manual.

### Ejecución local

Recomendado: Python 3.11 o 3.12.

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

No uses `python app.py` para iniciar Streamlit. No agregues `!pip install` al archivo.

## 📊 Componentes

| Pestaña | Contenido |
|---|---|
| 📈 Tendencias | Tasas móviles originales; trimestres no solapados; comparación temporal; descriptivos; variación interanual; sensibilidad |
| 📐 Modelos | Tendencia lineal, tendencia estacional, AR(1) condicional y referencia de persistencia; MAE/RMSE y diagnósticos |
| 🏢 Empresas | Carga y validación de series de creación/cierre de empresas de Pasto; saldo neto y gráfico |
| 🗺️ Territorio | Contorno municipal mediante geoBoundaries; **no** representa desempleo intraurbano |
| 📚 RAG documental | Indexación local de PDF, DOCX, TXT, MD y recuperación TF-IDF con fuente del fragmento |
| 🛡️ Auditoría | Conteos, duplicados, nulos, rangos, SHA256 y reporte ejecutivo descriptivo |

## 🧪 Enfoques metodológicos

1. **Tendencia lineal** estimada por MCO.
2. **Tendencia + estacionalidad trimestral** con indicadores de trimestre.
3. **Modelo AR(1) condicional** para persistencia de la desocupación.

Se incluye persistencia sin estimación como línea base. La comparación reserva los **últimos cuatro trimestres no solapados disponibles** y calcula errores de predicción de un paso. Para AR(1), cada predicción utiliza la tasa real anterior. Es una **comparación predictiva exploratoria** y no equivale a confrontar tres estrategias de identificación causal. Si falta una secuencia trimestral continua, los modelos se bloquean en vez de interpolar.

## 🏛️ Fuente estadística y requisitos

- **DANE:** [GEIH históricos](https://www.dane.gov.co/index.php/estadisticas-por-tema/mercado-laboral/empleo-y-desempleo/geih-historicos). Se intenta descargar el anexo **diciembre 2025** y se exige la hoja `Total 23 ciudades A.M. Trim`, con un bloque inequívoco de **Pasto**.
- **Periodo de estudio:** 2019–2025 (2025 puede tener períodos parciales según el anexo).
- **Serie empresarial:** no incluida en el notebook fuente. Para cargarla, utiliza CSV/XLSX con columnas `anio`, `creaciones`, `cierres`; los registros deben referirse solo a **San Juan de Pasto**. Se valida estructura, no autenticidad institucional.
- **Mapa:** [geoBoundaries](https://www.geoboundaries.org/), límites ADM2. No se hacen estimaciones de Moran/LISA/SpVAR a partir de una sola ciudad.

**Limitaciones de las tasas móviles:** un trimestre móvil comparte meses con el siguiente y no constituye una observación trimestral independiente. La aplicación conserva la serie original para visualización y usa períodos `ene-mar`, `abr-jun`, `jul-sep`, `oct-dic` para comparación de modelos. **No calcula tasa anual oficial a partir de la media simple.**

## 📚 Módulo RAG y ética investigativa

Carga el artículo y sus fuentes (hasta 15 documentos de máximo 12 MB por archivo; PDF hasta 150 páginas). Se segmentan textos y se localizan hasta tres fragmentos con TF-IDF/coseno. La aplicación **no utiliza LLM**, por lo tanto es una recuperación documental *extractiva*, no una respuesta generativa; no envía documentos a proveedores de IA. Las referencias de fragmento no reemplazan citas APA 7 ni verificación en los documentos originales. Los PDF escaneados requieren OCR previo.

## ✅ Rúbrica académica

El código aporta al **producto tecnológico reproducible**; su uso en el artículo requiere conectar cada afirmación con resultados efectivamente calculados, describir limitaciones, incluir los enfoques metodológicos y completar la versión bilingüe del manuscrito. La rúbrica exige un sistema RAG sobre el corpus, incluido el artículo: debe cargarse ese corpus para que las consultas tengan evidencia. La app **no certifica automáticamente** el cumplimiento integral de la rúbrica, ni sustituye la discusión crítica y las conclusiones académicas.

## 🔎 Auditoría y reproducibilidad

- En carga del Excel: comprobación de formato y estructura esperada, bloque Pasto inequívoco, duplicados y límites de tasa.
- En fuente: URL, modo de acceso y SHA256 del archivo usado.
- En series: se conserva la periodicidad y se detectan huecos; no hay imputaciones silenciosas.
- En modelos: validación cronológica, errores fuera de muestra, Durbin-Watson y Ljung-Box.
- En empresas: se rechazan conteos negativos, faltantes, años duplicados y datos no enteros.

## ⚠️ Solución de errores frecuentes

**`ModuleNotFoundError: analitica`:** cambia el archivo principal en Streamlit Cloud a esta versión de `app.py` y elimina las versiones antiguas que importaban módulos locales.

**No se descargan datos del DANE:** utiliza la carga manual desde el portal oficial, conservando el anexo en su formato original. No desactives la validación.

**No aparecen modelos:** revisa que el archivo tenga al menos 16 trimestres no solapados consecutivos.

**RAG no devuelve texto:** incorpora documentos con texto seleccionable; escaneos de imagen requieren OCR.

---

**Proyecto académico: TerritorioPulse — Pasto.** Las fuentes estadísticas pertenecen a sus productores. Los cálculos son responsabilidad de quien implemente y valide el proyecto.
