#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RPA - Cargue automatico de la tabla resolucion_ruaf
====================================================

Automatiza el procedimiento del "Instructivo Actualizacion tabla
resolucion_ruaf", pero OPTIMIZADO: se elimina la tabla intermedia
'unificadas' y se carga directamente en 'resolucion_ruaf', aplicando las
transformaciones al vuelo (streaming) mientras se descomprime el archivo.

Flujo:

    unzip -p archivo.zip  ->  transformador Python  ->  COPY resolucion_ruaf FROM STDIN

    1. (Re)crea la tabla resolucion_ruaf + indice.
    2. Descomprime y lee el archivo en streaming (sin volcarlo a disco).
    3. Por cada linea (ancho fijo) parsea los 4 campos por posicion, AUTODETECTA
       el formato de fecha (AAAA-MM-DD / AAAAMMDD) y normaliza:
          - tipo_documento     = posiciones 1-2
          - nro_documento      = posiciones 3-18  (TRIM; si es numerico se
                                 normaliza quitando ceros a la izquierda, igual
                                 que el ::BIGINT del instructivo; si es
                                 alfanumerico -extranjeros/pasaportes- se
                                 conserva tal cual)
          - cod_administradora = posiciones 19-24 (TRIM, sin espacios)
          - fecha              = posiciones 25-.. -> se entrega SIEMPRE AAAA-MM-DD
    4. Carga los campos ya transformados con COPY (rapido).
    5. Valida: conteo BD == lineas leidas == filas COPY, fechas de longitud 10,
       cod_administradora sin espacios; deja todo en consola y en un log.

Alcance: carga + transformacion + validacion (igual que el instructivo).
La copia final interssi -> bdua_fosyga de produccion la ejecuta redes via ticket.

--------------------------------------------------------------------------------
Portabilidad (Docker de prueba  ->  infra real del instructivo)
--------------------------------------------------------------------------------
  * --mode docker  (por defecto)  ejecuta psql DENTRO del contenedor.
  * --mode direct  ejecuta el psql local contra un servidor remoto, p.ej.:

        python3 rpa_cargue_ruaf.py --mode direct \\
            --host 10.10.11.161 --user jamaica --dbname interssi \\
            --input /home/pardo.contreras/Videos/RUA200AAFP...dat

    La contraseña se obtiene desde ~/.pgpass (ver DEVELOPMENT.md).

Ejemplo de uso en la prueba local (Docker):

    python3 rpa_cargue_ruaf.py \\
        --input RUA200AAFP20260619NI000900474727.zip \\
        --mode docker --container mi_postgres_data \\
        --user postgres --dbname bdua_fosyga
"""

import argparse
import logging
import os
import subprocess
import sys
import time
from datetime import datetime


# ----------------------------------------------------------------------------- #
#  Layout de ancho fijo (posiciones 1-based del instructivo -> slices 0-based)
# ----------------------------------------------------------------------------- #
TIPO_DOC   = slice(0, 2)     # posiciones 1-2
NRO_DOC    = slice(2, 18)    # posiciones 3-18  (16)
COD_ADMIN  = slice(18, 24)   # posiciones 19-24 (6)
FECHA_INI  = 24              # la fecha empieza en la posicion 25 (indice 24)
DASH_IDX   = 28              # posicion 29: si es '-' el formato trae guiones

# (Re)creacion de la tabla destino. Se elimina 'unificadas' por si quedo de
# ejecuciones previas con el enfoque anterior.
DDL = """
DROP TABLE IF EXISTS unificadas;

DROP TABLE IF EXISTS resolucion_ruaf;
CREATE TABLE resolucion_ruaf (
    tipo_documento     character varying(3),
    nro_documento      character varying(17),
    cod_administradora character varying(6),
    fecha              character varying(10)
);
CREATE INDEX idx_ruaf ON resolucion_ruaf USING btree (tipo_documento, nro_documento);
"""


# ----------------------------------------------------------------------------- #
#  Utilidades de ejecucion de psql
# ----------------------------------------------------------------------------- #
class RpaError(Exception):
    """Error controlado del RPA (aborta con mensaje claro)."""


def build_env(cfg):
    # Solo hereda variables de entorno.
    # PGPASSWORD debe venir de:
    #   1. ~/.pgpass (recomendado, permisos 600)
    #   2. Variable de entorno PGPASSWORD exportada previamente
    # NUNCA se pasa contraseña en argumentos de línea de comandos.
    env = os.environ.copy()
    return env


def psql_cmd(cfg, extra=None):
    """Comando base de psql segun el modo (docker | direct).

    Las credenciales se obtienen desde:
      - ~/.pgpass (recomendado, permisos 600)
      - Variable de entorno PGPASSWORD (si está disponible)

    NUNCA se pasan credenciales como argumentos de línea de comandos.
    """
    extra = extra or []
    common = ["-U", cfg.user, "-d", cfg.dbname, "-v", "ON_ERROR_STOP=1"]
    if cfg.mode == "docker":
        base = ["docker", "exec", "-i", cfg.container, "psql"] + common
    else:
        base = ["psql", "-h", cfg.host, "-p", str(cfg.port)] + common
    return base + extra


def run_sql(cfg, sql):
    """Ejecuta SQL; devuelve stdout. Lanza RpaError si falla."""
    proc = subprocess.run(
        psql_cmd(cfg, ["-c", sql]), input="", stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env=build_env(cfg), text=True,
    )
    if proc.returncode != 0:
        raise RpaError("psql fallo (rc=%d):\n%s" % (proc.returncode, proc.stderr.strip()))
    return proc.stdout.strip()


def scalar_sql(cfg, sql):
    """Ejecuta SQL y devuelve un unico valor escalar."""
    proc = subprocess.run(
        psql_cmd(cfg, ["-t", "-A", "-c", sql]), input="", stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env=build_env(cfg), text=True,
    )
    if proc.returncode != 0:
        raise RpaError("psql fallo (rc=%d):\n%s" % (proc.returncode, proc.stderr.strip()))
    return proc.stdout.strip()


def decompressor_cmd(path):
    """Comando que emite el contenido del archivo por stdout (streaming)."""
    lower = path.lower()
    if lower.endswith(".zip"):
        return ["unzip", "-p", path]
    if lower.endswith(".gz"):
        return ["gzip", "-dc", path]
    return ["cat", path]  # .txt / .dat sin comprimir


# ----------------------------------------------------------------------------- #
#  Transformacion en streaming + carga
# ----------------------------------------------------------------------------- #
BATCH = 100000  # lineas por escritura al pipe de psql


def _transformar(instream, outstream, log):
    """
    Lee lineas de ancho fijo (bytes) de 'instream', las parsea/normaliza y
    escribe filas TAB-delimitadas en 'outstream' (stdin de COPY).
    Devuelve (lineas_procesadas, script_fecha).
    """
    n = 0
    script = None          # 1 = AAAA-MM-DD, 2 = AAAAMMDD
    buf = []
    append = buf.append

    for raw in instream:
        line = raw.rstrip(b"\r\n")
        if not line:
            continue

        # Autodeteccion del formato de fecha en la primera linea util
        if script is None:
            script = 1 if line[DASH_IDX:DASH_IDX + 1] == b"-" else 2
            log.info("Formato de fecha detectado: %s -> SCRIPT %d",
                     "AAAA-MM-DD" if script == 1 else "AAAAMMDD", script)

        tipo = line[TIPO_DOC].strip()
        doc = line[NRO_DOC].strip()
        adm = line[COD_ADMIN].strip()

        # Normalizacion del documento (fiel al ::BIGINT del instructivo para
        # numericos; conserva alfanumericos de extranjeros/pasaportes).
        if doc.isdigit():
            doc = doc.lstrip(b"0") or b"0"

        # Fecha -> siempre AAAA-MM-DD
        if script == 2:
            d = line[FECHA_INI:FECHA_INI + 8]        # AAAAMMDD
            fecha = d[0:4] + b"-" + d[4:6] + b"-" + d[6:8]
        else:
            fecha = line[FECHA_INI:FECHA_INI + 10].strip()  # ya viene AAAA-MM-DD

        append(tipo + b"\t" + doc + b"\t" + adm + b"\t" + fecha + b"\n")
        n += 1
        if len(buf) >= BATCH:
            outstream.write(b"".join(buf))
            buf.clear()

    if buf:
        outstream.write(b"".join(buf))
    return n, script


def transformar_y_cargar(cfg, path, log):
    """
    Pipeline:  descompresor -> transformador Python -> COPY resolucion_ruaf.
    Devuelve (filas_copy, lineas_leidas, script_fecha).
    """
    dcmd = decompressor_cmd(path)
    ccmd = psql_cmd(cfg, ["-c",
                          "COPY resolucion_ruaf "
                          "(tipo_documento, nro_documento, cod_administradora, fecha) "
                          "FROM STDIN"])
    log.info("Descompresor : %s", " ".join(dcmd))
    log.info("Carga        : %s", " ".join(ccmd))

    decomp = subprocess.Popen(dcmd, stdout=subprocess.PIPE, bufsize=1024 * 1024)
    psql = subprocess.Popen(
        ccmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env=build_env(cfg),
    )

    lineas = 0
    script = None
    copy_err = None
    try:
        lineas, script = _transformar(decomp.stdout, psql.stdin, log)
    except BrokenPipeError:
        copy_err = "psql cerro la conexion durante la carga (BrokenPipe)."
    finally:
        try:
            psql.stdin.close()
        except BrokenPipeError:
            pass
        decomp.stdout.close()

    out, err = psql.communicate()
    decomp.wait()

    if decomp.returncode not in (0, None):
        raise RpaError("El descompresor fallo (rc=%d) sobre %s" % (decomp.returncode, path))
    if psql.returncode != 0 or copy_err:
        detail = (err or b"").decode(errors="replace").strip()
        raise RpaError("COPY fallo (rc=%s): %s\n%s" % (psql.returncode, copy_err or "", detail))

    # psql imprime "COPY <n>"
    filas = None
    for l in (out or b"").decode(errors="replace").splitlines():
        l = l.strip()
        if l.upper().startswith("COPY"):
            try:
                filas = int(l.split()[1])
            except (IndexError, ValueError):
                pass
    if filas is None:
        raise RpaError("No se pudo leer el conteo de COPY. Salida:\n%s"
                       % (out or b"").decode(errors="replace"))
    return filas, lineas, script


# ----------------------------------------------------------------------------- #
#  Validaciones
# ----------------------------------------------------------------------------- #
def validar(cfg, filas_copy, lineas_leidas, log):
    res = {"filas_copy": filas_copy, "lineas_leidas": lineas_leidas}
    res["resolucion_ruaf"] = int(scalar_sql(cfg, "SELECT count(*) FROM resolucion_ruaf;"))
    res["fechas_no_10"] = int(scalar_sql(
        cfg, "SELECT count(*) FROM resolucion_ruaf WHERE length(fecha) <> 10;"))
    res["admin_con_espacios"] = int(scalar_sql(
        cfg, "SELECT count(*) FROM resolucion_ruaf "
             "WHERE cod_administradora <> TRIM(cod_administradora);"))
    res["docs_alfanumericos"] = int(scalar_sql(
        cfg, "SELECT count(*) FROM resolucion_ruaf WHERE nro_documento !~ '^[0-9]+$';"))

    log.info("-" * 60)
    log.info("VALIDACIONES")
    log.info("  Lineas leidas del archivo    : %s", f"{res['lineas_leidas']:,}")
    log.info("  Filas cargadas (COPY)        : %s", f"{res['filas_copy']:,}")
    log.info("  count(*) resolucion_ruaf     : %s", f"{res['resolucion_ruaf']:,}")
    log.info("  fechas con longitud != 10    : %s  (esperado 0)", res["fechas_no_10"])
    log.info("  cod_administradora c/espacios: %s  (esperado 0)", res["admin_con_espacios"])
    log.info("  documentos alfanumericos     : %s  (informativo)", f"{res['docs_alfanumericos']:,}")

    problemas = []
    if res["filas_copy"] != res["lineas_leidas"]:
        problemas.append("filas COPY != lineas leidas")
    if res["resolucion_ruaf"] != res["filas_copy"]:
        problemas.append("count(resolucion_ruaf) != filas COPY")
    if res["fechas_no_10"] != 0:
        problemas.append("hay fechas con longitud distinta de 10")
    if res["admin_con_espacios"] != 0:
        problemas.append("hay cod_administradora con espacios")

    res["ok"] = not problemas
    res["problemas"] = problemas
    return res


def muestra(cfg, log):
    out = run_sql(cfg, "SELECT * FROM resolucion_ruaf LIMIT 5;")
    log.info("Muestra resolucion_ruaf:\n%s", out)


# ----------------------------------------------------------------------------- #
#  Orquestacion
# ----------------------------------------------------------------------------- #
def procesar(cfg, log):
    t0 = time.time()
    if not os.path.isfile(cfg.input):
        raise RpaError("No existe el archivo de entrada: %s" % cfg.input)

    log.info("=" * 60)
    log.info("RPA cargue resolucion_ruaf (carga directa, sin tabla unificadas)")
    log.info("Archivo : %s (%.1f MB)", cfg.input, os.path.getsize(cfg.input) / 1e6)
    log.info("Destino : modo=%s db=%s user=%s", cfg.mode, cfg.dbname, cfg.user)
    if cfg.mode == "docker":
        log.info("          contenedor=%s", cfg.container)
    else:
        log.info("          host=%s puerto=%s", cfg.host, cfg.port)
    log.info("=" * 60)

    log.info("[1/3] (Re)creando tabla resolucion_ruaf ...")
    run_sql(cfg, DDL)

    log.info("[2/3] Transformando y cargando (streaming) ...")
    filas, lineas, script = transformar_y_cargar(cfg, cfg.input, log)
    log.info("      -> %s filas cargadas en resolucion_ruaf.", f"{filas:,}")

    log.info("[3/3] Validando ...")
    res = validar(cfg, filas, lineas, log)
    muestra(cfg, log)

    dt = time.time() - t0
    log.info("-" * 60)
    if res["ok"]:
        log.info("RESULTADO: OK. resolucion_ruaf lista con %s registros. (%.1f s)",
                 f"{res['resolucion_ruaf']:,}", dt)
        log.info("Siguiente paso manual (instructivo): solicitar a redes la copia "
                 "de resolucion_ruaf hacia bdua_fosyga de produccion.")
    else:
        log.error("RESULTADO: FALLARON validaciones -> %s", "; ".join(res["problemas"]))
    log.info("=" * 60)
    return 0 if res["ok"] else 2


# ----------------------------------------------------------------------------- #
#  CLI
# ----------------------------------------------------------------------------- #
def parse_args(argv):
    p = argparse.ArgumentParser(
        description="RPA de cargue automatico de la tabla resolucion_ruaf.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--input", default=os.environ.get("RUAF_INPUT", ""),
                   help="Ruta al archivo .zip / .gz / .txt / .dat de RUA200AAFP.")
    p.add_argument("--mode", choices=["docker", "direct"],
                   default=os.environ.get("RUAF_MODE", "docker"),
                   help="docker (psql dentro del contenedor) | direct (psql -h host).")
    p.add_argument("--container", default=os.environ.get("RUAF_CONTAINER", "mi_postgres_data"),
                   help="Nombre del contenedor (modo docker).")
    p.add_argument("--host", default=os.environ.get("PGHOST", "127.0.0.1"))
    p.add_argument("--port", default=os.environ.get("PGPORT", "5432"))
    p.add_argument("--user", default=os.environ.get("PGUSER", "postgres"))
    p.add_argument("--dbname", default=os.environ.get("PGDATABASE", "bdua_fosyga"))
    p.add_argument("--log-dir", default=os.environ.get("RUAF_LOGDIR", "logs"),
                   help="Carpeta donde se escriben los logs.")
    return p.parse_args(argv)


def setup_logging(log_dir):
    os.makedirs(log_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, "rpa_ruaf_%s.log" % stamp)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")
    log = logging.getLogger("rpa_ruaf")
    log.setLevel(logging.INFO)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(sh)
    log.addHandler(fh)
    log.info("Log: %s", log_path)
    return log


def main(argv=None):
    cfg = parse_args(argv if argv is not None else sys.argv[1:])
    log = setup_logging(cfg.log_dir)
    if not cfg.input:
        log.error("Debe indicar --input (o variable RUAF_INPUT).")
        return 1
    try:
        return procesar(cfg, log)
    except RpaError as e:
        log.error("ABORTADO: %s", e)
        return 2
    except KeyboardInterrupt:
        log.error("Interrumpido por el usuario.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
