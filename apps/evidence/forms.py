from django import forms

from apps.evidence.models import IdentityVerification


class IdentityVerificationFilterForm(forms.Form):
    request_id = forms.UUIDField()


class IdentityVerificationCreateForm(forms.Form):
    request_id = forms.UUIDField()
    verification_method = forms.ChoiceField(
        choices=IdentityVerification.VerificationMethod.choices
    )
    result = forms.ChoiceField(choices=IdentityVerification.Result.choices)
    validation_notes = forms.CharField(required=False, max_length=5000)


class AttachmentFilterForm(forms.Form):
    request_id = forms.UUIDField()
