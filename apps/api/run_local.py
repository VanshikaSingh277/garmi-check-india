"""Local runner: python -I run_local.py [extra_site_packages_dir] [port]
Uses absolute paths so it works from any working directory."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if len(sys.argv) > 1 and sys.argv[1]:
    sys.path.insert(0, sys.argv[1])
sys.path.insert(0, HERE)
os.chdir(HERE)
import uvicorn  # noqa: E402

# no uvicorn access log (it records query strings, i.e. coordinates) and no Server header: spec §8.5-8.6
uvicorn.run("main:app", host="127.0.0.1", port=int(sys.argv[2]) if len(sys.argv) > 2 else 8765, loop="asyncio", http="h11",
            access_log=False, server_header=False)
