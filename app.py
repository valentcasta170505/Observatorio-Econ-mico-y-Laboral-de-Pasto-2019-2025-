"""TerritorioPulse Pasto | observatorio laboral reproducible (GEIH-DANE).
Sin datos falsos: si la fuente no es accesible, el usuario puede cargar el Excel oficial.
"""
import io
import json
import re
import hashlib
import unicodedata
from pathlib import Path
from urllib.parse import urljoin

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import gradio as gr
from analitica import comparar
from rag_documental import indexar, consultar
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = Path(__file__).resolve().parent
CACHE = BASE / "cache"
CACHE.mkdir(exist_ok=True)
HIST = "https://www.dane.gov.co/index.php/estadisticas-por-tema/mercado-laboral/empleo-y-desempleo/geih-historicos"
DANE_URL = "https://www.dane.gov.co/files/operaciones/GEIH/anex-GEIH-dic2025.xlsx"
SHEET = "Total 23 ciudades A.M. Trim"
VALIDOS = {"ene-mar": 1, "abr-jun": 2, "jul-sep": 3, "oct-dic": 4}
DARK = "plotly_dark"


def sesion():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 TerritorioPulse/1.0"})
    s.mount("https://", HTTPAdapter(max_retries=Retry(total=2, backoff_factor=1,
             status_forcelist=[429, 500, 502, 503, 504])))
    return s


def excel_valido(data):
    if len(data) < 10000 or not data.startswith(b"PK"):
        return False
    try:
        b = pd.ExcelFile(io.BytesIO(data))
        return SHEET in b.sheet_names
    except Exception:
        return False


def urls_candidatas(s):
    urls = [DANE_URL]
    try:
        r = s.get(HIST, timeout=18)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            u = urljoin(HIST, a["href"])
            contexto = (a.get_text(" ", strip=True) + " " + u).lower()
            if ("dic2025" in contexto or "dic-2025" in contexto or "diciembre 2025" in contexto) and ("xlsx" in contexto or "anex" in contexto):
                urls.append(u)
    except requests.RequestException:
        pass
    return list(dict.fromkeys(urls))


def obtener_excel(archivo=None):
    if archivo:
        data = Path(archivo).read_bytes()
        if not excel_valido(data):
            raise ValueError(f"El archivo cargado no es un XLSX válido con la hoja '{SHEET}'.")
        return data, "Archivo GEIH aportado por usuario (verificar procedencia)", "manual"
    cache = CACHE / "GEIH_dic2025.xlsx"
    if cache.exists() and excel_valido(cache.read_bytes()):
        return cache.read_bytes(), DANE_URL, "caché validada"
    s = sesion()
    for url in urls_candidatas(s):
        try:
            r = s.get(url, timeout=32, headers={"Referer": HIST})
            if r.status_code == 200 and excel_valido(r.content):
                cache.write_bytes(r.content)
                return r.content, url, "descarga verificada"
        except requests.RequestException:
            pass
    raise RuntimeError("No fue posible acceder al anexo GEIH. Descarga el Excel oficial del DANE y súbelo aquí; no se reemplazará por datos simulados.")


def normalizar_periodo(x):
    x = str(x).lower().replace("–", "-").replace("—", "-")
    x = re.sub(r"\s*-\s*", "-", x)
    return re.sub(r"\s+", " ", x.strip())


def extraer_pasto(data, fuente):
    d = pd.read_excel(io.BytesIO(data), sheet_name=SHEET, header=None)
    indices = [i for i in range(len(d)) if str(d.iat[i, 0]).strip().casefold() == "pasto"]
    if len(indices) != 1:
        raise ValueError(f"Bloque Pasto no identificado de manera única: {len(indices)} coincidencias.")
    i = indices[0]
    if "Tasa de Desocupación" not in str(d.iat[i+7, 0]):
        raise ValueError("La estructura del anexo GEIH cambió: se requiere revisar la fila de desocupación.")
    anios = d.iloc[i+2].ffill()
    periodos = d.iloc[i+3]
    valores = d.iloc[i+7]
    filas = []
    for j in range(1, d.shape[1]):
        try:
            anio = int(anios.iat[j])
        except (ValueError, TypeError, OverflowError):
            continue
        if not 2019 <= anio <= 2025:
            continue
        valor = pd.to_numeric(valores.iat[j], errors="coerce")
        if pd.notna(valor) and 0 <= valor <= 100:
            periodo = normalizar_periodo(periodos.iat[j])
            filas.append({"anio": anio, "periodo": periodo, "td_pct": float(valor),
                          "columna_excel": j + 1, "fuente": fuente, "ciudad": "Pasto"})
    df = pd.DataFrame(filas)
    if df.empty or df.duplicated(["anio", "periodo"]).any():
        raise ValueError("No se recuperaron períodos válidos o existen duplicados en el anexo.")
    return df.sort_values(["anio", "columna_excel"]).reset_index(drop=True)


def resumen(df):
    t = df[df.periodo.isin(VALIDOS)].copy()
    t["trimestre"] = t.periodo.map(VALIDOS)
    t = t.sort_values(["anio", "trimestre"])
    t["etiqueta"] = t.anio.astype(str) + "-T" + t.trimestre.astype(str)
    a = t.groupby("anio").agg(media_descriptiva_pct=("td_pct", "mean"), n_trimestres=("td_pct", "count")).reset_index()
    a.loc[a.n_trimestres != 4, "media_descriptiva_pct"] = np.nan
    return t, a


def graficar(df, t, a, vista):
    if vista == "Serie trimestral":
        fig = px.line(t, x="etiqueta", y="td_pct", markers=True,
                      title="Pasto | tasas de desocupación trimestrales no solapadas")
        fig.update_xaxes(title="Trimestre"); fig.update_yaxes(title="Tasa de desocupación (%)")
    elif vista == "Medias descriptivas":
        fig = px.line(a.dropna(subset=["media_descriptiva_pct"]), x="anio", y="media_descriptiva_pct", markers=True,
                      title="Media simple de cuatro trimestres (NO es tasa anual oficial)")
        fig.update_yaxes(title="Media descriptiva (%)")
    elif vista == "Comparación por trimestre":
        fig = px.line(t, x="anio", y="td_pct", color="trimestre", markers=True,
                      title="Evolución de la desocupación por trimestre")
    elif vista == "Mapa de calor":
        pivot = t.pivot(index="anio", columns="trimestre", values="td_pct")
        fig = px.imshow(pivot, labels={"x": "Trimestre", "y": "Año", "color": "TD (%)"},
                        x=[f"T{x}" for x in pivot.columns], y=pivot.index.astype(str),
                        text_auto=".1f", title="Mapa de calor | desocupación trimestral")
    elif vista == "Cambios trimestrales":
        d = t.copy(); d["variacion_pp"] = d.td_pct.diff()
        # No calcular cambios si hay lagunas entre trimestres
        d["seq"] = d.anio * 4 + d.trimestre
        d.loc[d.seq.diff() != 1, "variacion_pp"] = np.nan
        fig = px.bar(d, x="etiqueta", y="variacion_pp", title="Variación respecto al trimestre anterior (puntos porcentuales)")
    elif vista == "Cambios interanuales":
        d = t.sort_values(["trimestre", "anio"]).copy()
        d["variacion_pp"] = d.groupby("trimestre").td_pct.diff()
        prev = d.groupby("trimestre").anio.shift()
        d.loc[(d.anio - prev) != 1, "variacion_pp"] = np.nan
        fig = px.bar(d, x="anio", y="variacion_pp", color="trimestre", barmode="group",
                     title="Variación interanual por trimestre (puntos porcentuales)")
    elif vista == "Distribución":
        fig = px.box(t, x="trimestre", y="td_pct", points="all", title="Distribución de TD por trimestre")
    elif vista == "Rango anual":
        d = t.groupby("anio").agg(minimo=("td_pct", "min"), maximo=("td_pct", "max")).reset_index()
        fig = go.Figure(); fig.add_trace(go.Scatter(x=d.anio, y=d.maximo, name="Máximo", mode="lines+markers"))
        fig.add_trace(go.Scatter(x=d.anio, y=d.minimo, name="Mínimo", mode="lines+markers", fill="tonexty"))
        fig.update_layout(title="Rango trimestral observado por año")
    else:
        fig = px.line(df, x="periodo", y="td_pct", color="anio", markers=True,
                      title="Trimestres móviles originales del DANE")
    fig.update_layout(template=DARK, paper_bgcolor="#0b1020", plot_bgcolor="#0b1020", font=dict(color="#e7edf7"), height=510)
    return fig


def sensib(a):
    v = a.dropna(subset=["media_descriptiva_pct"])
    return pd.DataFrame([
        {"escenario": "Todos los años con 4 trimestres", "años": len(v), "media_pct": v.media_descriptiva_pct.mean()},
        {"escenario": "Sin 2020 y 2021", "años": len(v[~v.anio.isin([2020, 2021])]),
         "media_pct": v.loc[~v.anio.isin([2020, 2021]), "media_descriptiva_pct"].mean()}
    ])


def mapa_pasto():
    path = CACHE / "pasto_limite.geojson"
    try:
        if path.exists():
            geo = json.loads(path.read_text(encoding="utf-8"))
        else:
            r = sesion().get("https://www.geoboundaries.org/api/current/gbOpen/COL/ADM2/", timeout=25)
            r.raise_for_status()
            geo_url = r.json()["gjDownloadURL"]
            r2 = sesion().get(geo_url, timeout=65); r2.raise_for_status()
            full = r2.json()
            def norm(x):
                return ''.join(c for c in unicodedata.normalize('NFD', str(x).lower()) if unicodedata.category(c) != 'Mn').strip()
            matches = [f for f in full["features"] if norm(f.get("properties", {}).get("shapeName", "")) == "pasto"]
            if len(matches) != 1:
                raise ValueError("No se encontró un único municipio Pasto en geoBoundaries.")
            geo = {"type": "FeatureCollection", "features": matches}
            path.write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")
        fig = px.choropleth_map(geojson=geo, locations=["Pasto"], featureidkey="properties.shapeName",
                                color=[1], center={"lat": 1.21, "lon": -77.28}, zoom=8,
                                map_style="carto-darkmatter", opacity=0.62)
        fig.update_layout(title="Delimitación municipal de Pasto (sin valores por comuna)", height=520,
                          template=DARK, coloraxis_showscale=False, margin=dict(l=0, r=0, t=55, b=0))
        return fig, "Mapa de límites administrativos geoBoundaries; NO es un mapa coroplético de desempleo." 
    except Exception as e:
        fig = go.Figure(); fig.add_annotation(text="No se pudo obtener la geometría municipal.", showarrow=False)
        fig.update_layout(template=DARK, height=400)
        return fig, f"Geometría no disponible: {e}"


def empresas_validar(archivo):
    if not archivo:
        return pd.DataFrame(), "Sin archivo empresarial. Los datos de creación y cierre NO están verificados en el notebook original.", None
    p = Path(archivo)
    try:
        d = pd.read_csv(p) if p.suffix.lower() == '.csv' else pd.read_excel(p)
        requerido = {"anio", "creaciones", "cierres"}
        if not requerido.issubset(d.columns):
            raise ValueError("Se requieren columnas: anio, creaciones, cierres (solo municipio de Pasto).")
        d = d[["anio", "creaciones", "cierres"]].copy()
        for col in d.columns: d[col] = pd.to_numeric(d[col], errors="raise")
        if d.isna().any().any() or d.duplicated("anio").any() or (d[["creaciones", "cierres"]] < 0).any().any():
            raise ValueError("Se encontraron faltantes, años duplicados o cantidades negativas.")
        if not np.all(np.isclose(d[["anio", "creaciones", "cierres"]].to_numpy() % 1, 0)):
            raise ValueError("Año y conteos deben ser enteros.")
        d = d.sort_values("anio"); d["saldo_neto"] = d.creaciones - d.cierres
        return d, "Archivo cargado y validado estructuralmente. Su procedencia oficial debe comprobarse antes de publicarlo.", px.bar(d, x="anio", y=["creaciones", "cierres"], barmode="group", template=DARK, title="Flujos empresariales cargados (pendientes de verificación documental)")
    except Exception as e:
        return pd.DataFrame(), f"Error de validación: {e}", None


def actualizar_excel(archivo):
    try:
        b, fuente, modo = obtener_excel(archivo)
        d = extraer_pasto(b, fuente)
        t, a = resumen(d)
        m = sensib(a)
        sha = hashlib.sha256(b).hexdigest()
        estado = (f"✅ Datos recuperados: **{len(d)} trimestres móviles**, **{len(t)} trimestres no solapados**. "
                  f"Modo: {modo}. Fuente: {fuente}. SHA256: `{sha}`. "
                  "Las medias de 4 trimestres son descriptivas, no tasas anuales oficiales del DANE.")
        return d, estado, graficar(d, t, a, "Serie trimestral"), a, m, d, ""
    except Exception as e:
        return pd.DataFrame(), f"⚠️ {e}", go.Figure(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), ""


def cambiar_vista(d, vista):
    if d is None or len(d) == 0:
        return go.Figure()
    d = pd.DataFrame(d)
    t, a = resumen(d)
    return graficar(d, t, a, vista)


def informe(d):
    if d is None or len(d) == 0:
        return "No hay datos verificados cargados."
    d = pd.DataFrame(d); t, a = resumen(d)
    years = f"{d.anio.min()}–{d.anio.max()}"
    complete = a.dropna(subset=["media_descriptiva_pct"])
    p = t.iloc[-1] if len(t) else None
    frase = f"Último trimestre no solapado disponible: **{p.etiqueta}**, desocupación **{p.td_pct:.2f}%**." if p is not None else "Sin trimestres completos."
    return (f"### Informe ejecutivo | Pasto ({years})\n\n{frase}\n\n"
            f"Hay **{len(complete)} años** con cuatro tasas trimestrales no solapadas disponibles. "
            "Los promedios presentados son **medias aritméticas descriptivas**, no tasas anuales oficiales. "
            "La sensibilidad sin 2020–2021 permite evaluar cuánto cambia la media al excluir la pandemia, "
            "pero no identifica un efecto causal.\n\n"
            "**Límites:** sin datos empresariales municipales verificables no se estima la relación entre empresas y desempleo. "
            "Sin múltiples unidades espaciales observadas no procede Moran, LISA ni SpVAR. "
            "El mapa muestra solo el contorno municipal, no diferencias por barrios ni comunas.")


with gr.Blocks(title="TerritorioPulse Pasto | Observatorio Laboral") as demo:
    gr.Markdown("# 🌐 TerritorioPulse | Pasto\n### Observatorio de dinámica laboral y empresarial · 2019–2025\nAnálisis reproducible de la **tasa de desocupación de Pasto**, basado en el anexo GEIH del DANE. Sin datos simulados ni inferencias espaciales indebidas.")
    state = gr.State(pd.DataFrame())
    with gr.Row():
        archivo = gr.File(label="Opcional: anexo Excel GEIH oficial (si falla la descarga)", file_types=[".xlsx"], type="filepath")
        cargar = gr.Button("🔄 Cargar datos oficiales", variant="primary")
    status = gr.Markdown("Inicia la descarga desde DANE o carga el Excel oficial.")
    with gr.Tabs():
        with gr.Tab("📈 Tendencias"):
            vista = gr.Dropdown(["Serie trimestral", "Medias descriptivas", "Comparación por trimestre", "Mapa de calor", "Cambios trimestrales", "Cambios interanuales", "Distribución", "Rango anual", "Móviles originales"], value="Serie trimestral", label="Visualización")
            graf = gr.Plot()
        with gr.Tab("📊 Datos y sensibilidad"):
            resumen_tab = gr.Dataframe(label="Media descriptiva (solo años con 4 trimestres)", interactive=False)
            sensibilidad_tab = gr.Dataframe(label="Sensibilidad: excluir 2020 y 2021", interactive=False)
            datos_tab = gr.Dataframe(label="Registros originales GEIH", interactive=False)
        with gr.Tab("📐 Metodologías comparadas"):
            gr.Markdown("""**Tres especificaciones temporales y referencia ingenua:** tendencia lineal, tendencia con estacionalidad, AR(1) condicional y persistencia. Comparación cronológica fuera de muestra (últimos cuatro trimestres), errores MAE/RMSE, Durbin-Watson y Ljung-Box. **No equivalen a tres estrategias de identificación causal.**""")
            comparar_btn = gr.Button("Estimar y contrastar modelos", variant="primary")
            comparar_resultados = gr.Dataframe(label="Evaluación fuera de muestra", interactive=False)
            comparar_diag = gr.Dataframe(label="Diagnósticos de residuos del ajuste", interactive=False)
            comparar_fig = gr.Plot()
            comparar_texto = gr.Markdown()
            comparar_btn.click(comparar, inputs=state, outputs=[comparar_resultados, comparar_diag, comparar_fig, comparar_texto])
        with gr.Tab("🗺️ Territorio"):
            gr.Markdown("El notebook contiene **solo tasas de Pasto**, así que no existe información para construir un coroplético por barrio ni estimar autocorrelación espacial.")
            mapa_btn = gr.Button("Mostrar límite municipal")
            mapa_out = gr.Plot()
            mapa_status = gr.Markdown()
            mapa_btn.click(mapa_pasto, outputs=[mapa_out, mapa_status])
        with gr.Tab("🏢 Dinámica empresarial (opcional)"):
            gr.Markdown("El Colab original **no verifica** series municipales de creaciones y cierres. Puedes aportar un CSV/XLSX documentado con columnas `anio`, `creaciones`, `cierres`. No se imputan valores ausentes.")
            empres_file = gr.File(label="Serie empresarial municipal documentada", file_types=[".csv", ".xlsx"], type="filepath")
            empres_btn = gr.Button("Validar y mostrar")
            empres_df = gr.Dataframe(interactive=False)
            empres_msg = gr.Markdown()
            empres_plot = gr.Plot()
            empres_btn.click(empresas_validar, inputs=empres_file, outputs=[empres_df, empres_msg, empres_plot])
        with gr.Tab("📚 RAG documental"):
            gr.Markdown("""Sube el artículo científico completo y documentos fuente (PDF, DOCX, TXT o Markdown). El módulo recupera fragmentos textuales con su documento de procedencia mediante TF-IDF. **No es un chatbot generativo**; no inventa información ni envía archivos a una API de IA. Los documentos no vienen incorporados por defecto.""")
            corpus_archivos = gr.File(label="Artículo y corpus documental", file_count="multiple", file_types=[".pdf", ".docx", ".txt", ".md"], type="filepath")
            boton_indexar = gr.Button("Construir índice documental", variant="primary")
            estado_indice = gr.Markdown()
            indice_state = gr.State([])
            pregunta_rag = gr.Textbox(label="Pregunta sobre documentos", placeholder="¿Cuáles son las limitaciones metodológicas del artículo?")
            boton_consultar = gr.Button("Recuperar evidencia")
            respuesta_rag = gr.Markdown()
            boton_indexar.click(indexar, inputs=corpus_archivos, outputs=[indice_state, estado_indice])
            boton_consultar.click(consultar, inputs=[pregunta_rag, indice_state], outputs=respuesta_rag)
        with gr.Tab("🛡️ Auditoría e informe"):
            report_btn = gr.Button("Generar informe basado en los datos cargados")
            report = gr.Markdown()
            report_btn.click(informe, inputs=state, outputs=report)
            gr.Markdown("**Criterios metodológicos:** se separan trimestres móviles y trimestres no solapados; no se calcula tasa anual oficial desde promedios simples; no se estiman modelos espaciales sin múltiples unidades; no se afirma causalidad.")
    cargar.click(actualizar_excel, inputs=archivo, outputs=[state, status, graf, resumen_tab, sensibilidad_tab, datos_tab, report])
    vista.change(cambiar_vista, inputs=[state, vista], outputs=graf)
    gr.Markdown("---\n**Fuentes:** DANE · GEIH históricos | Límites: geoBoundaries · Código académico reproducible")

if __name__ == "__main__":
    demo.launch()
