"""Start the local prototype. Install requirements explicitly before running."""
import argparse
import os
from pathlib import Path
import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["disabled", "demo", "remote"], default=None)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    os.chdir(Path(__file__).resolve().parent)
    if args.mode is not None:
        os.environ["KINVOICE_MODE"] = args.mode
    uvicorn.run("app.main:app", host="127.0.0.1", port=args.port, access_log=False)
