from django.contrib import admin

from .models import Household, Member, Chore


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("name", "household")
    list_filter = ("household",)


@admin.register(Chore)
class ChoreAdmin(admin.ModelAdmin):
    list_display = ("name", "household", "assignee", "is_completed", "due_date")
    list_filter = ("household", "is_completed", "assignee")
