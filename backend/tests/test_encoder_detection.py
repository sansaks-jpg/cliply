import pytest
import subprocess
from unittest.mock import Mock, patch
from app.services import encoder_detection

@pytest.fixture(autouse=True)
def reset_cache():
    encoder_detection._ENCODER_CACHE = None
    yield
    encoder_detection._ENCODER_CACHE = None

def mock_subprocess_run_success(*args, **kwargs):
    cmd = args[0] if args else kwargs.get('args', [])
    if "powershell" in cmd:
        mock_stdout = Mock()
        mock_stdout.stdout = "NVIDIA GeForce RTX 3080\nIntel(R) UHD Graphics\nAMD Radeon(TM) Graphics"
        return mock_stdout
    elif "ffmpeg" in cmd:
        mock_stdout = Mock()
        mock_stdout.stdout = "nvenc qsv amf"
        return mock_stdout
    return Mock(stdout="")

def mock_subprocess_run_missing_ffmpeg(*args, **kwargs):
    cmd = args[0] if args else kwargs.get('args', [])
    if "powershell" in cmd:
        mock_stdout = Mock()
        mock_stdout.stdout = "NVIDIA GeForce RTX 3080\nIntel(R) UHD Graphics\nAMD Radeon(TM) Graphics"
        return mock_stdout
    elif "ffmpeg" in cmd:
        mock_stdout = Mock()
        mock_stdout.stdout = "libx264"
        return mock_stdout
    return Mock(stdout="")

def mock_subprocess_run_missing_hardware(*args, **kwargs):
    cmd = args[0] if args else kwargs.get('args', [])
    if "powershell" in cmd:
        mock_stdout = Mock()
        mock_stdout.stdout = "Microsoft Basic Display Adapter"
        return mock_stdout
    elif "ffmpeg" in cmd:
        mock_stdout = Mock()
        mock_stdout.stdout = "nvenc qsv amf"
        return mock_stdout
    return Mock(stdout="")

def test_detect_encoders_all_available():
    with patch("subprocess.run", side_effect=mock_subprocess_run_success):
        result = encoder_detection.detect_encoders()
        assert result == {"nvidia": True, "intel": True, "amd": True}

def test_detect_encoders_missing_ffmpeg():
    with patch("subprocess.run", side_effect=mock_subprocess_run_missing_ffmpeg):
        result = encoder_detection.detect_encoders()
        assert result == {"nvidia": False, "intel": False, "amd": False}

def test_detect_encoders_missing_hardware():
    with patch("subprocess.run", side_effect=mock_subprocess_run_missing_hardware):
        result = encoder_detection.detect_encoders()
        assert result == {"nvidia": False, "intel": False, "amd": False}

def test_detect_encoders_subprocess_timeout(caplog):
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="cmd", timeout=10)):
        result = encoder_detection.detect_encoders()
        assert result == {"nvidia": False, "intel": False, "amd": False}
        assert "GPU vendor detection failed" in caplog.text

def test_detect_encoders_subprocess_oserror(caplog):
    with patch("subprocess.run", side_effect=OSError("Test OS Error")):
        result = encoder_detection.detect_encoders()
        assert result == {"nvidia": False, "intel": False, "amd": False}
        assert "GPU vendor detection failed" in caplog.text

def test_detect_encoders_caching():
    mock_run = Mock(side_effect=mock_subprocess_run_success)
    with patch("subprocess.run", mock_run):
        result1 = encoder_detection.detect_encoders()
        result2 = encoder_detection.detect_encoders()

        assert result1 == {"nvidia": True, "intel": True, "amd": True}
        assert result2 == {"nvidia": True, "intel": True, "amd": True}
        assert result1 is result2

        # subprocess.run should only be called twice (once for powershell, once for ffmpeg) during the first detect_encoders call
        assert mock_run.call_count == 2
