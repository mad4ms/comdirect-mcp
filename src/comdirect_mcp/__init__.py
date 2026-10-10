"""comdirect REST API client and MCP server."""

from importlib.metadata import PackageNotFoundError, version

from ._openapi.exceptions import ApiException
from .auth import TanChallenge
from .client import ComdirectClient
from .exceptions import AuthenticationError, ComdirectError, TanError

try:
    __version__ = version("comdirect-mcp")
except PackageNotFoundError:  # pragma: no cover - running from a source tree without installation
    __version__ = "0.0.0"

__all__ = [
    "ApiException",
    "AuthenticationError",
    "ComdirectClient",
    "ComdirectError",
    "TanChallenge",
    "TanError",
    "__version__",
]
