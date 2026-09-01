from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import ChoreForm
from .models import Chore


def chore_list(request):
    """List all chores, split into pending and completed sections."""
    chores = Chore.objects.select_related("assignee", "household")
    context = {
        "pending_chores": chores.filter(is_completed=False),
        "completed_chores": chores.filter(is_completed=True),
    }
    return render(request, "chores/chore_list.html", context)


def chore_detail(request, pk):
    """Show a single chore's full details."""
    chore = get_object_or_404(
        Chore.objects.select_related("assignee", "household"), pk=pk
    )
    return render(request, "chores/chore_detail.html", {"chore": chore})


def chore_create(request):
    """Create a new chore."""
    if request.method == "POST":
        form = ChoreForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("chores:chore_list")
    else:
        form = ChoreForm()
    return render(
        request,
        "chores/chore_form.html",
        {"form": form, "form_title": "New chore"},
    )


def chore_update(request, pk):
    """Edit an existing chore, including reassigning it to another member."""
    chore = get_object_or_404(Chore, pk=pk)
    if request.method == "POST":
        form = ChoreForm(request.POST, instance=chore)
        if form.is_valid():
            form.save()
            return redirect("chores:chore_detail", pk=chore.pk)
    else:
        form = ChoreForm(instance=chore)
    return render(
        request,
        "chores/chore_form.html",
        {"form": form, "form_title": "Edit chore"},
    )


def chore_delete(request, pk):
    """Delete a chore after a confirmation step."""
    chore = get_object_or_404(Chore, pk=pk)
    if request.method == "POST":
        chore.delete()
        return redirect("chores:chore_list")
    return render(request, "chores/chore_confirm_delete.html", {"chore": chore})


def chore_toggle(request, pk):
    """Toggle a chore's completion status (mark complete / reopen)."""
    chore = get_object_or_404(Chore, pk=pk)
    if request.method == "POST":
        chore.is_completed = not chore.is_completed
        chore.save(update_fields=["is_completed"])
    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}
    ):
        return redirect(next_url)
    return redirect("chores:chore_list")
