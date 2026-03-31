Here is the updated project with the name changed to **`nano-queue`**. All references—including package names, class names, file paths, and SQL table names—have been adjusted to reflect the new identity.

### `README.md`

```markdown
# 🪶 nano-queue

**Zero-infra background jobs for Python. No Redis. No Celery. No extra server costs.**

Created by **[Fidel Chukwunyere](https://github.com/Fidel-c)**

[![PyPI version](https://badge.fury.io/py/nano-queue.svg)](https://badge.fury.io/py/nano-queue)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

You just want to send a welcome email or generate a PDF in the background. But suddenly, you are installing Celery, configuring a Redis cluster, and paying for an extra "Worker" dyno on Render or Heroku. 

`nano-queue` fixes this. 

It is a plug-and-play background task queue that **piggybacks on your existing database** (Postgres/SQLite) and runs silently in a **background daemon thread** inside your main web server process (FastAPI/Django/Flask). 

Stop paying for extra infrastructure just to send an email.

---

## 🥊 nano-queue vs. FastAPI BackgroundTasks

*Wait, doesn't FastAPI already have `BackgroundTasks`?* Yes, but it is a massive footgun for production apps. FastAPI's built-in tasks live entirely in RAM and are bound to the specific worker that received the request. `nano-queue` transforms that fragile setup into a **durable message broker**.

| Feature | FastAPI `BackgroundTasks` | `nano-queue` |
| :--- | :--- | :--- |
| **Server Restart / Crash** | ❌ All pending jobs are permanently lost | ✅ Jobs safely persist in your DB |
| **Load Balancing**| ❌ CPU spikes on a single Gunicorn worker | ✅ Idle workers automatically grab jobs |
| **Failure Observability** | ❌ Silent terminal errors | ✅ Tracebacks saved to DB for easy retry |
| **Infrastructure Required** | ✅ None | ✅ None (Piggybacks existing DB) |

---

## ✨ Features
* **Zero Extra Infra:** Uses the database you already have.
* **PaaS Friendly:** Perfect for Render, Heroku, and Railway single-instance deployments.
* **Atomic Locks:** Safe for multi-worker environments (e.g., 4 Gunicorn workers? You get a 4-thread queue automatically without double-processing).
* **Framework Agnostic:** Works beautifully with FastAPI, Django, Flask, or pure Python scripts.

---

## 📦 Installation

```bash
pip install nano-queue

# If you are using Postgres in production, make sure you have your driver:
pip install psycopg2-binary
```

---

## 🚀 How it Works

1. You wrap a function with `@background_task(queue=q)`.
2. When called, it instantly serializes the arguments and saves the job to a `nano_tasks` table in your DB.
3. A background daemon thread safely polls the DB, atomically claims the job, and executes it without blocking your web requests.

---

## ⚡ FastAPI Integration

Integrating with FastAPI is effortless. We recommend using an environment variable (`DATABASE_URL`) so it runs on SQLite locally, but seamlessly connects to your production Postgres on Render/Heroku.

```python
# main.py
import os
import time
from fastapi import FastAPI
from nano_queue import NanoQueue, background_task

# 1. Initialize the queue (Defaults to local SQLite if no ENV var is found)
db_url = os.getenv("DATABASE_URL", "sqlite:///local_tasks.db")
q = NanoQueue(db_url)

app = FastAPI()

# 2. Decorate your heavy functions
@background_task(queue=q)
def send_welcome_email(user_email: str):
    print(f"Connecting to SMTP... sending email to {user_email}")
    time.sleep(3) # Simulate heavy I/O
    print("Email sent!")

# 3. Call them normally in your endpoints
@app.post("/signup")
def signup(email: str):
    # This returns instantly. The email sends in the background.
    send_welcome_email(email)
    return {"message": "Account created! Check your email."}
```

---

## 🎸 Django Integration

For Django, you want to ensure the queue is initialized when your app starts, but avoid running the worker thread during management commands like `makemigrations`.

**1. Define your tasks (`myapp/tasks.py`)**
```python
import os
import time
from nano_queue import NanoQueue, background_task
from django.conf import settings

# Grab the DB URL from your environment (standard for PaaS deployments)
db_url = os.environ.get("DATABASE_URL", "sqlite:///db.sqlite3")

# Initialize the queue
q = NanoQueue(db_url)

@background_task(queue=q)
def process_payment_webhook(payload: dict):
    print("Processing webhook payload...")
    time.sleep(5) # Simulate external API call
    print(f"Webhook {payload.get('id')} processed safely!")
```

**2. Safely start it in your AppConfig (`myapp/apps.py`)**
```python
import sys
from django.apps import AppConfig

class MyAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'myapp'

    def ready(self):
        # Only import and start the queue if we are actually running the server
        # This prevents the daemon from starting during `python manage.py collectstatic`
        if 'runserver' in sys.argv or 'gunicorn' in sys.argv[0]:
            import myapp.tasks
```

**3. Call it in your views (`myapp/views.py`)**
```python
from django.http import JsonResponse
from .tasks import process_payment_webhook

def stripe_webhook(request):
    payload = {"id": "evt_12345", "amount": 5000}
    
    # Enqueues to DB instantly and returns 200 OK to Stripe
    process_payment_webhook(payload) 
    
    return JsonResponse({"status": "received"})
```

---

## 🛠️ Production Tips (Render / Heroku)

If you are deploying to a PaaS like Render, **you do not need a background worker dyno**. 

Simply deploy your web service as usual (e.g., `gunicorn app.main:app`). Because `nano-queue` uses a Daemon Thread, it will boot up alongside your web server. 

If you scale your web service to 3 instances, you will automatically have 3 background threads processing jobs. The `UPDATE ... RETURNING` SQL logic ensures that no two instances will ever process the same job twice.

---

## 👤 Author

- **[Fidel Chukwunyere](https://github.com/Fidel-c)** — Creator of nano-queue

---

## 🤝 Contributing
Found a bug? Want to add Redis support? (Just kidding, please don't). Pull requests are welcome!
```

---

