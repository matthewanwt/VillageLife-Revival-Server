# Preserved code, not the new backend

These `.py` files are exact copies of the *source* in the user-provided
`backend.zip`, excluding `backend/private_state/`, generated `.pyc` files,
databases, images and any other private artefacts. They are here so original
behaviour, RPC formats and quirks are not lost during the rewrite.

**Do not deploy this directory as the new server.** The legacy server imports
its peers as top-level modules and expects external `analysis/` databases,
asset inventories, original archives and runtime state. Some old tests
also depend on those resources and are not part of the new green test suite.

Port one existing use case at a time into `src/villagelife/services/`, with
original protocol data and regression tests. Keep this directory unchanged as
reference evidence. When all equivalent verified tests pass, it may eventually
be archived out of the main repo.
