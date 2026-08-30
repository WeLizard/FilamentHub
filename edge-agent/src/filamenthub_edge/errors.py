"""Expected Edge runtime failures."""


class EdgeError(Exception):
    """Base class for an actionable runtime failure."""


class ConfigurationError(EdgeError):
    """The local runtime configuration is invalid."""


class StateError(EdgeError):
    """Persistent Edge state cannot be loaded or saved safely."""


class HttpRequestError(EdgeError):
    """An HTTP peer could not satisfy a bounded JSON request."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AuthenticationError(HttpRequestError):
    """The FilamentHub bridge token is invalid or revoked."""


class IdentityConflict(HttpRequestError):
    """A snapshot belongs to a different device; retrying it cannot fix the binding."""


class PairingRequired(EdgeError):
    """A new one-time pairing code is required."""


class ProviderUnavailable(EdgeError):
    """The configured local provider is unavailable or returned invalid data."""
