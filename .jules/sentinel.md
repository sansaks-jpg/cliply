
## $(date +%Y-%m-%d) - [SSRF Filter Bypass via Empty Hostname]
**Vulnerability:** The `/models` endpoint proxy had an SSRF filter bypass. It checked `if host and host not in TRUSTED_HOSTS:`. If the parsed hostname was an empty string (which can occur with certain malformed inputs or URL parsing quirks), the condition evaluated to false, allowing the request to bypass the trusted hosts check.
**Learning:** Checking for `if host` before enforcing a whitelist allows empty strings to completely bypass the whitelist validation logic. It essentially acts as an implicit allowlist for empty hostnames.
**Prevention:** Always enforce strict matching against the whitelist. If the host is empty or falsy, it should default to rejection (`if host.lower() not in TRUSTED_HOSTS:`). Rely on exact string matching or use robust IP resolution validation rather than short-circuiting truthiness checks on security boundaries.
