"""Temporary-device ID rules from the official material."""

TEMP_DEVICE_PREFIX = "TMP"


def is_temp_device_id(device_id: object) -> bool:
    return str(device_id or "").strip().upper().startswith(TEMP_DEVICE_PREFIX)


def ensure_temp_device_id(value: object) -> str:
    normalized = str(value or "").strip().upper()
    if not normalized:
        raise ValueError("Temporary device ID cannot be empty")
    if normalized.startswith(TEMP_DEVICE_PREFIX):
        return normalized
    return f"{TEMP_DEVICE_PREFIX}{normalized}"
