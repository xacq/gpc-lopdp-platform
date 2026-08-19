from django import forms

from apps.cases.models import RightsRequest


class AssignmentListFilterForm(forms.Form):
    search = forms.CharField(required=False, max_length=100)
    right_id = forms.UUIDField(required=False)
    status = forms.ChoiceField(
        required=False,
        choices=[("", "Todos"), *RightsRequest.Status.choices],
    )
    assignment_state = forms.ChoiceField(
        required=False,
        choices=(
            ("", "Todos"),
            ("ASSIGNED", "Asignados"),
            ("UNASSIGNED", "Sin asignar"),
        ),
    )
    assigned_to = forms.UUIDField(required=False)
    due_from = forms.DateField(required=False)
    due_to = forms.DateField(required=False)
    page = forms.IntegerField(required=False, min_value=1, initial=1)
    page_size = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=100,
        initial=20,
    )

    def clean_search(self):
        return (self.cleaned_data.get("search") or "").strip()

    def clean(self):
        cleaned = super().clean()
        due_from = cleaned.get("due_from")
        due_to = cleaned.get("due_to")
        if due_from and due_to and due_from > due_to:
            self.add_error(
                "due_to",
                "La fecha final no puede ser anterior a la inicial.",
            )
        return cleaned


class AssignmentHistoryFilterForm(forms.Form):
    request_id = forms.UUIDField(required=False)
    page = forms.IntegerField(required=False, min_value=1, initial=1)
    page_size = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=100,
        initial=20,
    )
