# subir_a_drive.py
import os, json, glob, io
import pandas as pd
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from pydrive2.auth import ServiceAccountCredentials

SEPARADOR = ';'  # Debe coincidir con captura_datos.py
DEDUP_KEYS = ['Fecha', 'Hora', 'stationId']  # Clave para evitar duplicados por hora/estación

def _ordenar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Pone primero ['Fecha','Hora','name','stationId'] y deja el resto al final."""
    base = ['Fecha', 'Hora', 'name', 'stationId']
    presentes = [c for c in base if c in df.columns]
    resto = [c for c in df.columns if c not in presentes]
    return df[presentes + resto]

def _merge_remoto_y_local(drive: GoogleDrive, folder_id: str, local_path: str):
    """Descarga (si existe) el CSV remoto con mismo nombre, concatena con local, deduplica y sube."""
    title = os.path.basename(local_path)

    # 1) Buscar archivo remoto con mismo nombre en la carpeta
    query = f"'{folder_id}' in parents and title = '{title}' and trashed = false"
    existentes = drive.ListFile({'q': query}).GetList()

    # 2) Leer local
    df_local = pd.read_csv(local_path, sep=SEPARADOR)

    if existentes:
        # 3) Descargar remoto y leerlo
        remoto = existentes[0]
        contenido = remoto.GetContentString(mimetype='text/csv')
        df_remoto = pd.read_csv(io.StringIO(contenido), sep=SEPARADOR)

        # 4) Unificar columnas (por si cambian monitores a mitad de día)
        # Concat hace la unión de columnas automáticamente
        combinado = pd.concat([df_remoto, df_local], ignore_index=True)

        # 5) Deduplicar por Fecha/Hora/Estación (conserva la última)
        combinado.drop_duplicates(subset=[k for k in DEDUP_KEYS if k in combinado.columns],
                                  keep='last', inplace=True)

        # 6) Ordenar columnas (cosmético)
        combinado = _ordenar_columnas(combinado)

        # 7) Subir al MISMO archivo (misma URL → nueva revisión)
        tmp_path = local_path + ".__merge_tmp__.csv"
        combinado.to_csv(tmp_path, sep=SEPARADOR, index=False)
        remoto.SetContentFile(tmp_path)
        remoto.Upload()
        os.remove(tmp_path)
        print(f"Actualizado en Drive (merge): {title}  -> filas: {len(combinado)}")
    else:
        # No existe: crear nuevo directamente
        nuevo = drive.CreateFile({
            'title': title,
            'parents': [{'id': folder_id}],
            'mimeType': 'text/csv'
        })
        nuevo.SetContentFile(local_path)
        nuevo.Upload()
        print(f"Creado en Drive: {title}  -> filas: {len(df_local)}")

def main():
    sa_json = os.environ["DRIVE_SA_JSON"]        # Secret: JSON completo de la Service Account
    folder_id = os.environ["ID_CARPETA_DRIVE"]   # Secret: ID de la carpeta en Drive

    # Autenticación
    sa_info = json.loads(sa_json)
    scope = ["https://www.googleapis.com/auth/drive.file"]
    gauth = GoogleAuth()
    gauth.credentials = ServiceAccountCredentials.from_json_keyfile_dict(sa_info, scope)
    drive = GoogleDrive(gauth)

    # Procesar todos los CSV generados hoy en ./salida (Aire y Meteorológicos)
    for path in glob.glob("salida/*.csv"):
        _merge_remoto_y_local(drive, folder_id, path)

if __name__ == "__main__":
    main()
