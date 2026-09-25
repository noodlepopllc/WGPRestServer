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
    proc = subprocess.run(
        ["restmodels"],
        capture_output=True,
        text=True,
        env=os.environ
    )
    out = proc.stdout

    # Find the first JSON object start
    idx = out.find("{")
    if idx == -1:
        return {"error": "no JSON found", "stdout": out, "stderr": proc.stderr}

    clean = out[idx:].strip()

    try:
        return json.loads(clean)
    except Exception as e:
        return {"error": str(e), "stdout": clean, "stderr": proc.stderr}


def fetch_model_defaults(model_id):
    proc = subprocess.run(
        ["restdefaults", model_id],
        capture_output=True,
        text=True,
        env=os.environ
    )
    out = proc.stdout

    # Find the first JSON object start
    idx = out.find("{")
    if idx == -1:
        return {"error": "no JSON found", "stdout": out, "stderr": proc.stderr}

    clean = out[idx:].strip()

    try:
        return json.loads(clean)
    except Exception as e:
        return {"error": str(e), "stdout": clean, "stderr": proc.stderr}



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
        ["restworker", json.dumps(args)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=os.environ
    )

    job_id = proc.stdout.readline().decode().strip()
    return json.dumps(job_id)

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
