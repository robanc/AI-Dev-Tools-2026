from django.core.exceptions import ValidationError
from django.db import models


class Household(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Member(models.Model):
    name = models.CharField(max_length=100)
    household = models.ForeignKey(
        Household,
        on_delete=models.CASCADE,
        related_name="members",
    )

    def __str__(self):
        return self.name


class Chore(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    household = models.ForeignKey(
        Household,
        on_delete=models.CASCADE,
        related_name="chores",
    )
    assignee = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chores",
    )

    def __str__(self):
        return self.name

    def clean(self):
        """A chore may only be assigned to a member of its own household."""
        if self.household_id and self.assignee_id:
            if self.assignee.household_id != self.household_id:
                raise ValidationError(
                    {"assignee": "Assignee must be a member of this household."}
                )
