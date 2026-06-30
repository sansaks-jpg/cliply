⚡ [performance improvement] Cache API model discovery

💡 **What:**
Implemented `localStorage` caching for the API model discovery process (`getAvailableModels`) within the settings page. The list of available models is cached using a key based on the `baseUrl`. A `forceRefresh` parameter was added to the `loadModels` function to allow users to manually bypass the cache using the reload button in the UI.

🎯 **Why:**
The list of available LLM models rarely changes. Previously, the application fetched this list on every settings page load or component mount, resulting in unnecessary network requests overhead and perceived sluggishness for the user. Caching this data drastically reduces API calls and speeds up component rendering.

📊 **Measured Improvement:**
Using a mock fetch benchmark script mimicking a 300ms network delay:
- **Baseline (No Cache, 3 consecutive loads):** 901.40 ms
- **Optimized (With Cache, 1 miss, 2 hits):** 300.74 ms
- **Improvement:** ~66.6% reduction in latency for subsequent model list loads, effectively turning 300ms network overhead into <1ms local read latency on cache hits.
