from django.urls import path

from . import views

app_name = "chores"

urlpatterns = [
    path("", views.chore_list, name="chore_list"),
    path("new/", views.chore_create, name="chore_create"),
    path("<int:pk>/", views.chore_detail, name="chore_detail"),
    path("<int:pk>/edit/", views.chore_update, name="chore_update"),
    path("<int:pk>/delete/", views.chore_delete, name="chore_delete"),
    path("<int:pk>/toggle/", views.chore_toggle, name="chore_toggle"),
]
