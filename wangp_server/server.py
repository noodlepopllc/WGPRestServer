#!/usr/bin/env python3
from wangp_server.bottle import route, run, request
import os, sqlite3, time, argparse, json, subprocess
from wangp_server.sql_manager import JobDB
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wangp", help="Path to Wan2GP root directory")
    return parser.parse_args()

args = parse_args()

if args.wangp:
    os.environ["WAN2GP_DIRECTORY"] = args.wangp

DB_PATH = os.environ.get("WAN2GP_DB", os.path.abspath(os.path.join(os.path.dirname(__file__), "jobs.db")))

os.environ["WAN2GP_DB"] = DB_PATH

CACHE_DIR = "./cache"

if Path(DB_PATH).exists():
    os.remove(DB_PATH)
DB = JobDB(DB_PATH)

def purge_cache():
    if not os.path.isdir(CACHE_DIR):
        return
    for name in os.listdir(CACHE_DIR):
        try:
            os.remove(os.path.join(CACHE_DIR, name))
        except OSError:
            pass

def fetch_models_runtime():
    r, w = os.pipe()
    pid = os.fork()

    if pid == 0:
        os.close(r)

        # 1. Child sets up environment
        import sys
        from pathlib import Path

        wan2gp = os.environ.get("WAN2GP_DIRECTORY")
        os.chdir(wan2gp)
        sys.path.append('.')

        # 2. Child initializes Wan2GP runtime
        from shared.api import init

        session = init(
            root=Path(wan2gp),
            cli_args=["--attention", "sdpa", "--profile", "4"],
            console_output=False
        )

        # 3. Child fetches availability
        available = [x for x in session.list_model_availability() if x["available"]]

        # 4. Child writes JSON to pipe
        os.write(w, json.dumps(available).encode())
        os.close(w)

        # 5. Child exits cleanly
        os._exit(0)

    # Parent: read result
    os.close(w)
    data = os.read(r, 1_000_000)
    os.close(r)
    return json.loads(data)

def fetch_model_defaults(model_id):
    r, w = os.pipe()
    pid = os.fork()

    if pid == 0:
        os.close(r)

        # 1. Child sets up environment
        import sys
        from pathlib import Path

        wan2gp = os.environ.get("WAN2GP_DIRECTORY")
        print("WANGP", wan2gp)
        os.chdir(wan2gp)
        sys.path.append('.')

        # 2. Child initializes Wan2GP runtime
        from shared.api import init

        session = init(
            root=Path(wan2gp),
            cli_args=["--attention", "sdpa", "--profile", "4"],
            console_output=False
        )

        default = session.get_default_settings(model_id)

        # 4. Child writes JSON to pipe
        os.write(w, json.dumps(default).encode())
        os.close(w)

        # 5. Child exits cleanly
        os._exit(0)

    # Parent: read result
    os.close(w)
    data = os.read(r, 1_000_000)
    os.close(r)
    return json.loads(data)

@route('/defaults/<model_id>')
def defaults(model_id):
    cache_dir = "./cache"
    os.makedirs(cache_dir, exist_ok=True)

    cache_path = os.path.join(cache_dir, f"default_{model_id}.json")

    # 1. Disk-first
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            return json.load(f)

    # 2. Runtime fetch (fork-only)
    default = fetch_model_defaults(model_id)

    # 3. Write cache
    with open(cache_path, "w") as f:
        json.dump(default, f, indent=4)

    return default


@route('/models')
def models():
    path = os.path.join(CACHE_DIR, "models_available.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)

    models = fetch_models_runtime()
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, "w") as f:
        json.dump(models, f, indent=4)
    return models


@route('/run', method='POST')
def run_job():
    args = request.json

    proc = subprocess.Popen(
        ["python3", "worker.py", json.dumps(args)],
        cwd="/home/todd/WGPRestServer/wan2gp",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=os.environ
    )

    stdout, stderr = proc.communicate()

    job_id = stdout.decode().strip()

    if not job_id:
        return {
            "error": "worker failed",
            "stderr": stderr.decode()
        }

    return {"job_id": job_id}

@route('/status')
def allstatus():
    return json.dumps(DB.get_all_jobs())

@route('/status/<job_id>')
def status(job_id):
    return json.dumps(DB.get_job(job_id))

@route('/updates/<job_id>')
def updates(job_id):
    return json.dumps(DB.get_latest_update(job_id))

def main():
    purge_cache()
    run(host='127.0.0.1', port=8080)

if __name__ == '__main__':
    main()
