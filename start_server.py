"""Start Streamlit on the port assigned by the hosting service."""
import os
import subprocess
import sys

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8501"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535")
    raise SystemExit(subprocess.call([
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.address=0.0.0.0", f"--server.port={port}",
        "--server.headless=true", "--browser.gatherUsageStats=false",
    ]))
