from django import forms

from apps.communications.models import RequestCommunication


class CommunicationFilterForm(forms.Form):
    request_id = forms.UUIDField(required=False)
    direction = forms.ChoiceField(
        required=False,
        choices=[("", "Todas"), *RequestCommunication.Direction.choices],
    )
    channel = forms.ChoiceField(
        required=False,
        choices=[("", "Todos"), *RequestCommunication.Channel.choices],
    )
    communication_type = forms.ChoiceField(
        required=False,
        choices=[("", "Todos"), *RequestCommunication.CommunicationType.choices],
    )
    delivery_status = forms.ChoiceField(
        required=False,
        choices=[("", "Todos"), *RequestCommunication.DeliveryStatus.choices],
    )
    visible_to_subject = forms.NullBooleanField(required=False)
    date_from = forms.DateField(required=False)
    date_to = forms.DateField(required=False)
    page = forms.IntegerField(required=False, min_value=1, initial=1)
    page_size = forms.IntegerField(
        required=False, min_value=1, max_value=100, initial=20
    )

    def clean(self):
        cleaned = super().clean()
        date_from = cleaned.get("date_from")
        date_to = cleaned.get("date_to")
        if date_from and date_to and date_from > date_to:
            self.add_error(
                "date_to", "La fecha final no puede ser anterior a la inicial."
            )
        return cleaned


class OutboundCommunicationForm(forms.Form):
    request_id = forms.UUIDField()
    communication_type = forms.ChoiceField(
        choices=RequestCommunication.CommunicationType.choices
    )
    recipient = forms.EmailField(max_length=254)
    subject = forms.CharField(max_length=998)
    body = forms.CharField()
    visible_to_subject = forms.BooleanField(required=False)
    idempotency_key = forms.UUIDField(required=False)


class InboundCommunicationForm(forms.Form):
    request_id = forms.UUIDField()
    channel = forms.ChoiceField(choices=RequestCommunication.Channel.choices)
    communication_type = forms.ChoiceField(
        choices=RequestCommunication.CommunicationType.choices
    )
    contact = forms.CharField(max_length=254)
    subject = forms.CharField(max_length=998)
    body = forms.CharField()
    visible_to_subject = forms.BooleanField(required=False)
    idempotency_key = forms.UUIDField(required=False)


class PortabilityGenerateForm(forms.Form):
    request_id = forms.UUIDField()
    export_format = forms.ChoiceField(
        choices=(("JSON", "JSON"), ("CSV", "CSV"))
    )


class PortabilityDownloadForm(forms.Form):
    export_id = forms.UUIDField()
    token = forms.CharField(max_length=512)
