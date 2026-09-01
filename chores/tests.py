"""Automated QA suite for the ChoreShare v1 scope.

Tests are written against the specification in `_docs/plan.md` and the backlog in
`_docs/backlog.md`. Where the implementation diverges from the spec and the fix would
require new product behaviour, the current behaviour is pinned by a test whose name and
docstring call out the gap.
"""

import datetime

from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .forms import ChoreForm
from .models import Chore, Household, Member


class HouseholdModelTests(TestCase):
    def test_str_is_the_name(self):
        self.assertEqual(str(Household(name="Flat 2B")), "Flat 2B")

    def test_name_is_required(self):
        with self.assertRaises(ValidationError) as ctx:
            Household(name="").full_clean()
        self.assertIn("name", ctx.exception.message_dict)

    def test_name_max_length_is_enforced_by_validation(self):
        with self.assertRaises(ValidationError) as ctx:
            Household(name="x" * 101).full_clean()
        self.assertIn("name", ctx.exception.message_dict)

    def test_members_and_chores_are_reachable_by_related_name(self):
        household = Household.objects.create(name="Flat 2B")
        member = Member.objects.create(name="Ana", household=household)
        chore = Chore.objects.create(name="Dishes", household=household)

        self.assertEqual(list(household.members.all()), [member])
        self.assertEqual(list(household.chores.all()), [chore])


class MemberModelTests(TestCase):
    def setUp(self):
        self.household = Household.objects.create(name="Flat 2B")

    def test_str_is_the_name(self):
        self.assertEqual(str(Member(name="Ana")), "Ana")

    def test_household_is_required(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Member.objects.create(name="Ana", household=None)

    def test_deleting_household_cascades_to_members(self):
        Member.objects.create(name="Ana", household=self.household)
        self.household.delete()
        self.assertEqual(Member.objects.count(), 0)


class ChoreModelTests(TestCase):
    def setUp(self):
        self.household = Household.objects.create(name="Flat 2B")
        self.member = Member.objects.create(name="Ana", household=self.household)

    def test_str_is_the_name(self):
        self.assertEqual(str(Chore(name="Take out bins")), "Take out bins")

    def test_defaults_match_the_spec(self):
        """Per spec: description and due date are optional, chores start pending."""
        chore = Chore.objects.create(name="Dishes", household=self.household)

        self.assertEqual(chore.description, "")
        self.assertIsNone(chore.due_date)
        self.assertIsNone(chore.assignee)
        self.assertFalse(chore.is_completed)

    def test_household_is_required(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Chore.objects.create(name="Dishes", household=None)

    def test_name_is_required(self):
        chore = Chore(name="", household=self.household)
        with self.assertRaises(ValidationError) as ctx:
            chore.full_clean()
        self.assertIn("name", ctx.exception.message_dict)

    def test_name_max_length_is_enforced_by_validation(self):
        chore = Chore(name="x" * 201, household=self.household)
        with self.assertRaises(ValidationError) as ctx:
            chore.full_clean()
        self.assertIn("name", ctx.exception.message_dict)

    def test_optional_fields_pass_validation_when_empty(self):
        chore = Chore(name="Dishes", household=self.household)
        chore.full_clean()  # must not raise

    def test_deleting_household_cascades_to_chores(self):
        Chore.objects.create(name="Dishes", household=self.household)
        self.household.delete()
        self.assertEqual(Chore.objects.count(), 0)

    def test_deleting_assignee_unassigns_chore_but_keeps_it(self):
        """Losing a member must not lose the chore: SET_NULL, not CASCADE."""
        chore = Chore.objects.create(
            name="Dishes", household=self.household, assignee=self.member
        )
        self.member.delete()
        chore.refresh_from_db()

        self.assertIsNone(chore.assignee)
        self.assertTrue(Chore.objects.filter(pk=chore.pk).exists())

    def test_assignee_must_belong_to_the_chores_household(self):
        """Spec: 'Assign a chore to a household member' — the assignee's household
        must be the chore's household."""
        other_household = Household.objects.create(name="Next door")
        outsider = Member.objects.create(name="Ben", household=other_household)

        chore = Chore(name="Dishes", household=self.household, assignee=outsider)
        with self.assertRaises(ValidationError) as ctx:
            chore.full_clean()
        self.assertIn("assignee", ctx.exception.message_dict)

    def test_assignee_from_same_household_is_valid(self):
        chore = Chore(name="Dishes", household=self.household, assignee=self.member)
        chore.full_clean()  # must not raise

    def test_clean_does_not_crash_when_household_is_missing(self):
        """`full_clean` runs field checks and `clean()` together; a missing household
        must surface as a field error, not an unrelated exception."""
        chore = Chore(name="Dishes")
        with self.assertRaises(ValidationError) as ctx:
            chore.full_clean()
        self.assertIn("household", ctx.exception.message_dict)


class ChoreFormTests(TestCase):
    def setUp(self):
        self.household = Household.objects.create(name="Flat 2B")
        self.member = Member.objects.create(name="Ana", household=self.household)

    def test_valid_with_only_the_required_fields(self):
        form = ChoreForm(data={"name": "Dishes", "household": self.household.pk})
        self.assertTrue(form.is_valid(), form.errors)

    def test_name_is_required(self):
        form = ChoreForm(data={"name": "", "household": self.household.pk})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_household_is_required(self):
        form = ChoreForm(data={"name": "Dishes", "household": ""})
        self.assertFalse(form.is_valid())
        self.assertIn("household", form.errors)

    def test_invalid_due_date_is_rejected(self):
        form = ChoreForm(
            data={
                "name": "Dishes",
                "household": self.household.pk,
                "due_date": "not-a-date",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("due_date", form.errors)

    def test_is_completed_is_not_editable_through_the_form(self):
        """Completion is changed only via the toggle action (backlog item 9)."""
        self.assertNotIn("is_completed", ChoreForm().fields)

    def test_rejects_assignee_from_another_household(self):
        outsider = Member.objects.create(
            name="Ben", household=Household.objects.create(name="Next door")
        )
        form = ChoreForm(
            data={
                "name": "Dishes",
                "household": self.household.pk,
                "assignee": outsider.pk,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("assignee", form.errors)

    def test_accepts_assignee_from_the_same_household(self):
        form = ChoreForm(
            data={
                "name": "Dishes",
                "household": self.household.pk,
                "assignee": self.member.pk,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)


class ChoreListViewTests(TestCase):
    def setUp(self):
        self.household = Household.objects.create(name="Flat 2B")
        self.member = Member.objects.create(name="Ana", household=self.household)
        self.url = reverse("chores:chore_list")

    def test_renders_empty_state_for_both_sections(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "chores/chore_list.html")
        self.assertContains(response, "No pending chores.")
        self.assertContains(response, "No completed chores.")

    def test_splits_pending_and_completed_chores(self):
        pending = Chore.objects.create(name="Dishes", household=self.household)
        done = Chore.objects.create(
            name="Vacuum", household=self.household, is_completed=True
        )

        response = self.client.get(self.url)

        self.assertCountEqual(response.context["pending_chores"], [pending])
        self.assertCountEqual(response.context["completed_chores"], [done])

    def test_shows_name_assignee_and_due_date(self):
        Chore.objects.create(
            name="Dishes",
            household=self.household,
            assignee=self.member,
            due_date=datetime.date(2026, 9, 1),
        )

        response = self.client.get(self.url)

        self.assertContains(response, "Dishes")
        self.assertContains(response, "Ana")
        self.assertContains(response, "Sept. 1, 2026")

    def test_shows_placeholders_when_assignee_and_due_date_are_empty(self):
        Chore.objects.create(name="Dishes", household=self.household)

        response = self.client.get(self.url)

        self.assertContains(response, "Unassigned")
        self.assertContains(response, "No due date")

    def test_each_chore_links_to_its_detail_page(self):
        chore = Chore.objects.create(name="Dishes", household=self.household)

        response = self.client.get(self.url)

        self.assertContains(
            response, reverse("chores:chore_detail", args=[chore.pk])
        )

    def test_offers_mark_complete_for_pending_and_reopen_for_completed(self):
        Chore.objects.create(name="Dishes", household=self.household)
        Chore.objects.create(
            name="Vacuum", household=self.household, is_completed=True
        )

        response = self.client.get(self.url)

        self.assertContains(response, "Mark complete")
        self.assertContains(response, "Reopen")

    def test_lists_chores_from_every_household_known_spec_gap(self):
        """KNOWN GAP: the spec says 'people only see their own home's chores' and
        backlog item 4 says the list is 'for a household', but `chore_list` is
        unscoped and shows every household's chores. v1 has no login and no
        household selector, so there is nothing to scope by. This test pins the
        current behaviour; closing the gap needs a product decision.
        """
        other = Household.objects.create(name="Next door")
        mine = Chore.objects.create(name="My dishes", household=self.household)
        theirs = Chore.objects.create(name="Their dishes", household=other)

        response = self.client.get(self.url)

        self.assertCountEqual(response.context["pending_chores"], [mine, theirs])


class ChoreDetailViewTests(TestCase):
    def setUp(self):
        self.household = Household.objects.create(name="Flat 2B")
        self.member = Member.objects.create(name="Ana", household=self.household)

    def test_shows_every_spec_field(self):
        chore = Chore.objects.create(
            name="Dishes",
            description="Including the pans",
            due_date=datetime.date(2026, 9, 1),
            household=self.household,
            assignee=self.member,
        )

        response = self.client.get(
            reverse("chores:chore_detail", args=[chore.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "chores/chore_detail.html")
        self.assertContains(response, "Dishes")
        self.assertContains(response, "Including the pans")
        self.assertContains(response, "Sept. 1, 2026")
        self.assertContains(response, "Ana")
        self.assertContains(response, "Flat 2B")
        self.assertContains(response, "Pending")

    def test_shows_completed_status(self):
        chore = Chore.objects.create(
            name="Dishes", household=self.household, is_completed=True
        )

        response = self.client.get(
            reverse("chores:chore_detail", args=[chore.pk])
        )

        self.assertContains(response, "Completed")

    def test_shows_placeholders_for_empty_optional_fields(self):
        chore = Chore.objects.create(name="Dishes", household=self.household)

        response = self.client.get(
            reverse("chores:chore_detail", args=[chore.pk])
        )

        self.assertContains(response, "Unassigned")
        self.assertContains(response, "No due date")
        self.assertContains(response, "No description")

    def test_unknown_chore_returns_404(self):
        response = self.client.get(reverse("chores:chore_detail", args=[9999]))
        self.assertEqual(response.status_code, 404)


class ChoreCreateViewTests(TestCase):
    def setUp(self):
        self.household = Household.objects.create(name="Flat 2B")
        self.member = Member.objects.create(name="Ana", household=self.household)
        self.url = reverse("chores:chore_create")

    def test_get_renders_a_blank_form(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "chores/chore_form.html")
        self.assertIsInstance(response.context["form"], ChoreForm)
        self.assertEqual(response.context["form_title"], "New chore")

    def test_post_creates_chore_and_redirects_to_the_list(self):
        response = self.client.post(
            self.url,
            {
                "name": "Dishes",
                "description": "Including the pans",
                "due_date": "2026-09-01",
                "household": self.household.pk,
                "assignee": self.member.pk,
            },
        )

        self.assertRedirects(response, reverse("chores:chore_list"))
        chore = Chore.objects.get()
        self.assertEqual(chore.name, "Dishes")
        self.assertEqual(chore.description, "Including the pans")
        self.assertEqual(chore.due_date, datetime.date(2026, 9, 1))
        self.assertEqual(chore.assignee, self.member)
        self.assertEqual(chore.household, self.household)
        self.assertFalse(chore.is_completed)

    def test_post_creates_chore_with_only_required_fields(self):
        response = self.client.post(
            self.url, {"name": "Dishes", "household": self.household.pk}
        )

        self.assertRedirects(response, reverse("chores:chore_list"))
        self.assertEqual(Chore.objects.count(), 1)

    def test_invalid_post_redisplays_form_with_errors_and_saves_nothing(self):
        response = self.client.post(
            self.url, {"name": "", "household": self.household.pk}
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "chores/chore_form.html")
        self.assertFormError(response.context["form"], "name", "This field is required.")
        self.assertEqual(Chore.objects.count(), 0)

    def test_cannot_create_chore_assigned_outside_its_household(self):
        outsider = Member.objects.create(
            name="Ben", household=Household.objects.create(name="Next door")
        )

        response = self.client.post(
            self.url,
            {
                "name": "Dishes",
                "household": self.household.pk,
                "assignee": outsider.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors["assignee"])
        self.assertEqual(Chore.objects.count(), 0)


class ChoreUpdateViewTests(TestCase):
    def setUp(self):
        self.household = Household.objects.create(name="Flat 2B")
        self.ana = Member.objects.create(name="Ana", household=self.household)
        self.ben = Member.objects.create(name="Ben", household=self.household)
        self.chore = Chore.objects.create(
            name="Dishes", household=self.household, assignee=self.ana
        )
        self.url = reverse("chores:chore_update", args=[self.chore.pk])

    def test_get_renders_form_prefilled_with_the_chore(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "chores/chore_form.html")
        self.assertEqual(response.context["form"].instance, self.chore)
        self.assertEqual(response.context["form_title"], "Edit chore")

    def test_post_updates_chore_and_redirects_to_detail(self):
        response = self.client.post(
            self.url,
            {
                "name": "Dishes and pans",
                "description": "Every night",
                "due_date": "2026-09-02",
                "household": self.household.pk,
                "assignee": self.ana.pk,
            },
        )

        self.assertRedirects(
            response, reverse("chores:chore_detail", args=[self.chore.pk])
        )
        self.chore.refresh_from_db()
        self.assertEqual(self.chore.name, "Dishes and pans")
        self.assertEqual(self.chore.description, "Every night")
        self.assertEqual(self.chore.due_date, datetime.date(2026, 9, 2))

    def test_can_reassign_to_another_member(self):
        """Spec feature 3: responsibility must be re-assignable."""
        self.client.post(
            self.url,
            {
                "name": "Dishes",
                "household": self.household.pk,
                "assignee": self.ben.pk,
            },
        )

        self.chore.refresh_from_db()
        self.assertEqual(self.chore.assignee, self.ben)

    def test_can_unassign_by_clearing_the_assignee(self):
        self.client.post(
            self.url,
            {"name": "Dishes", "household": self.household.pk, "assignee": ""},
        )

        self.chore.refresh_from_db()
        self.assertIsNone(self.chore.assignee)

    def test_editing_does_not_change_completion_status(self):
        self.chore.is_completed = True
        self.chore.save(update_fields=["is_completed"])

        self.client.post(
            self.url, {"name": "Dishes", "household": self.household.pk}
        )

        self.chore.refresh_from_db()
        self.assertTrue(self.chore.is_completed)

    def test_invalid_post_redisplays_form_and_keeps_stored_values(self):
        response = self.client.post(
            self.url, {"name": "", "household": self.household.pk}
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "name", "This field is required.")
        self.chore.refresh_from_db()
        self.assertEqual(self.chore.name, "Dishes")

    def test_cannot_reassign_to_a_member_of_another_household(self):
        outsider = Member.objects.create(
            name="Cass", household=Household.objects.create(name="Next door")
        )

        response = self.client.post(
            self.url,
            {
                "name": "Dishes",
                "household": self.household.pk,
                "assignee": outsider.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors["assignee"])
        self.chore.refresh_from_db()
        self.assertEqual(self.chore.assignee, self.ana)

    def test_unknown_chore_returns_404(self):
        response = self.client.get(reverse("chores:chore_update", args=[9999]))
        self.assertEqual(response.status_code, 404)


class ChoreDeleteViewTests(TestCase):
    def setUp(self):
        self.household = Household.objects.create(name="Flat 2B")
        self.chore = Chore.objects.create(name="Dishes", household=self.household)
        self.url = reverse("chores:chore_delete", args=[self.chore.pk])

    def test_get_shows_confirmation_without_deleting(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "chores/chore_confirm_delete.html")
        self.assertContains(response, "Dishes")
        self.assertTrue(Chore.objects.filter(pk=self.chore.pk).exists())

    def test_post_deletes_chore_and_redirects_to_the_list(self):
        response = self.client.post(self.url)

        self.assertRedirects(response, reverse("chores:chore_list"))
        self.assertFalse(Chore.objects.filter(pk=self.chore.pk).exists())

    def test_deleting_a_chore_leaves_household_and_members_intact(self):
        member = Member.objects.create(name="Ana", household=self.household)

        self.client.post(self.url)

        self.assertTrue(Household.objects.filter(pk=self.household.pk).exists())
        self.assertTrue(Member.objects.filter(pk=member.pk).exists())

    def test_unknown_chore_returns_404(self):
        response = self.client.get(reverse("chores:chore_delete", args=[9999]))
        self.assertEqual(response.status_code, 404)


class ChoreToggleViewTests(TestCase):
    def setUp(self):
        self.household = Household.objects.create(name="Flat 2B")
        self.chore = Chore.objects.create(name="Dishes", household=self.household)
        self.url = reverse("chores:chore_toggle", args=[self.chore.pk])

    def test_post_marks_a_pending_chore_complete(self):
        response = self.client.post(self.url)

        self.assertRedirects(response, reverse("chores:chore_list"))
        self.chore.refresh_from_db()
        self.assertTrue(self.chore.is_completed)

    def test_post_reopens_a_completed_chore(self):
        self.chore.is_completed = True
        self.chore.save(update_fields=["is_completed"])

        self.client.post(self.url)

        self.chore.refresh_from_db()
        self.assertFalse(self.chore.is_completed)

    def test_toggle_moves_chore_between_list_sections(self):
        self.client.post(self.url)
        response = self.client.get(reverse("chores:chore_list"))

        self.assertCountEqual(response.context["pending_chores"], [])
        self.assertCountEqual(response.context["completed_chores"], [self.chore])

    def test_honours_a_safe_next_url(self):
        detail = reverse("chores:chore_detail", args=[self.chore.pk])

        response = self.client.post(self.url, {"next": detail})

        self.assertRedirects(response, detail)

    def test_ignores_an_off_site_next_url(self):
        response = self.client.post(
            self.url, {"next": "https://evil.example.com/steal"}
        )

        self.assertRedirects(response, reverse("chores:chore_list"))

    def test_get_does_not_change_status(self):
        """Toggling is a mutation, so it must not happen on a GET."""
        response = self.client.get(self.url)

        self.assertRedirects(response, reverse("chores:chore_list"))
        self.chore.refresh_from_db()
        self.assertFalse(self.chore.is_completed)

    def test_toggling_does_not_change_other_fields(self):
        chore = Chore.objects.create(
            name="Vacuum",
            description="Upstairs",
            due_date=datetime.date(2026, 9, 1),
            household=self.household,
            assignee=Member.objects.create(name="Ana", household=self.household),
        )

        self.client.post(reverse("chores:chore_toggle", args=[chore.pk]))

        chore.refresh_from_db()
        self.assertEqual(chore.name, "Vacuum")
        self.assertEqual(chore.description, "Upstairs")
        self.assertEqual(chore.due_date, datetime.date(2026, 9, 1))
        self.assertEqual(chore.assignee.name, "Ana")

    def test_toggling_one_chore_leaves_others_alone(self):
        other = Chore.objects.create(name="Vacuum", household=self.household)

        self.client.post(self.url)

        other.refresh_from_db()
        self.assertFalse(other.is_completed)

    def test_unknown_chore_returns_404(self):
        response = self.client.post(reverse("chores:chore_toggle", args=[9999]))
        self.assertEqual(response.status_code, 404)


class AdminTests(TestCase):
    """Backlog item 3: the admin is the data-entry path for households and members."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="qa", email="qa@example.com", password="pw-for-tests"
        )

    def setUp(self):
        self.client.force_login(self.superuser)

    def test_all_three_models_are_registered(self):
        for model in (Household, Member, Chore):
            with self.subTest(model=model.__name__):
                self.assertIn(model, admin.site._registry)

    def test_chore_changelist_shows_household_assignee_and_status(self):
        household = Household.objects.create(name="Flat 2B")
        Chore.objects.create(
            name="Dishes",
            household=household,
            assignee=Member.objects.create(name="Ana", household=household),
        )

        response = self.client.get(reverse("admin:chores_chore_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dishes")
        self.assertContains(response, "Flat 2B")
        self.assertContains(response, "Ana")

    def test_admin_also_rejects_an_assignee_from_another_household(self):
        household = Household.objects.create(name="Flat 2B")
        outsider = Member.objects.create(
            name="Ben", household=Household.objects.create(name="Next door")
        )

        response = self.client.post(
            reverse("admin:chores_chore_add"),
            {
                "name": "Dishes",
                "description": "",
                "due_date": "",
                "household": household.pk,
                "assignee": outsider.pk,
            },
        )

        self.assertEqual(response.status_code, 200)  # re-rendered with errors
        self.assertEqual(Chore.objects.count(), 0)


class NavigationTests(TestCase):
    def test_every_page_links_back_to_the_chore_list(self):
        """Backlog item 10: shared layout reachable from every page."""
        household = Household.objects.create(name="Flat 2B")
        chore = Chore.objects.create(name="Dishes", household=household)
        list_url = reverse("chores:chore_list")

        for url in (
            list_url,
            reverse("chores:chore_create"),
            reverse("chores:chore_detail", args=[chore.pk]),
            reverse("chores:chore_update", args=[chore.pk]),
            reverse("chores:chore_delete", args=[chore.pk]),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, f'href="{list_url}"')
