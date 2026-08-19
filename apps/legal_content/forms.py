from django import forms

from apps.legal_content.models import LegalDocument


class LegalDocumentFilterForm(forms.Form):
    document_type = forms.ChoiceField(
        required=False,
        choices=[("", "Todos"), *LegalDocument.DocumentType.choices],
    )
    published = forms.NullBooleanField(required=False)


class LegalDocumentCreateForm(forms.Form):
    document_type = forms.ChoiceField(choices=LegalDocument.DocumentType.choices)
    title = forms.CharField(max_length=250)
    slug = forms.SlugField(required=False, max_length=180)
    version = forms.CharField(max_length=30)
    content_html = forms.CharField()
    effective_from = forms.DateTimeField()
