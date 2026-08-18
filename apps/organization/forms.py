from django import forms

from apps.organization.models import SystemSetting


class SystemSettingForm(forms.ModelForm):
    class Meta:
        model = SystemSetting
        fields = (
            "legal_name",
            "trade_name",
            "ruc",
            "domain",
            "address",
            "phone",
            "contact_email",
            "controller_name",
            "controller_email",
            "controller_phone",
            "dpd_name",
            "dpd_email",
            "dpd_phone",
            "complaint_authority_name",
            "complaint_channel_url",
            "complaint_instructions",
            "request_prefix",
            "timezone",
            "logo_url",
            "favicon_url",
            "primary_color",
            "secondary_color",
            "accent_color",
        )
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
            "complaint_instructions": forms.Textarea(
                attrs={"rows": 4}
            ),
            "primary_color": forms.TextInput(
                attrs={"placeholder": "#RRGGBB"}
            ),
            "secondary_color": forms.TextInput(
                attrs={"placeholder": "#RRGGBB"}
            ),
            "accent_color": forms.TextInput(
                attrs={"placeholder": "#RRGGBB"}
            ),
        }
