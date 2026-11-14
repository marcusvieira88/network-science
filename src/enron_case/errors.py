"""Pipeline errors. Each maps to a documented exit code (specs/.../contracts/cli.md).

Error messages must never contain a header value, address, name or key.
"""


class PipelineError(Exception):
    exit_code = 1


class UsageError(PipelineError):
    exit_code = 2


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
