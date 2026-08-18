from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from apps.cases.services.cases import (
    CaseWorkflowService,
)


class RequestAssignForm(forms.Form):
    assignee = forms.ModelChoiceField(
        label="Asignar a",
        queryset=get_user_model().objects.none(),
        empty_label="Seleccione un usuario",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        user_model = get_user_model()

        self.fields["assignee"].queryset = (
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
