use std::fs;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;
use tauri::Manager;

pub struct BackendState(pub Mutex<Option<Child>>);

impl Drop for BackendState {
    fn drop(&mut self) {
        if let Ok(mut guard) = self.0.lock() {
            if let Some(mut child) = guard.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

#[derive(serde::Serialize, serde::Deserialize, Clone, Debug)]
pub struct AppSettings {
    pub storage_dir: String,
    pub first_run: bool,
    pub gemini_api_key: String,
    pub openai_api_key: String,
    pub openai_base_url: String,
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
        openai_api_key: "".to_string(),
        openai_base_url: "".to_string(),
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
                    if let Some(o) = loaded_val.get("openai_api_key").and_then(|v| v.as_str()) {
                        settings.openai_api_key = o.to_string();
                    }
                    if let Some(u) = loaded_val.get("openai_base_url").and_then(|v| v.as_str()) {
                        settings.openai_base_url = u.to_string();
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

fn start_backend_process(
    app: &tauri::AppHandle,
    state: &tauri::State<'_, BackendState>,
    storage_dir: &str,
    settings: &AppSettings,
) -> Result<(), String> {
    // 1. Kill old process if any
    {
        let mut proc_guard = state.0.lock().map_err(|e| e.to_string())?;
        if let Some(mut child) = proc_guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }

    // 2. Locate backend directory
    let backend_dir = find_backend_dir(app).ok_or_else(|| "Backend directory not found".to_string())?;

    // 3. Check for compiled cliply_server executable
    let exe_name = if cfg!(target_os = "windows") { "cliply_server.exe" } else { "cliply_server" };
    let compiled_exe = backend_dir.join(exe_name);
    let dist_dir = backend_dir.join("dist").join(exe_name);

    let mut cmd = if compiled_exe.exists() {
        log::info!("Menggunakan backend executable di {:?}", compiled_exe);
        let mut c = Command::new(&compiled_exe);
        c.args(["--storage-dir", storage_dir, "--port", "8000"]);
        c
    } else if dist_dir.exists() {
        log::info!("Menggunakan backend executable di {:?}", dist_dir);
        let mut c = Command::new(&dist_dir);
        c.args(["--storage-dir", storage_dir, "--port", "8000"]);
        c
    } else {
        // Fallback to python script run
        let python = find_python(&backend_dir).ok_or_else(|| "Python tidak ditemukan".to_string())?;
        log::info!("Menggunakan script Python via {:?}", python);
        let mut c = Command::new(&python);
        c.args([
            "-m",
            "uvicorn",
            "app.main:app",
            "--port",
            "8000",
            "--host",
            "127.0.0.1",
        ]);
        c
    };

    cmd.current_dir(&backend_dir)
        .env("STORAGE_DIR", storage_dir)
        .env("GEMINI_API_KEY", &settings.gemini_api_key)
        .env("OPENAI_API_KEY", &settings.openai_api_key)
        .env("OPENAI_BASE_URL", &settings.openai_base_url)
        .env("LLM_PROVIDER", &settings.llm_provider);

    match cmd.spawn() {
        Ok(child) => {
            log::info!("Backend dimulai dengan PID {}", child.id());
            let mut proc_guard = state.0.lock().map_err(|e| e.to_string())?;
            *proc_guard = Some(child);
            
            // Beri waktu startup
            thread::sleep(Duration::from_millis(1500));
            Ok(())
        }
        Err(e) => {
            let err_msg = format!("Gagal menjalankan backend: {}", e);
            log::error!("{}", err_msg);
            Err(err_msg)
        }
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
            let handle = app.handle().clone();

            // Register backend state
            let state = BackendState(Mutex::new(None));
            app.manage(state);

            // Load settings and start backend
            let settings = load_settings(&handle);
            log::info!("Loaded settings: {:?}", settings);

            let state_ref = app.state::<BackendState>();
            if let Err(e) = start_backend_process(&handle, &state_ref, &settings.storage_dir, &settings) {
                log::error!("Gagal menjalankan backend saat startup: {}", e);
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
        .run(tauri::generate_context!())
        .expect("error saat menjalankan aplikasi tauri");
}
