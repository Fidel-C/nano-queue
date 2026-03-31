### `nano_queue/core.py`

import threading
import time
import json
import uuid
import traceback
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

# In-memory registry mapping string names to actual Python functions
_task_registry = {}

class NanoQueue:
    def __init__(self, db_url: str = "sqlite:///nano_queue.db", poll_interval: int = 2):
        self.engine = create_engine(db_url, future=True)
        self.poll_interval = poll_interval
        self._init_db()
        self._start_worker()

    def _init_db(self):
        """Creates the tasks table if it doesn't exist."""
        with self.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS nano_tasks (
                    id VARCHAR(36) PRIMARY KEY,
                    task_name VARCHAR(255) NOT NULL,
                    payload TEXT NOT NULL,
                    status VARCHAR(50) DEFAULT 'pending',
                    error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))

    def enqueue(self, task_name: str, *args, **kwargs):
        """Inserts a job into the database."""
        task_id = str(uuid.uuid4())
        payload = json.dumps({"args": args, "kwargs": kwargs})
        
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO nano_tasks (id, task_name, payload) 
                VALUES (:id, :name, :payload)
            """), {"id": task_id, "name": task_name, "payload": payload})
        
        return task_id

    def _worker_loop(self):
        """The infinite loop that runs in the background thread."""
        while True:
            try:
                self._process_next_job()
            except Exception as e:
                pass # In production, hook this into logging/Sentry
            time.sleep(self.poll_interval)

    def _process_next_job(self):
        """Atomically claims a job and executes it."""
        with self.engine.begin() as conn:
            # Atomic claim: Find the oldest pending job and mark it processing.
            # (Note: For massive scale Postgres, use FOR UPDATE SKIP LOCKED. 
            # This is the universal MVP approach).
            result = conn.execute(text("""
                UPDATE nano_tasks 
                SET status = 'processing' 
                WHERE id = (
                    SELECT id FROM nano_tasks 
                    WHERE status = 'pending' 
                    ORDER BY created_at ASC 
                    LIMIT 1
                ) RETURNING id, task_name, payload
            """)).fetchone()

        if not result:
            return # No jobs pending

        job_id, task_name, payload_str = result
        payload = json.loads(payload_str)

        try:
            # Execute the actual function
            func = _task_registry.get(task_name)
            if not func:
                raise ValueError(f"Task '{task_name}' not found in registry.")
            
            func(*payload.get("args", []), **payload.get("kwargs", {}))
            
            # Mark as completed
            with self.engine.begin() as conn:
                conn.execute(text("UPDATE nano_tasks SET status = 'completed' WHERE id = :id"), {"id": job_id})
                
        except Exception as e:
            # Mark as failed and store the traceback
            error_trace = traceback.format_exc()
            with self.engine.begin() as conn:
                conn.execute(text("UPDATE nano_tasks SET status = 'failed', error = :error WHERE id = :id"), 
                             {"id": job_id, "error": error_trace})

    def _start_worker(self):
        """Spins up the daemon thread."""
        worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        worker_thread.start()


def background_task(queue: NanoQueue, name: str = None):
    """Decorator to register and enqueue background tasks."""
    def decorator(func):
        task_name = name or func.__name__
        _task_registry[task_name] = func

        def wrapper(*args, **kwargs):
            # When the decorated function is called, enqueue it instead of running it
            return queue.enqueue(task_name, *args, **kwargs)
            
        wrapper.run_sync = func # Allow manual synchronous execution if needed
        return wrapper
    return decorator
