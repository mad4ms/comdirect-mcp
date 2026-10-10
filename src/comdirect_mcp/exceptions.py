class ComdirectError(Exception):
    """Base exception for all comdirect API errors."""


class AuthenticationError(ComdirectError):
    pass


class TanError(AuthenticationError):
    pass


class TransactionFilterError(ComdirectError):
    """A transaction filter is invalid or cannot be applied to incomplete data."""


class DataError(ComdirectError):
    """An API result is ambiguous or incomplete and cannot be used safely."""
