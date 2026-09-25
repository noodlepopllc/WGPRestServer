# worker.py
import os, sys, json
from sql_manager import JobDB
import time

db = JobDB(os.environ.get("WAN2GP_DB"))

# 1. validate args
input_data = json.loads(sys.argv[1])

parent_pid = os.getppid()
child_pid = os.getpid()

if job_id := db.any_job_running():
    print(job_id)
    sys.exit(0)

# 2. insert job
job_id = db.insert_job(parent_pid, child_pid, input_data)

# 3. pending
db.set_job_state(job_id, "pending")

# 5. fork into runner
pid = os.fork()

if pid == 0:
    # --- CHILD PROCESS ---
    # Re-initialize or ensure DB connection is clean for the child process 
    # if your JobDB class supports re-connecting/cloning.
    
    root = os.environ.get("WAN2GP_DIRECTORY")

    db.set_job_state(job_id, "running")

    result = None  # Prevent NameError in finally block
    try:
        os.chdir(root)
        sys.path.append('.')
        from pathlib import Path
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
                db.add_job_update(job_id, progress=f'{update.status} Step: {update.current_step}, Total: {update.total_steps}')

        job = session.submit_task(input_data, callbacks=WorkerCallbacks())
        result = job.result()
        
        # If success
        db.set_job_state(job_id, "complete", f'success: {result.success}, files: {result.generated_files}, errors: {result.errors}')
    
    except Exception as e:
        # Catch unexpected errors so the DB state doesn't stay stuck on "running"
        db.set_job_state(job_id, "failed", f'exception: {str(e)}')
    
    finally:
        # Use os._exit in forked child to prevent flushing/closing parent streams
        os._exit(0) 
else:
    # --- PARENT PROCESS ---
    # 6. parent: return job_id immediately
    print(job_id)
    sys.exit(0)
