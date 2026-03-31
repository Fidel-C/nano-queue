import pytest
import time
import json
from sqlalchemy import text
from nano_queue.core import NanoQueue, background_task, _task_registry

# --- FIXTURES ---

@pytest.fixture(autouse=True)
def clean_state():
    """
    Runs before EVERY test. 
    Ensures the global task registry is wiped clean so tests don't leak state.
    """
    _task_registry.clear()
    yield

@pytest.fixture
def queue(tmp_path):
    """
    Provides a fresh NanoQueue instance for each test.
    We use a temporary file path instead of :memory: because the daemon 
    thread requires a shared, file-backed connection.
    """
    db_path = tmp_path / "test_queue.db"
    
    # Set poll_interval to 10 seconds. 
    # This prevents the background daemon from instantly grabbing our jobs,
    # allowing us to test the 'pending' state and manually step through execution.
    q = NanoQueue(db_url=f"sqlite:///{db_path}", poll_interval=10)
    yield q
    # tmp_path automatically cleans up the file after the test finishes


# --- TESTS ---

def test_database_initialization(queue):
    """Ensures the tasks table is successfully created on instantiation."""
    with queue.engine.connect() as conn:
        result = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='nano_tasks'"
        ))
        assert result.fetchone() is not None, "Database table was not created."

def test_enqueue_task(queue):
    """Tests that a decorated function correctly serializes and inserts a pending job."""
    
    @background_task(queue=queue)
    def dummy_email_task(email, template="welcome"):
        pass

    # Calling the function should NOT execute it, but enqueue it.
    task_id = dummy_email_task("test@example.com", template="upgrade")
    
    with queue.engine.connect() as conn:
        row = conn.execute(text("SELECT status, payload FROM nano_tasks WHERE id = :id"), 
                           {"id": task_id}).fetchone()
        
        assert row is not None
        assert row[0] == 'pending'
        
        # Verify serialization
        payload = json.loads(row[1])
        assert payload["args"] == ["test@example.com"]
        assert payload["kwargs"] == {"template": "upgrade"}

def test_successful_execution(queue):
    """Tests that a job processes correctly and updates its status to 'completed'."""
    
    # We use a mutable list to track side-effects in the local scope
    side_effect_tracker = []

    @background_task(queue=queue)
    def math_task(a, b):
        side_effect_tracker.append(a + b)

    task_id = math_task(5, 7)
    
    # Manually trigger the processor to bypass the thread's 10-second sleep
    queue._process_next_job()

    # Verify the function actually ran
    assert side_effect_tracker == [12]
    
    # Verify the database state was updated
    with queue.engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM nano_tasks WHERE id = :id"), 
                              {"id": task_id}).scalar()
        assert status == 'completed'

def test_failed_execution(queue):
    """Tests that exceptions are caught, tracebacks are saved, and status becomes 'failed'."""
    
    @background_task(queue=queue)
    def failing_task():
        raise ValueError("Simulated API Timeout")

    task_id = failing_task()
    
    # Manually process
    queue._process_next_job()

    with queue.engine.connect() as conn:
        row = conn.execute(text("SELECT status, error FROM nano_tasks WHERE id = :id"), 
                           {"id": task_id}).fetchone()
        
        assert row[0] == 'failed'
        assert "ValueError: Simulated API Timeout" in row[1]

def test_live_daemon_thread(tmp_path):
    """
    Integration test: Verifies that the background thread actually wakes up, 
    claims a job, and processes it without manual intervention.
    """
    db_path = tmp_path / "test_integration.db"
    
    # We use a tiny 0.1s poll interval so the test runs fast
    q = NanoQueue(db_url=f"sqlite:///{db_path}", poll_interval=0.1) 

    execution_flag = []

    @background_task(queue=q)
    def fast_task():
        execution_flag.append(True)

    task_id = fast_task()
    
    # Sleep just long enough for the daemon thread to wake up and process it
    time.sleep(0.3)

    assert len(execution_flag) == 1, "Daemon thread failed to execute the task."
    
    with q.engine.connect() as conn:
        status = conn.execute(text("SELECT status FROM nano_tasks WHERE id = :id"), 
                              {"id": task_id}).scalar()
        assert status == 'completed'