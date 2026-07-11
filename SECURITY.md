# 🔐 POLÍTICA DE SEGURIDAD - RUAF RPA

## Resumen Ejecutivo

Este documento describe las medidas de seguridad implementadas en el RPA RUAF y cómo configurarlo de forma segura.

**CAMBIOS DE SEGURIDAD IMPLEMENTADOS (v1.1.0):**
- ✅ Credenciales NO se pasan como argumentos de CLI (evita `ps aux` exposure)
- ✅ SSL/TLS verification HABILITADA para FTPS (previene MITM)
- ✅ Validación de host keys SSH (previene host spoofing)
- ✅ Path traversal protection en descargas
- ✅ `.pgpass` para credenciales PostgreSQL (secure storage)
- ✅ Excepciones específicas (mejor error handling)

---

## 1. CREDENCIALES - NUNCA EN ARGUMENTOS DE LÍNEA DE COMANDOS

### ❌ INCORRECTO (Inseguro)
```bash
# NUNCA hagas esto - visible en ps aux
psql -h host -U user -d db -p password='123456'
python3 script.py --password 'mi_contraseña'
```

**Por qué es malo:**
```bash
# Cualquiera en el sistema puede ver:
$ ps aux | grep psql
user 12345 ... psql -h host -U user -p password='123456'
```

### ✅ CORRECTO (Seguro)

**Opción A: ~/.pgpass (RECOMENDADO)**
```bash
# Crear ~/.pgpass con formato:
# host:port:database:user:password
chmod 600 ~/.pgpass
```

**Opción B: Variable de entorno (solo en desarrollo)**
```bash
export PGPASSWORD="contraseña"
psql -h host -U user -d db
# Limpia después: unset PGPASSWORD
```

**Opción C: CI/CD (GitHub Actions, etc.)**
```yaml
env:
  PGPASSWORD: ${{ secrets.DB_PASSWORD }}
```

---

## 2. CERTIFICADOS SSL/TLS - VERIFICACIÓN OBLIGATORIA

### ❌ INSEGURO (Sin verificación)
```python
# NUNCA hagas esto
ctx = ssl.create_default_context()
ctx.verify_mode = ssl.CERT_NONE
ctx.check_hostname = False
```

**Por qué es malo:**
- Vulnerable a **Man-in-the-Middle (MITM) attacks**
- Atacante puede interceptar todos los datos
- Imposible confiar que hablas con el servidor correcto

### ✅ CORRECTO (Verificación habilitada)
```python
# CORRECTO - Verifica certificados
ctx = ssl.create_default_context()
ctx.check_hostname = True
ctx.verify_mode = ssl.CERT_REQUIRED
# Los certificados se validan contra CA del sistema
```

**Si tienes error de certificado inválido:**
```
ERROR: Error de verificación SSL en ftp.minsalud.gov.co
```

**Soluciones:**
1. El certificado del servidor puede no ser válido
2. Contacta a administración del servidor
3. Si es certificado autofirmado, NO desactives verificación (malo)
4. En su lugar, agrégalo a la CA local (mediante administrador)

---

## 3. VALIDACIÓN DE HOST SSH - PREVENIR SPOOFING

### ❌ INSEGURO (Sin validación)
```python
# NUNCA hagas esto
ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
```

**Por qué es malo:**
- Acepta cualquier clave de host
- Atacante puede suplantarse como servidor
- El usuario nunca se da cuenta del ataque

### ✅ CORRECTO (Validación de clave)
```python
# CORRECTO - Valida contra known_hosts
ssh_client.load_system_host_keys()
ssh_client.set_missing_host_key_policy(paramiko.WarningPolicy())
```

**Primer acceso a un servidor:**
```bash
# Agregar clave del servidor a known_hosts
ssh-keyscan -t rsa mft.adres.gov.co >> ~/.ssh/known_hosts

# Verificar huella digital (fingerprint)
ssh-keygen -l -f ~/.ssh/known_hosts
```

**Contactar a administración SFTP para verificar fingerprint:**
```
Servidor: mft.adres.gov.co
Tipo: ed25519
Fingerprint: SHA256:xxxxx...
```

---

## 4. MANEJO DE ARCHIVOS - PATH TRAVERSAL PROTECTION

### ❌ INSECURO (Sin validación)
```python
# NUNCA hagas esto - vulnerable a path traversal
local = os.path.join(dest_dir, nombre_remoto)
# Si nombre_remoto = "../../etc/passwd", falla
```

### ✅ CORRECTO (Con validación)
```python
# Validar que no hay caracteres peligrosos
if ".." in nombre or nombre.startswith("/"):
    raise SystemExit("Nombre inválido")

local = os.path.join(dest_dir, nombre)

# Verificación adicional
if not os.path.abspath(local).startswith(os.path.abspath(dest_dir)):
    raise SystemExit("Path fuera del directorio permitido")
```

---

## 5. CREDENCIALES EN ARCHIVOS - .gitignore

### Archivos sensibles (NO deben ir a git)
```
config.*.env          # Archivos de configuración con secretos
FileZilla.xml         # Credenciales SFTP en Base64
.pgpass              # Credenciales PostgreSQL
.env*                # Variables de entorno
.ssh/                # Claves SSH privadas
```

**Verificar que `.gitignore` incluye:**
```bash
grep -E "config.*env|FileZilla|\.pgpass|\.env|\.ssh" .gitignore
```

**Si accidentalmente commiteaste un secret:**
```bash
# URGENTE: Cambiar contraseña inmediatamente
# Luego, remover del historio git
git filter-branch --tree-filter 'rm -f config.prod.env' HEAD
```

---

## 6. ARCHIVOS DE EJEMPLO - TEMPLATES SIN SECRETOS

Todos los archivos sensibles tienen templates `.example`:

```
config.docker.env.example    ← Template PÚBLICO (sin credenciales)
config.docker.env            ← PRIVADO (credenciales reales)

FileZilla.xml.example        ← Template PÚBLICO
FileZilla.xml                ← PRIVADO

config.prod.env.example      ← Template PÚBLICO
config.prod.env              ← PRIVADO
```

**Para nuevo usuario:**
```bash
# 1. Copiar template
cp config.prod.env.example config.prod.env

# 2. Agregar credenciales (sin pasar contraseña)
# Editar config.prod.env
# PGPASSWORD se cargar desde ~/.pgpass

# 3. Copiar FileZilla.xml template
cp FileZilla.xml.example FileZilla.xml
# Agregar credenciales SFTP
```

---

## 7. LOGGING - NO EXPONER SECRETOS

### ❌ INSECURO (Loguea secretos)
```python
# NUNCA hagas esto
log.info(f"Conectando a {host} con contraseña {password}")
log.debug(f"Environment: {os.environ}")  # Incluye PGPASSWORD
```

### ✅ CORRECTO (No loguea secretos)
```python
# CORRECTO - Solo información no sensible
log.info(f"Conectando a {cfg['host']}:{cfg['port']} como {cfg['user']}")
log.debug(f"Modo: {cfg['mode']}, BD: {cfg['dbname']}")
```

**Revisar logs en búsqueda de secretos:**
```bash
# Nunca hagas esto, pero para auditar:
grep -r "PGPASSWORD\|password\|secret" logs/ config/
```

---

## 8. CICLO DE VIDA DE SECRETOS

```
┌─────────────────────────────────────────┐
│ 1. CREAR/GENERAR SECRETO                │
│    (API key, contraseña, SSH key)       │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│ 2. ALMACENAR SECRETO                    │
│    ~/.pgpass (600)                      │
│    ~/.ssh/ (700)                        │
│    CI/CD Secrets Manager                │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│ 3. USAR SECRETO EN EJECUCIÓN            │
│    NUNCA en argumentos CLI              │
│    NUNCA en logs                        │
│    NUNCA hardcoded en código            │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│ 4. LIMPIAR DESPUÉS DE USAR              │
│    unset PGPASSWORD                     │
│    rm -f temporal_auth_file             │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│ 5. ROTAR REGULARMENTE                   │
│    Mensual: cambiar contraseñas         │
│    Anual: regenerar SSH keys            │
│    Cuando alguien sale del equipo       │
└─────────────────────────────────────────┘
```

---

## 9. CHECKLIST DE SEGURIDAD

### Pre-Desarrollo
- [ ] Leer este documento completo
- [ ] No compartir contraseñas por Slack/email
- [ ] Usar password manager (LastPass, 1Password, etc.)
- [ ] Generar SSH keys únicas para desarrollo

### Pre-Producción
- [ ] `.pgpass` creado con permisos 600
- [ ] Certificados SSL validados (no CERT_NONE)
- [ ] Host keys SSH verificadas
- [ ] No hay secrets en git history
- [ ] Audit de logs: sin contraseñas, hosts, usuarios
- [ ] Backup de datos antes de primera ejecución
- [ ] Plan de rotación de credenciales (trimestral)

### Monitoreo Continuo
- [ ] Logs sin información sensible
- [ ] Alertas si credenciales fallan repetidamente
- [ ] Auditoría mensual de acceso
- [ ] Notificación si detectan secrets en git

---

## 10. INCIDENTES DE SEGURIDAD

### Si sospechas exposición de credenciales:

1. **INMEDIATAMENTE:**
   ```bash
   # Cambiar contraseña en la base de datos
   # Avisar a administración
   # NO usar la credencial comprometida
   ```

2. **AUDITORÍA:**
   ```bash
   # Revisar logs de BD para acceso no autorizado
   # Revisar cambios recientes en resolucion_ruaf
   # Buscar en git history si fue commiteda
   ```

3. **REMEDIACIÓN:**
   ```bash
   # Si está en git history
   git filter-branch --tree-filter 'rm -f config.prod.env' HEAD
   # Hacer force push
   git push -f
   # Notificar a todo el equipo que haga pull
   ```

---

## 11. CONTACTOS Y REFERENCIAS

**Reporte de vulnerabilidades:** (No usar para consultas normales)
- Email: SECURITY@[dominio]
- PGP Key: (Disponible en documentación privada)

**Referencias:**
- OWASP: https://owasp.org/
- CWE-798: Use of Hard-Coded Credentials
- CWE-295: Improper Certificate Validation
- CWE-22: Path Traversal

---

## Versionado de Cambios de Seguridad

| Versión | Fecha | Cambio |
|---------|-------|--------|
| 1.1.0 | 2026-07-11 | Remover credenciales de argumentos CLI, habilitar SSL verificación |
| 1.0.0 | 2026-01-01 | Versión inicial |

---

**Última revisión:** 2026-07-11
**Próxima revisión recomendada:** 2026-10-11 (Trimestral)

⚠️ **Si tienes dudas de seguridad, SIEMPRE pide opinión de un colega antes de implementar.**
