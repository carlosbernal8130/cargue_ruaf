"""Configuración y fixtures compartidas para tests."""

import io
import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def logger():
    """Logger para tests."""
    log = logging.getLogger("test_logger")
    log.setLevel(logging.INFO)
    handler = logging.StreamHandler(io.StringIO())
    log.addHandler(handler)
    return log


@pytest.fixture
def temp_dir():
    """Directorio temporal para tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_fixed_width_data():
    """Datos de ejemplo en formato ancho fijo (AAAA-MM-DD)."""
    return (
        b"CCCC00000000123456BANKDATE2024-07-11\n"
        b"CCCC00000000654321ADMINXXX2024-07-12\n"
        b"CCCC99999999000000OTHERXX2024-07-13\n"
    )


@pytest.fixture
def sample_fixed_width_data_aaaammdd():
    """Datos de ejemplo en formato ancho fijo (AAAAMMDD)."""
    return (
        b"CCCC00000000123456BANKDATE20240711\n"
        b"CCCC00000000654321ADMINXXX20240712\n"
        b"CCCC99999999000000OTHERXX20240713\n"
    )


@pytest.fixture
def sample_pgpass_file(temp_dir):
    """Archivo .pgpass de ejemplo para testing."""
    pgpass_path = temp_dir / ".pgpass"
    pgpass_content = """
127.0.0.1:5432:testdb:testuser:testpass
10.0.0.1:5432:proddb:produser:prodpass
"""
    pgpass_path.write_text(pgpass_content)
    pgpass_path.chmod(0o600)
    return pgpass_path


@pytest.fixture
def mock_subprocess_run(mocker):
    """Mock de subprocess.run para testing."""
    mock = mocker.patch("subprocess.run")
    mock.return_value = MagicMock(
        returncode=0,
        stdout="COPY 100",
        stderr="",
    )
    return mock


@pytest.fixture
def mock_psql_connection(mocker):
    """Mock de conexión PostgreSQL."""
    mock = mocker.patch("subprocess.Popen")
    mock_instance = MagicMock()
    mock_instance.communicate.return_value = (b"COPY 100", b"")
    mock_instance.returncode = 0
    mock_instance.stdin = io.BytesIO()
    mock_instance.stdout = io.BytesIO()
    mock.return_value = mock_instance
    return mock


@pytest.fixture
def mock_sftp_transport(mocker):
    """Mock de transporte SFTP para testing."""
    mock = MagicMock()
    mock.listdir.return_value = [
        "RUA200AAFP20240601NI000900474727.zip",
        "RUA200AAFP20240715NI000900474727.zip",
        "RUA200AAFP20240710NI000900474727.zip",
    ]
    mock.size.return_value = 1024 * 1024  # 1 MB
    mock.get.return_value = None
    return mock


@pytest.fixture
def mock_ftp_transport(mocker):
    """Mock de transporte FTPS para testing."""
    mock = MagicMock()
    mock.listdir.return_value = [
        "RUA200AAFP20240601NI000900474727.zip",
        "RUA200AAFP20240715NI000900474727.zip",
        "RUA200AAFP20240710NI000900474727.zip",
    ]
    mock.size.return_value = 2048 * 1024  # 2 MB
    mock.get.return_value = None
    return mock
