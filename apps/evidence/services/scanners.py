from __future__ import annotations

import subprocess

from django.conf import settings
from django.utils.module_loading import import_string


class ClamAVCommandScanner:
    """Scan bytes through ClamAV stdin without creating plaintext files."""

    def scan(self, content: bytes) -> str:
        executable = getattr(settings, "CLAMAV_EXECUTABLE", "clamscan")
        timeout = int(getattr(settings, "MALWARE_SCAN_TIMEOUT_SECONDS", 30))
        if timeout <= 0:
            return "FAILED"

        try:
            result = subprocess.run(
                [executable, "--no-summary", "-"],
                input=content,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.SubprocessError):
            return "FAILED"

        if result.returncode == 0:
            return "CLEAN"
        if result.returncode == 1:
            return "INFECTED"
        return "FAILED"


def get_public_upload_scanner():
    backend = getattr(
        settings,
        "PUBLIC_UPLOAD_MALWARE_SCANNER",
        "apps.evidence.services.scanners.ClamAVCommandScanner",
    )
    scanner_class = import_string(backend)
    return scanner_class()
