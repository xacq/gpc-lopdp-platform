from __future__ import annotations

import uuid

from django.http import HttpResponse
from django.shortcuts import render
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_http_methods, require_POST

from apps.cases.forms import PublicDownloadForm, PublicTrackingForm
from apps.cases.models import RightsRequest
from apps.cases.services.public_downloads import (
    PublicDownloadAccessError,
    PublicDownloadService,
)
from apps.cases.services.public_tracking import (
    PublicTrackingAccessError,
    PublicTrackingService,
)
from apps.core.services.crypto import CryptoError
from apps.core.services.storage import PrivateStorageError
from apps.evidence.services.attachments import AttachmentIntegrityError


GENERIC_TRACKING_ERROR = (
    "No fue posible consultar la solicitud. Verifica la referencia y el "
    "código de seguimiento."
)
GENERIC_DOWNLOAD_ERROR = (
    "No fue posible descargar el documento. Verifica los datos de acceso."
)


def _private_response(response: HttpResponse) -> HttpResponse:
    response["Cache-Control"] = "no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


def _status_label(value: str) -> str:
    try:
        return RightsRequest.Status(value).label
    except ValueError:
        return value


@require_http_methods(["GET", "POST"])
def public_tracking(request):
    result = None
    history = ()
    access_error = None

    if request.method == "POST":
        submitted_form = PublicTrackingForm(request.POST)
        if submitted_form.is_valid():
            try:
                result = PublicTrackingService.get_status(
                    reference_number=(
                        submitted_form.cleaned_data["reference_number"]
                    ),
                    token=submitted_form.cleaned_data["token"],
                    correlation_id=uuid.uuid4(),
                )
            except PublicTrackingAccessError:
                access_error = GENERIC_TRACKING_ERROR
            else:
                history = tuple(
                    {
                        "label": _status_label(item.status),
                        "changed_at": item.changed_at,
                    }
                    for item in result.history
                )
        else:
            access_error = GENERIC_TRACKING_ERROR

        # Never re-render submitted access codes, including malformed ones.
        form = PublicTrackingForm()
    else:
        form = PublicTrackingForm()

    response = render(
        request,
        "cases/public_tracking.html",
        {
            "form": form,
            "result": result,
            "status_label": (
                _status_label(result.status) if result is not None else None
            ),
            "history": history,
            "access_error": access_error,
        },
    )
    return _private_response(response)


@require_http_methods(["GET"])
def public_download_form(request):
    response = render(
        request,
        "cases/public_download.html",
        {
            "form": PublicDownloadForm(),
        },
    )
    return _private_response(response)


@require_POST
def public_download(request):
    form = PublicDownloadForm(request.POST)

    if not form.is_valid():
        response = render(
            request,
            "cases/public_download.html",
            {
                "form": PublicDownloadForm(),
                "access_error": GENERIC_DOWNLOAD_ERROR,
            },
            status=404,
        )
        return _private_response(response)

    try:
        download = PublicDownloadService.download_attachment(
            reference_number=form.cleaned_data["reference_number"],
            attachment_id=form.cleaned_data["attachment_id"],
            token=form.cleaned_data["token"],
            correlation_id=uuid.uuid4(),
        )
    except (
        PublicDownloadAccessError,
        AttachmentIntegrityError,
        PrivateStorageError,
        CryptoError,
    ):
        response = render(
            request,
            "cases/public_download.html",
            {
                "form": PublicDownloadForm(),
                "access_error": GENERIC_DOWNLOAD_ERROR,
            },
            status=404,
        )
        return _private_response(response)

    response = HttpResponse(
        download.content,
        content_type=download.mime_type,
    )
    response["Content-Disposition"] = content_disposition_header(
        True,
        download.filename,
    )
    response["Content-Length"] = str(download.size_bytes)
    response["X-Content-Type-Options"] = "nosniff"
    return _private_response(response)
