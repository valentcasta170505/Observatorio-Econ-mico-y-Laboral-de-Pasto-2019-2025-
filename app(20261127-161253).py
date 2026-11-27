"""TerritorioPulse | Pasto (2019–2025).
Aplicación autónoma para Streamlit Cloud: no requiere core.py, analitica.py ni rag_documental.py.
Fuente de desempleo: anexo oficial GEIH-DANE; nunca se generan observaciones ficticias.
Los resultados son descriptivos/predictivos y no justifican causalidad.
"""


# ===== MODELOS TEMPORALES =====

"""Comparación temporal exploratoria; jamás inferencia causal ni espacial."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import statsmodels.api as sm
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.stats.stattools import durbin_watson

METODOS = ["Tendencia lineal", "Tendencia + estacionalidad", "AR(1) condicional", "Persistencia (referencia)"]


def panel_trimestral(df):
    """Recibe tasa DANE por trimestre no solapado; no rellena ausentes."""
    claves = {"ene-mar": 1, "abr-jun": 2, "jul-sep": 3, "oct-dic": 4}
    t = df[df["periodo"].isin(claves)].copy()
    t["trimestre"] = t["periodo"].map(claves)
    t["seq"] = t["anio"].astype(int)*4 + t["trimestre"].astype(int)
    t = t.sort_values("seq").reset_index(drop=True)
    if t.seq.duplicated().any():
        raise ValueError("Periodos trimestrales duplicados")
    return t


def _matriz(t, metodo):
    idx = np.arange(len(t), dtype=float)
    if metodo == "Tendencia lineal":
        return pd.DataFrame({"const": 1., "t": idx})
    if metodo == "Tendencia + estacionalidad":
        d = pd.DataFrame({"const": 1., "t": idx})
        for q in (2, 3, 4):
            d[f"T{q}"] = (t["trimestre"].to_numpy() == q).astype(float)
        return d
    if metodo == "AR(1) condicional":
        return pd.DataFrame({"const": 1., "y_prev": t["td_pct"].shift(1)})
    raise ValueError(metodo)


def evaluar_modelos(df, horizonte=4):
    """Holdout cronológico común, predicción a un paso con valor previo observado para AR1.
    No sustituye validación prospectiva ni compara mecanismos causales.
    """
    t = panel_trimestral(df)
    if len(t) < 16:
        raise ValueError("Se requieren al menos 16 trimestres no solapados para una comparación mínima.")
    if not np.all(np.diff(t.seq.to_numpy()) == 1):
        raise ValueError("La serie tiene huecos trimestrales. No se interpolan datos para estimar modelos.")
    horizonte = max(3, min(int(horizonte), 6))
    if len(t) - horizonte < 12:
        raise ValueError("Muestra de entrenamiento insuficiente.")
    cut = len(t) - horizonte
    y = t.td_pct.astype(float).to_numpy()
    if not np.isfinite(y).all():
        raise ValueError("La serie contiene valores no finitos.")
    resultados, pronosticos, diagn = [], [], []
    for metodo in METODOS:
        if metodo == "Persistencia (referencia)":
            pred = y[cut-1:-1]
            resultados.append({"Enfoque": metodo, "MAE (pp)": np.mean(abs(y[cut:]-pred)), "RMSE (pp)": np.sqrt(np.mean((y[cut:]-pred)**2)), "R² entrenamiento": np.nan, "N entrenamiento": cut})
        else:
            X = _matriz(t, metodo)
            train = X.iloc[:cut].copy()
            idx_ok = ~train.isna().any(axis=1)
            ajuste = sm.OLS(y[:cut][idx_ok.to_numpy()], train.loc[idx_ok].astype(float)).fit()
            pred = np.asarray(ajuste.predict(X.iloc[cut:].astype(float)), dtype=float)
            residuos = np.asarray(ajuste.resid)
            diag = {"Enfoque": metodo, "Durbin-Watson": float(durbin_watson(residuos)), "N entrenamiento": int(ajuste.nobs)}
            if len(residuos) > 7:
                diag["Ljung-Box p (rezago 4)"] = float(acorr_ljungbox(residuos, lags=[4], return_df=True)["lb_pvalue"].iloc[0])
            else:
                diag["Ljung-Box p (rezago 4)"] = np.nan
            diagn.append(diag)
            resultados.append({"Enfoque": metodo, "MAE (pp)": float(np.mean(abs(y[cut:]-pred))), "RMSE (pp)": float(np.sqrt(np.mean((y[cut:]-pred)**2))), "R² entrenamiento": float(ajuste.rsquared), "N entrenamiento": int(ajuste.nobs)})
        for j, val in enumerate(pred):
            pronosticos.append({"periodo": f"{int(t.iloc[cut+j].anio)}-T{int(t.iloc[cut+j].trimestre)}", "Enfoque": metodo, "predicho": float(val), "real": float(y[cut+j])})
    return pd.DataFrame(resultados).round(4), pd.DataFrame(pronosticos), pd.DataFrame(diagn).round(4), t


def comparar(df):
    try:
        res, pred, diag, t = evaluar_modelos(pd.DataFrame(df))
        fig = go.Figure()
        reales = pred[pred.Enfoque == METODOS[0]]
        fig.add_trace(go.Scatter(x=reales.periodo, y=reales.real, mode="lines+markers", name="DANE observado", line=dict(width=4)))
        for nombre, bloque in pred.groupby("Enfoque", sort=False):
            fig.add_trace(go.Scatter(x=bloque.periodo, y=bloque.predicho, mode="lines+markers", name=nombre))
        fig.update_layout(title="Evaluación fuera de muestra · últimos 4 trimestres disponibles", template="plotly_dark", height=490, xaxis_title="Trimestre", yaxis_title="Desocupación (%)")
        alerta = ("**Comparación exploratoria y no causal.** Se reservan los últimos cuatro trimestres como prueba cronológica. "
                  "AR(1) utiliza el dato real previo para evaluar pronósticos de un paso; no representa una predicción a cuatro pasos. "
                  "MAE/RMSE en puntos porcentuales. Con muestra pequeña, los resultados son frágiles y no justifican recomendaciones causales.")
        return res, diag, fig, alerta
    except Exception as e:
        return pd.DataFrame(), pd.DataFrame(), go.Figure(), f"⚠️ Comparación no disponible: {e}"


# ===== RAG EXTRACTIVO =====

"""RAG extractivo local: recuperación TF-IDF y respuesta citada sin generación especulativa.
No se envían documentos a ningún servicio de IA.
"""
from pathlib import Path
import re
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

EXT = {'.txt', '.md', '.pdf', '.docx'}
MAX_BYTES = 12_000_000


def extraer(path):
    p = Path(path)
    if p.suffix.lower() not in EXT or p.stat().st_size > MAX_BYTES:
        raise ValueError(f"Formato/tamaño no permitido: {p.name}")
    if p.suffix.lower() in ('.txt', '.md'):
        return p.read_text(encoding='utf-8', errors='replace')
    if p.suffix.lower() == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(str(p))
        if len(reader.pages) > 150:
            raise ValueError("PDF de más de 150 páginas")
        return '\n\n'.join(f'[Página {i+1}] '+(page.extract_text() or '') for i,page in enumerate(reader.pages))
    from docx import Document
    doc = Document(str(p))
    return '\n\n'.join(p.text for p in doc.paragraphs if p.text.strip())


def fragmentar(texto, tam=850, salto=650):
    limpio = re.sub(r'\s+', ' ', texto).strip()
    if len(limpio) < 30:
        return []
    return [limpio[i:i+tam] for i in range(0, len(limpio), salto) if len(limpio[i:i+tam]) >= 35]


def indexar(paths):
    if not paths:
        return [], "No hay documentos. Sube tu artículo y las fuentes para construir el índice."
    fragmentos, problemas = [], []
    for path in paths[:15]:
        try:
            p = Path(path)
            for i, trozo in enumerate(fragmentar(extraer(p)), 1):
                fragmentos.append({'documento': p.name, 'fragmento': i, 'texto': trozo})
        except Exception as ex:
            problemas.append(f'{Path(path).name}: {ex}')
    if len(fragmentos) > 2000:
        fragmentos = fragmentos[:2000]
        problemas.append('El índice se truncó a 2.000 fragmentos.')
    status = f'Índice creado con {len(fragmentos)} fragmentos de {len(set(x["documento"] for x in fragmentos))} documento(s).'
    if problemas:
        status += ' Advertencias: ' + '; '.join(problemas)
    return fragmentos, status


def consultar(pregunta, fragmentos):
    if not fragmentos or not pregunta or len(pregunta.strip()) < 4:
        return 'Carga documentos y escribe una pregunta específica.'
    textos = [x['texto'] for x in fragmentos]
    try:
        vec = TfidfVectorizer(lowercase=True, strip_accents='unicode', ngram_range=(1,2), min_df=1, max_features=20000)
        matriz = vec.fit_transform(textos + [pregunta])
        similitud = cosine_similarity(matriz[-1], matriz[:-1]).ravel()
        tops = sorted(range(len(similitud)), key=lambda i: -similitud[i])[:3]
        tops = [i for i in tops if similitud[i] >= .055]
        if not tops:
            return 'No encontré evidencia textual suficiente en los archivos cargados. No se genera una respuesta sin fuentes.'
        bloques = ['### Fragmentos documentales más relevantes', 'Este es un **RAG extractivo**: devuelve evidencia y referencias, no inventa una respuesta generativa.']
        for i in tops:
            x = fragmentos[i]
            bloques.append(f'**[{x["documento"]} · fragmento {x["fragmento"]}]** (similitud: {similitud[i]:.2f})\n\n> {x["texto"][:680]}')
        bloques.append('**Nota:** La similitud textual no confirma la veracidad del documento; verifica los originales y las páginas antes de citar en el artículo.')
        return '\n\n'.join(bloques)
    except ValueError:
        return 'Los documentos no contienen texto indexable. Si son PDF escaneados necesitarán OCR externo.'


# ===== CARGA, AUDITORÍA Y VISUALIZACIÓN =====

"""TerritorioPulse Pasto | observatorio laboral reproducible (GEIH-DANE).
Sin datos falsos: si la fuente no es accesible, el usuario puede cargar el Excel oficial.
"""
import io
import tempfile
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
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = Path(__file__).resolve().parent
CACHE = Path(tempfile.gettempdir()) / "territoriopulse_pasto_cache"
CACHE.mkdir(parents=True, exist_ok=True)
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


def obtener_excel(archivo=None, forzar_red=False):
    if archivo:
        data = Path(archivo).read_bytes()
        if not excel_valido(data):
            raise ValueError(f"El archivo cargado no es un XLSX válido con la hoja '{SHEET}'.")
        return data, "Archivo GEIH aportado por usuario (verificar procedencia)", "manual"
    cache = CACHE / "GEIH_dic2025.xlsx"
    if not forzar_red and cache.exists() and excel_valido(cache.read_bytes()):
        meta = CACHE / "GEIH_dic2025_fuente.txt"
        fuente_cache = meta.read_text(encoding="utf-8").strip() if meta.exists() else DANE_URL
        return cache.read_bytes(), fuente_cache, "caché oficial validada"
    s = sesion()
    for url in urls_candidatas(s):
        try:
            r = s.get(url, timeout=32, headers={"Referer": HIST})
            if r.status_code == 200 and excel_valido(r.content):
                try:
                    cache.write_bytes(r.content)
                    (CACHE / "GEIH_dic2025_fuente.txt").write_text(url, encoding="utf-8")
                except OSError:
                    pass
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
            try:
                path.write_text(json.dumps(geo, ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass
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




# ===== INTERFAZ STREAMLIT =====

"""TerritorioPulse Pasto - despliegue nativo Streamlit.
Los cálculos proceden de core.py, analitica.py y rag_documental.py.
"""
import hashlib
import tempfile
from pathlib import Path
import pandas as pd
import streamlit as st

def ejecutar_app():
    st.set_page_config(page_title="TerritorioPulse | Pasto", page_icon="🌐", layout="wide")
    st.title("🌐 TerritorioPulse | Pasto")
    st.caption("Observatorio laboral y empresarial · GEIH-DANE · 2019–2025 · Fuentes verificables")
    st.info("Las tasas corresponden a Pasto. Los promedios de cuatro trimestres son descriptivos, no tasas anuales oficiales. Las estimaciones temporales no demuestran causalidad.")
    
    @st.cache_data(show_spinner=False, ttl=86400)
    def datos_oficiales(forzar_red=False):
        """Descarga/valida automáticamente el mismo anexo GEIH del Colab.
        Al pedir actualización ignora la copia del disco y consulta DANE otra vez.
        """
        b, fuente, modo = obtener_excel(forzar_red=forzar_red)
        return extraer_pasto(b, fuente), fuente, modo, hashlib.sha256(b).hexdigest()

    with st.sidebar:
        st.header("Conexión oficial · DANE")
        st.markdown("**GEIH — anexo diciembre de 2025**")
        st.caption("Hoja: Total 23 ciudades A.M. Trim · municipio: Pasto · 2019–2025")
        st.markdown(f"[Abrir anexo XLSX]({DANE_URL}) · [GEIH históricos]({HIST})")
        st.caption("Carga automáticamente al iniciar. La actualización vuelve a consultar DANE; no usa datos ficticios.")
        refrescar = st.button("🔄 Consultar DANE nuevamente", use_container_width=True)
        archivo = st.file_uploader("Respaldo: Excel oficial DANE (.xlsx)", type=["xlsx"], key="excel")
        manual = st.button("📎 Validar Excel cargado", use_container_width=True, disabled=archivo is None)
        if st.button("🧹 Limpiar caché de la aplicación", use_container_width=True):
            datos_oficiales.clear()
            st.session_state.pop("datos", None)
            st.session_state.pop("detalle", None)
            st.session_state.pop("error_dane", None)
            st.session_state.pop("autocarga_intentada", None)
            st.rerun()

    if "datos" not in st.session_state:
        st.session_state.datos = None
    if "autocarga_intentada" not in st.session_state:
        st.session_state.autocarga_intentada = False

    # Primera entrada: conexión directa a la base DANE sin clic adicional.
    cargar_automatico = not st.session_state.autocarga_intentada
    if cargar_automatico or refrescar or manual:
        st.session_state.autocarga_intentada = True
        with st.spinner("Conectando con el DANE y validando el anexo oficial de Pasto…"):
            try:
                if manual:
                    contenido = archivo.getvalue()
                    if not excel_valido(contenido):
                        raise ValueError(f"El archivo suministrado no es el anexo esperado: falta la hoja {SHEET}.")
                    fuente = f"Excel aportado por usuario: {archivo.name} (origen por verificar)"
                    modo = "carga manual validada"
                    d = extraer_pasto(contenido, fuente)
                    sha = hashlib.sha256(contenido).hexdigest()
                else:
                    if refrescar:
                        datos_oficiales.clear()
                    d, fuente, modo, sha = datos_oficiales(forzar_red=bool(refrescar))
                st.session_state.datos = d
                st.session_state.detalle = {"modo": modo, "fuente": fuente, "sha256": sha,
                                            "archivo": "anex-GEIH-dic2025.xlsx", "hoja": SHEET,
                                            "municipio": "Pasto", "periodo": "2019–2025"}
                st.session_state.error_dane = None
            except Exception as exc:
                # En una actualización fallida se conserva la última serie validada, pero se advierte.
                st.session_state.error_dane = str(exc)

    if st.session_state.get("error_dane"):
        st.warning("No fue posible consultar/validar la fuente del DANE: "
                   + st.session_state.error_dane
                   + ". Puedes cargar el anexo XLSX desde la barra lateral. No se sustituyen datos por estimaciones simuladas.")
    if st.session_state.datos is not None:
        detalle = st.session_state.detalle
        st.success(f"Fuente conectada: {detalle['modo']} · {len(st.session_state.datos)} periodos móviles de Pasto")
        with st.expander("Trazabilidad y control de la fuente", expanded=False):
            st.json(detalle)
            st.caption("SHA256 identifica exactamente el archivo procesado. La cobertura publicada se limita al período del Colab original.")

    d=st.session_state.datos
    p1,p2,p3,p4,p5,p6=st.tabs(['📈 Tendencias','📐 Modelos','🏢 Empresas','🗺️ Territorio','📚 RAG documental','🛡️ Auditoría'])
    with p1:
        if d is None:
            st.warning('No se pudo cargar la base oficial automáticamente. Puedes volver a consultar DANE o cargar el Excel original desde la barra lateral.')
        else:
            t,a=resumen(d)
            c1,c2,c3=st.columns(3)
            c1.metric('Observaciones móviles',len(d))
            c2.metric('Trimestres sin solapamiento',len(t))
            c3.metric('Última tasa disponible',f"{t.iloc[-1].td_pct:.2f}%" if len(t) else 'N/D')
            vistas=['Serie trimestral','Medias descriptivas','Comparación por trimestre','Mapa de calor','Cambios trimestrales','Cambios interanuales','Distribución','Rango anual','Móviles originales']
            vista=st.selectbox('Visualización',vistas)
            st.plotly_chart(graficar(d,t,a,vista),use_container_width=True)
            st.subheader('Medias descriptivas por año')
            st.dataframe(a,use_container_width=True)
            st.subheader('Sensibilidad al excluir 2020–2021')
            st.dataframe(sensib(a),use_container_width=True)
            st.download_button('Descargar datos validados (CSV)',d.to_csv(index=False).encode('utf-8-sig'),'pasto_geih_validado.csv','text/csv')
    with p2:
        st.markdown('### Tres especificaciones comparadas y referencia ingenua')
        st.caption('Tendencia lineal, tendencia estacional, AR(1) y persistencia. Evaluación cronológica fuera de muestra; análisis exploratorio, no identificación causal.')
        if d is None: st.warning('Carga primero datos GEIH en la barra lateral.')
        elif st.button('Estimar modelos',key='modelos'):
            r,diag,fig,nota=comparar(d)
            st.markdown(nota)
            if not r.empty: st.dataframe(r,use_container_width=True)
            if not diag.empty: st.dataframe(diag,use_container_width=True)
            st.plotly_chart(fig,use_container_width=True)
    with p3:
        st.markdown('### Creación y cierre de empresas')
        st.info('No se publican series empresariales inventadas. Carga CSV/XLSX con columnas anio, creaciones, cierres, relativas únicamente a Pasto. Verifica la fuente antes de publicar resultados.')
        e=st.file_uploader('Cargar serie empresarial documentada',type=['csv','xlsx'],key='empresas')
        if e is not None:
            with tempfile.NamedTemporaryFile(suffix='.'+e.name.rsplit('.',1)[-1],delete=False) as f:
                f.write(e.getvalue()); tmp=Path(f.name)
            try:
                tabla,mensaje,fig=empresas_validar(str(tmp))
                st.markdown(mensaje)
                if not tabla.empty:
                    st.dataframe(tabla,use_container_width=True)
                    st.plotly_chart(fig,use_container_width=True)
                    st.download_button('Exportar serie empresarial validada',tabla.to_csv(index=False).encode('utf-8-sig'),'empresas_pasto.csv','text/csv')
            finally: tmp.unlink(missing_ok=True)
    with p4:
        st.caption('Sólo delimitación del municipio; no representa diferencias comunales ni autocorrelación espacial.')
        if st.button('Cargar geometría municipal'):
            with st.spinner('Consultando geometría…'):
                fig,mensaje=mapa_pasto()
            st.markdown(mensaje)
            st.plotly_chart(fig,use_container_width=True)
    with p5:
        st.markdown('### Recuperación documental con citas a fragmentos')
        st.caption('RAG extractivo TF-IDF. No inventa respuestas ni transmite archivos a servicios de IA. Sube el artículo y fuentes para indexarlos.')
        uploads=st.file_uploader('Documentos PDF, DOCX, TXT y MD',type=['pdf','docx','txt','md'],accept_multiple_files=True,key='rag')
        if 'fragmentos' not in st.session_state: st.session_state.fragmentos=[]
        if st.button('Indexar documentos'):
            with tempfile.TemporaryDirectory() as folder:
                rutas=[]
                for j,f in enumerate(uploads[:15] if uploads else []):
                    p=Path(folder)/f'{j}_{Path(f.name).name}'
                    p.write_bytes(f.getvalue()); rutas.append(str(p))
                frag,mensaje=indexar(rutas)
            st.session_state.fragmentos=frag
            st.info(mensaje)
        pregunta=st.text_input('Pregunta sobre los documentos')
        if st.button('Consultar evidencia'):
            st.markdown(consultar(pregunta,st.session_state.fragmentos))
    with p6:
        st.subheader('Informe ejecutivo')
        st.markdown(informe(d) if d is not None else 'Primero carga la fuente GEIH.')
        if d is not None:
            st.write({'registros':len(d),'años':sorted(d.anio.unique().tolist()),'duplicados':int(d.duplicated(['anio','periodo']).sum()),'valores_nulos':int(d.td_pct.isna().sum()),'minimo':float(d.td_pct.min()),'maximo':float(d.td_pct.max())})
        st.caption('Para la rúbrica: los modelos temporales son comparaciones exploratorias, no tres diseños de identificación; la relación empresa-desempleo requiere incorporar y verificar una serie empresarial.')
        st.subheader('Ficha de fuente y metodología')
        st.markdown(f'**Fuente primaria:** [DANE, GEIH — anexo diciembre de 2025]({DANE_URL}). '
                    f'**Hoja:** `{SHEET}`. **Unidad:** Pasto. **Horizonte:** 2019–2025. '
                    'Se conserva la serie de trimestres móviles y se extraen cuatro ventanas no solapadas por año para las estimaciones. '
                    'La capa municipal geoBoundaries se emplea únicamente para localización.')

if __name__ == "__main__":
    ejecutar_app()
