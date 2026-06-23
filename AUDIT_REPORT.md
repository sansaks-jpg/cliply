# Code Audit Report — Cliply

> **Generated:** 24 Jun 2026
> **Methodology:** ECC skills audit pipeline (`codebase-inspection`, `security-review`, `coding-standards`, `frontend-patterns`, `backend-patterns`)
> **Scope:** Full monorepo (Next.js 15 frontend + Python FastAPI backend + Tauri v2 wrapper)

---

## Summary

| Category | Count |
|----------|-------|
| 🔴 Critical | 3 |
| 🟠 High | 5 |
| 🟡 Medium | 4 |
| 🟢 Low | 3 |
| **Total** | **15** |

---

## 🔴 Critical

### C1. Garbled TypeScript `***` in function signature — api.ts

**File:** `frontend/src/lib/api.ts:148`
```typescript
export async function getAvailableModels(baseUrl: string, apiKey: *** Promise<string[]> {
```

**Problem:** Literal `***` in type annotation position. `: string)` is missing after `apiKey`, plus missing `):` before `Promise`. Causes TypeScript compilation error.

**Impact:** `getAvailableModels()` won't compile. The Settings page (`loadModels` caller) also broken.

**Fix:**
```typescript
export async function getAvailableModels(baseUrl: string, apiKey: string): Promise<string[]> {
```

---

### C2. Garbled TypeScript `***` in function signature — settings/page.tsx

**File:** `frontend/src/app/settings/page.tsx:129`
```typescript
const loadModels = async (baseUrl: string, apiKey: *** => {
```

**Problem:** Same `***` garbled pattern. Causes TypeScript error.

**Fix:**
```typescript
const loadModels = async (baseUrl: string, apiKey: string) => {
```

---

### C3. localStorage migration removes the wrong key

**File:** `frontend/src/app/page.tsx:314-315`
```typescript
localStorage.setItem("cliply_recent_tasks", legacy);        // line 314 — copies to new key
localStorage.removeItem("cliply_recent_tasks");              // line 315 — ✗ removes the NEW key
```

**Problem:** After copying data from legacy key `"clip_ai_recent_tasks"` to the new `"cliply_recent_tasks"`, line 315 removes the **new** key instead of the legacy one. The migrated data is immediately lost.

**Impact:** All recent task history is deleted on every page load if the user still has the legacy key.

**Fix:**
```typescript
localStorage.setItem("cliply_recent_tasks", legacy);
localStorage.removeItem("clip_ai_recent_tasks");             // ✓ remove the legacy key
```

---

## 🟠 High

### H1. `print()` instead of logging in transcriber.py

**File:** `backend/app/engine/transcriber.py` (30+ occurrences)

**Problem:** Raw `print(f"[transcribe] ...", flush=True)` scattered throughout the file instead of using `logger.info()` / `logger.warning()`. No structured logging, no severity levels, no context propagation.

**Impact:** Logs are not controllable by log level. Cannot filter, cannot redirect. Noise in stdout.

**Fix:** Replace all `print(...)` with `logger.info(...)` / `logger.warning(...)`.

---

### H2. `/health` endpoint swallows all exceptions

**File:** `backend/app/main.py:94`
```python
except Exception:
    pass
```

**Problem:** Any error in `ping_redis()` is silently ignored. Even `ConnectionResetError`, `RedisError`, or `AttributeError` are suppressed.

**Impact:** Health endpoint might return misleading `redis: false` without reporting why. Debugging redis issues becomes harder.

**Fix:** Log the exception instead of silent pass:
```python
except Exception as e:
    logger.warning("Health check redis ping failed: %s", e)
```

---

### H3. API key sent as URL query parameter

**File:** `frontend/src/lib/api.ts:151-154`
```typescript
const params = new URLSearchParams({
    base_url: baseUrl,
    api_key: apiKey
});
const res = await fetch(`${API_URL}/models?${params.toString()}`);
```

**Problem:** API key is transmitted as a `?api_key=sk-...` query parameter. URLs are logged by web servers, proxies, and browser history.

**Impact:** API key could leak through server access logs, nginx logs, or referrer headers.

**Fix:** Send API key in a custom header instead (e.g., `X-API-Key`) via the backend proxy, or use POST body.

---

### H4. No input validation on `encoder` field

**File:** `backend/app/routes/tasks.py:51`
```python
encoder: Optional[str] = Field(default=None, description="...")
```

**Problem:** `encoder` accepts any arbitrary string. Allowed values are `auto | nvidia | intel | amd | cpu`, but there is no validation constraint. If an invalid value is passed, `config.resolve_encoder()` silently falls back to CPU.

**Impact:** Silent fallback means users might think HW encoding is active when it's using CPU. No validation error feedback.

**Fix:** Add a `pattern` or use a `Literal` type:
```python
encoder: Optional[str] = Field(default=None, pattern=r"^(auto|nvidia|intel|amd|cpu)$")
```

---

### H5. `/models` endpoint has no rate limiting

**File:** `backend/app/main.py:116-147`

**Problem:** The `/models` proxy endpoint accepts a user-supplied URL and API key, fetches from it, and returns the result. No rate limiting, no auth. It's an open proxy that could be abused as a blind SSRF or credential relay.

**Impact:** If exposed publicly, this is a security risk — potential SSRF, credential theft, or abuse as an open redirect-like proxy.

**Fix:** Add rate limiting, validate `base_url` against allowed patterns (localhost-only for Tauri users), and consider removing the API key forwarding entirely.

---

## 🟡 Medium

### M1. Missing loading/skeleton state when switching clips

**File:** `frontend/src/app/tasks/page.tsx:418-498`

**Problem:** When the user clicks a different clip in the right panel, the video player briefly goes blank while the new video loads. There's no skeleton, spinner, or transition state.

**Impact:** Perceived lag. Users might think the UI is stuck.

**Fix:** Wrap the video player in a transition state that shows a loading indicator while `activeClipHref` is loading (use `onLoadStart` / `onCanPlay` events).

---

### M2. `onProgress` event handler duplicates `handleTimeUpdate`

**File:** `frontend/src/components/vertical-player.tsx:163-165`
```typescript
onTimeUpdate={handleTimeUpdate}
onProgress={handleTimeUpdate}
```

**Problem:** Both `timeupdate` and `progress` events fire `handleTimeUpdate`. The `progress` event fires more frequently, causing excessive state updates and potential React re-renders unnecessarily.

**Impact:** Unnecessary re-renders on every progress event. `handleTimeUpdate` also reads `buffered` which is already provided by `onProgress` natively.

**Fix:** Create separate handlers:
```typescript
onTimeUpdate={handleTimeUpdate}
onProgress={(e) => { ... handle buffered separately ... }}
```

---

### M3. Fallback polling runs even when SSE is connected

**File:** `frontend/src/app/tasks/page.tsx:294-303`

**Problem:** A 5-second polling interval (`setInterval(refresh, 5000)`) runs alongside the SSE connection. Both update the same state simultaneously.

**Impact:** Redundant API calls. Could cause race conditions where polling overwrites SSE data with stale responses.

**Fix:** Disable polling when SSE is active. Only enable polling as fallback after SSE errors.

---

### M4. `CREDENTIALS` env var never used

**File:** `backend/app/config.py`

**Problem:** No `CREDENTIALS` or similar env var is read in config. The `.env` file might contain legacy keys. Dead config code or undocumented required variables.

**Impact:** Maintainability — if someone adds `.env` expecting `CREDENTIALS` to be read, it won't work.

**Fix:** Remove unused env var references or document all expected vars.

---

## 🟢 Low

### L1. `console.error` in catch blocks without user feedback

**File:** Various frontend files

**Problem:** Several `catch` blocks only call `console.error(err)` without showing a toast or user-facing error. Example: `page.tsx:238` in `handleSetupComplete`.

**Fix:** Add user-facing error toasts in all catch blocks.

---

### L2. Hardcoded fallback models when baseUrl is empty

**File:** `frontend/src/lib/api.ts:149`
```typescript
if (!baseUrl) return ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"];
```

**Problem:** Returns hardcoded model list which may not match the user's actual provider. May confuse users when they select a model that doesn't exist.

**Fix:** Return empty array and let the UI show a "no models — configure base URL" message.

---

### L3. `smart_crop.py` not a separate file

**File:** `AGENTS.md + backend/app/engine/`

**Problem:** `AGENTS.md` and `pipeline.py` reference `smart_crop.py` as a separate engine module, but all smart crop logic is embedded inside `render.py` as private functions (`_detect_faces`, `_smart_crop_plan`, etc.).

**Impact:** Misleading for new developers trying to understand the architecture.

**Fix:** Either extract smart_crop into a separate file, or update AGENTS.md to reflect the actual file structure.

---

## Stats Reference

| Metric | Value |
|--------|-------|
| Total LOC | 8,982 |
| Python | 4,825 LOC (31 files) |
| TSX/TS | 3,073 LOC (35 files) |
| Rust | 414 LOC (3 files) |
| Duplicate files | 9 detected |
| Hardcoded secrets | 0 ✅ |
| Shell injection vectors | 0 ✅ |
| eval/exec usage | 0 ✅ |
| Path traversal | 0 ✅ |

---

*Report generated using `codebase-inspection`, `security-review`, `coding-standards`, and `frontend-patterns` ECC skills.*
