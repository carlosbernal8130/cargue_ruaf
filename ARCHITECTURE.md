# 🏗️ ARQUITECTURA - RUAF RPA

## Visión General

RUAF RPA es una aplicación de **Robotic Process Automation (RPA)** que automatiza la descarga y cargue de datos del ministerio de salud colombiano en la tabla `resolucion_ruaf` de PostgreSQL.

```
┌─────────────────────────────────────────────────────────────┐
│                    FLUJO GENERAL DEL RPA                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [SFTP/FTPS Server]                                        │
│       │                                                     │
│       └─→ descargar_sftp.py ──→ Archivo RUA200AAFP.zip    │
│                                         │                  │
│                                         ▼                  │
│                      rpa_cargue_ruaf.py                    │
│                      ┌─────────────┬──────────────┐        │
│                      │             │              │        │
│                  [Decompress] [Transform] [Validate]       │
│                      │             │              │        │
│                      └──────┬──────┴──────────────┘        │
│                             ▼                              │
│                      [PostgreSQL]                          │
│                   resolucion_ruaf table                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 📋 Componentes Principales

### 1. **descargar_sftp.py**
Descarga automática de archivos RUA200AAFP desde servidores SFTP/FTPS.

**Responsabilidades:**
- Leer configuración desde `FileZilla.xml`
- Conectar a servidor SFTP o FTPS
- Listar archivos remotos
- Seleccionar el más reciente (por fecha en nombre)
- Descargar a directorio local

**Clases principales:**
```python
class SFTPTransport:
    """Conexión segura SFTP con validación de host keys."""
    - __init__(cfg, remote_dir, timeout)
    - listdir()
    - size(name)
    - get(name, local, callback)
    - close()

class FTPSTransport:
    """Conexión segura FTPS con validación de certificados SSL."""
    - __init__(cfg, remote_dir, timeout)
    - listdir()
    - size(name)
    - get(name, local, callback)
    - close()
```

**Funciones principales:**
```python
def leer_filezilla(path, site=None):
    """Lee credenciales de FileZilla.xml"""

def elegir_ultimo(transport, patron):
    """Selecciona archivo más reciente"""

def descargar(transport, nombre, dest_dir, force):
    """Descarga archivo con validación de seguridad"""

def main(argv=None):
    """Punto de entrada"""
```

---

### 2. **rpa_cargue_ruaf.py**
Transformación y cargue de datos en PostgreSQL.

**Responsabilidades:**
- Crear/recrear tabla `resolucion_ruaf`
- Descomprimir archivo
- Transformar datos (ancho fijo → TAB-delimitado)
- Normalizar campos (documentos, fechas, admin)
- Validar integridad de datos
- Generar reportes

**Flujo de transformación:**
```
ZIP → [unzip -p] → [Python transformer] → [COPY stdin] → PostgreSQL

Posiciones (ancho fijo):
- tipo_documento:     1-2     (2 caracteres)
- nro_documento:      3-18    (16 caracteres)
- cod_administradora: 19-24   (6 caracteres)
- fecha:              25-...  (10 ó 8 caracteres)

Transformación:
- Tipo doc: TRIM
- Nro doc: TRIM + normalizacion (0-pad si numerico, conservar si alfanumerico)
- Admin: TRIM
- Fecha: Autodetectar AAAA-MM-DD vs AAAAMMDD → convertir a AAAA-MM-DD
```

**Funciones principales:**
```python
def _transformar(instream, outstream, log):
    """Streaming transform de líneas de ancho fijo."""
    # Lee línea por línea sin cargar todo en memoria
    # Autodetecta formato de fecha en primera línea
    # Devuelve (lineas_procesadas, script_fecha)

def transformar_y_cargar(cfg, path, log):
    """Pipeline: descompresor → transformador → COPY."""
    # Ejecuta en paralelo:
    # unzip -p archivo | python transformer | psql COPY
    # Devuelve (filas_copy, lineas_leidas, script_fecha)

def validar(cfg, filas_copy, lineas_leidas, log):
    """Valida integridad de carga."""
    # Compara conteos
    # Valida formatos (fechas 10 chars, admin sin espacios)
    # Devuelve dict con resultados

def procesar(cfg, log):
    """Orquestador principal: crea tabla → carga → valida."""

def main(argv=None):
    """Punto de entrada."""
```

---

### 3. **verify_security.py**
Verificación automática de mejoras de seguridad.

**Responsabilidades:**
- Validar que credenciales NO se pasan como argumentos
- Verificar SSL/TLS habilitado
- Validar host keys SSH
- Verificar path traversal protection
- Auditar .gitignore
- Documentación de seguridad

**10 chequeos de seguridad:**
1. Credenciales en CLI
2. Credenciales en .env
3. SSL/TLS Verification
4. SSH Host Validation
5. Path Traversal Protection
6. .gitignore - Archivos sensibles
7. Documentación de seguridad
8. Manejo de excepciones
9. Logging seguro
10. Argumentos CLI

---

## 🔄 Flujos de Ejecución

### Flujo Normal (run_ruaf.sh)
```
1. Mostrar menú interactivo
2. Seleccionar ambiente (Docker/Producción)
3. Cargar configuración desde config.*.env
4. Ejecutar descargar_sftp.py
   → Conectar a SFTP/FTPS
   → Listar archivos
   → Seleccionar más reciente
   → Descargar
5. Ejecutar rpa_cargue_ruaf.py
   → (Re)crear tabla
   → Descomprimir en streaming
   → Transformar y cargar
   → Validar integridad
6. Mostrar resultado y logs
```

### Flujo Seguro (Argumentos y Credenciales)
```
┌─────────────────────────────────────────┐
│ Credenciales                           │
├─────────────────────────────────────────┤
│                                        │
│ NUNCA en argumentos CLI:               │
│ ✓ psql ... (sin -password)             │
│ ✓ python script.py (sin --password)    │
│                                        │
│ SÍ en:                                 │
│ ✓ ~/.pgpass (600)                     │
│ ✓ Variable de entorno PGPASSWORD       │
│ ✓ CI/CD Secrets Manager                │
│                                        │
└─────────────────────────────────────────┘
```

---

## 📊 Modelo de Datos

### Tabla: `resolucion_ruaf`
```sql
CREATE TABLE resolucion_ruaf (
    tipo_documento      character varying(3),
    nro_documento       character varying(17),
    cod_administradora  character varying(6),
    fecha               character varying(10)
);

CREATE INDEX idx_ruaf ON resolucion_ruaf 
    USING btree (tipo_documento, nro_documento);
```

**Campos:**
- `tipo_documento`: Tipo de documento (CC, CE, PA, etc.) - 2 chars
- `nro_documento`: Número de documento - hasta 17 chars, sin ceros a izquierda
- `cod_administradora`: Código de administradora de pensiones - 6 chars, sin espacios
- `fecha`: Fecha de afiliación - formato AAAA-MM-DD, siempre 10 chars

**Índice:**
- Compuesto (tipo_documento, nro_documento) para búsquedas rápidas

---

## 🔐 Seguridad

### Niveles de Protección

**1. Credenciales**
- ❌ NO en argumentos CLI (visible en `ps aux`)
- ✅ `.pgpass` con permisos 600
- ✅ Variable de entorno (solo en CI/CD)

**2. Transporte**
- ✅ SSL/TLS verification habilitado (CERT_REQUIRED)
- ✅ SSH host key validation (WarningPolicy + known_hosts)
- ❌ Sin certificados autofirmados aceptados

**3. Entrada**
- ✅ Path traversal protection (validación de ".." y "/")
- ✅ Validación de longitud de línea
- ✅ Validación de formato de datos

**4. Excepciones**
- ✅ Excepciones específicas (no genéricas)
- ✅ Manejo de errores SSH y SSL
- ✅ Logging sin secretos

**5. Auditoría**
- ✅ Logs con timestamp y nivel
- ✅ Sin información sensible en logs
- ✅ Archivos de log en `logs/` con rotación

---

## 🧪 Testing

### Estrategia de Testing

```
tests/
├── __init__.py
├── conftest.py              # Fixtures compartidas
├── test_rpa_cargue_ruaf.py  # Tests unitarios (15+ tests)
├── test_descargar_sftp.py   # Tests unitarios (12+ tests)
└── fixtures/
    └── sample_data/         # Datos de ejemplo
```

**Cobertura Target:** 80%+

**Tipos de tests:**
- Unit tests: Funciones individuales
- Integration tests: Pipelines completos
- Security tests: Validaciones de seguridad

**Ejecución:**
```bash
pytest tests/ -v --cov=. --cov-report=html
```

---

## 🚀 Deployments

### Ambientes

**1. Docker (Desarrollo/Testing)**
```
Host Machine
    └─ Docker Container
        ├─ PostgreSQL 15
        ├─ Python 3.9+
        └─ RPA Scripts
```

**2. Producción (Infraestructura)**
```
Server
    ├─ PostgreSQL (10.10.11.161:5432)
    │   └─ interssi DB
    ├─ .pgpass (~/.pgpass)
    └─ RPA Scripts (vía cron o manual)
```

### CI/CD (GitHub Actions)

**Workflows:**
- Tests: Python 3.9, 3.10, 3.11
- Linting: flake8, black, isort
- Security: verify_security.py
- Coverage: Reportado a codecov

---

## 📈 Performance

### Optimizaciones

**1. Streaming**
- No se carga archivo completo en memoria
- `unzip -p` → Python transformer → `psql COPY`
- Buffer de 100k líneas antes de escribir

**2. Batch Processing**
- COPY de múltiples filas por transacción
- Índices para búsquedas rápidas

**3. Compresión**
- Archivo ZIP reduce tamaño 10x
- Descompresión in-flight (sin descomprimir a disco)

**Benchmarks:**
- Archivo típico: 250+ MB (comprimido)
- Velocidad: ~50k filas/segundo
- Memoria: < 50 MB (constante)

---

## 📚 Estructura de Directorios

```
RUAF/
├── rpa_cargue_ruaf.py           # Script principal cargue
├── descargar_sftp.py            # Script descarga
├── run_rpa.sh                   # Orquestador simple
├── run_ruaf.sh                  # Menú interactivo
├── verify_security.py           # Verificación seguridad
│
├── requirements.txt             # Dependencias producción
├── requirements-dev.txt         # Dependencias desarrollo
├── pyproject.toml              # Configuración herramientas
├── pytest.ini                  # Configuración pytest
├── .flake8                     # Configuración linting
│
├── config.docker.env           # Config Docker (NO git)
├── config.docker.env.example   # Template público
├── config.prod.env             # Config Prod (NO git)
├── config.prod.env.example     # Template público
├── FileZilla.xml               # Credenciales SFTP (NO git)
├── FileZilla.xml.example       # Template público
│
├── README.md                   # Documentación principal
├── DEVELOPMENT.md              # Guía desarrollo
├── SECURITY.md                 # Política seguridad
├── ARCHITECTURE.md             # Este archivo
│
├── .github/
│   └── workflows/
│       └── tests.yml          # CI/CD pipeline
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py            # Fixtures pytest
│   ├── test_rpa_cargue_ruaf.py
│   ├── test_descargar_sftp.py
│   └── fixtures/
│
├── logs/                        # Logs de ejecución
└── .gitignore                  # Archivos protegidos
```

---

## 🔧 Desarrollo

### Setup Local

```bash
# 1. Crear venv
python3 -m venv .venv
source .venv/bin/activate

# 2. Instalar dependencias
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 3. Configurar pre-commit (opcional)
pre-commit install

# 4. Ejecutar tests
pytest tests/ -v

# 5. Linting
black --check .
flake8 .
isort --check .
```

### Convenciones de Código

- **Estilo:** Black (100 caracteres)
- **Linting:** flake8 + isort
- **Type hints:** Opcionales (Python 3.9+)
- **Docstrings:** Google style (función + parámetros + return)
- **Tests:** pytest con 80%+ cobertura

### Commits

```
Format: <emoji> <tipo>: <descripción>

✅ feat:    Nueva característica
🔒 security: Cambio de seguridad
🐛 fix:     Bug fix
📚 docs:    Documentación
🧪 test:    Test/testing
♻️ refactor: Refactorización
⚡ perf:    Performance
```

---

## 🤝 Contribuciones

1. Fork el proyecto
2. Crea rama (`git checkout -b feature/amazing-feature`)
3. Commit cambios (`git commit -m "✅ Add amazing feature"`)
4. Push a rama (`git push origin feature/amazing-feature`)
5. Abre Pull Request

**Requisitos para PR:**
- ✅ Tests pasados (pytest)
- ✅ Linting pasado (flake8, black)
- ✅ Seguridad verificada (verify_security.py)
- ✅ Documentación actualizada

---

## 📖 Referencias

### Documentos internos
- [`README.md`](README.md) - Descripción general y uso
- [`DEVELOPMENT.md`](DEVELOPMENT.md) - Setup y troubleshooting
- [`SECURITY.md`](SECURITY.md) - Política de seguridad
- [`.github/workflows/tests.yml`](.github/workflows/tests.yml) - CI/CD

### Referencias externas
- [PostgreSQL COPY](https://www.postgresql.org/docs/current/sql-copy.html)
- [Paramiko SSH Library](https://www.paramiko.org/)
- [Python subprocess](https://docs.python.org/3/library/subprocess.html)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)

---

**Última actualización:** 2026-07-11
**Versión:** 1.1.0
**Mantenedor:** Carlos

---

Para preguntas sobre arquitectura, ver [`DEVELOPMENT.md`](DEVELOPMENT.md) o [`SECURITY.md`](SECURITY.md).
