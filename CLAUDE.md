# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

Coursework and homework for the [DataTalksClub](https://datatalks.club/) **AI Dev Tools Zoomcamp**. It is a personal learning repository that tracks assignments and notes as the course progresses.

The Module 1 homework is **ChoreShare**, a Django web app for managing shared household chores. It currently occupies the repository root. The product spec is in `_docs/plan.md` and the ordered implementation backlog is in `_docs/backlog.md`; both define a deliberately small v1 scope, and out-of-scope items are listed explicitly (recurring chores, notifications, gamification, mobile, real-time, multi-household users). Do not add features from the out-of-scope list.

## Stack

- Python 3.12+, Django 6.1 (`requirements.txt` is the only dependency manifest)
- SQLite (`db.sqlite3`, gitignored via `*.sqlite3`)
- Server-rendered Django templates; no frontend build step, no CSS/JS framework
- No linter, formatter, or type checker is configured

## Commands

Run from the repository root with the virtualenv active (`.\venv\Scripts\Activate.ps1` on Windows PowerShell, `source venv/bin/activate` elsewhere).

```bash
pip install -r requirements.txt      # install deps
python manage.py migrate             # apply migrations
python manage.py createsuperuser     # admin login for /admin
python manage.py runserver           # dev server at http://127.0.0.1:8000/
python manage.py makemigrations      # after any models.py change
python manage.py test                # full suite (66 tests in chores/tests.py)
python manage.py test chores.tests.ChoreToggleViewTests         # one test class
python manage.py check               # config sanity check
```

## Layout

- `choreshare/` — project package: `settings.py`, root `urls.py` (admin at `admin/`, everything else included from `chores.urls`)
- `chores/` — the single app: `models.py`, `views.py`, `forms.py`, `urls.py`, `admin.py`, `tests.py`, `migrations/`
- `chores/templates/chores/` — app-level templates (`base.html` plus list/detail/form/confirm-delete)
- `_docs/` — product spec (`plan.md`) and backlog (`backlog.md`)

## Code conventions

- **Models:** `Household` → `Member` (FK, CASCADE) → `Chore` (FK to both; `assignee` is nullable with `SET_NULL`). Every model defines `__str__`. `Chore.clean()` enforces that the assignee belongs to the chore's household — validation lives on the model so both `ChoreForm` and the admin form inherit it.
- **Views:** plain function-based views, not class-based generics. Each has a one-line docstring. Use `get_object_or_404`, `select_related` for FK access in lists, and mutating actions accept `POST` only.
- **URLs:** the `chores` app uses `app_name = "chores"`, so always reverse as `chores:chore_list`, `chores:chore_detail`, etc.
- **Forms:** `ModelForm` with an explicit `fields` list.
- **Style:** double-quoted strings and trailing commas in app code (the `choreshare/` files remain as `django-admin` generated them, with single quotes). Standard-library, Django, then local imports.

## Notes

- `settings.py` is development-only: `DEBUG = True` and the generated `django-insecure-` secret key are checked in. That is acceptable for this coursework; do not add production deployment config unless asked.
- Keep planning and course notes under `_docs/`. If later course units add separate work, give each unit its own directory rather than mixing it into `chores/`.
