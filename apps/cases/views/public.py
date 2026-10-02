from __future__ import annotations

import uuid

from django.db import IntegrityError
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.views.decorators.http import require_http_methods, require_POST

from apps.cases.forms import (
    PublicDownloadForm,
    PublicEmailVerificationForm,
    PublicRequestForm,
    PublicTrackingCodeResendForm,
    PublicTrackingForm,
)
from apps.cases.models import PublicIntakeSubmission, RightsRequest
from apps.cases.services.cases import CaseWorkflowError
from apps.cases.services.intake import CaseIntakeError
from apps.cases.services.public_downloads import (
    PublicDownloadAccessError,
    PublicDownloadService,
)
from apps.cases.services.public_tracking import (
    PublicTrackingAccessError,
    PublicTrackingCodeResendError,
    PublicTrackingCodeResendService,
    PublicTrackingService,
)
from apps.cases.services.public_intake import (
    PublicEmailVerificationAccessError,
    PublicEmailVerificationService,
    PublicIntakeError,
    PublicIntakeService,
)
from apps.communications.services.notifications import NotificationServiceError
from apps.core.services.crypto import CryptoError
from apps.core.services.storage import PrivateStorageError
from apps.evidence.services.attachments import (
    AttachmentIntegrityError,
    AttachmentLimitError,
    AttachmentService,
    FileRejectedError,
    MalwareScannerUnavailableError,
)
from apps.evidence.services.scanners import get_public_upload_scanner
from apps.evidence.services.temporary_uploads import (
    TemporaryUploadError,
    TemporaryUploadService,
)
from apps.subjects.services.subjects import SubjectServiceError


GENERIC_TRACKING_ERROR = (
    "No fue posible consultar la solicitud. Verifica la referencia y el "
    "código de seguimiento."
)
GENERIC_DOWNLOAD_ERROR = (
    "No fue posible descargar el documento. Verifica los datos de acceso."
)
GENERIC_VERIFICATION_ERROR = (
    "No fue posible verificar el correo. Revisa la referencia y el código."
)
PUBLIC_UPLOAD_REJECTION_ERROR = (
    "No fue posible aceptar los documentos. Verifica que sean PDF, JPG o "
    f"PNG, que no superen {AttachmentService.MAX_FILE_SIZE_MB} MB por "
    "archivo y que el contenido corresponda al formato indicado."
)


def _private_response(response: HttpResponse) -> HttpResponse:
    response["Cache-Control"] = "no-store, max-age=0"
    response["Pragma"] = "no-cache"
    # A strict no-referrer policy turns the Origin header into "null" for
    # same-origin HTML form submissions in Firefox, which Django must reject
    # to preserve CSRF protection. Keep referrers within this portal only.
    response["Referrer-Policy"] = "same-origin"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


def _public_request_received_redirect() -> HttpResponse:
    return _private_response(
        HttpResponse(
            status=303,
            headers={
                "Location": reverse("cases:public_request_received"),
            },
        )
    )


def _status_label(value: str) -> str:
    try:
        return RightsRequest.Status(value).label
    except ValueError:
        return value


@require_http_methods(["GET", "POST"])
def public_request_create(request):
    if request.method == "POST":
        form = PublicRequestForm(request.POST, request.FILES)
        if form.is_valid():
            cleaned = form.cleaned_data
            submission_record = None
            try:
                submission_record = PublicIntakeSubmission.objects.create(
                    idempotency_key=cleaned["submission_key"],
                )
            except IntegrityError:
                return _public_request_received_redirect()

            upload_fields = (
                ("identity_document", "IDENTITY_DOCUMENT"),
                ("authority_document", "AUTHORITY_DOCUMENT"),
                ("supporting_document", "SUPPORTING_DOCUMENT"),
            )
            issued_uploads = []
            upload_session_key = None

            if any(cleaned.get(name) for name, _ in upload_fields):
                if request.session.session_key is None:
                    request.session.create()
                upload_session_key = request.session.session_key

                try:
                    scanner = get_public_upload_scanner()
                    for field_name, attachment_type in upload_fields:
                        uploaded_file = cleaned.get(field_name)
                        if uploaded_file is None:
                            continue
                        if uploaded_file.size > AttachmentService.MAX_FILE_SIZE:
                            raise FileRejectedError("File size is not allowed.")
                        content = uploaded_file.read(
                            AttachmentService.MAX_FILE_SIZE + 1
                        )
                        issued_uploads.append(
                            TemporaryUploadService.create(
                                session_key=upload_session_key,
                                attachment_type=attachment_type,
                                filename=uploaded_file.name,
                                declared_mime=(uploaded_file.content_type or ""),
                                content=content,
                                scanner=scanner,
                                correlation_id=uuid.uuid4(),
                            )
                        )
                except (
                    AttachmentLimitError,
                    CryptoError,
                    FileRejectedError,
                    MalwareScannerUnavailableError,
                    PrivateStorageError,
                    TemporaryUploadError,
                    ImportError,
                    OSError,
                ):
                    for issued_upload in issued_uploads:
                        TemporaryUploadService.discard(
                            issued_upload=issued_upload,
                            session_key=upload_session_key,
                        )
                    if submission_record is not None:
                        submission_record.delete()
                    form.add_error(
                        None,
                        PUBLIC_UPLOAD_REJECTION_ERROR,
                    )
                    response = render(
                        request,
                        "cases/public_request_form.html",
                        {"form": form},
                    )
                    return _private_response(response)

            submitted = False
            try:
                result = PublicIntakeService.submit(
                    subject_type=cleaned["subject_type"],
                    document_type=cleaned["document_type"],
                    document_number=cleaned["document_number"],
                    full_name=cleaned["full_name"],
                    email=cleaned["email"],
                    phone=cleaned.get("phone"),
                    right=cleaned["right"],
                    request_details=cleaned["request_details"],
                    representative_name=cleaned.get("representative_name"),
                    representative_document_type=cleaned.get(
                        "representative_document_type"
                    ),
                    representative_document_number=cleaned.get(
                        "representative_document_number"
                    ),
                    representative_email=cleaned.get("representative_email"),
                    temporary_uploads=issued_uploads,
                    upload_session_key=upload_session_key,
                    correlation_id=uuid.uuid4(),
                )
            except (
                PublicIntakeError,
                CaseIntakeError,
                CaseWorkflowError,
                SubjectServiceError,
                NotificationServiceError,
                AttachmentLimitError,
                CryptoError,
                PrivateStorageError,
                TemporaryUploadError,
                ValueError,
            ):
                # The same confirmation prevents disclosure of existing
                # subject or representative records.
                pass
            else:
                submitted = True
                if submission_record is not None:
                    submission_record.request = result.request
                    submission_record.completed_at = timezone.now()
                    submission_record.save(
                        update_fields=[
                            "request",
                            "completed_at",
                        ]
                    )
            finally:
                if not submitted:
                    for issued_upload in issued_uploads:
                        TemporaryUploadService.discard(
                            issued_upload=issued_upload,
                            session_key=upload_session_key,
                        )
                    if submission_record is not None:
                        submission_record.delete()
            return _public_request_received_redirect()
    else:
        form = PublicRequestForm()

    response = render(
        request,
        "cases/public_request_form.html",
        {"form": form},
    )
    return _private_response(response)


@require_http_methods(["GET"])
def public_request_received(request):
    response = render(request, "cases/public_request_received.html")
    return _private_response(response)


@require_http_methods(["GET", "POST"])
def public_email_verification(request):
    verified = False
    access_error = None

    if request.method == "POST":
        submitted_form = PublicEmailVerificationForm(request.POST)
        if submitted_form.is_valid():
            try:
                PublicEmailVerificationService.verify(
                    reference_number=(
                        submitted_form.cleaned_data["reference_number"]
                    ),
                    token=submitted_form.cleaned_data["token"],
                    correlation_id=uuid.uuid4(),
                )
            except PublicEmailVerificationAccessError:
                access_error = GENERIC_VERIFICATION_ERROR
            else:
                verified = True
        else:
            access_error = GENERIC_VERIFICATION_ERROR
        form = PublicEmailVerificationForm()
    else:
        form = PublicEmailVerificationForm()

    response = render(
        request,
        "cases/public_email_verification.html",
        {
            "form": form,
            "verified": verified,
            "access_error": access_error,
        },
    )
    return _private_response(response)


@require_http_methods(["GET", "POST"])
def public_tracking(request):
    result = None
    history = ()
    access_error = None
    form = PublicTrackingForm()

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
            missing_fields = {
                field_name
                for field_name in ("reference_number", "token")
                if not str(request.POST.get(field_name, "")).strip()
            }
            if missing_fields:
                # Render only presence errors and never echo submitted access
                # credentials back into the response.
                form = PublicTrackingForm(data={})
                form.is_valid()
                for field_name in tuple(form.errors):
                    if field_name not in missing_fields:
                        form.errors.pop(field_name, None)
            else:
                access_error = GENERIC_TRACKING_ERROR

        # Never re-render submitted access codes, including malformed ones.

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


@require_http_methods(["GET", "POST"])
def public_tracking_code_resend(request):
    form = PublicTrackingCodeResendForm()
    submitted = False
    validation_error = False

    if request.method == "POST":
        submitted_form = PublicTrackingCodeResendForm(request.POST)
        if submitted_form.is_valid():
            submitted = True
            try:
                PublicTrackingCodeResendService.resend(
                    reference_number=(
                        submitted_form.cleaned_data["reference_number"]
                    ),
                    email=submitted_form.cleaned_data["email"],
                    correlation_id=uuid.uuid4(),
                )
            except (
                PublicTrackingCodeResendError,
                NotificationServiceError,
                CryptoError,
                SystemSetting.DoesNotExist,
                ValueError,
            ):
                pass
        else:
            validation_error = True
        # Do not render submitted reference numbers or email addresses.
        form = PublicTrackingCodeResendForm()

    response = render(
        request,
        "cases/public_tracking_code_resend.html",
        {
            "form": form,
            "submitted": submitted,
            "validation_error": validation_error,
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
