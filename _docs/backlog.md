# Implementation Backlog: ChoreShare (v1)

Ordered tasks for the v1 scope defined in [plan.md](./plan.md). Complete them top to
bottom — each builds on the previous. Scope is limited to v1; out-of-scope items from the
plan are excluded.

---

## 1. Project & app scaffolding
Set up the Django project and a single `chores` app.
- **Outcome:** `python manage.py runserver` starts cleanly and serves the default page; the
  `chores` app is registered in `INSTALLED_APPS`.

## 2. Data models
Define the three v1 models in the `chores` app.
- `Household` — name.
- `Member` — name, ForeignKey to `Household`.
- `Chore` — name, optional description, optional due date, `is_completed` flag, ForeignKey
  to `Household`, nullable ForeignKey to `Member` (assignee).
- **Outcome:** Models are written, migrations created and applied, and a `__str__` is
  defined on each model.

## 3. Admin registration
Register all three models with the Django admin.
- **Outcome:** A superuser can create households, members, and chores through `/admin`,
  and chore list view shows household, assignee, and completion status.

## 4. Chore list view
Build the main page listing chores for a household, separated into **pending** and
**completed** sections, each showing name, assignee, and due date.
- **Outcome:** Visiting the chore list URL renders both sections from the database.

## 5. Chore detail view
Show a single chore's full details (name, description, due date, assignee, status).
- **Outcome:** Each chore in the list links to a working detail page.

## 6. Create chore
Add a form + view to create a new chore (name, description, due date, household, assignee).
- **Outcome:** Submitting the form saves a new chore and redirects to the list; validation
  errors are shown for invalid input.

## 7. Edit chore
Add a form + view to edit an existing chore, including reassigning it to a different member.
- **Outcome:** Submitting the edit form updates the chore and redirects to its detail page.

## 8. Delete chore
Add a delete view with a confirmation step.
- **Outcome:** Confirming deletion removes the chore and redirects to the list.

## 9. Mark complete / reopen
Add an action to toggle a chore's completion status directly from the list or detail view.
- **Outcome:** Toggling moves the chore between the pending and completed sections and
  persists the change.

## 10. Base template & navigation
Add a shared base template with minimal navigation and apply it across the pages.
- **Outcome:** All pages share a consistent layout; the chore list is reachable from every
  page.

## 11. README & run instructions
Document how to set up and run the project (install, migrate, create superuser, runserver).
- **Outcome:** A new developer can follow the README to run the app locally from a clean
  checkout.

---

### Explicitly deferred (not in this backlog)
Per the plan's out-of-scope list: recurring chores, notifications/reminders, gamification,
mobile app, real-time updates, and multi-household users.
