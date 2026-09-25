# worker.py
import os, sys, json
from wangp_server.sql_manager import JobDB
import time
from pathlib import Path

def main():
    db = JobDB(os.environ.get("WAN2GP_DB"))

    # 1. validate args
    input_data = json.loads(sys.argv[1])

    parent_pid = os.getppid()
    child_pid = os.getpid()

    # If a job is already running, return its ID immediately
    if job_id := db.any_job_running():
        print(job_id, flush=True)
        return

    # 2. insert job
    job_id = db.insert_job(parent_pid, child_pid, input_data)

    # 3. pending
    db.set_job_state(job_id, "pending")

    # --- CHILD PROCESS (the worker itself) ---
    # Print job_id immediately so the server can return it
    print(job_id, flush=True)

    root = os.environ.get("WAN2GP_DIRECTORY")
    db.set_job_state(job_id, "running")

    try:
        # Switch into Wan2GP core directory
        os.chdir(root)
        sys.path.append('.')

        from shared.api import init

        if 'output_dir' in input_data:
            session = init(
                root=Path(root),
                cli_args=["--attention", "sage2", "--profile", "4"],
                output_dir=Path(input_data['output_dir']),
                console_output=True
            )
        else:
            session = init(
                root=Path(root),
                cli_args=["--attention", "sage2", "--profile", "4"],
                console_output=True
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

if __name__ == '__main__':
    main()

