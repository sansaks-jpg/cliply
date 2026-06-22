"""Hardware encoder detection via WMI + ffmpeg probing.

Results are cached after first call to avoid repeated subprocess invocations.
"""
import logging
import os
import re
import subprocess
from typing import Optional

log = logging.getLogger(__name__)

# Prevent console windows flashing on Windows
CREATION_FLAGS = 0
if os.name == "nt":
    CREATION_FLAGS = 0x08000000 # subprocess.CREATE_NO_WINDOW

_ENCODER_CACHE: Optional[dict[str, bool]] = None


def detect_encoders() -> dict[str, bool]:
    """Return a dict of {encoder_key: available} for nvidia, intel, amd.

    Result is cached after the first call.
    """
    global _ENCODER_CACHE
    if _ENCODER_CACHE is not None:
        return _ENCODER_CACHE

    gpu_vendors: set[str] = set()
    try:
        output = subprocess.run(
            ["powershell", "-Command",
             "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True, timeout=10,
            creationflags=CREATION_FLAGS,
        ).stdout.lower()
        gpu_vendors.update(re.findall(r"(nvidia|intel|amd|advanced micro devices|ati radeon)", output))
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("GPU vendor detection failed: %s", exc)

    has_nvidia_hw = "nvidia" in gpu_vendors
    has_intel_hw = "intel" in gpu_vendors
    has_amd_hw = bool(gpu_vendors & {"amd", "advanced micro devices", "ati radeon"})

    ff_nvenc = ff_qsv = ff_amf = False
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
            creationflags=CREATION_FLAGS,
        ).stdout.lower()
        ff_nvenc = "nvenc" in out
        ff_qsv = "qsv" in out
        ff_amf = "amf" in out
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("ffmpeg encoder probing failed: %s", exc)

    result: dict[str, bool] = {
        "nvidia": has_nvidia_hw and ff_nvenc,
        "intel":  has_intel_hw and ff_qsv,
        "amd":    has_amd_hw and ff_amf,
    }
    _ENCODER_CACHE = result
    return result
