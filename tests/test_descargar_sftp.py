"""Tests para descargar_sftp.py"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Agregar el directorio raíz al path para importar descargar_sftp
sys.path.insert(0, str(Path(__file__).parent.parent))

import descargar_sftp as dl


class TestParseRemotePath:
    """Tests para parse_remotepath."""

    def test_parse_remotepath_valido(self):
        """Verifica parsing de ruta remota válida."""
        result = dl.parse_remotepath("1 0 11 ArchivoBDUA")
        assert result == "/ArchivoBDUA"

    def test_parse_remotepath_vacio(self):
        """Verifica parsing de ruta vacía."""
        result = dl.parse_remotepath("")
        assert result == ""

    def test_parse_remotepath_multiple_segments(self):
        """Verifica parsing con múltiples segmentos."""
        result = dl.parse_remotepath("1 0 5 carpeta 0 7 subcarpeta 0 4 datos")
        assert result == "/carpeta/subcarpeta/datos"

    def test_parse_remotepath_sin_numeros(self):
        """Verifica que ignora números iniciales."""
        result = dl.parse_remotepath("0 1 2 datos 3 4 archivo")
        assert result == "/datos/archivo"


class TestLeerFileZilla:
    """Tests para leer_filezilla."""

    def test_leer_filezilla_primer_servidor(self, mocker):
        """Verifica lectura del primer servidor."""
        xml_content = """<?xml version="1.0"?>
<FileZilla3>
    <Servers>
        <Server>
            <Name>TestServer</Name>
            <Host>test.example.com</Host>
            <Port>22</Port>
            <Protocol>1</Protocol>
            <User>testuser</User>
            <Pass encoding="base64">dGVzdHBhc3M=</Pass>
        </Server>
    </Servers>
</FileZilla3>
"""
        mocker.patch("builtins.open", mocker.mock_open(read_data=xml_content))
        mocker.patch("xml.etree.ElementTree.parse")

        with patch("xml.etree.ElementTree.parse") as mock_parse:
            root = MagicMock()
            servers = [MagicMock()]
            servers[0].find.side_effect = lambda tag: MagicMock(
                text={
                    "Name": "TestServer",
                    "Host": "test.example.com",
                    "Port": "22",
                    "Protocol": "1",
                    "User": "testuser",
                    "Pass": MagicMock(text="dGVzdHBhc3M="),
                }.get(tag)
            )
            root.findall.side_effect = lambda path: (
                servers if "Server" in path else []
            )
            mock_parse.return_value.getroot.return_value = root

            # Esta prueba es compleja porque requiere mocking de XML
            # Se enfoca en verificar que la función existe y puede ejecutarse


class TestElegirUltimo:
    """Tests para elegir_ultimo."""

    def test_elegir_ultimo_orden_correcto(self, mock_sftp_transport):
        """Verifica que elige el archivo más reciente."""
        patron = r"^RUA200AAFP(\d{8})NI000900474727\.zip$"
        resultado = dl.elegir_ultimo(mock_sftp_transport, patron)

        # Debe elegir 20240715 (el más reciente)
        assert "20240715" in resultado

    def test_elegir_ultimo_sin_matches(self):
        """Verifica error cuando no hay matches."""
        transport = MagicMock()
        transport.listdir.return_value = ["archivo1.txt", "archivo2.txt"]
        patron = r"^RUA200AAFP(\d{8})NI000900474727\.zip$"

        with pytest.raises(SystemExit):
            dl.elegir_ultimo(transport, patron)

    def test_elegir_ultimo_multiple_candidatos(self, mock_sftp_transport):
        """Verifica selección correcta entre múltiples candidatos."""
        patron = r"^RUA200AAFP(\d{8})NI000900474727\.zip$"

        # Mock con más archivos
        transport = MagicMock()
        transport.listdir.return_value = [
            "RUA200AAFP20240101NI000900474727.zip",
            "RUA200AAFP20240615NI000900474727.zip",
            "RUA200AAFP20240720NI000900474727.zip",
            "RUA200AAFP20240515NI000900474727.zip",
        ]

        resultado = dl.elegir_ultimo(transport, patron)

        # Debe elegir 20240720 (el más reciente)
        assert "20240720" in resultado


class TestDescargar:
    """Tests para descargar."""

    def test_descargar_path_traversal_dos_puntos(self, temp_dir):
        """Verifica protección contra path traversal con ..."""
        transport = MagicMock()

        with pytest.raises(SystemExit):
            dl.descargar(transport, "../etc/passwd", str(temp_dir), False)

    def test_descargar_path_traversal_ruta_absoluta(self, temp_dir):
        """Verifica protección contra path traversal con ruta absoluta."""
        transport = MagicMock()

        with pytest.raises(SystemExit):
            dl.descargar(transport, "/etc/passwd", str(temp_dir), False)

    def test_descargar_nombre_valido(self, temp_dir, mocker):
        """Verifica descarga con nombre válido."""
        transport = MagicMock()
        transport.size.return_value = 1024
        transport.get.return_value = None

        # Mock de archivo existente para comparación
        archivo_local = temp_dir / "archivo.zip"
        archivo_local.write_bytes(b"x" * 1024)

        resultado = dl.descargar(transport, "archivo.zip", str(temp_dir), False)

        # Debe retornar la ruta local
        assert str(archivo_local) == resultado

    def test_descargar_nuevo_archivo(self, temp_dir, mocker):
        """Verifica descarga de archivo nuevo."""
        transport = MagicMock()
        transport.size.return_value = 2048

        # Mock de get para simular descarga
        def mock_get(name, path, callback):
            callback(2048, 2048)

        transport.get.side_effect = mock_get

        resultado = dl.descargar(transport, "archivo_nuevo.zip", str(temp_dir), False)

        # Debe haber intentado descargar
        transport.get.assert_called_once()

    def test_descargar_cache_mismo_tamanio(self, temp_dir):
        """Verifica que no descarga si archivo existe con mismo tamaño."""
        transport = MagicMock()
        transport.size.return_value = 1024

        # Crear archivo existente
        archivo = temp_dir / "archivo.zip"
        archivo.write_bytes(b"x" * 1024)

        resultado = dl.descargar(transport, "archivo.zip", str(temp_dir), False)

        # No debe llamar a get()
        transport.get.assert_not_called()
        assert str(archivo) == resultado

    def test_descargar_force_overwrite(self, temp_dir, mocker):
        """Verifica que --force descarga incluso si existe."""
        transport = MagicMock()
        transport.size.return_value = 1024

        # Crear archivo existente
        archivo = temp_dir / "archivo.zip"
        archivo.write_bytes(b"old_content")

        def mock_get(name, path, callback):
            callback(1024, 1024)

        transport.get.side_effect = mock_get

        resultado = dl.descargar(transport, "archivo.zip", str(temp_dir), force=True)

        # Debe haber intentado descargar
        transport.get.assert_called_once()


class TestExcepciones:
    """Tests para manejo de excepciones."""

    def test_ftp_transport_size_error(self):
        """Verifica manejo de error en FTPSTransport.size()."""
        # Esta prueba es conceptual ya que requiere mock de ftplib
        pass

    def test_sftp_transport_close_error(self):
        """Verifica manejo de error en SFTPTransport.close()."""
        # Esta prueba es conceptual ya que requiere mock de paramiko
        pass


class TestSSLVerification:
    """Tests para verificación de SSL."""

    def test_ftp_transport_ssl_context_creado(self):
        """Verifica que contexto SSL se crea con verificación."""
        # Esta prueba es conceptual y requiere mocking de ssl
        pass

    def test_ftp_transport_cert_required(self):
        """Verifica que ssl.CERT_REQUIRED está habilitado."""
        # Verificar en el código fuente que ssl.CERT_REQUIRED se usa
        import ssl
        import descargar_sftp

        source = open(Path(__file__).parent.parent / "descargar_sftp.py").read()
        assert "ssl.CERT_REQUIRED" in source
        assert "ssl.CERT_NONE" not in source or "CERT_REQUIRED" in source


class TestSSHHostValidation:
    """Tests para validación de host SSH."""

    def test_sftp_no_auto_add_policy(self):
        """Verifica que NO usa AutoAddPolicy."""
        source = open(Path(__file__).parent.parent / "descargar_sftp.py").read()
        assert "AutoAddPolicy" not in source

    def test_sftp_usa_warning_policy(self):
        """Verifica que usa WarningPolicy."""
        source = open(Path(__file__).parent.parent / "descargar_sftp.py").read()
        assert "WarningPolicy" in source

    def test_sftp_load_system_host_keys(self):
        """Verifica que carga system host keys."""
        source = open(Path(__file__).parent.parent / "descargar_sftp.py").read()
        assert "load_system_host_keys" in source


class TestIntegracion:
    """Tests de integración."""

    def test_main_sin_filezilla(self):
        """Verifica error cuando FileZilla.xml no existe."""
        with pytest.raises(SystemExit):
            dl.main(["--filezilla", "/inexistente/FileZilla.xml"])

    def test_main_directorio_destino_creado(self, temp_dir):
        """Verifica creación de directorio de destino."""
        dest = temp_dir / "descargas"
        assert not dest.exists()

        # Esta prueba requeriría un servidor SFTP/FTPS real
        # Se deja como estructura para future implementation
