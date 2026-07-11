#!/usr/bin/env bash
# ============================================================================
#  RPA RUAF - Orquestador de una sola ejecución
#  ============================================================================
#  1) Descarga por SFTP/FTPS el último archivo RUA200AAFP del servidor del
#     ministerio (según FileZilla.xml).
#  2) Carga y transforma su contenido en la tabla 'resolucion_ruaf'.
#
#  SEGURIDAD:
#  - Las contraseñas NUNCA se especifican aquí ni en argumentos
#  - Para PostgreSQL: usar ~/.pgpass (permisos 600)
#  - Para SFTP: usar claves SSH si es posible
#
#  Uso:
#      ./run_rpa.sh                                    # Modo Docker (por defecto)
#      SKIP_SSL_VERIFY=1 ./run_rpa.sh                 # Deshabilitar validación SSL
#      ./run_ruaf.sh                                  # Menú interactivo (recomendado)
#
#  Configuración por archivo:
#      cp config.docker.env.example config.docker.env
#      . ./config.docker.env
#      ./run_rpa.sh
#
#  Documentación:
#      Ver DEVELOPMENT.md para instrucciones detalladas
# ============================================================================
set -euo pipefail

cd "$(dirname "$0")"

# --- Configuración (valores por defecto = prueba local en Docker) -----------
PYTHON="${PYTHON:-.venv/bin/python}"     # intérprete con paramiko instalado
FILEZILLA="${FILEZILLA:-FileZilla.xml}"  # configuración de conexión
SITE="${SITE:-Ministerio 2}"             # site donde publican los RUA200AAFP
DEST="${DEST:-.}"                        # carpeta de descarga local
SKIP_SSL_VERIFY="${SKIP_SSL_VERIFY:-}"   # deshabilitar verificación SSL (vacío=no, "1"=sí)

# Base de datos destino (cambiar para la infra del instructivo)
DB_MODE="${DB_MODE:-docker}"             # docker | direct
DB_CONTAINER="${DB_CONTAINER:-mi_postgres_data}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-postgres}"
DB_NAME="${DB_NAME:-bdua_fosyga}"
# NOTA: DB_PASS NO TIENE VALOR POR DEFECTO
# Las credenciales se cargan desde ~/.pgpass o PGPASSWORD en el entorno
# Ver DEVELOPMENT.md para configurar
# ----------------------------------------------------------------------------

echo "============================================================"
echo " RPA RUAF  -  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"

echo "==> [1/2] Descargando ultimo RUA200AAFP (SFTP/FTPS) ..."
# descargar_sftp.py escribe el progreso por STDERR y SOLO la ruta por STDOUT.
DOWNLOAD_OPTS=(
    --filezilla "$FILEZILLA"
    --site "$SITE"
    --dest "$DEST"
)
if [[ -n "$SKIP_SSL_VERIFY" ]]; then
    DOWNLOAD_OPTS+=(--skip-ssl-verify)
fi
ARCHIVO="$("$PYTHON" descargar_sftp.py "${DOWNLOAD_OPTS[@]}")"

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
    --dbname "$DB_NAME"

echo "==> Proceso RPA finalizado OK."
