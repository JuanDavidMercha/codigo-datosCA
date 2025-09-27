# captura_datos.py
import os
import pytz
import pandas as pd
import requests
from datetime import datetime

ZONA_HORARIA = 'America/Bogota'
CARPETA_SALIDA = os.environ.get('CARPETA_SALIDA', 'salida')  # carpeta de salida
SEPARADOR = ';'

URLS = [
    ("http://rmcab.ambientebogota.gov.co/dynamicTabulars/TabularReportTable?id=58", "Datos_Meteorologicos"),
    ("http://rmcab.ambientebogota.gov.co/dynamicTabulars/TabularReportTable?id=12", "Datos_Aire"),
]

def obtener_datos(url: str, timeout=30):
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        tab = data['TabularList']
        df_raw = pd.read_json(tab) if isinstance(tab, (str, bytes)) else pd.DataFrame(tab)

        # Validación de columnas esperadas
        for col in ['stationId', 'name', 'monitors']:
            if col not in df_raw.columns:
                print(f"[ADVERTENCIA] Falta columna {col} en la respuesta.")
                return None

        df = df_raw[['stationId', 'name', 'monitors']].copy()

        # Claves únicas de 'monitors'
        claves = set()
        for lista in df['monitors']:
            if isinstance(lista, list):
                for m in lista:
                    k = m.get('Name')
                    if k:
                        claves.add(k)

        # Expandir a columnas
        filas = []
        for _, fila in df.iterrows():
            base = {'stationId': fila['stationId'], 'name': fila['name']}
            valores = {k: float('nan') for k in claves}
            if isinstance(fila['monitors'], list):
                for m in fila['monitors']:
                    k = m.get('Name'); v = m.get('value')
                    if k is not None:
                        valores[k] = v
            base.update(valores)
            filas.append(base)

        df_exp = pd.DataFrame(filas)

        # Timestamp Bogotá
        tz = pytz.timezone(ZONA_HORARIA)
        ahora = datetime.now(tz)
        df_exp['Fecha'] = ahora.strftime('%d-%m-%Y')
        df_exp['Hora']  = ahora.strftime('%H:%M')

        # Reordenar columnas
        primero = ['Fecha', 'Hora', 'name', 'stationId']
        resto = [c for c in df_exp.columns if c not in primero]
        df_exp = df_exp[primero + resto]
        return df_exp

    except Exception as e:
        print(f"[ERROR] obtener_datos({url}): {e}")
        return None

def guardar_csv_incremental(df: pd.DataFrame, ruta: str, claves_dedup=None):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    if os.path.exists(ruta):
        try:
            previo = pd.read_csv(ruta, sep=SEPARADOR)
            combinado = pd.concat([previo, df], ignore_index=True)
            if claves_dedup:
                combinado.drop_duplicates(subset=claves_dedup, keep='last', inplace=True)
            combinado.to_csv(ruta, sep=SEPARADOR, index=False)
        except Exception as e:
            print(f"[ADVERTENCIA] Problema leyendo {ruta}: {e}. Reescribiendo.")
            df.to_csv(ruta, sep=SEPARADOR, index=False)
    else:
        df.to_csv(ruta, sep=SEPARADOR, index=False)

def main():
    tz = pytz.timezone(ZONA_HORARIA)
    hoy_iso = datetime.now(tz).strftime('%Y-%m-%d')
    archivo_aire = os.path.join(CARPETA_SALIDA, f"Datos_Aire_{hoy_iso}.csv")
    archivo_met  = os.path.join(CARPETA_SALIDA, f"Datos_Meteorologicos_{hoy_iso}.csv")

    claves_dedup = ['Fecha', 'Hora', 'stationId']

    for url, nombre in URLS:
        df = obtener_datos(url)
        if df is None or df.empty:
            print(f"[ADVERTENCIA] Sin datos para {nombre}")
            continue

        if nombre == "Datos_Aire":
            guardar_csv_incremental(df, archivo_aire, claves_dedup)
            print(f"[OK] Guardado {archivo_aire} (+{len(df)} filas)")
        else:
            guardar_csv_incremental(df, archivo_met, claves_dedup)
            print(f"[OK] Guardado {archivo_met} (+{len(df)} filas)")

if __name__ == "__main__":
    main()
