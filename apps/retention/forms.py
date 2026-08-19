from django import forms

from apps.retention.models import DataDisposalEvent


class RetentionEventFilterForm(forms.Form):
    status = forms.ChoiceField(
        required=False,
        choices=[("", "Todos"), *DataDisposalEvent.Status.choices],
    )
    action = forms.ChoiceField(
        required=False,
        choices=[("", "Todas"), *DataDisposalEvent.Action.choices],
    )
    entity_type = forms.CharField(required=False, max_length=50)
    date_from = forms.DateField(required=False)
    date_to = forms.DateField(required=False)
    page = forms.IntegerField(required=False, min_value=1, initial=1)
    page_size = forms.IntegerField(
        required=False, min_value=1, max_value=100, initial=20
    )

    def clean_entity_type(self):
        return (self.cleaned_data.get("entity_type") or "").strip().upper()

    def clean(self):
        cleaned = super().clean()
        date_from = cleaned.get("date_from")
        date_to = cleaned.get("date_to")
        if date_from and date_to and date_from > date_to:
            self.add_error(
                "date_to", "La fecha final no puede ser anterior a la inicial."
            )
        return cleaned
