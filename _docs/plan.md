# Product Spec: Household Chore Manager (ChoreShare)

*Module 1 homework project — Django. Version 1 scope.*

## Problem

People sharing a home — roommates, families, partners — argue about chores because
the work is **invisible and unaccountable**. There is no shared record of what needs
doing, who owns it, or whether it got done. The result is nagging, resentment, and the
"I always do more than you" argument.

The core problem is not *doing* chores — it is **shared visibility and fair attribution**
of who is responsible for what. ChoreShare's job is to be the single source of truth for
"what needs doing and who owns it."

## Target users

- **Primary:** Adults in shared living situations (roommates, couples, families) who
  split recurring domestic tasks.
- **Household size:** Small groups of ~2–6 people.
- **Tech comfort:** Everyday web users, not power users. Must be usable in seconds.

## Product principle (v1)

Make the state of chores visible and undeniable. Resolve arguments with a shared,
accurate record. Anything beyond visibility and ownership is out of scope for v1.

## Core features (v1)

1. **Households & members**
   Create a household and add members to it. Every chore and assignment belongs to one
   household, so people only see their own home's chores.

2. **Chore management (CRUD)**
   Create, view, edit, and delete chores. A chore has a name, an optional description,
   and an optional due date.

3. **Assignment & ownership**
   Assign a chore to a household member so responsibility is explicit and visible to all.

4. **Mark complete / status tracking**
   A member marks a chore as done. The list clearly separates pending vs. completed work,
   delivering the shared visibility that solves the core problem.

## Out of scope for v1

Deliberately deferred to keep the build achievable:

- Recurring / auto-repeating chores
- Notifications and reminders
- Points, leaderboards, or fairness scoring
- Mobile app
- Real-time updates
- A single user belonging to multiple households

## Why this fits a Module 1 Django homework

The spec maps cleanly onto core Django concepts with no extras:

- **Models:** Household, Member, Chore
- **Relationships:** ForeignKeys tying chores to a household and to an assigned member
- **CRUD:** standard views, forms, and templates for chores
- **Admin:** built-in admin for quick data entry
- **Templates:** simple list/detail pages showing pending vs. completed chores

It exercises the Django fundamentals end-to-end while staying small.
