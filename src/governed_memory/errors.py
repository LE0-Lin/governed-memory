class Denied(PermissionError):
    """The current credential cannot perform this operation."""


class Conflict(ValueError):
    """The reviewed revision or lifecycle state no longer permits this change."""


class PolicyUnavailable(RuntimeError):
    """An explicitly enabled policy engine could not provide a valid decision."""
