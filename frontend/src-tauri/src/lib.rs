use std::path::PathBuf;
use std::process::{Child, Command};
use tauri::Manager;

struct BackendProcess(Option<Child>);

impl Drop for BackendProcess {
    fn drop(&mut self) {
        if let Some(ref mut child) = self.0 {
            #[cfg(target_os = "windows")]
            {
                let _ = child.kill();
                let _ = child.wait();
            }
            #[cfg(not(target_os = "windows"))]
            {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

fn find_backend_dir() -> Option<PathBuf> {
    let candidates = [
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("..")
            .join("backend"),
        PathBuf::from("../backend"),
        PathBuf::from("backend"),
    ];
    for p in &candidates {
        if p.join("app").join("main.py").exists() {
            return Some(p.canonicalize().unwrap_or(p.clone()));
        }
    }
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
        if p.is_file() || p.to_str().map_or(false, |s| !s.contains('\\') && !s.contains('/')) {
            return Some(p.clone());
        }
    }
    None
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let backend_dir = find_backend_dir();
            if let Some(ref dir) = backend_dir {
                if let Some(python) = find_python(dir) {
                    match Command::new(&python)
                        .args(["-m", "uvicorn", "app.main:app", "--port", "8000"])
                        .current_dir(dir)
                        .spawn()
                    {
                        Ok(child) => {
                            log::info!("Backend started with PID {}", child.id());
                            app.manage(BackendProcess(Some(child)));
                        }
                        Err(e) => {
                            log::warn!("Failed to start backend: {}", e);
                            app.manage(BackendProcess(None));
                        }
                    }
                } else {
                    log::warn!("Python not found in .venv or system PATH");
                    app.manage(BackendProcess(None));
                }
            } else {
                log::warn!("Backend directory not found");
                app.manage(BackendProcess(None));
            }

            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
