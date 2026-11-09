"""Stable domain exceptions; transport adapters map these into client-specific errors."""


class VillageLifeError(Exception):
    """Base exception for expected game-service failures."""


class NotImplementedRule(VillageLifeError):
    """Original behaviour has not been sufficiently verified to implement."""


class InvalidAction(VillageLifeError):
    """A command does not satisfy verified domain invariants."""


class RevisionConflict(VillageLifeError):
    """The save changed since the client last observed it."""


class DuplicateActionConflict(VillageLifeError):
    """An idempotency key was reused with different inputs."""


class NotFound(VillageLifeError):
    """Requested account, village or resource does not exist."""


class MigrationConflict(VillageLifeError):
    """Previously imported legacy data differs from the source now supplied."""
