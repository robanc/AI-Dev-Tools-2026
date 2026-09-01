# ChoreShare

A simple Django web app for managing shared household chores. Create households and
members, add chores, assign them, and track what's pending vs. completed.

Built as coursework for the DataTalksClub **AI Dev Tools Zoomcamp** (Module 1).
See [`_docs/plan.md`](_docs/plan.md) for the product spec and
[`_docs/backlog.md`](_docs/backlog.md) for the implementation backlog.

## Requirements

- Python 3.12+

## Setup

From a clean checkout, create and activate a virtual environment, then install
dependencies.

**Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux:**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run

Apply database migrations, create an admin user, and start the development server:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Then open:

- **App:** http://127.0.0.1:8000/
- **Admin:** http://127.0.0.1:8000/admin/ (log in with the superuser you created)

Use the admin to create a Household and Members, then manage chores from the main app.

## Project layout

- `choreshare/` — Django project settings and root URL config
- `chores/` — the app: models, views, forms, URLs, and templates
- `_docs/` — product spec and backlog
