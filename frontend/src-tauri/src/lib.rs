use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};
use tauri::{Emitter, Manager};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

const BACKEND_START_TIMEOUT: Duration = Duration::from_secs(30);
const BACKEND_POLL_INTERVAL: Duration = Duration::from_millis(500);
const LOG_MAX_SIZE: u64 = 5 * 1024 * 1024; // 5 MB
const LOG_MAX_FILES: u32 = 3;
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

pub struct BackendState {
    pub child: Mutex<Option<Child>>,
    pub monitor_cancel: Arc<AtomicBool>,
}

fn kill_child(mut child: Child) {
    #[cfg(windows)]
    {
        let pid = child.id();
        let mut cmd = Command::new("taskkill");
        cmd.args(["/F", "/T", "/PID", &pid.to_string()]);
        cmd.creation_flags(CREATE_NO_WINDOW);
        let _ = cmd.output();
    }
    #[cfg(not(windows))]
    {
        let _ = child.kill();
        let _ = child.wait();
    }
}

impl Drop for BackendState {
    fn drop(&mut self) {
        self.monitor_cancel.store(true, Ordering::SeqCst);
        if let Ok(mut guard) = self.child.lock() {
            if let Some(child) = guard.take() {
                kill_child(child);
            }
        }
    }
}

#[derive(serde::Serialize, serde::Deserialize, Clone, Debug)]
pub struct AppSettings {
    pub storage_dir: String,
    pub first_run: bool,
    pub gemini_api_key: String,
    pub groq_api_key: String,
    pub openai_api_key: String,
    pub openai_base_url: String,
    pub openai_model: String,
    pub llm_provider: String,
}

/// Cari direktori backend saat runtime — relatif terhadap executable atau CWD.
fn find_backend_dir(app: &tauri::AppHandle) -> Option<PathBuf> {
    // 1. Coba relatif terhadap resource_dir (Tauri bundle)
    let resource_based = app
        .path()
        .resource_dir()
        .ok()
        .map(|r| r.join("backend"));

    // 2. Coba relatif terhadap direktori executable
    let exe_based = std::env::current_exe()
        .ok()
        .and_then(|e| e.parent().map(|p| p.to_path_buf()))
        .map(|p| p.join("backend"));

    // 3. Coba direktori kerja saat ini (development mode)
    let cwd_based = std::env::current_dir().ok().map(|p| p.join("backend"));

    // 4. Coba satu level di atas CWD (ketika CWD = frontend/)
    let parent_based = std::env::current_dir()
        .ok()
        .and_then(|p| p.parent().map(|pp| pp.to_path_buf()))
        .map(|p| p.join("backend"));

    #[cfg(debug_assertions)]
    let dev_source_based = Some(
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .parent()
            .unwrap()
            .join("backend"),
    );

    #[cfg(debug_assertions)]
    let candidates: Vec<PathBuf> = [resource_based, exe_based, cwd_based, parent_based, dev_source_based]
        .into_iter()
        .flatten()
        .collect();

    #[cfg(not(debug_assertions))]
    let candidates: Vec<PathBuf> = [resource_based, exe_based, cwd_based, parent_based]
        .into_iter()
        .flatten()
        .collect();

    for p in &candidates {
        if p.join("app").join("main.py").exists()
            || p.join("cliply_server.exe").exists()
            || p.join("cliply_server").exists()
            || p.join("dist").join("cliply_server.exe").exists()
            || p.join("dist").join("cliply_server").exists()
        {
            log::info!("Backend ditemukan di: {:?}", p);
            return Some(p.canonicalize().unwrap_or(p.clone()));
        }
    }

    log::warn!("Backend tidak ditemukan di semua kandidat path: {:?}", candidates);
    None
}

fn find_python(backend_dir: &PathBuf) -> Option<PathBuf> {
    let candidates = if cfg!(target_os = "windows") {
        vec![
            backend_dir.join(".venv").join("Scripts").join("python.exe"),
            PathBuf::from("python"),
        ]
    } else {
        vec![
            backend_dir.join(".venv").join("bin").join("python3"),
            backend_dir.join(".venv").join("bin").join("python"),
            PathBuf::from("python3"),
            PathBuf::from("python"),
        ]
    };
    for p in &candidates {
        let is_system_cmd = p
            .to_str()
            .map_or(false, |s| !s.contains('\\') && !s.contains('/'));
        if p.is_file() || is_system_cmd {
            log::info!("Python ditemukan di: {:?}", p);
            return Some(p.clone());
        }
    }
    None
}

fn get_config_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let config_dir = app.path().app_config_dir().map_err(|e| e.to_string())?;
    if !config_dir.exists() {
        fs::create_dir_all(&config_dir).map_err(|e| e.to_string())?;
    }
    Ok(config_dir.join("settings.json"))
}

fn get_log_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let log_dir = app.path().app_log_dir().map_err(|e| e.to_string())?;
    if !log_dir.exists() {
        fs::create_dir_all(&log_dir).map_err(|e| e.to_string())?;
    }
    Ok(log_dir.join("backend.log"))
}

fn load_settings(app: &tauri::AppHandle) -> AppSettings {
    let default_storage = app
        .path()
        .app_data_dir()
        .map(|p| p.join("workspace"))
        .unwrap_or_else(|_| PathBuf::from("workspace"))
        .to_string_lossy()
        .into_owned();

    let mut settings = AppSettings {
        storage_dir: default_storage,
        first_run: true,
        gemini_api_key: "".to_string(),
        groq_api_key: "".to_string(),
        openai_api_key: "".to_string(),
        openai_base_url: "".to_string(),
        openai_model: "gpt-4o-mini".to_string(),
        llm_provider: "openai".to_string(),
    };

    if let Ok(config_path) = get_config_path(app) {
        if config_path.exists() {
            if let Ok(content) = fs::read_to_string(&config_path) {
                if let Ok(loaded) = serde_json::from_str::<AppSettings>(&content) {
                    return loaded;
                } else if let Ok(loaded_val) = serde_json::from_str::<serde_json::Value>(&content) {
                    if let Some(s) = loaded_val.get("storage_dir").and_then(|v| v.as_str()) {
                        settings.storage_dir = s.to_string();
                    }
                    if let Some(f) = loaded_val.get("first_run").and_then(|v| v.as_bool()) {
                        settings.first_run = f;
                    }
                    if let Some(g) = loaded_val.get("gemini_api_key").and_then(|v| v.as_str()) {
                        settings.gemini_api_key = g.to_string();
                    }
                    if let Some(g) = loaded_val.get("groq_api_key").and_then(|v| v.as_str()) {
                        settings.groq_api_key = g.to_string();
                    }
                    if let Some(o) = loaded_val.get("openai_api_key").and_then(|v| v.as_str()) {
                        settings.openai_api_key = o.to_string();
                    }
                    if let Some(u) = loaded_val.get("openai_base_url").and_then(|v| v.as_str()) {
                        settings.openai_base_url = u.to_string();
                    }
                    if let Some(m) = loaded_val.get("openai_model").and_then(|v| v.as_str()) {
                        settings.openai_model = m.to_string();
                    }
                    if let Some(l) = loaded_val.get("llm_provider").and_then(|v| v.as_str()) {
                        settings.llm_provider = l.to_string();
                    }
                }
            }
        }
    }

    settings
}

fn save_settings(app: &tauri::AppHandle, settings: &AppSettings) -> Result<(), String> {
    let config_path = get_config_path(app)?;
    let content = serde_json::to_string_pretty(settings).map_err(|e| e.to_string())?;
    fs::write(config_path, content).map_err(|e| e.to_string())?;
    Ok(())
}

fn log_line(file: &mut fs::File, msg: &str) {
    let ts = chrono::Local::now().format("%Y-%m-%d %H:%M:%S");
    let _ = writeln!(file, "{} [INFO] {}", ts, msg);
}

fn stream_to_log<R: BufRead + Send + 'static>(reader: R, mut log_file: fs::File, prefix: &'static str) {
    thread::spawn(move || {
        for line in reader.lines() {
            if let Ok(l) = line {
                let ts = chrono::Local::now().format("%Y-%m-%d %H:%M:%S");
                let _ = writeln!(log_file, "{} [{}] {}", ts, prefix, l);
            }
        }
    });
}

fn rotate_logs(log_path: &PathBuf) {
    if !log_path.exists() {
        return;
    }
    if let Ok(meta) = log_path.metadata() {
        if meta.len() < LOG_MAX_SIZE {
            return;
        }
    }
    // Shift existing backups: backend.2.log → gone, backend.1.log → backend.2.log, etc.
    for i in (1..LOG_MAX_FILES).rev() {
        let old = log_path.with_extension(format!("{}.log", i));
        let new = log_path.with_extension(format!("{}.log", i + 1));
        if old.exists() {
            let _ = fs::rename(&old, &new);
        }
    }
    // Rotate current → backend.1.log
    let first = log_path.with_extension("1.log");
    let _ = fs::rename(log_path, &first);
}

fn spawn_backend_monitor(app: &tauri::AppHandle) {
    let app_clone = app.clone();
    let cancel = app_clone.state::<BackendState>().monitor_cancel.clone();
    // Reset cancel flag so this monitor runs; any previous monitor will see it was cancelled
    // via the sleep+check cycle (it checks cancel before emitting events).
    // We also set cancel=true briefly in start_backend_process before calling this.
    cancel.store(false, Ordering::SeqCst);
    thread::spawn(move || {
        loop {
            thread::sleep(Duration::from_secs(3));
            if cancel.load(Ordering::SeqCst) {
                return; // Another monitor replaced us
            }
            let exit_status = {
                let state = app_clone.state::<BackendState>();
                let mut guard = match state.child.lock() {
                    Ok(g) => g,
                    Err(_) => return,
                };
                guard.as_mut().and_then(|c| c.try_wait().ok().flatten())
            };
            if let Some(status) = exit_status {
                if !cancel.load(Ordering::SeqCst) {
                    let code = status.code().unwrap_or(-1);
                    let _ = app_clone.emit("backend-crashed", code);
                }
                return;
            }
        }
    });
}

fn start_backend_process(
    app: &tauri::AppHandle,
    state: &tauri::State<'_, BackendState>,
    storage_dir: &str,
    settings: &AppSettings,
) -> Result<(), String> {
    // 0. Initial diagnostics
    let log_path = get_log_path(app)?;
    {
        let mut f = fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log_path)
            .map_err(|e| format!("Cannot open log file {:?}: {}", log_path, e))?;
        log_line(&mut f, "=== Cliply Backend ===");
    }

    // 1. Rotate logs if needed
    rotate_logs(&log_path);

    // 2. Open log file (fresh or after rotation)
    let mut log_file = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .map_err(|e| format!("Cannot open log file {:?}: {}", log_path, e))?;

    log_line(&mut log_file, &format!("Log file: {:?}", log_path));
    log_line(&mut log_file, &format!("Backend version: {}", env!("CARGO_PKG_VERSION")));
    log_line(&mut log_file, "Port: 8003");
    if let Ok(res_dir) = app.path().resource_dir() {
        log_line(&mut log_file, &format!("Resource directory: {:?}", res_dir));
    }
    if let Ok(exe_path) = std::env::current_exe() {
        log_line(&mut log_file, &format!("Tauri executable: {:?}", exe_path));
    }
    if let Ok(cwd) = std::env::current_dir() {
        log_line(&mut log_file, &format!("Current directory: {:?}", cwd));
    }

    // 3. Kill old process if any
    {
        let mut proc_guard = state.child.lock().map_err(|e| e.to_string())?;
        if let Some(mut child) = proc_guard.take() {
            log_line(&mut log_file, "Killing previous backend process...");
            let _ = child.kill();
            let _ = child.wait();
        }
    }

    // 4. Locate backend directory
    let backend_dir = find_backend_dir(app).ok_or_else(|| "Backend directory not found".to_string())?;
    log_line(&mut log_file, &format!("Backend directory: {:?}", backend_dir));

    // 5. Check for compiled cliply_server executable
    let exe_name = if cfg!(target_os = "windows") { "cliply_server.exe" } else { "cliply_server" };
    let compiled_exe = backend_dir.join(exe_name);
    let dist_dir = backend_dir.join("dist").join(exe_name);

    let mut cmd = if compiled_exe.exists() {
        log_line(&mut log_file, &format!("Using executable: {:?}", compiled_exe));
        let mut c = Command::new(&compiled_exe);
        c.args(["--storage-dir", storage_dir, "--port", "8003"]);
        c
    } else if dist_dir.exists() {
        log_line(&mut log_file, &format!("Using executable: {:?}", dist_dir));
        let mut c = Command::new(&dist_dir);
        c.args(["--storage-dir", storage_dir, "--port", "8003"]);
        c
    } else {
        let python = find_python(&backend_dir).ok_or_else(|| "Python tidak ditemukan".to_string())?;
        log_line(&mut log_file, &format!("Using Python: {:?}", python));
        let mut c = Command::new(&python);
        c.args(["-m", "uvicorn", "app.main:app", "--port", "8003", "--host", "127.0.0.1"]);
        c
    };

    // 6. Capture stdout + stderr
    // Only inject env vars when the Tauri setting is non-empty.
    // Empty values would override the backend .env file (load_dotenv uses
    // override=False), silently wiping keys the user configured in .env.
    cmd.stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .current_dir(&backend_dir)
        .env("STORAGE_DIR", storage_dir);
    if !settings.gemini_api_key.is_empty() {
        cmd.env("GEMINI_API_KEY", &settings.gemini_api_key);
    }
    if !settings.groq_api_key.is_empty() {
        cmd.env("GROQ_API_KEY", &settings.groq_api_key);
    }
    if !settings.openai_api_key.is_empty() {
        cmd.env("OPENAI_API_KEY", &settings.openai_api_key);
    }
    if !settings.openai_base_url.is_empty() {
        cmd.env("OPENAI_BASE_URL", &settings.openai_base_url);
    }
    if !settings.openai_model.is_empty() {
        cmd.env("OPENAI_MODEL", &settings.openai_model);
    }
    if !settings.llm_provider.is_empty() {
        cmd.env("LLM_PROVIDER", &settings.llm_provider);
    }

    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);

    // 7. Spawn
    let mut child = match cmd.spawn() {
        Ok(c) => {
            log_line(&mut log_file, &format!("Backend started with PID {}", c.id()));
            c
        }
        Err(e) => {
            let err = format!("Failed to spawn backend: {}", e);
            log_line(&mut log_file, &err);
            return Err(err);
        }
    };
    let spawned_pid = child.id();

    // 8. Check immediate exit
    match child.try_wait() {
        Ok(Some(status)) => {
            let err = format!("Backend exited immediately (code: {:?})", status.code());
            log_line(&mut log_file, &err);
            return Err(err);
        }
        Ok(None) => {}
        Err(e) => {
            let err = format!("Error checking backend process: {}", e);
            log_line(&mut log_file, &err);
            return Err(err);
        }
    }

    // 9. Pipe stdout + stderr to log (must happen BEFORE moving child to state)
    if let Some(stdout) = child.stdout.take() {
        let log_file_stdout = log_file.try_clone().map_err(|e| e.to_string())?;
        stream_to_log(BufReader::new(stdout), log_file_stdout, "STDOUT");
    }
    if let Some(stderr) = child.stderr.take() {
        let log_file_stderr = log_file.try_clone().map_err(|e| e.to_string())?;
        stream_to_log(BufReader::new(stderr), log_file_stderr, "STDERR");
    }

    // 10. Move child to state (ownership transferred — no clone needed)
    {
        let mut proc_guard = state.child.lock().map_err(|e| e.to_string())?;
        *proc_guard = Some(child);
    }

    // 11. Poll /health endpoint — require PID match to avoid accepting stale backend
    let agent: ureq::Agent = ureq::Agent::config_builder()
        .timeout_global(Some(Duration::from_secs(2)))
        .build()
        .into();
    let start = Instant::now();
    log_line(&mut log_file, "Waiting for backend to become ready...");
    let health_url = "http://127.0.0.1:8003/health";
    let build_url = "http://127.0.0.1:8003/debug/build";
    let mut last_error = String::new();

    loop {
        // a) Check if process died (via state mutex — non-blocking)
        let exit_status = {
            let mut guard = state.child.lock().map_err(|e| e.to_string())?;
            guard.as_mut().and_then(|c| c.try_wait().ok().flatten())
        };
        if let Some(status) = exit_status {
            let err = format!(
                "Backend crashed during startup (exit code: {:?}). Check log: {:?}",
                status.code(),
                log_path
            );
            log_line(&mut log_file, &err);
            return Err(err);
        }

        // b) Try health endpoint — then verify PID matches our spawned process
        match agent.get(health_url).call() {
            Ok(resp) if resp.status() == 200 => {
                // Health endpoint responded. Now verify PID via /debug/build.
                match agent.get(build_url).call() {
                    Ok(mut build_resp) if build_resp.status() == 200 => {
                        if let Ok(body) = build_resp.body_mut().read_json::<serde_json::Value>() {
                            let reported_pid = body.get("pid").and_then(|v| v.as_u64()).unwrap_or(0);
                            if reported_pid != spawned_pid as u64 {
                                let msg = format!(
                                    "Health check PID mismatch: expected {}, got {}. Stale backend on port 8003.",
                                    spawned_pid, reported_pid
                                );
                                log_line(&mut log_file, &msg);
                                last_error = msg;
                                thread::sleep(BACKEND_POLL_INTERVAL);
                                continue;
                            }
                            log_line(&mut log_file, &format!(
                                "Backend is ready (PID {} verified via /debug/build)", spawned_pid
                            ));
                        } else {
                            log_line(&mut log_file, "Backend is ready (could not parse /debug/build JSON, trusting health check)");
                        }
                    }
                    _ => {
                        // /debug/build not available — older backend, accept health check
                        log_line(&mut log_file, "Backend is ready (health check passed, /debug/build unavailable)");
                    }
                }
                // Cancel any existing monitor thread before starting a new one
                state.monitor_cancel.store(true, Ordering::SeqCst);
                thread::sleep(Duration::from_millis(100)); // Brief pause for old monitor to exit
                spawn_backend_monitor(app);
                let _ = app.emit("backend-ready", true);
                return Ok(());
            }
            Ok(resp) => {
                last_error = format!("Health check returned {}", resp.status());
            }
            Err(e) => {
                last_error = format!("Health check failed: {}", e);
            }
        }

        if start.elapsed() >= BACKEND_START_TIMEOUT {
            let err = format!(
                "Backend did not become ready within {}s. Last error: {}. Log: {:?}",
                BACKEND_START_TIMEOUT.as_secs(),
                last_error,
                log_path,
            );
            log_line(&mut log_file, &err);
            return Err(err);
        }

        thread::sleep(BACKEND_POLL_INTERVAL);
    }
}

// --- Tauri Commands ---

#[tauri::command]
fn get_settings(app: tauri::AppHandle) -> Result<AppSettings, String> {
    Ok(load_settings(&app))
}

#[tauri::command]
fn set_storage_dir(app: tauri::AppHandle, path: String) -> Result<(), String> {
    let mut settings = load_settings(&app);
    settings.storage_dir = path;
    settings.first_run = false;
    save_settings(&app, &settings)?;
    Ok(())
}

#[tauri::command]
fn save_app_settings(app: tauri::AppHandle, new_settings: AppSettings) -> Result<(), String> {
    save_settings(&app, &new_settings)?;
    Ok(())
}

#[tauri::command]
fn pick_storage_dir() -> Option<String> {
    rfd::FileDialog::new()
        .pick_folder()
        .map(|p| p.to_string_lossy().into_owned())
}

#[tauri::command]
fn open_storage_dir(path: String) -> Result<(), String> {
    let p = PathBuf::from(path);
    if !p.exists() {
        return Err("Folder tidak ditemukan".to_string());
    }

    #[cfg(target_os = "windows")]
    {
        Command::new("explorer")
            .arg(p)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .arg(p)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    #[cfg(not(any(target_os = "windows", target_os = "macos")))]
    {
        Command::new("xdg-open")
            .arg(p)
            .spawn()
            .map_err(|e| e.to_string())?;
    }

    Ok(())
}

#[tauri::command]
fn restart_backend(
    app: tauri::AppHandle,
    state: tauri::State<'_, BackendState>,
    storage_path: String,
) -> Result<(), String> {
    let settings = load_settings(&app);
    start_backend_process(&app, &state, &storage_path, &settings)
}

#[tauri::command]
fn relaunch_app(app: tauri::AppHandle) {
    app.restart();
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .setup(|app| {
            // Register backend state
            let state = BackendState {
                child: Mutex::new(None),
                monitor_cancel: Arc::new(AtomicBool::new(false)),
            };
            app.manage(state);

            // Load settings and start backend
            let settings = load_settings(app.handle());
            log::info!("Loaded settings: storage_dir={}, first_run={}, llm_provider={}, openai_model={}",
                settings.storage_dir, settings.first_run, settings.llm_provider, settings.openai_model);

            let state_ref = app.state::<BackendState>();
            if let Err(e) = start_backend_process(app.handle(), &state_ref, &settings.storage_dir, &settings) {
                log::error!("Gagal menjalankan backend saat startup: {}", e);
                let log_path = get_log_path(app.handle()).unwrap_or_default();
                let payload = serde_json::json!({
                    "error": e,
                    "log_path": log_path.to_string_lossy(),
                });
                let _ = app.handle().emit("backend-error", payload.to_string());
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_settings,
            set_storage_dir,
            save_app_settings,
            pick_storage_dir,
            open_storage_dir,
            restart_backend,
            relaunch_app
        ])
        .build(tauri::generate_context!())
        .expect("error saat membangun aplikasi tauri")
        .run(|app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                use tauri::Manager;
                // Paksa bunuh backend process jika masih berjalan
                if let Some(state) = app_handle.try_state::<BackendState>() {
                    state.monitor_cancel.store(true, Ordering::SeqCst);
                    if let Ok(mut guard) = state.child.lock() {
                        if let Some(child) = guard.take() {
                            kill_child(child);
                        }
                    }
                }
                // Paksa matikan proses utama untuk membersihkan seluruh thread dan WebView2 helper
                std::process::exit(0);
            }
        });
}
