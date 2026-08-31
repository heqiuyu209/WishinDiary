# Security Policy

## Reporting a vulnerability

Do not open a public issue for suspected vulnerabilities involving credentials,
authentication, private health data, or model files.

Use GitHub's **Private vulnerability reporting** entry on the repository
Security page whenever it is available. Include the affected version or commit,
reproduction steps, impact, and a minimal proof of concept that contains no real
user data. If private reporting has not been enabled yet, contact the repository
maintainer privately and wait for a secure response channel before sending
sensitive details.

Please allow a reasonable remediation window before public disclosure. Never
test against an installation or data set that you do not own or have explicit
permission to assess.

## Local secrets

- Never commit `.env`, database passwords, JWT secrets, credentials, or local
  health data.
- Use `wishindiary-api/scripts/setup_local.ps1` to create a local `.env` and a
  cryptographically random `SECRET_KEY`.
- Do not commit model artifacts unless they are intentionally released and
  their license, provenance, and SHA-256 checksum are documented.
- Revoke and rotate any credential immediately if it is accidentally committed;
  deleting the file from the latest commit is not sufficient.

## Data scope

WishinDiary handles sensitive health information. Use synthetic data in demos,
tests, and pull requests. Production deployments should use HTTPS, restricted
database access, encrypted backups, and a documented deletion policy.

## Supported versions

Security fixes are provided for the latest commit on the default branch. Until
versioned releases are published, older snapshots should be treated as
unsupported.
