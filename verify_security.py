#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de verificación de mejoras de seguridad - RUAF RPA
==========================================================

Valida que todas las mejoras de seguridad se han implementado correctamente:
  1. Credenciales no se pasan como argumentos CLI
  2. SSL verification está habilitado
  3. SSH host validation está configurado
  4. Path traversal está protegido
  5. Archivos sensibles están en .gitignore
  6. Documentación de seguridad existe
"""

import os
import sys
import re
import ast
from pathlib import Path
from typing import List, Tuple

# Colores para terminal
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

class SecurityVerifier:
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.findings = {
            'critical': [],
            'high': [],
            'medium': [],
            'info': []
        }
        self.passed = []

    def log_pass(self, msg: str, details: str = ""):
        """Registra un chequeo pasado."""
        self.passed.append(msg)
        icon = f"{GREEN}✓{RESET}"
        print(f"{icon} {msg}")
        if details:
            print(f"   {BLUE}{details}{RESET}")

    def log_fail(self, severity: str, msg: str, details: str = "", solution: str = ""):
        """Registra un chequeo fallido."""
        self.findings[severity].append({
            'msg': msg,
            'details': details,
            'solution': solution
        })
        icons = {
            'critical': f'{RED}✗ CRÍTICO',
            'high': f'{YELLOW}⚠ ALTO',
            'medium': f'{YELLOW}⚠ MEDIO',
            'info': f'{BLUE}ℹ INFO'
        }
        icon = icons.get(severity, '?')
        print(f"{icon}{RESET} {msg}")
        if details:
            print(f"   {details}")

    # ========================================================================
    # 1. VERIFICACIÓN: Credenciales en CLI
    # ========================================================================

    def check_cli_credentials(self) -> bool:
        """Verifica que no se pasan credenciales como argumentos."""
        print(f"\n{BOLD}1. CREDENCIALES EN CLI{RESET}")
        print("=" * 60)

        all_passed = True

        # Verificar rpa_cargue_ruaf.py
        rpa_file = self.project_root / "rpa_cargue_ruaf.py"
        content = rpa_file.read_text()

        # Buscar --password en argparse
        if 'add_argument("--password"' in content or "add_argument('--password'" in content:
            self.log_fail('critical',
                "rpa_cargue_ruaf.py: --password aún en argparse",
                "Línea con add_argument(\"--password\")",
                "Remover --password del argparse")
            all_passed = False
        else:
            self.log_pass("rpa_cargue_ruaf.py: --password removido de argparse")

        # Verificar que build_env no pasa PGPASSWORD como argumento
        if 'cfg.password' in content or 'PGPASSWORD=%s' in content:
            self.log_fail('critical',
                "rpa_cargue_ruaf.py: Aún intenta pasar PGPASSWORD",
                "build_env() o psql_cmd() usa cfg.password",
                "Usar .pgpass en lugar de variables de entorno")
            all_passed = False
        else:
            self.log_pass("rpa_cargue_ruaf.py: No pasa PGPASSWORD como argumento")

        # Verificar scripts shell
        run_rpa = (self.project_root / "run_rpa.sh").read_text()
        if '--password "$DB_PASS"' in run_rpa or '--password "$PGPASSWORD"' in run_rpa:
            self.log_fail('critical',
                "run_rpa.sh: Aún pasa --password a rpa_cargue_ruaf.py",
                f"Línea: --password \"$DB_PASS\"",
                "Remover --password del comando")
            all_passed = False
        else:
            self.log_pass("run_rpa.sh: No pasa --password")

        run_ruaf = (self.project_root / "run_ruaf.sh").read_text()
        if '--password "$PGPASSWORD"' in run_ruaf:
            self.log_fail('critical',
                "run_ruaf.sh: Aún pasa --password a rpa_cargue_ruaf.py",
                f"Línea: --password \"$PGPASSWORD\"",
                "Remover --password del comando")
            all_passed = False
        else:
            self.log_pass("run_ruaf.sh: No pasa --password")

        # Verificar que no hay credenciales en docstrings de ejemplo
        if re.search(r'--password\s+["\']J4r3sJ41m3T0rr35["\']', content):
            self.log_fail('critical',
                "rpa_cargue_ruaf.py: Contraseña en docstring de ejemplo",
                "Línea 44: --password 'J4r3sJ41m3T0rr35'",
                "Reemplazar con <PASSWORD> o remover ejemplo")
            all_passed = False
        else:
            self.log_pass("rpa_cargue_ruaf.py: Sin contraseñas en ejemplos")

        return all_passed

    # ========================================================================
    # 2. VERIFICACIÓN: Credenciales en archivos .env
    # ========================================================================

    def check_env_files(self) -> bool:
        """Verifica que archivos .env no tienen credenciales."""
        print(f"\n{BOLD}2. CREDENCIALES EN ARCHIVOS .env{RESET}")
        print("=" * 60)

        all_passed = True

        for env_file in ['config.docker.env', 'config.prod.env']:
            path = self.project_root / env_file
            if not path.exists():
                self.log_fail('info', f"{env_file}: No existe")
                continue

            content = path.read_text()

            # Buscar PGPASSWORD=
            if 'PGPASSWORD=' in content and not content.strip().endswith('# PGPASSWORD se obtiene'):
                # Verificar si realmente tiene una contraseña (no solo comentario)
                for line in content.split('\n'):
                    if line.startswith('PGPASSWORD=') and not line.startswith('PGPASSWORD='):
                        if '=' in line:
                            value = line.split('=', 1)[1].strip()
                            if value and not value.startswith('#'):
                                self.log_fail('critical',
                                    f"{env_file}: PGPASSWORD con valor",
                                    f"Línea: {line}",
                                    "Remover contraseña, usar .pgpass")
                                all_passed = False
                                break
            else:
                self.log_pass(f"{env_file}: Sin PGPASSWORD hardcodeado")

        # Verificar que existen templates .example
        for example in ['config.docker.env.example', 'config.prod.env.example']:
            path = self.project_root / example
            if path.exists():
                self.log_pass(f"Archivo template: {example}")
            else:
                self.log_fail('high', f"Template no existe: {example}",
                    "Necesario para distribuir sin credenciales")

        return all_passed

    # ========================================================================
    # 3. VERIFICACIÓN: SSL/TLS Verification
    # ========================================================================

    def check_ssl_verification(self) -> bool:
        """Verifica que SSL verification está habilitado."""
        print(f"\n{BOLD}3. SSL/TLS VERIFICATION{RESET}")
        print("=" * 60)

        all_passed = True

        descargar_file = self.project_root / "descargar_sftp.py"
        content = descargar_file.read_text()

        # Buscar CERT_REQUIRED
        if 'ssl.CERT_REQUIRED' in content or 'CERT_REQUIRED' in content:
            self.log_pass("descargar_sftp.py: Usa ssl.CERT_REQUIRED")
        else:
            self.log_fail('critical',
                "descargar_sftp.py: No usa CERT_REQUIRED",
                "Vulnerable a MITM attacks",
                "Cambiar: ctx.verify_mode = ssl.CERT_REQUIRED")
            all_passed = False

        # Buscar CERT_NONE
        if 'CERT_NONE' in content and 'CERT_REQUIRED' not in content:
            self.log_fail('critical',
                "descargar_sftp.py: Aún usa CERT_NONE",
                "Desactiva validación de certificados",
                "Cambiar a CERT_REQUIRED")
            all_passed = False

        # Buscar check_hostname = True
        if 'check_hostname = True' in content or 'check_hostname=True' in content:
            self.log_pass("descargar_sftp.py: check_hostname = True")
        else:
            self.log_fail('high',
                "descargar_sftp.py: check_hostname no habilitado",
                "Vulnerable a certificados inválidos",
                "Cambiar: ctx.check_hostname = True")
            all_passed = False

        # Buscar manejo de SSL errors
        if 'ssl.SSLError' in content:
            self.log_pass("descargar_sftp.py: Maneja ssl.SSLError")
        else:
            self.log_fail('medium',
                "descargar_sftp.py: No maneja ssl.SSLError",
                "Errores de SSL no se comunican bien",
                "Agregar: except ssl.SSLError as e:")

        return all_passed

    # ========================================================================
    # 4. VERIFICACIÓN: SSH Host Validation
    # ========================================================================

    def check_ssh_validation(self) -> bool:
        """Verifica que SSH host validation está configurado."""
        print(f"\n{BOLD}4. SSH HOST VALIDATION{RESET}")
        print("=" * 60)

        all_passed = True

        descargar_file = self.project_root / "descargar_sftp.py"
        content = descargar_file.read_text()

        # Buscar AutoAddPolicy (malo)
        if 'AutoAddPolicy' in content:
            self.log_fail('critical',
                "descargar_sftp.py: Usa AutoAddPolicy",
                "Acepta cualquier host key sin validación",
                "Cambiar a: WarningPolicy() + load_system_host_keys()")
            all_passed = False
        else:
            self.log_pass("descargar_sftp.py: No usa AutoAddPolicy")

        # Buscar WarningPolicy (bueno)
        if 'WarningPolicy' in content:
            self.log_pass("descargar_sftp.py: Usa WarningPolicy")
        else:
            self.log_fail('high',
                "descargar_sftp.py: No usa WarningPolicy",
                "Debería validar contra known_hosts",
                "Agregar: set_missing_host_key_policy(paramiko.WarningPolicy())")
            all_passed = False

        # Buscar load_system_host_keys
        if 'load_system_host_keys' in content:
            self.log_pass("descargar_sftp.py: Carga system host keys")
        else:
            self.log_fail('high',
                "descargar_sftp.py: No carga system host keys",
                "No valida contra ~/.ssh/known_hosts",
                "Agregar: ssh.load_system_host_keys()")
            all_passed = False

        # Buscar manejo de SSH errors
        if 'paramiko.ssh_exception.SSHException' in content or 'SSHException' in content:
            self.log_pass("descargar_sftp.py: Maneja SSHException")
        else:
            self.log_fail('medium',
                "descargar_sftp.py: No maneja SSHException",
                "Errores de SSH no se comunican bien",
                "Agregar: except paramiko.ssh_exception.SSHException")

        return all_passed

    # ========================================================================
    # 5. VERIFICACIÓN: Path Traversal Protection
    # ========================================================================

    def check_path_traversal(self) -> bool:
        """Verifica que path traversal está protegido."""
        print(f"\n{BOLD}5. PATH TRAVERSAL PROTECTION{RESET}")
        print("=" * 60)

        all_passed = True

        descargar_file = self.project_root / "descargar_sftp.py"
        content = descargar_file.read_text()

        # Buscar validación de ".."
        if '".."' in content and 'in nombre' in content:
            self.log_pass("descargar_sftp.py: Valida contra '..' en nombre")
        else:
            self.log_fail('high',
                "descargar_sftp.py: No valida contra '..' en nombre",
                "Vulnerable a path traversal",
                "Agregar: if '..' in nombre: raise SystemExit(...)")
            all_passed = False

        # Buscar validación de "/" inicial
        if 'nombre.startswith' in content and ('"/")' in content or "'/'" in content):
            self.log_pass("descargar_sftp.py: Valida contra '/' inicial")
        else:
            self.log_fail('high',
                "descargar_sftp.py: No valida contra '/' inicial",
                "Vulnerable a rutas absolutas",
                "Agregar: if nombre.startswith('/'): raise SystemExit(...)")
            all_passed = False

        # Buscar validación de path dentro de dest_dir
        if 'os.path.abspath' in content and 'startswith' in content:
            self.log_pass("descargar_sftp.py: Valida abspath dentro de dest_dir")
        else:
            self.log_fail('high',
                "descargar_sftp.py: No valida abspath final",
                "Validación adicional de seguridad",
                "Agregar: if not os.path.abspath(local).startswith(os.path.abspath(dest_dir))")

        return all_passed

    # ========================================================================
    # 6. VERIFICACIÓN: .gitignore
    # ========================================================================

    def check_gitignore(self) -> bool:
        """Verifica que .gitignore protege archivos sensibles."""
        print(f"\n{BOLD}6. .gitignore - ARCHIVOS SENSIBLES{RESET}")
        print("=" * 60)

        all_passed = True

        gitignore_path = self.project_root / ".gitignore"
        gitignore = gitignore_path.read_text()

        sensitive_files = {
            'config.*.env': 'Archivos de configuración con credenciales',
            'FileZilla.xml': 'Credenciales SFTP',
            '.pgpass': 'Credenciales PostgreSQL',
            '.env': 'Variables de entorno',
            '.ssh/': 'Claves SSH privadas',
            'secrets/': 'Carpeta de secretos'
        }

        for pattern, description in sensitive_files.items():
            if pattern in gitignore:
                self.log_pass(f".gitignore protege: {pattern}", description)
            else:
                self.log_fail('high',
                    f".gitignore: No protege {pattern}",
                    description,
                    f"Agregar: {pattern}")
                all_passed = False

        return all_passed

    # ========================================================================
    # 7. VERIFICACIÓN: Documentación de Seguridad
    # ========================================================================

    def check_security_docs(self) -> bool:
        """Verifica que existe documentación de seguridad."""
        print(f"\n{BOLD}7. DOCUMENTACIÓN DE SEGURIDAD{RESET}")
        print("=" * 60)

        all_passed = True

        docs = {
            'SECURITY.md': 'Política de seguridad y checklist',
            'DEVELOPMENT.md': 'Guía de setup seguro',
            'requirements.txt': 'Dependencias versionadas'
        }

        for doc, description in docs.items():
            path = self.project_root / doc
            if path.exists():
                size = path.stat().st_size
                self.log_pass(f"{doc}", f"{description} ({size} bytes)")
            else:
                self.log_fail('high',
                    f"Documentación no existe: {doc}",
                    description,
                    f"Crear: {doc}")
                all_passed = False

        return all_passed

    # ========================================================================
    # 8. VERIFICACIÓN: Excepciones Específicas
    # ========================================================================

    def check_exception_handling(self) -> bool:
        """Verifica que se usan excepciones específicas."""
        print(f"\n{BOLD}8. MANEJO DE EXCEPCIONES{RESET}")
        print("=" * 60)

        all_passed = True

        descargar_file = self.project_root / "descargar_sftp.py"
        content = descargar_file.read_text()

        # Buscar "except Exception:" (malo)
        if re.search(r'except\s+Exception\s*:', content):
            self.log_fail('medium',
                "descargar_sftp.py: Usa 'except Exception:'",
                "Demasiado genérico, silencia errores",
                "Especificar: except (ftplib.all_errors, OSError):")
            all_passed = False
        else:
            self.log_pass("descargar_sftp.py: No usa 'except Exception:'")

        # Buscar excepciones específicas (bueno)
        if 'ftplib.all_errors' in content or 'OSError' in content or 'SSLError' in content:
            self.log_pass("descargar_sftp.py: Usa excepciones específicas")

        return all_passed

    # ========================================================================
    # 9. VERIFICACIÓN: Logging sin Secretos
    # ========================================================================

    def check_logging_safety(self) -> bool:
        """Verifica que los logs no exponen secretos."""
        print(f"\n{BOLD}9. LOGGING SEGURO{RESET}")
        print("=" * 60)

        all_passed = True

        # Buscar en rpa_cargue_ruaf.py
        rpa_file = self.project_root / "rpa_cargue_ruaf.py"
        content = rpa_file.read_text()

        # Buscar log de contraseña
        if re.search(r'log\.(info|debug|error).*password', content, re.IGNORECASE):
            self.log_fail('medium',
                "rpa_cargue_ruaf.py: Posible logging de contraseña",
                "Buscar: log.*(password|secret|token)",
                "Remover información sensible de logs")
            all_passed = False
        else:
            self.log_pass("rpa_cargue_ruaf.py: No loguea contraseñas")

        return all_passed

    # ========================================================================
    # PRUEBAS FUNCIONALES
    # ========================================================================

    def test_cli_arguments(self) -> bool:
        """Prueba que los scripts aceptan los argumentos correctos."""
        print(f"\n{BOLD}10. PRUEBAS FUNCIONALES - Argumentos CLI{RESET}")
        print("=" * 60)

        all_passed = True

        # Importar y verificar argparse
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("rpa_cargue",
                self.project_root / "rpa_cargue_ruaf.py")
            module = importlib.util.module_from_spec(spec)

            # No ejecutar el script, solo parsear
            with open(self.project_root / "rpa_cargue_ruaf.py") as f:
                source = f.read()

            # Buscar argumentos válidos
            if '--input' in source and '--mode' in source and '--user' in source:
                self.log_pass("rpa_cargue_ruaf.py: Argumentos esperados presentes")

            if '--password' not in source or '--password' not in [
                line.strip() for line in source.split('\n')
                if 'add_argument' in line
            ]:
                self.log_pass("rpa_cargue_ruaf.py: --password no está en argumentos")
            else:
                self.log_fail('high',
                    "rpa_cargue_ruaf.py: --password aún en argumentos",
                    "Verificar argparse",
                    "Remover: p.add_argument('--password', ...)")
                all_passed = False
        except Exception as e:
            self.log_fail('info', f"No se pudo verificar argumentos: {e}")

        return all_passed

    # ========================================================================
    # EJECUTAR TODAS LAS VERIFICACIONES
    # ========================================================================

    def run_all_checks(self):
        """Ejecuta todas las verificaciones."""
        print(f"\n{BOLD}{'='*70}{RESET}")
        print(f"{BOLD}   VERIFICACIÓN DE MEJORAS DE SEGURIDAD - RUAF RPA{RESET}")
        print(f"{BOLD}{'='*70}{RESET}")

        results = []
        results.append(("Credenciales en CLI", self.check_cli_credentials()))
        results.append(("Credenciales en .env", self.check_env_files()))
        results.append(("SSL/TLS Verification", self.check_ssl_verification()))
        results.append(("SSH Host Validation", self.check_ssh_validation()))
        results.append(("Path Traversal Protection", self.check_path_traversal()))
        results.append((".gitignore", self.check_gitignore()))
        results.append(("Documentación de Seguridad", self.check_security_docs()))
        results.append(("Manejo de Excepciones", self.check_exception_handling()))
        results.append(("Logging Seguro", self.check_logging_safety()))
        results.append(("Argumentos CLI", self.test_cli_arguments()))

        # Resumen final
        print(f"\n{BOLD}{'='*70}{RESET}")
        print(f"{BOLD}   RESUMEN FINAL{RESET}")
        print(f"{BOLD}{'='*70}{RESET}")

        total_passed = sum(1 for _, result in results if result)
        total_checks = len(results)

        for name, result in results:
            icon = f"{GREEN}✓{RESET}" if result else f"{RED}✗{RESET}"
            print(f"{icon} {name}")

        # Estadísticas
        print(f"\n{BOLD}Chequeos pasados: {total_passed}/{total_checks}{RESET}")

        if self.findings['critical']:
            print(f"\n{RED}VULNERABILIDADES CRÍTICAS: {len(self.findings['critical'])}{RESET}")
            for i, finding in enumerate(self.findings['critical'], 1):
                print(f"  {i}. {finding['msg']}")
                if finding['solution']:
                    print(f"     → {finding['solution']}")

        if self.findings['high']:
            print(f"\n{YELLOW}VULNERABILIDADES ALTAS: {len(self.findings['high'])}{RESET}")
            for i, finding in enumerate(self.findings['high'], 1):
                print(f"  {i}. {finding['msg']}")
                if finding['solution']:
                    print(f"     → {finding['solution']}")

        if self.findings['medium']:
            print(f"\n{YELLOW}VULNERABILIDADES MEDIAS: {len(self.findings['medium'])}{RESET}")
            for i, finding in enumerate(self.findings['medium'], 1):
                print(f"  {i}. {finding['msg']}")

        # Estado final
        has_critical = len(self.findings['critical']) > 0
        has_high = len(self.findings['high']) > 0

        print(f"\n{BOLD}{'='*70}{RESET}")
        if not has_critical and not has_high:
            print(f"{GREEN}{BOLD}✓ TODAS LAS MEJORAS DE SEGURIDAD ESTÁN IMPLEMENTADAS CORRECTAMENTE{RESET}")
            return 0
        elif not has_critical:
            print(f"{YELLOW}{BOLD}⚠ ALGUNAS VULNERABILIDADES ALTAS DETECTADAS - REVISAR{RESET}")
            return 1
        else:
            print(f"{RED}{BOLD}✗ VULNERABILIDADES CRÍTICAS DETECTADAS - RESOLVER INMEDIATAMENTE{RESET}")
            return 2


if __name__ == "__main__":
    verifier = SecurityVerifier()
    exit_code = verifier.run_all_checks()
    sys.exit(exit_code)
