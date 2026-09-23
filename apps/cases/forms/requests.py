from django import forms
from django.contrib.auth import (
    get_user_model,
)
from django.db.models import Q

from apps.cases.models import (
    CaseOutcomeReason,
    RequestResolution,
    RightsRequest,
)
from apps.cases.services.cases import (
    CaseWorkflowService,
)
from apps.legal_content.models import (
    RightCatalog,
)
from apps.subjects.models import (
    DataSubject,
    SubjectRepresentative,
)


class OutcomeReasonSelect(forms.Select):
    """Expose the reason category so the resolution form can filter it."""

    def create_option(
        self,
        name,
        value,
        label,
        selected,
        index,
        subindex=None,
        attrs=None,
    ):
        option = super().create_option(
            name,
            value,
            label,
            selected,
            index,
            subindex=subindex,
            attrs=attrs,
        )
        instance = getattr(value, "instance", None)
        if instance is not None:
            option["attrs"]["data-reason-type"] = instance.reason_type
        return option


class RequestListFilterForm(forms.Form):
    search = forms.CharField(required=False, max_length=100)
    right = forms.ModelChoiceField(
        required=False,
        queryset=RightCatalog.objects.none(),
        empty_label="Todos los derechos",
    )
    status = forms.ChoiceField(
        required=False,
        choices=(("", "Todos los estados"), *RightsRequest.Status.choices),
    )
    assignment_state = forms.ChoiceField(
        required=False,
        choices=(
            ("", "Todos"),
            ("ASSIGNED", "Asignados"),
            ("UNASSIGNED", "Sin asignar"),
        ),
    )
    page = forms.IntegerField(required=False, min_value=1, initial=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["right"].queryset = RightCatalog.objects.filter(
            is_active=True
        ).order_by("name")

    def clean_search(self):
        return (self.cleaned_data.get("search") or "").strip()


class RequestCreateForm(forms.Form):
    subject_type = forms.ChoiceField(
        label="Tipo de titular",
        choices=(
            DataSubject
            .SubjectType
            .choices
        ),
    )

    document_type = forms.ChoiceField(
        label="Tipo de documento",
        choices=(
            DataSubject
            .DocumentType
            .choices
        ),
    )

    document_number = (
        forms.CharField(
            label="Número de documento",
            max_length=80,
        )
    )

    full_name = forms.CharField(
        label="Nombre completo",
        max_length=180,
    )

    email = forms.EmailField(
        label="Correo electrónico",
        max_length=254,
    )

    phone = forms.CharField(
        label="Teléfono",
        max_length=50,
        required=False,
    )

    right = forms.ModelChoiceField(
        label="Derecho",
        queryset=(
            RightCatalog.objects.none()
        ),
        empty_label=(
            "Seleccione un derecho"
        ),
    )

    request_details = (
        forms.CharField(
            label=(
                "Descripción de la solicitud"
            ),
            widget=forms.Textarea(
                attrs={
                    "rows": 7,
                }
            ),
        )
    )

    source_channel = (
        forms.ChoiceField(
            label="Canal de recepción",
            choices=(
                RightsRequest
                .SourceChannel
                .choices
            ),
            initial=(
                RightsRequest
                .SourceChannel
                .WEB
            ),
        )
    )

    has_representative = (
        forms.BooleanField(
            label=(
                "La solicitud utiliza "
                "representante"
            ),
            required=False,
        )
    )

    representative_name = (
        forms.CharField(
            label=(
                "Nombre del representante"
            ),
            max_length=180,
            required=False,
        )
    )

    representative_document_type = (
        forms.ChoiceField(
            label=(
                "Tipo de documento "
                "del representante"
            ),
            choices=(
                [
                    ("", "Seleccione"),
                    *(
                        SubjectRepresentative
                        .DocumentType
                        .choices
                    ),
                ]
            ),
            required=False,
        )
    )

    representative_document_number = (
        forms.CharField(
            label=(
                "Número de documento "
                "del representante"
            ),
            max_length=80,
            required=False,
        )
    )

    representative_email = (
        forms.EmailField(
            label=(
                "Correo del representante"
            ),
            max_length=254,
            required=False,
        )
    )

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.fields[
            "right"
        ].queryset = (
            RightCatalog.objects
            .filter(is_active=True)
            .order_by(
                "code"
            )
        )

    def clean(self):
        cleaned = super().clean()

        has_representative = bool(
            cleaned.get(
                "has_representative"
            )
        )

        representative_fields = [
            "representative_name",
            (
                "representative_"
                "document_type"
            ),
            (
                "representative_"
                "document_number"
            ),
        ]

        supplied_any = any(
            cleaned.get(field_name)
            for field_name in (
                representative_fields
                + [
                    (
                        "representative_"
                        "email"
                    )
                ]
            )
        )

        if (
            has_representative
            or supplied_any
        ):
            for field_name in (
                representative_fields
            ):
                if not cleaned.get(
                    field_name
                ):
                    self.add_error(
                        field_name,
                        (
                            "Este campo es "
                            "obligatorio cuando "
                            "existe representante."
                        ),
                    )

        return cleaned


class RequestAssignForm(forms.Form):
    assignee = (
        forms.ModelChoiceField(
            label="Asignar a",
            queryset=(
                get_user_model()
                .objects
                .none()
            ),
            empty_label=(
                "Seleccione un usuario"
            ),
        )
    )

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        user_model = get_user_model()

        self.fields[
            "assignee"
        ].queryset = (
            user_model.objects
            .filter(is_active=True)
            .filter(
                Q(is_superuser=True)
                | Q(
                    role_assignments__revoked_at__isnull=True,
                    role_assignments__role__is_active=True,
                    role_assignments__role__code__in=(
                        CaseWorkflowService
                        .ASSIGNEE_ROLE_CODES
                    ),
                )
            )
            .distinct()
            .order_by(
                "full_name",
                "email",
            )
        )


class RequestClarificationForm(forms.Form):
    message = forms.CharField(
        label=(
            "Solicitud de aclaración"
        ),
        widget=forms.Textarea(
            attrs={
                "rows": 6,
            }
        ),
    )

    clarification_due_at = (
        forms.DateTimeField(
            label=(
                "Fecha límite para responder"
            ),
            required=False,
            input_formats=[
                "%Y-%m-%dT%H:%M",
            ],
            widget=forms.DateTimeInput(
                format=(
                    "%Y-%m-%dT%H:%M"
                ),
                attrs={
                    "type": "datetime-local",
                },
            ),
        )
    )

    legal_basis = forms.CharField(
        label="Base jurídica",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
            }
        ),
    )


class RequestClarificationReceiveForm(
    forms.Form
):
    response_message = forms.CharField(
        label="Respuesta recibida",
        widget=forms.Textarea(
            attrs={
                "rows": 6,
            }
        ),
    )


class RequestExtensionForm(forms.Form):
    reason = forms.CharField(
        label="Motivo de la extensión",
        widget=forms.Textarea(
            attrs={
                "rows": 6,
            }
        ),
    )


class RequestResolutionForm(forms.Form):
    resolution_type = forms.ChoiceField(
        label="Tipo de resolución",
        choices=(
            RequestResolution
            .ResolutionType
            .choices
        ),
    )

    details = forms.CharField(
        label="Detalle de la resolución",
        widget=forms.Textarea(
            attrs={
                "rows": 8,
            }
        ),
    )

    outcome_reason = (
        forms.ModelChoiceField(
            label="Causal",
            queryset=(
                CaseOutcomeReason.objects.none()
            ),
            required=False,
            widget=OutcomeReasonSelect,
            empty_label=(
                "Seleccione una causal"
            ),
        )
    )

    legal_basis = forms.CharField(
        label="Base jurídica",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
            }
        ),
    )

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.fields[
            "outcome_reason"
        ].queryset = (
            CaseOutcomeReason.objects
            .filter(is_active=True)
            .order_by(
                "reason_type",
                "code",
            )
        )
