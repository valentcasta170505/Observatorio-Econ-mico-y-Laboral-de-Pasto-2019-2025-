"""TerritorioPulse Pasto | Streamlit autocontenido. Sin módulos locales ni RAG.
Fuentes: DANE GEIH, Colab de referencia y Cámara de Comercio de Pasto.
No inventa observaciones si la fuente externa no responde.
"""
from __future__ import annotations
import io
import hashlib
import re
from urllib.parse import urljoin
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from bs4 import BeautifulSoup
from statsmodels.api import OLS, add_constant
from statsmodels.stats.stattools import durbin_watson

st.set_page_config(page_title="TerritorioPulse | Pasto", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")
DANE_URL = "https://www.dane.gov.co/files/operaciones/GEIH/anex-GEIH-dic2025.xlsx"
DANE_HIST = "https://www.dane.gov.co/index.php/estadisticas-por-tema/mercado-laboral/empleo-y-desempleo/geih-historicos"
CAMARA_PDF = "https://ccpasto.org.co/2024/wp-content/uploads/2025/12/CAMARA-DE-COMERCIO-INFORME-FINAL-DEF.pdf"
CAMARA_INFO = "https://ccpasto.org.co/2024/wp-content/uploads/2026/01/Documento-3-Estudio-Economico-CCPasto-2025.pdf"
SHEET = "Total 23 ciudades A.M. Trim"
TRIM = {"ene-mar": 1, "abr-jun": 2, "jul-sep": 3, "oct-dic": 4}
# Valores que aparecen expresamente en la salida del Colab proporcionado: medias descriptivas
# de cuatro trimestres NO SOLAPADOS. No son tasas anuales oficiales DANE.
RESPALDO_COLAB = pd.DataFrame({"año": [2019, 2021, 2022, 2023, 2024, 2025],
    "media_descriptiva": [10.881864, 13.353445, 11.963633, 10.783313, 11.022893, 9.457835]})
# Serie de SOCIEDADES (personas jurídicas) del informe económico de Cámara de Comercio
# de Pasto, sección "Número de sociedades canceladas, inscritas y renovadas 2017–2025 en Pasto".
# NO representa el total de empresas, ni la jurisdicción de 41 municipios.
SOCIEDADES = pd.DataFrame({"año": list(range(2019, 2026)),
    "inscritas": [577, 547, 641, 628, 618, 691, 644],
    "canceladas": [95, 73, 124, 108, 126, 120, 114],
    "renovadas": [2972, 2744, 2844, 3099, 3211, 3314, 3602]})
SOCIEDADES["saldo_registral"] = SOCIEDADES.inscritas - SOCIEDADES.canceladas

st.markdown("""<style>
.block-container{padding-top:1.5rem;max-width:1320px}
h1,h2,h3{letter-spacing:-.035em} .pill{display:inline-block;padding:.4rem .8rem;background:#0d4540;
color:#ccfff2;border-radius:999px;font-size:.82rem;font-weight:650}
.note{padding:1rem 1.15rem;border-radius:14px;background:#152632;border-left:4px solid #3cc9af;
margin:10px 0 20px 0;line-height:1.65}
.hero{background:linear-gradient(115deg,#083b45,#123358 65%,#222d50);padding:1.65rem;
border-radius:20px;color:white;margin-bottom:1.4rem}
.hero h1{color:white;margin:0;font-size:2.45rem}.hero p{color:#d4e7f5;margin-bottom:0}
[data-testid="stMetric"]{background:rgba(45,106,118,.11);padding:1rem;border-radius:14px}
</style>""", unsafe_allow_html=True)

def note(title, body):
    st.markdown(f'<div class="note"><strong>{title}</strong><div>{body}</div></div>', unsafe_allow_html=True)

def fmt(x, dec=2):
    return f"{x:,.{dec}f}".replace(",", "_").replace(".", ",").replace("_", ".")

def normal_period(x):
    return re.sub(r"\s*[-–—]\s*", "-", str(x).lower().strip())

def excel_ok(raw):
    if len(raw) < 10000 or not raw.startswith(b"PK"):
        return False
    try:
        return SHEET in pd.ExcelFile(io.BytesIO(raw)).sheet_names
    except Exception:
        return False

def parse_dane(raw, url):
    d = pd.read_excel(io.BytesIO(raw), sheet_name=SHEET, header=None)
    found = [i for i in range(len(d)) if str(d.iat[i,0]).strip().casefold() == "pasto"]
    if len(found) != 1:
        raise ValueError("No se identificó un único bloque de Pasto")
    i = found[0]
    if i + 7 >= len(d) or "desocupaci" not in str(d.iat[i+7,0]).lower():
        raise ValueError("La estructura de la tasa de desocupación cambió")
    years = d.iloc[i+2].ffill()
    periods = d.iloc[i+3]
    vals = d.iloc[i+7]
    rows=[]
    for j in range(1, d.shape[1]):
        y = pd.to_numeric(years.iat[j], errors="coerce")
        v = pd.to_numeric(vals.iat[j], errors="coerce")
        if pd.notna(y) and int(y) in range(2019,2026) and pd.notna(v) and 0 <= v <= 100:
            rows.append({"año":int(y),"periodo":normal_period(periods.iat[j]), "tasa":float(v),"orden_excel":j})
    if not rows:
        raise ValueError("No se encontraron observaciones válidas")
    out=pd.DataFrame(rows).sort_values(["año","orden_excel"])
    if out.duplicated(["año","periodo"]).any():
        raise ValueError("Periodos duplicados en DANE")
    return out, hashlib.sha256(raw).hexdigest(), url

@st.cache_data(ttl=60*60*24,show_spinner=False)
def load_geih():
    urls=[DANE_URL]
    sess=requests.Session()
    sess.headers["User-Agent"]="Mozilla/5.0 (compatible; academic-dashboard/1.0)"
    try:
        page=sess.get(DANE_HIST,timeout=10)
        if page.ok:
            for a in BeautifulSoup(page.text,"html.parser").select("a[href]"):
                u=urljoin(DANE_HIST,a.get("href"))
                s=(u+" "+a.get_text(" ",strip=True)).lower()
                if ("dic2025" in s or "dic-2025" in s or "diciembre 2025" in s) and "xls" in s:
                    urls.append(u)
    except requests.RequestException:
        pass
    for u in dict.fromkeys(urls):
        try:
            r=sess.get(u,headers={"Referer":DANE_HIST},timeout=23)
            if r.ok and excel_ok(r.content):
                return parse_dane(r.content,u)
        except (requests.RequestException,ValueError,KeyError,IndexError):
            continue
    return None,None,None

def trimestre(d):
    t=d[d.periodo.isin(TRIM)].copy()
    if t.empty:return t
    t["trimestre"]=t.periodo.map(TRIM)
    t["secuencia"]=t["año"]*4+t.trimestre
    t=t.sort_values("secuencia")
    t["etiqueta"]=t["año"].astype(str)+"-T"+t.trimestre.astype(str)
    return t

def anual(t):
    if t.empty:return RESPALDO_COLAB.copy()
    a=t.groupby("año").agg(media_descriptiva=("tasa","mean"),n=("tasa","size")).reset_index()
    return a[a.n==4][["año","media_descriptiva"]]

def style_chart(fig,height=455):
    fig.update_layout(template="plotly_dark",height=height,margin=dict(t=65,b=32,l=12,r=15),
                      paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(size=13),hovermode="x unified")
    return fig

def comparison(t):
    """Holdout temporal de 4 trimestres. AR1 usa valores previos observados: un paso."""
    if len(t)<20 or (t.secuencia.diff().dropna()!=1).any():return None
    y=t.tasa.to_numpy(float);n=len(t);cut=n-4;idx=np.arange(n,dtype=float)
    fitrows=[];pr=[]
    models={
      "Tendencia":np.column_stack([np.ones(n),idx]),
      "Tendencia + estacionalidad":np.column_stack([np.ones(n),idx]+[(t.trimestre.to_numpy()==q).astype(float) for q in [2,3,4]]),
      "AR(1) condicional":np.column_stack([np.ones(n),np.r_[np.nan,y[:-1]]])
    }
    for name,X in models.items():
        keep=np.isfinite(X[:cut]).all(axis=1)
        fitted=OLS(y[:cut][keep],X[:cut][keep]).fit()
        pred=fitted.predict(X[cut:])
        err=y[cut:]-pred
        fitrows.append({"Modelo":name,"MAE (pp)":np.mean(abs(err)),"RMSE (pp)":np.sqrt(np.mean(err**2)),
                        "R² entrenamiento":fitted.rsquared,"Durbin-Watson":durbin_watson(fitted.resid)})
        for j,v in enumerate(pred): pr.append({"Trimestre":t.etiqueta.iloc[cut+j],"Modelo":name,"Predicción":v,"Observado":y[cut+j]})
    baseline=y[cut-1:-1];e=y[cut:]-baseline
    fitrows.append({"Modelo":"Persistencia (base)","MAE (pp)":np.mean(abs(e)),"RMSE (pp)":np.sqrt(np.mean(e**2)),"R² entrenamiento":np.nan,"Durbin-Watson":np.nan})
    for j,v in enumerate(baseline):pr.append({"Trimestre":t.etiqueta.iloc[cut+j],"Modelo":"Persistencia (base)","Predicción":v,"Observado":y[cut+j]})
    return pd.DataFrame(fitrows),pd.DataFrame(pr)

with st.sidebar:
    st.markdown("### 📊 TerritorioPulse")
    st.caption("Pasto · 2019–2025 · Seminario de Investigación Regional 2")
    if st.button("🔄 Actualizar fuente DANE",use_container_width=True):
        load_geih.clear()
        st.rerun()
    st.markdown("**Fuentes originales**")
    st.markdown(f"[GEIH DANE]({DANE_HIST})  \n[Anexo Excel]({DANE_URL})  \n[Cámara de Comercio de Pasto]({CAMARA_PDF})")
    st.caption("Los datos empresariales publicados corresponden exclusivamente a sociedades del municipio de Pasto.")

st.markdown('''<div class="hero"><span class="pill">OBSERVATORIO ECONÓMICO TERRITORIAL</span>
<h1>TerritorioPulse · Pasto</h1><p>Dinámica empresarial y desempleo local | Evidencia 2019–2025 | Interpretación económica de cada resultado</p></div>''',unsafe_allow_html=True)

with st.spinner("Consultando la serie oficial disponible..."):
    data,sha,source=load_geih()
t=trimestre(data) if data is not None else pd.DataFrame()
a=anual(t)
full=data is not None
last=a.iloc[-1] if not a.empty else None
st_tabs=st.tabs(["🏠 Panorama","📈 Desempleo","🏢 Empresas","🧪 Modelos","🧭 Interpretación y conclusiones","📚 Fuentes y método"])

with st_tabs[0]:
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Última media descriptiva",f"{fmt(float(last.media_descriptiva))}%" if last is not None else "—",help="Media de cuatro trimestres no solapados; no equivale a tasa anual oficial")
    c2.metric("Sociedades inscritas · 2025",f"{int(SOCIEDADES.iloc[-1].inscritas):,}".replace(",","."))
    c3.metric("Sociedades canceladas · 2025",f"{int(SOCIEDADES.iloc[-1].canceladas):,}".replace(",","."))
    c4.metric("Saldo registral de sociedades",f"+{int(SOCIEDADES.iloc[-1].saldo_registral)}")
    note("Lectura integrada", "El desempleo se mide en personas y tasas; las matrículas mercantiles, en registros jurídicos. Son dimensiones complementarias, pero no equivalentes. Un saldo positivo de sociedades no demuestra por sí mismo creación neta de empleo.")
    ca,cb=st.columns([1.15,1])
    with ca:
        fig=px.line(a,x="año",y="media_descriptiva",markers=True,title="Desocupación: media descriptiva de cuatro trimestres",labels={"media_descriptiva":"Porcentaje (%)"})
        fig.update_traces(line_color="#42e0c3",line_width=3)
        st.plotly_chart(style_chart(fig),use_container_width=True)
    with cb:
        fig=px.bar(SOCIEDADES,x="año",y=["inscritas","canceladas"],barmode="group",title="Sociedades en Pasto: nuevas inscripciones y cancelaciones",labels={"value":"Sociedades","variable":"Tipo"},color_discrete_sequence=["#43ceb9","#ff937d"])
        st.plotly_chart(style_chart(fig),use_container_width=True)
    note("Conclusión del panorama",f"Entre 2019 y 2025, las medias descriptivas disponibles pasan de {fmt(float(a.iloc[0].media_descriptiva))}% a {fmt(float(a.iloc[-1].media_descriptiva))}%. En 2025 se registraron 644 sociedades inscritas y 114 canceladas (saldo +530). Esto describe dos fenómenos distintos: no se debe interpretar su simultaneidad como causalidad.")

with st_tabs[1]:
    st.subheader("Cómo evolucionó el desempleo en Pasto")
    if full and not t.empty:
        st.caption("Detalle extraído en esta sesión del anexo oficial GEIH DANE. Se distinguen trimestres no solapados y trimestres móviles.")
        fig=px.line(t,x="etiqueta",y="tasa",markers=True,title="Serie de trimestres no solapados",labels={"etiqueta":"Trimestre","tasa":"Tasa de desocupación (%)"})
        fig.update_traces(line_color="#55d9cd",line_width=3)
        st.plotly_chart(style_chart(fig),use_container_width=True)
        p=t.iloc[-1]
        first=t.iloc[0]
        note("¿Qué indica la línea?",f"Cada punto corresponde a un trimestre no solapado. La tasa observada pasó de {fmt(first.tasa)}% ({first.etiqueta}) a {fmt(p.tasa)}% ({p.etiqueta}). Las oscilaciones muestran variabilidad del mercado laboral, no necesariamente cambios estructurales permanentes.")
        pivot=t.pivot(index="año",columns="trimestre",values="tasa")
        fig=px.imshow(pivot,text_auto=".1f",aspect="auto",color_continuous_scale="Tealgrn",title="Mapa de calor: intensidad de la desocupación",labels={"color":"Tasa (%)","x":"Trimestre","y":"Año"})
        fig.update_xaxes(tickmode="array",tickvals=list(pivot.columns),ticktext=[f"T{j}" for j in pivot.columns])
        st.plotly_chart(style_chart(fig,420),use_container_width=True)
        maxrow=t.loc[t.tasa.idxmax()];minrow=t.loc[t.tasa.idxmin()]
        note("Interpretación del mapa de calor",f"El trimestre con mayor desocupación en la serie utilizada fue {maxrow.etiqueta} ({fmt(maxrow.tasa)}%) y el menor fue {minrow.etiqueta} ({fmt(minrow.tasa)}%). El color permite localizar episodios altos y bajos; no representa diferencias entre barrios o comunas.")
        change=t.copy();change["variación_pp"]=change.tasa.diff();change.loc[change.secuencia.diff()!=1,"variación_pp"]=np.nan
        fig=px.bar(change,x="etiqueta",y="variación_pp",title="Variación frente al trimestre previo (puntos porcentuales)",color="variación_pp",color_continuous_scale="RdYlGn_r")
        st.plotly_chart(style_chart(fig),use_container_width=True)
        note("¿Cómo se lee la variación?","Una barra positiva indica aumento de la tasa de desocupación, y una negativa, disminución, en puntos porcentuales. No se calcula una diferencia cuando falta un trimestre anterior consecutivo.")
    else:
        st.caption("Vista histórica precalculada a partir del Colab de referencia. La extracción trimestral completa requiere acceso al anexo GEIH del DANE.")
    fig=px.line(a,x="año",y="media_descriptiva",markers=True,title="Comparación de medias descriptivas por año",labels={"media_descriptiva":"Media de trimestres (%)"})
    fig.update_traces(line_color="#69b7ff",line_width=3)
    st.plotly_chart(style_chart(fig),use_container_width=True)
    if 2020 not in a.año.values:
        note("Por qué no aparece 2020","En el Colab compartido solo se recuperó un trimestre no solapado para 2020. Se omite la media de ese año porque no sería comparable con las medias de cuatro trimestres de los demás años. No se interpolaron valores.")
    arr=a.sort_values("año"); hi=arr.loc[arr.media_descriptiva.idxmax()];lo=arr.loc[arr.media_descriptiva.idxmin()]
    note("Conclusión de la comparación anual",f"Entre los años disponibles con cuatro trimestres, la media más elevada corresponde a {int(hi['año'])} ({fmt(hi.media_descriptiva)}%) y la menor a {int(lo['año'])} ({fmt(lo.media_descriptiva)}%). Se trata de promedios descriptivos, no de una tasa anual oficial recalculada por el DANE.")

with st_tabs[2]:
    st.subheader("Dinámica de sociedades registradas en Pasto")
    st.caption("Fuente: Cámara de Comercio de Pasto. Datos del municipio de Pasto para PERSONAS JURÍDICAS; no todas las unidades productivas.")
    sel=st.select_slider("Explora el año",options=list(SOCIEDADES.año),value=2025)
    r=SOCIEDADES[SOCIEDADES.año==sel].iloc[0]
    q1,q2,q3,q4=st.columns(4)
    q1.metric("Nuevas sociedades",int(r.inscritas));q2.metric("Cancelaciones",int(r.canceladas));q3.metric("Renovaciones",int(r.renovadas));q4.metric("Saldo registral",int(r.saldo_registral))
    fig=px.line(SOCIEDADES,x="año",y=["inscritas","canceladas","renovadas"],markers=True,
                title="Inscripción, renovación y cancelación de sociedades (2019–2025)",labels={"value":"Registros","variable":"Serie"},color_discrete_sequence=["#43ceb9","#ff957b","#7a9cff"])
    st.plotly_chart(style_chart(fig),use_container_width=True)
    note("Interpretación de las tres curvas",f"En {sel} se inscribieron {int(r.inscritas)} sociedades, se cancelaron {int(r.canceladas)} y se renovaron {int(r.renovadas)}. Las renovaciones indican continuidad registral en el año, pero no deben sumarse a las inscripciones para calcular creación de empresas.")
    fig=px.bar(SOCIEDADES,x="año",y="saldo_registral",color="saldo_registral",color_continuous_scale="Teal",title="Saldo registral anual: inscripciones menos cancelaciones",labels={"saldo_registral":"Saldo de sociedades"})
    st.plotly_chart(style_chart(fig),use_container_width=True)
    note("¿Qué significa el saldo?",f"En 2025 el saldo fue positivo en {int(SOCIEDADES.iloc[-1].saldo_registral)} sociedades. Es una diferencia de flujos registrales, no una estimación del crecimiento del empleo, del stock total ni de la supervivencia empresarial.")
    st.dataframe(SOCIEDADES.rename(columns={"año":"Año","inscritas":"Inscritas","canceladas":"Canceladas","renovadas":"Renovadas","saldo_registral":"Saldo"}),hide_index=True,use_container_width=True)
    st.download_button("⬇️ Descargar tabla empresarial",SOCIEDADES.to_csv(index=False).encode("utf-8-sig"),"sociedades_pasto_2019_2025.csv","text/csv")

with st_tabs[3]:
    st.subheader("Tres enfoques de comparación temporal")
    st.markdown("**Modelos:** tendencia lineal, tendencia con estacionalidad y AR(1) condicional; se incluye persistencia como referencia. Se reserva la parte final de la serie para una comparación fuera de muestra.")
    if full and not t.empty:
        result=comparison(t)
    else:result=None
    if result is not None:
        metrics,preds=result
        st.dataframe(metrics.round(3),hide_index=True,use_container_width=True)
        best=metrics.loc[metrics["RMSE (pp)"].idxmin()]
        f=px.line(preds,x="Trimestre",y="Predicción",color="Modelo",markers=True,title="Últimos cuatro trimestres: predicciones de un paso")
        obs=preds.drop_duplicates("Trimestre")
        f.add_trace(go.Scatter(x=obs.Trimestre,y=obs.Observado,name="DANE observado",mode="lines+markers",line=dict(color="white",width=4,dash="dash")))
        st.plotly_chart(style_chart(f),use_container_width=True)
        note("Lectura de los resultados",f"En esta evaluación el menor RMSE corresponde a «{best.Modelo}», con {fmt(best['RMSE (pp)'])} puntos porcentuales. El resultado solo describe el desempeño en cuatro trimestres de prueba; no identifica una relación causal con empresas. El AR(1) utiliza el dato real del trimestre previo (pronóstico de un paso).")
        st.download_button("⬇️ Descargar comparación",metrics.to_csv(index=False).encode("utf-8-sig"),"modelos_pasto.csv","text/csv")
    else:
        st.markdown("#### Diseño econométrico reproducible")
        st.markdown("""La comparación econométrica utiliza **trimestres no solapados consecutivos**. Para evitar estimaciones engañosas, solo se activa cuando el anexo completo de GEIH está disponible y se verifican suficientes observaciones. Las cifras anuales precalculadas no se usan para reconstruir trimestres ni para fabricar resultados econométricos.""")
        note("Interpretación académica","La tendencia lineal estima una trayectoria promedio, la tendencia estacional controla diferencias de trimestre y el AR(1) modela persistencia temporal. Ninguno, por sí solo, prueba que el registro de sociedades cause cambios en el desempleo.")

with st_tabs[4]:
    st.subheader("Conclusiones que se desprenden de los datos")
    start=float(a.iloc[0].media_descriptiva);end=float(a.iloc[-1].media_descriptiva)
    diff=end-start
    st.markdown(f"""### 1. Mercado laboral
La media descriptiva de la desocupación pasó de **{fmt(start)}% en 2019** a **{fmt(end)}% en 2025**, una diferencia de **{fmt(diff)} puntos porcentuales**. La comparación omite 2020 por falta de cuatro trimestres en la serie histórica del Colab. Este cambio no puede adjudicarse exclusivamente a la dinámica empresarial.

### 2. Formalización y rotación de sociedades
Las inscripciones de sociedades pasaron de **577 en 2019** a **644 en 2025**; las cancelaciones, de **95** a **114**. El saldo registral siguió siendo positivo. La trayectoria de renovaciones permite analizar continuidad administrativa, pero no mide directamente empleo.

### 3. Relación entre ambos fenómenos
La coexistencia de variaciones en desempleo y registros mercantiles **no confirma causalidad ni dirección del efecto**. Para estimar esa relación se requiere armonizar periodicidades, disponer de controles y precisar la población empresarial observada.

### 4. Implicaciones territoriales
Conviene complementar el análisis de sociedades con empresas de personas naturales, informalidad laboral, sectores productivos y resultados de la GEIH. No es metodológicamente correcto interpretar cifras agregadas de los 41 municipios de la jurisdicción cameral como si pertenecieran exclusivamente a Pasto.
""")
    st.markdown("### Preguntas para discusión")
    for title,body in [
        ("¿Que la desocupación baje significa que aumentaron los empleos formales?","No necesariamente. Deben examinarse ocupación, participación laboral, informalidad y calidad del empleo."),
        ("¿Una sociedad cancelada equivale a una empresa cerrada con pérdida de trabajadores?","No. Es un evento registral. Los efectos laborales requieren información adicional."),
        ("¿Los mapas pueden mostrar zonas de mayor desempleo dentro de Pasto?","No con los datos utilizados: la GEIH reportada aquí es una tasa agregada para Pasto, sin desagregación por barrios o comunas.")]:
        with st.expander(title):st.write(body)

with st_tabs[5]:
    st.subheader("Trazabilidad, fuentes y definiciones")
    st.markdown(f"""**1. DANE – GEIH:** [Anexo de diciembre de 2025]({DANE_URL}), hoja `{SHEET}`, bloque de **Pasto** y fila **Tasa de Desocupación**. El notebook de referencia recuperó 82 períodos móviles entre 2019 y 2025; las medias descriptivas de cuatro trimestres no solapados proceden de sus salidas.

**2. Cámara de Comercio de Pasto:** [Informe con serie de sociedades 2017–2025]({CAMARA_PDF}). Para esta app se transcriben únicamente las observaciones 2019–2025 de **sociedades inscritas, canceladas y renovadas en Pasto**. El [Informe Económico 2025]({CAMARA_INFO}) incluye también cifras de **toda la jurisdicción (41 municipios)**, que no se atribuyen a la ciudad.

**3. Unidad temporal:** trimestre no solapado (ene–mar, abr–jun, jul–sep, oct–dic). Los trimestres móviles superpuestos se conservan en la extracción, pero no se tratan como observaciones independientes para la modelación.

**4. Media descriptiva:** promedio simple de cuatro tasas trimestrales no solapadas; **no** es una tasa anual oficial del DANE.

**5. Saldo registral:** sociedades inscritas menos sociedades canceladas en un año. No debe confundirse con stock de firmas, generación neta de empleo ni supervivencia.
""")
    if full:
        st.caption(f"Fuente GEIH consultada: {source} · SHA256: {sha}")
        st.download_button("⬇️ Descargar serie GEIH extraída",data.to_csv(index=False).encode("utf-8-sig"),"pasto_geih_2019_2025.csv","text/csv")
    else:
        st.caption("Serie histórica descriptiva tomada de la ejecución del Colab proporcionado. No se ha podido comprobar en esta sesión la descarga completa del anexo externo.")
    st.download_button("⬇️ Descargar medias descriptivas",a.to_csv(index=False).encode("utf-8-sig"),"pasto_medias_colab.csv","text/csv")
    st.markdown("**Control metodológico:** la aplicación no inventa datos ni calcula modelos con series insuficientes. La fuente de sociedades está precargada y no requiere subir archivos. No contiene RAG ni dependencias de archivos Python locales.")

st.markdown("---")
st.caption("TerritorioPulse · Pasto 2019–2025 · Fuentes DANE GEIH y Cámara de Comercio de Pasto · Interpretación descriptiva, sin atribuciones causales")
