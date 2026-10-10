class ComdirectError(Exception):
    """Base exception for all comdirect API errors."""


class AuthenticationError(ComdirectError):
    pass


class TanError(AuthenticationError):
    pass
