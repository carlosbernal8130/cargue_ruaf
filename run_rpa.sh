#!/usr/bin/env bash
# ============================================================================
#  RPA RUAF - Orquestador de una sola ejecucion
#  ----------------------------------------------------------------------------
#  1) Descarga por SFTP/FTPS el ultimo archivo RUA200AAFP del servidor del
#     ministerio (segun FileZilla.xml).
#  2) Carga y transforma su contenido en la tabla 'resolucion_ruaf'.
#
#  Uso:
#      ./run_rpa.sh
#
#  Todo es parametrizable por variables de entorno (ver mas abajo). Para la
#  infra del instructivo basta con exportar las variables antes de ejecutar,
#  p.ej.:
#      DB_MODE=direct DB_HOST=10.10.11.161 DB_USER=jamaica DB_NAME=interssi \
#      DB_PASS='J4r3sJ41m3T0rr35' SITE='Ministerio 2' ./run_rpa.sh
# ============================================================================
set -euo pipefail

cd "$(dirname "$0")"

# --- Configuracion (valores por defecto = prueba local en Docker) -----------
PYTHON="${PYTHON:-.venv/bin/python}"     # interprete con paramiko instalado
FILEZILLA="${FILEZILLA:-FileZilla.xml}"  # config de conexion
SITE="${SITE:-Ministerio 2}"             # site donde publican los RUA200AAFP
DEST="${DEST:-.}"                        # carpeta de descarga local

# Base de datos destino (cambiar para la infra del instructivo)
DB_MODE="${DB_MODE:-docker}"             # docker | direct
DB_CONTAINER="${DB_CONTAINER:-mi_postgres_data}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-postgres}"
DB_NAME="${DB_NAME:-bdua_fosyga}"
DB_PASS="${DB_PASS:-Majito.08}"          # OJO: en produccion usar variable/secreto
# ----------------------------------------------------------------------------

echo "============================================================"
echo " RPA RUAF  -  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"

echo "==> [1/2] Descargando ultimo RUA200AAFP (SFTP/FTPS) ..."
# descargar_sftp.py escribe el progreso por STDERR y SOLO la ruta por STDOUT.
ARCHIVO="$("$PYTHON" descargar_sftp.py \
              --filezilla "$FILEZILLA" \
              --site "$SITE" \
              --dest "$DEST")"

if [[ -z "$ARCHIVO" || ! -f "$ARCHIVO" ]]; then
    echo "ERROR: no se obtuvo un archivo valido de la descarga." >&2
    exit 1
fi
echo "==> Archivo listo: $ARCHIVO"

echo "==> [2/2] Cargando y transformando en '$DB_NAME' ..."
"$PYTHON" rpa_cargue_ruaf.py \
    --input "$ARCHIVO" \
    --mode "$DB_MODE" \
    --container "$DB_CONTAINER" \
    --host "$DB_HOST" \
    --port "$DB_PORT" \
    --user "$DB_USER" \
    --dbname "$DB_NAME" \
    --password "$DB_PASS"

echo "==> Proceso RPA finalizado OK."
