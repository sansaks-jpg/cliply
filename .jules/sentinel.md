## 2025-02-14 - Fix SSRF TOCTOU vulnerability in API Proxy

**Vulnerability:** The `/models` proxy endpoint previously validated hostnames against a string whitelist (`localhost`, `127.0.0.1`, `0.0.0.0`) to prevent Server-Side Request Forgery. However, this was vulnerable to DNS rebinding bypass or redirect-following because requests.get could resolve alternative IPs or follow redirects to internal non-whitelisted IPs.

**Learning:** String-based hostname whitelisting is not sufficient for SSRF protection because it ignores DNS resolution mechanics and Time-of-Check to Time-of-Use (TOCTOU) windows. Relying on default redirect-following in proxy endpoints creates additional SSRF vectors.

**Prevention:** Always perform asynchronous DNS resolution (e.g. `asyncio.get_running_loop().getaddrinfo`) prior to making HTTP requests in a proxy context. Validate the resolved IP using Python's `ipaddress` module to ensure it falls within acceptable constraints (e.g. `ip_obj.is_loopback`). Finally, rewrite the destination URL to use the validated IP address to eliminate TOCTOU and disable request redirects to prevent redirect bypasses, injecting the original hostname into the `Host` header if necessary to maintain virtual-host compatibility.
