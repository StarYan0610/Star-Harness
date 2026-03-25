from __future__ import annotations


class CodingAgentError(Exception):
    pass


class ValidationError(CodingAgentError):
    pass


class UsageError(ValidationError):
    pass


class BootstrapError(CodingAgentError):
    pass


class ProjectValidationError(ValidationError):
    pass


class StateTransitionError(CodingAgentError):
    pass
