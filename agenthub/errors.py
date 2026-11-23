"""The one error type of AgentHub's domain code; the API turns it into an HTTP response."""


class HubError(Exception):
    """A refused request about tasks, tickets, users, settings or harness runs."""

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.status = status
