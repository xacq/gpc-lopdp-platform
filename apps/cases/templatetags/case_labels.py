from django import template

from apps.cases.models import RightsRequest
from apps.subjects.models import DataSubject, SubjectRepresentative


register = template.Library()


def _label_from_choices(value, choices):
    if value in (None, ""):
        return ""
    labels = dict(choices)
    return labels.get(str(value), value)


@register.filter
def subject_type_label(value):
    return _label_from_choices(value, DataSubject.SubjectType.choices)


@register.filter
def document_type_label(value):
    return _label_from_choices(value, DataSubject.DocumentType.choices)


@register.filter
def representative_document_type_label(value):
    return _label_from_choices(value, SubjectRepresentative.DocumentType.choices)


@register.filter
def representative_verification_status_label(value):
    return _label_from_choices(
        value,
        SubjectRepresentative.VerificationStatus.choices,
    )


@register.filter
def request_status_label(value):
    return _label_from_choices(value, RightsRequest.Status.choices)
