# app_control_horario_demo.py

import io
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import streamlit as st

# =============================
# 1. CONFIGURACIÓN BÁSICA
# =============================

st.set_page_config(
    page_title="Demo Control Horario",
    layout="wide",
)

st.title("🕒 Demo Control Horario – Streamlit + Excel")

st.markdown(
    """
    Esta es una **demo** no funcional contra la API real, pensada para:
    - Ver cómo quedaría la interfaz en Streamlit.
    - Generar **informes Excel** con varios niveles:
      - Diario
      - Semanal
      - Top despistes
      - Ausencias
    - Simular la configuración de avisos y correo electrónico.
    """
)

# =============================
# 2. SIMULACIÓN DE DATOS
# =============================

def generar_datos_demo(num_empleados=5, dias=7, fecha_fin=None):
    """
    Genera un DataFrame de ejemplo con fichajes diarios por empleado.
    En la versión real, aquí se llamaría a la API de Bixpe.
    """
    if fecha_fin is None:
        fecha_fin = datetime.today().date()

    fechas = [fecha_fin - timedelta(days=i) for i in range(dias)]
    empleados = [
        (101, "Juan Pérez", 8.0),
        (102, "María López", 6.0),
        (103, "Pedro García", 4.0),
        (104, "Ana Martínez", 8.0),
        (105, "Luis Sánchez", 8.0),
    ][:num_empleados]

    rows = []

    rng = np.random.default_rng(42)

    for fecha in fechas:
        for emp_id, nombre, horas_obj in empleados:
            # Simulación: algunos días no trabaja
            deberia_trabajar = rng.choice([True, True, True, False], p=[0.7, 0.2, 0.05, 0.05])

            if not deberia_trabajar:
                # Día de descanso o vacaciones: sin fichajes
                rows.append({
                    "fecha": fecha,
                    "empleado_id": emp_id,
                    "nombre": nombre,
                    "primera_entrada": None,
                    "ultima_salida": None,
                    "horas_trabajadas": 0.0,
                    "horas_objetivo": horas_obj,
                    "tiene_fichaje_abierto": False,
                    "fichaje_incorrecto": False,
                    "deberia_trabajar": False,
                })
                continue

            # Generar hora de entrada y salida "normales"
            hora_entrada = datetime.combine(fecha, datetime.min.time()) + timedelta(hours=8)  # 08:00
            # Variación ± 1h
            hora_entrada += timedelta(minutes=int(rng.normal(0, 20)))

            horas_trab = horas_obj + float(rng.normal(0, 1))  # +- 1h alrededor de objetivo
            horas_trab = max(0, horas_trab)
            hora_salida = hora_entrada + timedelta(hours=horas_trab)

            # Simular problemas de fichaje
            fichaje_abierto = rng.choice([False, False, False, True], p=[0.75, 0.15, 0.05, 0.05])
            fichaje_incorrecto = rng.choice([False, False, True], p=[0.8, 0.1, 0.1])

            if fichaje_abierto:
                hora_salida_real = None
            else:
                hora_salida_real = hora_salida

            if fichaje_incorrecto:
                # Por ejemplo, perder la hora de entrada o salida
                if rng.random() < 0.5:
                    hora_entrada_real = None
                else:
                    hora_salida_real = None
            else:
                hora_entrada_real = hora_entrada if not fichaje_abierto else hora_entrada

            # Recalcular horas_trabajadas "efectivas"
            if hora_entrada_real is not None and hora_salida_real is not None:
                horas_efectivas = (hora_salida_real - hora_entrada_real).total_seconds() / 3600
            else:
                horas_efectivas = 0.0

            rows.append({
                "fecha": fecha,
                "empleado_id": emp_id,
                "nombre": nombre,
                "primera_entrada": hora_entrada_real,
                "ultima_salida": hora_salida_real,
                "horas_trabajadas": round(horas_efectivas, 2),
                "horas_objetivo": horas_obj,
                "tiene_fichaje_abierto": fichaje_abierto,
                "fichaje_incorrecto": fichaje_incorrecto,
                "deberia_trabajar": True,
            })

    df = pd.DataFrame(rows)
    return df


# Guardamos los datos demo en sesión
if "df_fichajes" not in st.session_state:
    st.session_state["df_fichajes"] = generar_datos_demo()

df = st.session_state["df_fichajes"]

# =============================
# 3. PANEL DE CONFIGURACIÓN
# =============================

with st.sidebar:
    st.header("⚙️ Configuración")
    st.write("En la versión real, estos parámetros se guardarían en una BBDD o un fichero de config.")

    correo_alertas = st.text_input("Correo de destino de informes/avisos", "gerencia@mi-bar.com")
    horas_max_extra = st.number_input(
        "Umbral de horas extra para avisar (por encima del objetivo)",
        min_value=0.0,
        max_value=12.0,
        value=1.0,
        step=0.5,
    )
    activar_alertas_ausencia = st.checkbox("Activar alertas de ausencia de fichaje", True)
    activar_alertas_despistes = st.checkbox("Activar ranking de 'despistes'", True)

    st.markdown("---")
    st.caption("Estos valores solo son de **demo** y no se están persistiendo todavía.")

# =============================
# 4. FUNCIONES DE CÁLCULO
# =============================

def resumen_diario(df: pd.DataFrame, fecha: datetime.date) -> pd.DataFrame:
    df_day = df[df["fecha"] == fecha].copy()
    df_day["estado"] = "OK"

    df_day.loc[df_day["fichaje_incorrecto"], "estado"] = "Fichaje incorrecto"
    df_day.loc[df_day["tiene_fichaje_abierto"], "estado"] = "Fichaje abierto"
    df_day.loc[
        (df_day["horas_trabajadas"] > df_day["horas_objetivo"] + horas_max_extra),
        "estado"
    ] = "Supera horas objetivo"

    return df_day


def resumen_semanal(df: pd.DataFrame) -> pd.DataFrame:
    agg = df.groupby(["empleado_id", "nombre"], as_index=False).agg(
        horas_trabajadas_total=("horas_trabajadas", "sum"),
        horas_objetivo_total=("horas_objetivo", "sum"),
        dias_trabajados=("deberia_trabajar", lambda x: (x == True).sum()),
        dias_con_problemas=("fichaje_incorrecto", lambda x: (x == True).sum()),
        fichajes_abiertos=("tiene_fichaje_abierto", lambda x: (x == True).sum()),
    )
    agg["horas_extra"] = agg["horas_trabajadas_total"] - agg["horas_objetivo_total"]
    return agg


def top_despistes(df: pd.DataFrame) -> pd.DataFrame:
    agg = df.groupby(["empleado_id", "nombre"], as_index=False).agg(
        fichajes_incorrectos=("fichaje_incorrecto", lambda x: (x == True).sum()),
        fichajes_abiertos=("tiene_fichaje_abierto", lambda x: (x == True).sum()),
    )
    agg["score_despiste"] = agg["fichajes_incorrectos"] + agg["fichajes_abiertos"]
    agg = agg.sort_values("score_despiste", ascending=False)
    return agg


def ausencias(df: pd.DataFrame) -> pd.DataFrame:
    df_abs = df[(df["deberia_trabajar"]) & (df["horas_trabajadas"] == 0)]
    return df_abs[["fecha", "empleado_id", "nombre"]]


def sugerencia_horario(row) -> str:
    """
    Demo sencilla de sugerencia de horario:
    - Si faltan horas -> sugerir salida más tarde.
    - Si sobran horas -> sugerir salida más pronto.
    Maneja también NaT (valores nulos de pandas) en fechas.
    """
    # Si falta entrada o salida, no sugerimos nada
    if pd.isna(row["primera_entrada"]) or pd.isna(row["ultima_salida"]):
        return "No se puede sugerir (falta entrada/salida)."

    salida_actual = row["ultima_salida"]
    entrada_actual = row["primera_entrada"]

    # Por seguridad extra, por si algo raro llega aquí
    if not isinstance(salida_actual, (pd.Timestamp, datetime)) or not isinstance(entrada_actual, (pd.Timestamp, datetime)):
        return "No se puede sugerir (formato de fecha no válido)."

    diff = float(row["horas_trabajadas"]) - float(row["horas_objetivo"])

    if abs(diff) < 0.1:
        return "Horario OK."

    if diff > 0:
        # Se ha pasado de las horas: sugerir salir antes
        nueva_salida = salida_actual - timedelta(hours=diff)
        return (
            f"Se pasa {diff:.2f} h. Cambiar salida de "
            f"{salida_actual.strftime('%H:%M')} a {nueva_salida.strftime('%H:%M')}."
        )
    else:
        # Faltan horas: sugerir salir más tarde
        falta = -diff
        nueva_salida = salida_actual + timedelta(hours=falta)
        return (
            f"Faltan {falta:.2f} h. Cambiar salida de "
            f"{salida_actual.strftime('%H:%M')} a {nueva_salida.strftime('%H:%M')}."
        )


# =============================
# 5. GENERACIÓN DE EXCEL
# =============================

def generar_excel_informes(df: pd.DataFrame) -> bytes:
    """
    Crea un Excel en memoria con varias hojas:
      - Diario (último día)
      - Semanal
      - Top despistes
      - Ausencias
    Con formato en rojo para los estados problemáticos en la hoja diaria.
    """
    ultimo_dia = df["fecha"].max()
    df_diario = resumen_diario(df, ultimo_dia)
    df_semanal = resumen_semanal(df)
    df_top = top_despistes(df)
    df_ausencias = ausencias(df) if activar_alertas_ausencia else pd.DataFrame()

    # Añadimos sugerencias en diario
    df_diario["sugerencia"] = df_diario.apply(sugerencia_horario, axis=1)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter", datetime_format="yyyy-mm-dd hh:mm") as writer:
        df_diario.to_excel(writer, index=False, sheet_name="Diario")
        df_semanal.to_excel(writer, index=False, sheet_name="Semanal")
        df_top.to_excel(writer, index=False, sheet_name="Top_despistes")
        if not df_ausencias.empty:
            df_ausencias.to_excel(writer, index=False, sheet_name="Ausencias")

        # Formato condicional en la hoja Diario
        workbook  = writer.book
        sheet = writer.sheets["Diario"]

        red_format = workbook.add_format({"font_color": "red"})
        # Buscamos la columna "estado"
        estado_col_idx = df_diario.columns.get_loc("estado")
        # Aplicar formato si estado != "OK"
        sheet.conditional_format(
            1, estado_col_idx,  # desde fila 2 (índice 1), col estado
            len(df_diario), estado_col_idx,
            {
                "type": "formula",
                "criteria": f'=$${chr(ord("A") + estado_col_idx)}2<>"OK"',  # truco rápido
                "format": red_format,
            }
        )

    return output.getvalue()

# =============================
# 6. INTERFAZ PRINCIPAL
# =============================

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📅 Informe diario", "📆 Resumen semanal", "🏅 Top despistes", "🚫 Ausencias", "📊 Dashboard"]
)

ultimo_dia = df["fecha"].max()

with tab1:
    st.subheader("Informe diario (último día)")
    st.write(f"Fecha: **{ultimo_dia}**")

    df_diario = resumen_diario(df, ultimo_dia)
    df_diario["primera_entrada"] = df_diario["primera_entrada"].astype("datetime64[ns]")
    df_diario["ultima_salida"] = df_diario["ultima_salida"].astype("datetime64[ns]")

    st.dataframe(df_diario)

    st.markdown("### Generar Excel de informes")
    excel_bytes = generar_excel_informes(df)
    st.download_button(
        label="⬇️ Descargar informes en Excel",
        data=excel_bytes,
        file_name=f"informes_control_horario_{ultimo_dia}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    if st.button("📧 (Demo) Enviar Excel por correo"):
        st.success(f"Simulación: se enviaría el Excel a **{correo_alertas}** (en la versión real con SMTP).")


with tab2:
    st.subheader("Resumen semanal")
    df_semanal = resumen_semanal(df)
    st.dataframe(df_semanal)

with tab3:
    st.subheader("Top despistes")
    if activar_alertas_despistes:
        df_top = top_despistes(df)
        st.dataframe(df_top)
    else:
        st.info("El ranking de despistes está desactivado en la configuración.")

with tab4:
    st.subheader("Ausencias (días con fichaje 0 pero día laboral)")
    if activar_alertas_ausencia:
        df_abs = ausencias(df)
        if df_abs.empty:
            st.success("No hay ausencias registradas en el periodo simulado.")
        else:
            st.dataframe(df_abs)
    else:
        st.info("Las alertas de ausencia están desactivadas en la configuración.")

with tab5:
    st.subheader("Dashboard básico")

    col_filtros, col_graf = st.columns([1, 2])

    with col_filtros:
        fechas_unicas = sorted(df["fecha"].unique())
        fecha_ini = st.select_slider("Fecha inicio", options=fechas_unicas, value=fechas_unicas[0])
        fecha_fin = st.select_slider("Fecha fin", options=fechas_unicas, value=fechas_unicas[-1])
        emp_sel = st.multiselect(
            "Empleados",
            options=sorted(df["nombre"].unique()),
            default=sorted(df["nombre"].unique()),
        )

        df_dash = df[
            (df["fecha"] >= fecha_ini)
            & (df["fecha"] <= fecha_fin)
            & (df["nombre"].isin(emp_sel))
        ]

    with col_graf:
        st.write("Horas trabajadas por día")
        if not df_dash.empty:
            df_plot = df_dash.groupby("fecha", as_index=False)["horas_trabajadas"].sum()
            st.line_chart(df_plot, x="fecha", y="horas_trabajadas")
        else:
            st.info("No hay datos para los filtros seleccionados.")
