import datetime
import io
import threading

_last_request_id = -1
_request_id_lock = threading.Lock()


def request_id() -> str:
    """
    Client request id for the x-http-request-info header: a 9-digit number in the format HHmmssSSS
    (API docs 1.2.2). Unique within the process: requests in the same millisecond count up.
    """
    global _last_request_id
    now = datetime.datetime.now()
    value = int(now.strftime("%H%M%S")) * 1000 + now.microsecond // 1000
    with _request_id_lock:
        # Count up on collisions, but accept the reset to small values after midnight.
        if _last_request_id >= value > _last_request_id - 60_000:
            value = _last_request_id + 1
        _last_request_id = value
    return f"{value % 1_000_000_000:09d}"


def is_valid_tan(tan: str) -> bool:
    return isinstance(tan, str) and len(tan) == 6 and tan.isdigit()


def default_photo_tan_callback(png_bytes: bytes) -> str:
    from PIL import Image

    Image.open(io.BytesIO(png_bytes)).show()
    tan = input("Enter Photo-TAN: ")
    if not is_valid_tan(tan):
        raise ValueError("Invalid Photo-TAN")
    return tan


def default_sms_tan_callback() -> str:
    tan = input("Enter SMS-TAN: ")
    if not is_valid_tan(tan):
        raise ValueError("Invalid SMS-TAN")
    return tan


def default_push_tan_callback() -> str:
    input("Approve the login in the photoTAN app, then press Enter")
    return ""  # no TAN is sent for push approvals
