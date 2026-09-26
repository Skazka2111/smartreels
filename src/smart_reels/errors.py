class SmartReelsError(RuntimeError):
    """A user-facing processing error."""

    def __init__(self, message: str, *, technical_detail: str | None = None) -> None:
        super().__init__(message)
        self.technical_detail = technical_detail


class ApiError(SmartReelsError):
    pass


class MediaError(SmartReelsError):
    pass


class RenderError(SmartReelsError):
    pass
