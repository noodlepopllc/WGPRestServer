# worker.py
import os, sys, json
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
def main_worker():
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

        job = session.submit_task(input_data, callbacks=WorkerCallbacks())
        result = job.result()

        db.set_job_state(
            job_id,
            "complete",
            f'success: {result.success}, files: {result.generated_files}, errors: {result.errors}'
        )

    except Exception as e:
        db.set_job_state(job_id, "failed", f'exception: {str(e)}')


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

