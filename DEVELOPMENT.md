# GUÍA DE DESARROLLO Y SEGURIDAD - RUAF RPA

## 🔐 CONFIGURACIÓN SEGURA DE CREDENCIALES

### PostgreSQL: Usando `.pgpass`

Las credenciales de PostgreSQL **NUNCA deben pasar como argumentos de línea de comandos** (serían visibles en `ps aux`).

**Opción 1: Archivo `.pgpass` (RECOMENDADO)**

Crea el archivo `~/.pgpass` con permisos restrictivos:

```bash
# Crear archivo
cat > ~/.pgpass << 'EOF'
# host:port:database:user:password
10.10.11.161:5432:interssi:jamaica:TU_CONTRASEÑA_AQUI
127.0.0.1:5432:bdua_fosyga:postgres:TU_CONTRASEÑA_DOCKER

# Ejemplo adicional para ADRES (si usas)
mft.adres.gov.co:22:*:PILA86:TU_CONTRASEÑA_ADRES
EOF

# CRÍTICO: Establecer permisos
chmod 600 ~/.pgpass
```

**Estructura del archivo `.pgpass`:**
```
host:port:database:user:password
```

- `host`: dirección IP o nombre del servidor
- `port`: puerto de PostgreSQL (usualmente 5432)
- `database`: nombre de la base de datos (o `*` para todas)
- `user`: usuario de PostgreSQL
- `password`: contraseña

PostgreSQL busca en `~/.pgpass` automáticamente cuando ejecutas `psql`.

**Opción 2: Variable de entorno**

Si prefieres usar una variable de entorno:

```bash
# Exportar en tu sesión (NO en scripts permanentes)
export PGPASSWORD="tu_contraseña"

# Ejecutar el script
./run_ruaf.sh
```

⚠️ **ADVERTENCIA**: Esta opción deja la contraseña visible en `history`. Usa solo en desarrollo local.

**Opción 3: CI/CD (GitHub Actions, GitLab CI, etc.)**

Para ejecución automatizada:

```yaml
# GitHub Actions ejemplo
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run RPA
        env:
          PGPASSWORD: ${{ secrets.POSTGRES_PASSWORD }}
        run: ./run_ruaf.sh
```

---

### SFTP/FTPS: Configuración en `FileZilla.xml`

#### Opción 1: Claves SSH (MÁS SEGURA para SFTP)

```bash
# 1. Generar par de claves (si no las tienes)
ssh-keygen -t ed25519 -f ~/.ssh/ruaf_sftp -C "ruaf-automation"

# 2. Añadir clave pública al servidor SFTP (contacta a administración ADRES)
cat ~/.ssh/ruaf_sftp.pub

# 3. Actualizar FileZilla.xml para usar clave en lugar de contraseña
#    (Consulta documentación de FileZilla)
```

#### Opción 2: Contraseña en `FileZilla.xml`

Si usas contraseña, ten en cuenta:

1. `FileZilla.xml` está en `.gitignore` (no se commitea)
2. Usa un template `FileZilla.xml.example` sin credenciales
3. La contraseña debe estar en Base64 en el archivo (NO es encriptación, solo encoding)

**Para crear la contraseña en Base64:**

```bash
# Codificar contraseña
echo -n "MI_CONTRASEÑA" | base64

# Resultado: TUlfQ09OVFJBU0XDkQ==
# Copiarlo en el campo <Pass encoding="base64">...</Pass>
```

⚠️ **IMPORTANTE**: Base64 es **encoding, no encriptación**. Cualquiera puede decodificar. Para mejor seguridad, usa claves SSH.

---

## 🚀 SETUP DE DESARROLLO

### 1. Clonar y Preparar Ambiente

```bash
# Clonar el repositorio
git clone <repo>
cd RUAF

# Crear virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
pip install -r requirements-dev.txt  # para testing
```

### 2. Crear Archivos de Configuración

```bash
# Docker (desarrollo)
cp config.docker.env.example config.docker.env
# Editar config.docker.env si es necesario (normalmente no)

# Producción (si aplica)
cp config.prod.env.example config.prod.env
# Editar con valores reales (excepto contraseña)
```

### 3. Configurar PostgreSQL local (Docker)

```bash
# Crear contenedor Docker con PostgreSQL
docker run --name mi_postgres_data \
    -e POSTGRES_PASSWORD=Majito.08 \
    -e POSTGRES_DB=bdua_fosyga \
    -p 5432:5432 \
    -d postgres:15

# Crear .pgpass para acceso sin contraseña en prompt
cat > ~/.pgpass << 'EOF'
127.0.0.1:5432:bdua_fosyga:postgres:Majito.08
EOF
chmod 600 ~/.pgpass
```

### 4. Configurar SFTP para Testing

```bash
# Si tienes acceso a SFTP real:
cp FileZilla.xml.example FileZilla.xml
# Editar con credenciales reales (la contraseña va en Base64)
```

### 5. Ejecutar el RPA

```bash
# Modo Docker (defecto)
./run_ruaf.sh
# Seleccionar opción 1

# Modo directo (si tienes BD remota)
source config.prod.env
./run_rpa.sh
```

---

## 🧪 TESTING

### Ejecutar Tests

```bash
# Todos los tests
pytest

# Con cobertura
pytest --cov=src

# Tests específicos
pytest tests/test_rpa_cargue_ruaf.py -v
```

### Tests Disponibles

```bash
# Transformación de fechas
pytest tests/test_rpa_cargue_ruaf.py::test_transformar_fecha_aaaammdd

# Normalización de documentos
pytest tests/test_rpa_cargue_ruaf.py::test_normalize_documento

# Descarga de archivos
pytest tests/test_descargar_sftp.py::test_elegir_ultimo
```

---

## 📋 CHECKLIST PRE-PRODUCCIÓN

Antes de ejecutar en producción:

- [ ] `.pgpass` creado y permisos 600
- [ ] `FileZilla.xml` con credenciales reales (NO en git)
- [ ] `config.prod.env` con valores correctos (EXCEPTO contraseña)
- [ ] SSH keys configuradas en servidor SFTP (si aplica)
- [ ] Prueba de conexión a BD: `psql -U jamaica -d interssi -h 10.10.11.161`
- [ ] Prueba de conexión a SFTP: `sftp USUARIO@HOST`
- [ ] Verificar logs en directorio `logs/`
- [ ] Backup de tabla `resolucion_ruaf` antes de primera ejecución

---

## 🔧 TROUBLESHOOTING

### Error: `psql: error: FATAL: password authentication failed`

**Causas:**
- `.pgpass` no existe o permisos incorrectos
- Contraseña en `.pgpass` es incorrecta
- Variable `PGPASSWORD` no está seteada

**Solución:**
```bash
# Verificar .pgpass
ls -la ~/.pgpass  # Debe ser -rw------- (600)
cat ~/.pgpass     # Verificar host, user, password

# Probar conexión directo
psql -h 10.10.11.161 -U jamaica -d interssi
```

### Error: `SSL: CERTIFICATE_VERIFY_FAILED`

**Causa:** Certificado SSL del servidor no es válido o no es de confianza

**Soluciones:**
1. Contactar a administración para certificado válido
2. Si es certificado autofirmado, agregar a CA local (NO recomendado)

### Error: `Host key verification failed`

**Causa:** Clave de host SSH desconocida

**Solución:**
```bash
# Agregar clave del servidor a known_hosts
ssh-keyscan -t rsa mft.adres.gov.co >> ~/.ssh/known_hosts

# Verificar
ssh-keyscan -H mft.adres.gov.co
```

### Error: `Connection refused` o `Timeout`

**Causas:**
- Servidor SFTP/FTPS no accesible
- Firewall bloqueando puerto
- Credenciales incorrectas

**Solución:**
```bash
# Probar conectividad
telnet mft.adres.gov.co 22
# o
nmap -p 22 mft.adres.gov.co
```

---

## 📚 REFERENCIAS

- [PostgreSQL .pgpass](https://www.postgresql.org/docs/current/libpq-pgpass.html)
- [Paramiko SSH Library](https://www.paramiko.org/)
- [Python ssl Module](https://docs.python.org/3/library/ssl.html)
- [OWASP: Credential Storage](https://cheatsheetseries.owasp.org/cheatsheets/Nodejs_Security_Cheat_Sheet.html#credential-storage)

---

**Última actualización:** 2026-07-11

¿Preguntas o problemas? Ver `TROUBLESHOOTING` arriba.
