const { spawn } = require("child_process");
const path = require("path");
const http = require("http");

// Fungsi untuk memeriksa apakah backend sudah berjalan di port 8000
function checkBackend(callback) {
  const req = http.get("http://localhost:8000/health", (res) => {
    if (res.statusCode === 200) {
      callback(true);
    } else {
      callback(false);
    }
  });
  
  req.on("error", () => {
    callback(false);
  });
  
  req.end();
}

function startBackend() {
  const backendDir = path.resolve(__dirname, "../../backend");
  // Tentukan path ke python executable di virtual env
  const isWindows = process.platform === "win32";
  const pythonExe = isWindows 
    ? path.join(backendDir, ".venv", "Scripts", "python.exe")
    : path.join(backendDir, ".venv", "bin", "python");

  console.log(`[Start-Backend] Memeriksa status backend...`);

  checkBackend((running) => {
    if (running) {
      console.log(`[Start-Backend] Backend sudah aktif di port 8000.`);
      process.exit(0);
    }

    console.log(`[Start-Backend] Backend belum aktif. Menghidupkan backend di ${backendDir}...`);
    
    const child = spawn(
      pythonExe,
      ["-m", "uvicorn", "app.main:app", "--port", "8000"],
      {
        cwd: backendDir,
        detached: true,
        stdio: "ignore",
        shell: isWindows // Penting untuk Windows agar resolve path dengan benar
      }
    );

    child.unref();
    console.log(`[Start-Backend] Perintah backend dijalankan di background.`);
    
    // Beri waktu 3 detik agar server inisialisasi sebelum build berlanjut
    setTimeout(() => {
      process.exit(0);
    }, 3000);
  });
}

startBackend();
