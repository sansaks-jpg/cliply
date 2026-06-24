"""Entry point untuk PyInstaller bundle.

Menerima argumen:
  --storage-dir <path>   Override lokasi penyimpanan file
  --port <port>          Port uvicorn (default 8003)
"""

import os
import sys


def _parse_args():
    storage_dir = None
    port = 8003
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--storage-dir" and i + 1 < len(args):
            storage_dir = args[i + 1]
            i += 2
        elif args[i] == "--port" and i + 1 < len(args):
            try:
                port = int(args[i + 1])
            except ValueError:
                pass
            i += 2
        else:
            i += 1
    return storage_dir, port


def main():
    storage_dir, port = _parse_args()

    # Env var override — dibaca oleh config.py saat import
    if storage_dir:
        os.environ["STORAGE_DIR"] = storage_dir

    # Saat di-bundle oleh PyInstaller, sys._MEIPASS berisi direktori sementara
    # tempat semua file dibundle. Kita tambahkan ke PYTHONPATH agar import app.* work.
    if hasattr(sys, "_MEIPASS"):
        meipass = sys._MEIPASS
        if meipass not in sys.path:
            sys.path.insert(0, meipass)

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=port,
        log_level="info",
        use_colors=False,
    )


if __name__ == "__main__":
    main()
