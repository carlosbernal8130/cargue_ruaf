#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Descarga el ultimo archivo RUA200AAFP del servidor del ministerio (ADRES/MinSalud).
====================================================================================

- Lee la configuracion (host/puerto/usuario/clave/protocolo) desde el
  FileZilla.xml del proyecto (la clave viene en base64).
- Soporta dos transportes, segun el protocolo del site en FileZilla:
      * SFTP           (Protocol=1)  -> via paramiko           (p.ej. ADRES)
      * FTPS implicito (puerto 990)  -> via ftplib (TLS)       (p.ej. MinSalud)
      * FTPS explicito (otro puerto) -> via ftplib (AUTH TLS)
- Lista el directorio remoto, filtra por  RUA200AAFP<AAAAMMDD>NI000900474727.zip
  y elige el MAS RECIENTE por la fecha AAAAMMDD del nombre.
- Descarga a la carpeta local (si ya existe con igual tamano, no lo repite).

Imprime en STDOUT unicamente la ruta local del archivo descargado (para
encadenarlo desde el .sh); el progreso va a STDERR.

Uso tipico (los RUA200AAFP estan en 'Ministerio 2' = ftp.minsalud.gov.co):
    python3 descargar_sftp.py                       # site por defecto: 'Ministerio 2'
    python3 descargar_sftp.py --site 'Adres'        # usar el SFTP de ADRES
    python3 descargar_sftp.py --remote-dir '' --dest .
"""

import argparse
import base64
import ftplib
import os
import re
import ssl
import sys
import time
import xml.etree.ElementTree as ET


PATRON_DEFECTO = r"^RUA200AAFP(\d{8})NI000900474727\.zip$"
SITE_DEFECTO = "Ministerio 2"     # servidor donde publican los RUA200AAFP
BLOQUE = 1024 * 1024              # 1 MB


def log(msg):
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


# ----------------------------------------------------------------------------- #
#  Lectura del FileZilla.xml
# ----------------------------------------------------------------------------- #
def _text(node, tag, default=""):
    el = node.find(tag)
    return el.text if (el is not None and el.text is not None) else default


def parse_remotepath(value):
    """RemotePath de FileZilla ('1 0 11 ArchivoBDUA') -> '/ArchivoBDUA'."""
    if not value:
        return ""
    tokens = value.split(" ")[1:]
    segs = [t for t in tokens if t and not t.isdigit()]
    return "/" + "/".join(segs) if segs else ""


def leer_filezilla(path, site=None):
    """Devuelve dict del servidor: name, host, port, user, password, protocol, remote_dir."""
    root = ET.parse(path).getroot()
    servers = root.findall("./Servers/Server")

    elegido = None
    if site:
        for s in servers:
            if _text(s, "Name").strip().lower() == site.strip().lower():
                elegido = s
                break
        if elegido is None:
            raise SystemExit("No se encontro el site '%s' en %s" % (site, path))
    else:
        elegido = servers[0] if servers else None
        if elegido is None:
            raise SystemExit("No hay servidores en %s" % path)

    host = _text(elegido, "Host")
    pass_b64 = _text(elegido, "Pass")
    cfg = {
        "name": _text(elegido, "Name"),
        "host": host,
        "port": int(_text(elegido, "Port", "22")),
        "user": _text(elegido, "User"),
        "password": base64.b64decode(pass_b64).decode("utf-8") if pass_b64 else "",
        "protocol": _text(elegido, "Protocol", "0"),
        "remote_dir": "",
    }
    # remote_dir desde la pestana activa que apunte al mismo host
    for tab in root.findall(".//Setting[@name='Tab data']/Tabs/Tab"):
        if _text(tab, "Host") == host:
            rd = parse_remotepath(_text(tab, "RemotePath"))
            if rd:
                cfg["remote_dir"] = rd
                break
    return cfg


# ----------------------------------------------------------------------------- #
#  Transportes
# ----------------------------------------------------------------------------- #
class ImplicitFTP_TLS(ftplib.FTP_TLS):
    """FTPS implicito (puerto 990): la sesion es TLS desde el primer byte."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._sock = None

    @property
    def sock(self):
        return self._sock

    @sock.setter
    def sock(self, value):
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value, server_hostname=self.host)
        self._sock = value


class FTPSTransport:
    """Backend FTPS (implicito o explicito) sobre ftplib."""

    def __init__(self, cfg, remote_dir, timeout):
        implicito = cfg["port"] == 990
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        cls = ImplicitFTP_TLS if implicito else ftplib.FTP_TLS
        log("Conectando FTPS %s a %s:%d ..."
            % ("implicito" if implicito else "explicito", cfg["host"], cfg["port"]))
        self.ftp = cls(context=ctx, timeout=timeout, encoding="latin-1")
        self.ftp.connect(cfg["host"], cfg["port"])
        self.ftp.login(cfg["user"], cfg["password"])
        self.ftp.prot_p()          # canal de datos cifrado
        self.ftp.set_pasv(True)
        self.ftp.voidcmd("TYPE I")  # binario (para SIZE/RETR)
        if remote_dir:
            self.ftp.cwd(remote_dir)
        log("Login OK. Directorio: %s" % self.ftp.pwd())

    def listdir(self):
        return [os.path.basename(n) for n in self.ftp.nlst()]

    def size(self, name):
        try:
            return self.ftp.size(name)
        except Exception:
            return None

    def get(self, name, local, callback):
        total = self.size(name) or 0
        got = 0
        with open(local, "wb") as f:
            def cb(block):
                nonlocal got
                f.write(block)
                got += len(block)
                callback(got, total)
            self.ftp.retrbinary("RETR " + name, cb, blocksize=BLOQUE)

    def close(self):
        try:
            self.ftp.quit()
        except Exception:
            try:
                self.ftp.close()
            except Exception:
                pass


class SFTPTransport:
    """Backend SFTP sobre paramiko (import perezoso)."""

    def __init__(self, cfg, remote_dir, timeout):
        import paramiko  # solo se necesita para SFTP
        self.remote_dir = remote_dir
        log("Conectando SFTP a %s@%s:%d ..." % (cfg["user"], cfg["host"], cfg["port"]))
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect(
            hostname=cfg["host"], port=cfg["port"], username=cfg["user"],
            password=cfg["password"], timeout=timeout, banner_timeout=timeout,
            auth_timeout=timeout, look_for_keys=False, allow_agent=False,
        )
        self.sftp = self.ssh.open_sftp()

    def _full(self, name):
        return (self.remote_dir.rstrip("/") + "/" + name) if self.remote_dir else name

    def listdir(self):
        return self.sftp.listdir(self.remote_dir or ".")

    def size(self, name):
        return self.sftp.stat(self._full(name)).st_size

    def get(self, name, local, callback):
        self.sftp.get(self._full(name), local, callback=callback)

    def close(self):
        try:
            self.sftp.close()
            self.ssh.close()
        except Exception:
            pass


def abrir_transporte(cfg, remote_dir, timeout):
    if cfg["protocol"] == "1":     # 1 = SFTP en FileZilla
        return SFTPTransport(cfg, remote_dir, timeout)
    return FTPSTransport(cfg, remote_dir, timeout)


# ----------------------------------------------------------------------------- #
#  Seleccion y descarga
# ----------------------------------------------------------------------------- #
def elegir_ultimo(tr, patron):
    rx = re.compile(patron, re.IGNORECASE)
    candidatos = []
    for nombre in tr.listdir():
        m = rx.match(nombre)
        if m:
            candidatos.append((m.group(1), nombre))  # (AAAAMMDD, nombre)
    if not candidatos:
        raise SystemExit("No se encontraron archivos que cumplan el patron.")
    candidatos.sort()
    fecha, nombre = candidatos[-1]
    log("Archivos que cumplen el patron: %d. Mas reciente: %s (fecha %s)"
        % (len(candidatos), nombre, fecha))
    return nombre


def descargar(tr, nombre, dest_dir, force):
    local = os.path.join(dest_dir, nombre)
    tam = tr.size(nombre)

    if os.path.isfile(local) and not force and tam and os.path.getsize(local) == tam:
        log("Ya existe localmente con el mismo tamano (%d bytes); no se descarga." % tam)
        return local

    log("Descargando %s (%.1f MB) -> %s"
        % (nombre, (tam or 0) / 1e6, local))
    estado = {"t": time.time()}

    def progreso(transferido, total):
        ahora = time.time()
        if ahora - estado["t"] >= 5 or (total and transferido >= total):
            pct = (transferido / total * 100) if total else 0
            log("   %6.1f%%  (%.1f / %.1f MB)"
                % (pct, transferido / 1e6, (total or 0) / 1e6))
            estado["t"] = ahora

    tr.get(nombre, local, progreso)
    log("Descarga completa: %s" % local)
    return local


# ----------------------------------------------------------------------------- #
#  CLI
# ----------------------------------------------------------------------------- #
def main(argv=None):
    p = argparse.ArgumentParser(description="Descarga del ultimo RUA200AAFP (SFTP/FTPS).")
    p.add_argument("--filezilla", default="FileZilla.xml")
    p.add_argument("--site", default=SITE_DEFECTO,
                   help="Nombre del site en FileZilla (por defecto '%s')." % SITE_DEFECTO)
    p.add_argument("--remote-dir", default=None,
                   help="Directorio remoto (por defecto: raiz / o el de la pestana).")
    p.add_argument("--dest", default=".")
    p.add_argument("--pattern", default=PATRON_DEFECTO)
    p.add_argument("--force", action="store_true")
    p.add_argument("--timeout", type=float, default=40.0)
    args = p.parse_args(argv if argv is not None else sys.argv[1:])

    if not os.path.isfile(args.filezilla):
        raise SystemExit("No existe el FileZilla.xml: %s" % args.filezilla)

    cfg = leer_filezilla(args.filezilla, args.site)
    remote_dir = args.remote_dir if args.remote_dir is not None else cfg["remote_dir"]
    log("Site: %s (%s:%d, protocolo FileZilla=%s)  dir: %s"
        % (cfg["name"], cfg["host"], cfg["port"], cfg["protocol"], remote_dir or "(raiz)"))

    os.makedirs(args.dest, exist_ok=True)
    tr = None
    try:
        tr = abrir_transporte(cfg, remote_dir, args.timeout)
        nombre = elegir_ultimo(tr, args.pattern)
        local = descargar(tr, nombre, args.dest, args.force)
    finally:
        if tr:
            tr.close()

    print(os.path.abspath(local))   # STDOUT = ruta local (para el .sh)
    return 0


if __name__ == "__main__":
    sys.exit(main())
