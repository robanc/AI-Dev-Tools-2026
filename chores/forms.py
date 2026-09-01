from django import forms

from .models import Chore


class ChoreForm(forms.ModelForm):
    class Meta:
        model = Chore
        fields = ["name", "description", "due_date", "household", "assignee"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }
