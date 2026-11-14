"""Pipeline errors. Each maps to a documented exit code (specs/.../contracts/cli.md).

Error messages must never contain a header value, address, name or key.
"""


class PipelineError(Exception):
    exit_code = 1


class UsageError(PipelineError):
    exit_code = 2


class PrerequisiteMissing(PipelineError):
    """A tool the one command needs is missing or too old, or the port or disk is not free."""

    exit_code = 1


class StepFailed(PipelineError):
    """A step of the one command failed; carries that step's own exit code."""

    def __init__(self, exit_code: int) -> None:
        super().__init__(f"step failed with exit code {exit_code}")
        self.exit_code = exit_code


class KeyProblem(PipelineError):
    """Key missing, too short, or stored inside the repository."""

    exit_code = 3


class CorpusError(PipelineError):
    """Corpus download failed or checksum mismatch."""

    exit_code = 4


class ContractViolation(PipelineError):
    """A table does not match its schema in contracts/schemas.py."""

    exit_code = 5


class PrivacyViolation(PipelineError):
    """Zone guard, minimum group size, identifier pattern or canary failure."""

    exit_code = 6


class PseudonymCollision(PipelineError):
    exit_code = 7
