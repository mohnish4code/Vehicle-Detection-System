class AppError(Exception):
    """An error with a message that is safe to show to the user.

    The API turns these into {"error": {"code", "message", "details"}} with the
    given HTTP status. Anything that isn't an AppError becomes a generic 500.
    """

    status = 500
    code = "INTERNAL_ERROR"

    def __init__(self, message: str, *, code: str | None = None, status: int | None = None, details=None):
        super().__init__(message)
        self.message = message
        self.details = details
        if code:
            self.code = code
        if status:
            self.status = status

    def to_dict(self) -> dict:
        body = {"code": self.code, "message": self.message}
        if self.details is not None:
            body["details"] = self.details
        return body
