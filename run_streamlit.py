#!/usr/bin/env python3
"""Launch HC Agent Streamlit frontend."""
import os, sys, subprocess

os.chdir(os.path.dirname(os.path.abspath(__file__)))
stapp = os.path.join("frontends", "stapp.py")
if not os.path.exists(stapp):
    print(f"[Error] {stapp} not found"); sys.exit(1)

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8501
print(f"[HC Agent] Starting Streamlit on http://localhost:{port}")
subprocess.run([sys.executable, "-m", "streamlit", "run", stapp,
                "--server.port", str(port), "--server.headless", "true",
                "--theme.base", "light"])
