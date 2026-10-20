# Security policy

## Supported versions

Security fixes go into the latest release on [PyPI](https://pypi.org/p/opendata-atlas). Older versions are not patched.

## Reporting a vulnerability

Report it privately through [GitHub's vulnerability reporting](https://github.com/briandconnelly/opendata-atlas/security/advisories/new), not in a public issue. Include the version, the tool call or input that triggers it, and what happens.

Expect an acknowledgement within a week. A confirmed issue gets a fix and a GitHub security advisory crediting the reporter, unless they ask not to be named.

The server only reads public open-data portals, so the reports that matter most involve the host it runs on: the cache directory, `SOCRATA_APP_TOKEN` handling, or input that makes the server send requests anywhere other than a registered portal.
