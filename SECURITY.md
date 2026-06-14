# Security Policy

## Supported versions

Security fixes are provided for the latest published minor release. Upgrade to the newest PyPI release before reporting an issue that may already be fixed.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use the repository's private [security advisory form](https://github.com/Harry-g25/CTkKanBan/security/advisories/new).

Include the affected version, impact, reproduction steps, and any suggested mitigation. Remove credentials, database contents, and personal data. You should receive an acknowledgement within seven days and a status update as investigation proceeds.

## Scope

Reports involving unsafe deserialization, SQL injection in the SQLite adapter, mutation authorization assumptions, release-pipeline compromise, or accidental credential exposure are especially useful. Applications remain responsible for authentication, authorization, encryption, backups, and database access controls around their custom data source.

