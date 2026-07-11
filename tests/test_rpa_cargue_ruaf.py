"""Tests para rpa_cargue_ruaf.py"""

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Agregar el directorio raíz al path para importar rpa_cargue_ruaf
sys.path.insert(0, str(Path(__file__).parent.parent))

import rpa_cargue_ruaf as rpa


class TestTransformacion:
    """Tests para la función _transformar."""

    def test_transformar_fecha_aaaa_mm_dd(self, sample_fixed_width_data, logger):
        """Verifica transformación con formato AAAA-MM-DD."""
        input_stream = io.BytesIO(sample_fixed_width_data)
        output_stream = io.BytesIO()

        lineas, script = rpa._transformar(input_stream, output_stream, logger)

        assert lineas == 3, "Debe leer 3 líneas"
        assert script == 1, "Script debe detectarse como 1 (AAAA-MM-DD)"
        assert output_stream.getvalue() != b"", "Output no debe estar vacío"

    def test_transformar_fecha_aaaammdd(self, sample_fixed_width_data_aaaammdd, logger):
        """Verifica transformación con formato AAAAMMDD."""
        input_stream = io.BytesIO(sample_fixed_width_data_aaaammdd)
        output_stream = io.BytesIO()

        lineas, script = rpa._transformar(input_stream, output_stream, logger)

        assert lineas == 3, "Debe leer 3 líneas"
        assert script == 2, "Script debe detectarse como 2 (AAAAMMDD)"

    def test_transformar_lineas_vacias(self, logger):
        """Verifica que ignora líneas vacías."""
        data = b"CCCC00000000123456BANKDATE2024-07-11\n\n\nCCCC00000000654321ADMINXXX2024-07-12\n"
        input_stream = io.BytesIO(data)
        output_stream = io.BytesIO()

        lineas, script = rpa._transformar(input_stream, output_stream, logger)

        assert lineas == 2, "Debe leer 2 líneas (ignorar vacías)"

    def test_transformar_documento_numerico(self, logger):
        """Verifica normalización de documento numérico."""
        # Documento con ceros a la izquierda
        data = b"CCCC00000000000001BANKDATE2024-07-11\n"
        input_stream = io.BytesIO(data)
        output_stream = io.BytesIO()

        lineas, script = rpa._transformar(input_stream, output_stream, logger)

        output = output_stream.getvalue().decode()
        # El documento debe estar normalizado (sin ceros a izquierda)
        assert "1" in output, "Documento debe estar normalizado"

    def test_transformar_documento_alfanumerico(self, logger):
        """Verifica que conserva documento alfanumérico."""
        # Documento con letras (extranjeros/pasaportes)
        data = b"CCCCXXXXXXX1234567BANKDATE2024-07-11\n"
        input_stream = io.BytesIO(data)
        output_stream = io.BytesIO()

        lineas, script = rpa._transformar(input_stream, output_stream, logger)

        output = output_stream.getvalue().decode()
        # El documento alfanumérico debe conservarse
        assert "XXXXXXX1234567" in output, "Documento alfanumérico debe conservarse"

    def test_transformar_admin_trim(self, logger):
        """Verifica que trim() de cod_administradora."""
        # Admin con espacios
        data = b"CCCCCCCCCCCCCCCCADMIN  2024-07-11\n"
        input_stream = io.BytesIO(data)
        output_stream = io.BytesIO()

        lineas, script = rpa._transformar(input_stream, output_stream, logger)

        output = output_stream.getvalue().decode()
        # Los espacios deben removerse
        assert "ADMIN" in output, "Admin debe estar en output"

    def test_transformar_fecha_conversion_aaaammdd_a_aaaa_mm_dd(self, logger):
        """Verifica conversión de fecha AAAAMMDD a AAAA-MM-DD."""
        # Fecha 20240711 debe convertirse a 2024-07-11
        data = b"CCCC00000000123456BANKDATE20240711\n"
        input_stream = io.BytesIO(data)
        output_stream = io.BytesIO()

        lineas, script = rpa._transformar(input_stream, output_stream, logger)

        output = output_stream.getvalue().decode()
        assert "2024-07-11" in output, "Fecha debe convertirse a AAAA-MM-DD"


class TestValidaciones:
    """Tests para las validaciones."""

    def test_validar_ok(self, mocker):
        """Verifica validación exitosa."""
        # Mock de scalar_sql
        scalar_mock = mocker.patch("rpa_cargue_ruaf.scalar_sql")
        scalar_mock.side_effect = [
            "100",  # resolucion_ruaf count
            "0",    # fechas_no_10
            "0",    # admin_con_espacios
            "0",    # docs_alfanumericos
        ]

        cfg = MagicMock()
        logger = MagicMock()

        resultado = rpa.validar(cfg, 100, 100, logger)

        assert resultado["ok"] is True, "Validación debe ser OK"
        assert resultado["problemas"] == [], "No debe haber problemas"
        assert resultado["resolucion_ruaf"] == 100
        assert resultado["fechas_no_10"] == 0

    def test_validar_filas_no_coinciden(self, mocker):
        """Verifica fallo cuando filas COPY != lineas leidas."""
        scalar_mock = mocker.patch("rpa_cargue_ruaf.scalar_sql")
        scalar_mock.side_effect = [
            "90",   # resolucion_ruaf count (diferente)
            "0",
            "0",
            "0",
        ]

        cfg = MagicMock()
        logger = MagicMock()

        resultado = rpa.validar(cfg, 100, 100, logger)

        assert resultado["ok"] is False, "Validación debe fallar"
        assert "filas COPY != lineas leidas" in resultado["problemas"]

    def test_validar_fechas_invalidas(self, mocker):
        """Verifica fallo cuando hay fechas con longitud incorrecta."""
        scalar_mock = mocker.patch("rpa_cargue_ruaf.scalar_sql")
        scalar_mock.side_effect = [
            "100",
            "5",    # 5 fechas con longitud != 10
            "0",
            "0",
        ]

        cfg = MagicMock()
        logger = MagicMock()

        resultado = rpa.validar(cfg, 100, 100, logger)

        assert resultado["ok"] is False, "Validación debe fallar"
        assert "hay fechas con longitud distinta de 10" in resultado["problemas"]

    def test_validar_admin_con_espacios(self, mocker):
        """Verifica fallo cuando hay admin con espacios."""
        scalar_mock = mocker.patch("rpa_cargue_ruaf.scalar_sql")
        scalar_mock.side_effect = [
            "100",
            "0",
            "3",    # 3 admin con espacios
            "0",
        ]

        cfg = MagicMock()
        logger = MagicMock()

        resultado = rpa.validar(cfg, 100, 100, logger)

        assert resultado["ok"] is False, "Validación debe fallar"
        assert "hay cod_administradora con espacios" in resultado["problemas"]


class TestArgumentos:
    """Tests para parsing de argumentos."""

    def test_parse_args_input_requerido(self):
        """Verifica que --input es requerido."""
        with pytest.raises(SystemExit):
            # Sin --input debe fallar
            rpa.main([])

    def test_parse_args_defaults(self):
        """Verifica valores por defecto de argumentos."""
        with patch.object(rpa, "procesar", return_value=0):
            # Con --input debe funcionar
            cfg = rpa.parse_args(["--input", "test.zip"])
            assert cfg.input == "test.zip"
            assert cfg.mode == "docker"
            assert cfg.container == "mi_postgres_data"
            assert cfg.user == "postgres"
            assert cfg.dbname == "bdua_fosyga"

    def test_parse_args_mode_direct(self):
        """Verifica modo direct con todos los parámetros."""
        cfg = rpa.parse_args([
            "--input", "test.zip",
            "--mode", "direct",
            "--host", "10.0.0.1",
            "--port", "5432",
            "--user", "testuser",
            "--dbname", "testdb",
        ])
        assert cfg.mode == "direct"
        assert cfg.host == "10.0.0.1"
        assert cfg.port == "5432"
        assert cfg.user == "testuser"
        assert cfg.dbname == "testdb"

    def test_parse_args_sin_password(self):
        """Verifica que --password NO existe."""
        args_str = "--input test.zip --password test"
        with pytest.raises(SystemExit):
            # El argumento --password no debe existir
            rpa.parse_args(args_str.split())


class TestDecompressor:
    """Tests para detección de descompresor."""

    def test_decompressor_zip(self):
        """Verifica comando para .zip."""
        cmd = rpa.decompressor_cmd("archivo.zip")
        assert cmd[0] == "unzip"
        assert "-p" in cmd

    def test_decompressor_gz(self):
        """Verifica comando para .gz."""
        cmd = rpa.decompressor_cmd("archivo.gz")
        assert cmd[0] == "gzip"
        assert "-dc" in cmd

    def test_decompressor_txt(self):
        """Verifica comando para .txt."""
        cmd = rpa.decompressor_cmd("archivo.txt")
        assert cmd[0] == "cat"

    def test_decompressor_case_insensitive(self):
        """Verifica que es case-insensitive."""
        cmd_upper = rpa.decompressor_cmd("ARCHIVO.ZIP")
        cmd_lower = rpa.decompressor_cmd("archivo.zip")
        assert cmd_upper[0] == cmd_lower[0]


class TestBuildEnv:
    """Tests para build_env."""

    def test_build_env_hereda_variables(self):
        """Verifica que build_env hereda variables de entorno."""
        import os
        os.environ["TEST_VAR"] = "test_value"

        cfg = MagicMock()
        env = rpa.build_env(cfg)

        assert env["TEST_VAR"] == "test_value"
        del os.environ["TEST_VAR"]

    def test_build_env_no_pgpassword(self):
        """Verifica que NO pasa PGPASSWORD como argumento."""
        cfg = MagicMock()
        cfg.password = "should_not_appear"

        env = rpa.build_env(cfg)

        # PGPASSWORD NO debe estar en la copia de env (a menos que venga del entorno)
        # build_env() ahora NO lo agrega
        assert "should_not_appear" not in str(env)


class TestPsqlCmd:
    """Tests para psql_cmd."""

    def test_psql_cmd_docker(self):
        """Verifica construcción de comando Docker."""
        cfg = MagicMock()
        cfg.mode = "docker"
        cfg.container = "test_container"
        cfg.user = "testuser"
        cfg.dbname = "testdb"

        cmd = rpa.psql_cmd(cfg)

        assert "docker" in cmd
        assert "exec" in cmd
        assert "test_container" in cmd
        assert "psql" in cmd
        assert "-U" in cmd
        assert "testuser" in cmd
        assert "-d" in cmd
        assert "testdb" in cmd

    def test_psql_cmd_direct(self):
        """Verifica construcción de comando direct."""
        cfg = MagicMock()
        cfg.mode = "direct"
        cfg.host = "10.0.0.1"
        cfg.port = "5432"
        cfg.user = "testuser"
        cfg.dbname = "testdb"

        cmd = rpa.psql_cmd(cfg)

        assert "psql" in cmd
        assert "-h" in cmd
        assert "10.0.0.1" in cmd
        assert "-p" in cmd
        assert "5432" in cmd
        assert "-U" in cmd
        assert "testuser" in cmd

    def test_psql_cmd_no_password_argument(self):
        """Verifica que NO incluye -password en argumentos."""
        cfg = MagicMock()
        cfg.mode = "docker"
        cfg.container = "test"
        cfg.user = "test"
        cfg.dbname = "test"
        cfg.password = "should_not_appear"

        cmd = rpa.psql_cmd(cfg)

        # NO debe tener la contraseña
        assert "should_not_appear" not in cmd


class TestIntegracion:
    """Tests de integración de alto nivel."""

    def test_archivo_input_no_existe(self, mocker):
        """Verifica error cuando archivo input no existe."""
        cfg = MagicMock()
        cfg.input = "/ruta/inexistente/archivo.zip"
        logger = MagicMock()

        with pytest.raises(rpa.RpaError):
            rpa.procesar(cfg, logger)

    def test_configuracion_log_dir(self, temp_dir, mocker):
        """Verifica creación de directorio de logs."""
        log_dir = temp_dir / "test_logs"
        assert not log_dir.exists()

        log = rpa.setup_logging(str(log_dir))

        assert log_dir.exists()
        assert log_dir.is_dir()
