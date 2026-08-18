# Security Policy

Security fixes are provided for the latest published release.

Do not open a public issue for a suspected vulnerability. Use the repository's private [security advisory form](https://github.com/Harry-g25/CTkKanBan/security/advisories/new).

Include the affected version, impact, reproduction steps, and suggested mitigation. Remove credentials and personal data. Host applications remain responsible for persistence security, authentication, authorization, encryption, and backups.

`ActionConfig` and the `allow_*_deletion` options control visible widget behavior
and public board methods; they are not an authorization or data-isolation
boundary. Do not expose `board.model` or unvalidated persistence operations to
untrusted callers merely because a UI action is disabled.
