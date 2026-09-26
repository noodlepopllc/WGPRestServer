# worker.py
import os, sys, json, traceback, subprocess
from pathlib import Path
from wangp_server.sql_manager import JobDB

# ---------------------------------------------------------
# Shared Wan2GP session initializer (used by all 3 entries)
# ---------------------------------------------------------
def create_session(attention="sdpa", profile="4", output_dir=None, console=False):
    wan2gp = os.environ["WAN2GP_DIRECTORY"]
    os.chdir(wan2gp)
    sys.path.append('.')

    from shared.api import init

    kwargs = {
        "root": Path(wan2gp),
        "cli_args": ["--attention", attention, "--profile", profile],
        "console_output": console
    }

    if output_dir is not None:
        kwargs["output_dir"] = Path(output_dir)

    return init(**kwargs)


# ---------------------------------------------------------
# 1. Long-running job worker
# ---------------------------------------------------------
def main_worker_old():
    db = JobDB(os.environ["WAN2GP_DB"])
    input_data = json.loads(sys.argv[1])

    parent_pid = os.getppid()
    child_pid = os.getpid()

    if job_id := db.any_job_running():
        print(job_id, flush=True)
        return

    job_id = db.insert_job(parent_pid, child_pid, input_data)
    db.set_job_state(job_id, "pending")

    # Return job_id immediately
    print(job_id, flush=True)

    db.set_job_state(job_id, "running")

    try:
        session = create_session(
            attention="sdpa",
            profile="4",
            output_dir=input_data.get("output_dir"),
            console=True
        )

        class WorkerCallbacks:
            def on_status(self, status):
                pass

            def on_progress(self, update):
                db.add_job_update(
                    job_id,
                    progress=f'{update.status} Step: {update.current_step}, Total: {update.total_steps}'
                )

        if "output_dir" in input_data:
            del input_data["output_dir"]

        job = session.submit_task(input_data, callbacks=WorkerCallbacks())
        result = job.result()

        db.set_job_state(
            job_id,
            "complete",
            f'success: {result.success}, files: {result.generated_files}, errors: {result.errors}'
        )

    except Exception as e:
        tb = traceback.format_exc()
        db.set_job_state(job_id, "failed", tb)


def main_worker():
    db = JobDB(os.environ["WAN2GP_DB"])
    input_data = json.loads(sys.argv[1])

    wan2gp = os.environ["WAN2GP_DIRECTORY"]
    os.chdir(wan2gp)

    parent_pid = os.getppid()
    child_pid = os.getpid()

    if job_id := db.any_job_running():
        print(job_id, flush=True)
        return

    job_id = db.insert_job(parent_pid, child_pid, input_data)
    db.set_job_state(job_id, "pending")

    # Return job_id immediately
    print(job_id, flush=True)

    db.set_job_state(job_id, "running")

    output_dir = input_data.get("output_dir", "outputs")

    # Write JSON payload for CLI
    with open('tmp.json', 'w') as fn:
        json.dump(input_data, fn)

    try:
        # Correct subprocess invocation
        job = subprocess.Popen(
            [
                "python",
                "wgp.py",
                "--process", "tmp.json",
                "--profile", "4.5",
                "--output-dir", output_dir,
                "--verbose", "0"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        queue_completed = False

        for raw in job.stdout:
            line = raw.rstrip()

            # tqdm progress
            if "%" in line and "|" in line:
                parts = line.split("|")
                pct = parts[0].strip()
                step = parts[-1].split()[0]
                db.add_job_update(job_id, progress=f"{pct} {step}")
                continue

            # queue completed marker
            if "Queue completed" in line:
                queue_completed = True

            # normal progress
            if line:
                db.add_job_update(job_id, progress=line)

        exit_code = job.wait()

        if exit_code == 0 and queue_completed:
            db.set_job_state(job_id, "complete", "success")
        else:
            db.set_job_state(job_id, "failed", f"exit={exit_code}")


    except Exception as e:
        tb = traceback.format_exc()
        db.set_job_state(job_id, "failed", tb)




# ---------------------------------------------------------
# 2. Fetch model availability
# ---------------------------------------------------------
def main_models():
    session = create_session(console=False)
    available = [x for x in session.list_model_availability() if x["available"]]
    print(json.dumps(available), flush=True)


# ---------------------------------------------------------
# 3. Fetch model defaults
# ---------------------------------------------------------
def main_defaults():
    model_id = sys.argv[1]
    session = create_session(console=False)
    default = session.get_default_settings(model_id)
    print(json.dumps(default), flush=True)

