# Security, privacy and publication notes

- Keep repository private while reviewing ownership and rights. Private GitHub
  repos are not appropriate storage for credentials or player data.
- Only locally authored code and user-provided backend source is included.
  Original APKs, XAPKs, OBBs, artwork, music and database assets are excluded.
- `backend/private_state/`, invitations/access keys, UUID mappings, player
  histories, saves, logs and any real API token must NEVER be committed.
- Legacy player access tokens are not silently migrated to the new API.
- New API binds loopback and checks bearer tokens and village ownership; this
  is development authentication, not a complete production identity provider.
- For hosted use, implement TLS termination, rate limits, dedicated account
  onboarding, token rotation/revocation, secrets management and abuse controls.
- SQLite is suitable for one host on a local disk. Do not use a live WAL
  database inside OneDrive/Dropbox/network shares. Use the SQLite backup API.
- Recovery exports carry save data in plaintext inside a ZIP. Encrypt or store
  securely, and never assume checksums prove authenticity or prevent tampering.
- Imported legacy state may contain sensitive names or personal information.
  The importer is designed for privately held local files, not public uploads.
- This code does not establish redistribution rights to original game assets,
  binaries, server materials or trademarks.
