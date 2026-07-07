#!/bin/bash
# Script ejecutor de RUAF - Mismo flujo para Docker y Producción
# 1. Descargar del FTP
# 2. Cargar en base de datos

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Colores
RED=$(printf '\033[0;31m')
GREEN=$(printf '\033[0;32m')
YELLOW=$(printf '\033[1;33m')
BLUE=$(printf '\033[0;34m')
NC=$(printf '\033[0m')

log_info() {
    echo "${BLUE}ℹ${NC} $1"
}

log_success() {
    echo "${GREEN}✓${NC} $1"
}

log_error() {
    echo "${RED}✗${NC} $1"
}

log_warning() {
    echo "${YELLOW}⚠${NC} $1"
}

# -----------------------------------------------------------------
#  Menú inicial
# -----------------------------------------------------------------
mostrar_menu() {
    echo
    echo "${BLUE}╔════════════════════════════════════════════╗${NC}"
    echo "${BLUE}║   RPA - CARGUE DE TABLA RESOLUCION_RUAF   ║${NC}"
    echo "${BLUE}╚════════════════════════════════════════════╝${NC}"
    echo
    echo "  1) DOCKER      - Cargue en contenedor local (pruebas)"
    echo "  2) PRODUCCIÓN  - Cargue en BD de producción"
    echo "  3) SALIR"
    echo
}

# -----------------------------------------------------------------
#  Cargar configuración y ejecutar
# -----------------------------------------------------------------
ejecutar() {
    local AMBIENTE=$1
    local CONFIG_FILE="config.${AMBIENTE}.env"

    # Validar archivo de configuración
    if [ ! -f "$CONFIG_FILE" ]; then
        log_error "No existe $CONFIG_FILE"
        exit 1
    fi

    log_info "Cargando configuración desde $CONFIG_FILE..."
    # shellcheck disable=SC1090
    . "$CONFIG_FILE"

    # Validar que python3 existe
    if ! python3 --version &>/dev/null; then
        log_error "Python3 no está instalado."
        exit 1
    fi

    # Validar que psql existe
    if ! command -v psql &>/dev/null; then
        log_error "psql no está instalado."
        exit 1
    fi

    echo
    log_info "════════════════════════════════════════════"
    log_info "AMBIENTE: $(echo $AMBIENTE | tr '[:lower:]' '[:upper:]')"
    log_info "════════════════════════════════════════════"

    # PASO 1: Descargar del FTP
    log_info "[PASO 1/2] Descargando archivo del FTP..."

    if [ ! -f "$RUAF_FILEZILLA" ]; then
        log_error "No existe $RUAF_FILEZILLA"
        exit 1
    fi

    INPUT_FILE=$(python3 descargar_sftp.py \
        --filezilla "$RUAF_FILEZILLA" \
        --site "$RUAF_SITE_FTP" \
        --dest "$RUAF_DEST_DIR" 2>&1 | tail -1)

    if [ -z "$INPUT_FILE" ] || [ ! -f "$INPUT_FILE" ]; then
        log_error "Error al descargar el archivo del FTP."
        exit 1
    fi

    log_success "Archivo descargado: $(basename $INPUT_FILE)"

    # PASO 2: Cargar en base de datos
    log_info "[PASO 2/2] Cargando en base de datos..."

    # Preparar comando psql según el ambiente
    if [ "$RUAF_MODE" = "docker" ]; then
        log_info "Modo: Docker (contenedor: $RUAF_CONTAINER)"
    else
        log_info "Modo: Direct (host: $PGHOST:$PGPORT, BD: $PGDATABASE)"
    fi

    python3 rpa_cargue_ruaf.py \
        --mode "$RUAF_MODE" \
        --container "$RUAF_CONTAINER" \
        --host "$PGHOST" \
        --port "$PGPORT" \
        --user "$PGUSER" \
        --dbname "$PGDATABASE" \
        --password "$PGPASSWORD" \
        --input "$INPUT_FILE" \
        --log-dir "$RUAF_LOGDIR"

    if [ $? -eq 0 ]; then
        echo
        log_success "════════════════════════════════════════════"
        log_success "CARGUE COMPLETADO EXITOSAMENTE"
        log_success "════════════════════════════════════════════"
        if [ "$RUAF_MODE" = "direct" ]; then
            log_info "Pasos siguientes:"
            log_info "  → Solicitar a redes la copia de resolucion_ruaf hacia bdua_fosyga"
        fi
        echo
        return 0
    else
        log_error "Error durante el cargue."
        exit 1
    fi
}

# -----------------------------------------------------------------
#  Main
# -----------------------------------------------------------------
main() {
    while true; do
        mostrar_menu
        read -p "Opción [1-3]: " OPCION

        case $OPCION in
            1)
                ejecutar "docker"
                break
                ;;
            2)
                ejecutar "prod"
                break
                ;;
            3)
                log_info "Saliendo..."
                exit 0
                ;;
            *)
                log_error "Opción inválida."
                ;;
        esac
    done
}

main "$@"
