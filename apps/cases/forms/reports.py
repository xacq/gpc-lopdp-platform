from datetime import timedelta

from django import forms

from apps.cases.models import RightsRequest


class CaseReportFilterForm(forms.Form):
    date_from = forms.DateField(required=False)
    date_to = forms.DateField(required=False)
    right_code = forms.CharField(required=False, max_length=50)
    status = forms.ChoiceField(
        required=False,
        choices=(("", "Todos"), *RightsRequest.Status.choices),
    )
    assigned_to = forms.UUIDField(required=False)

    def clean(self):
        cleaned = super().clean()
        date_from = cleaned.get("date_from")
        date_to = cleaned.get("date_to")
        if bool(date_from) != bool(date_to):
            raise forms.ValidationError(
                "Debe proporcionar ambas fechas del rango."
            )
        if date_from and date_to:
            if date_from > date_to:
                raise forms.ValidationError(
                    "La fecha inicial no puede superar la fecha final."
                )
            if date_to - date_from > timedelta(days=366):
                raise forms.ValidationError(
                    "El rango no puede superar 366 días."
                )
        cleaned["right_code"] = (
            cleaned.get("right_code") or ""
        ).strip().upper()
        cleaned["status"] = cleaned.get("status") or ""
        return cleaned

