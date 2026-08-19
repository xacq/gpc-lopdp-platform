from datetime import timedelta

from django import forms

from apps.audit.models import AuditLog


class AuditEventFilterForm(forms.Form):
    date_from = forms.DateField(required=False)
    date_to = forms.DateField(required=False)
    actor = forms.UUIDField(required=False)
    action = forms.CharField(required=False, max_length=100)
    entity_type = forms.CharField(required=False, max_length=50)
    source = forms.ChoiceField(
        required=False,
        choices=(("", "Todos"), *AuditLog.Source.choices),
    )
    correlation_id = forms.UUIDField(required=False)
    chain_scope = forms.CharField(required=False, max_length=50)
    page = forms.IntegerField(required=False, min_value=1, initial=1)
    page_size = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=100,
        initial=25,
    )

    def clean(self):
        cleaned = super().clean()
        date_from = cleaned.get("date_from")
        date_to = cleaned.get("date_to")
        if date_from and date_to:
            if date_from > date_to:
                raise forms.ValidationError(
                    "La fecha inicial no puede superar la fecha final."
                )
            if date_to - date_from > timedelta(days=93):
                raise forms.ValidationError(
                    "El rango de auditoría no puede superar 93 días."
                )
        for field in ("action", "entity_type", "chain_scope"):
            cleaned[field] = (cleaned.get(field) or "").strip().upper()
        cleaned["source"] = cleaned.get("source") or ""
        cleaned["page"] = cleaned.get("page") or 1
        cleaned["page_size"] = cleaned.get("page_size") or 25
        return cleaned


class AuditIntegrityForm(forms.Form):
    chain_scope = forms.CharField(required=False, max_length=50)

    def clean_chain_scope(self):
        return (self.cleaned_data.get("chain_scope") or "GLOBAL").strip().upper()
