## 2025-02-27 - [Sentinel] Prevent yt-dlp option injection in subprocess
**Vulnerability:** Argument/option injection vulnerability due to user-controlled URL string in `subprocess.run(["yt-dlp", ..., url])`.
**Learning:** `yt-dlp` allows passing arbitrary command-line options. A malicious user can provide a URL starting with `-` (e.g., `--exec='malicious_command'`), which is parsed as an option instead of a URL.
**Prevention:** Always use `--` (double dash) before user-provided arguments in `subprocess.run` to terminate option parsing. Example: `["yt-dlp", "--dump-json", "--", url]`.
