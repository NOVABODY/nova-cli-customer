class NovaCliError(Exception):
    """Base class for expected CLI errors."""

    exit_code = 1


class UsageError(NovaCliError):
    exit_code = 2


class AuthError(NovaCliError):
    exit_code = 1


class TokenStoreUnavailable(UsageError):
    pass


class PollTimeout(NovaCliError):
    """A wait/poll command hit its deadline without reaching the target state."""

    exit_code = 3


class ApiError(NovaCliError):
    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        detail: object | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.detail = detail
        self.request_id = request_id
