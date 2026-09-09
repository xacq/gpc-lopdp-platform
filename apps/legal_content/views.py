import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.legal_content.forms import (
    LegalDocumentCreateForm,
    LegalDocumentFilterForm,
)
from apps.legal_content.models import LegalDocument
from apps.legal_content.policies import can_manage_legal
from apps.legal_content.services.documents import (
    LegalDocumentError,
    LegalDocumentService,
)
from apps.organization.defaults import VINESA_PRIVACY_POLICY_URL
from apps.organization.models import SystemSetting


PUBLIC_DOCUMENTS = (
    {
        "key": "privacidad",
        "type": LegalDocument.DocumentType.PRIVACY_POLICY,
        "summary": "Política general sobre el tratamiento de datos personales.",
        "requirements": (
            "Identificación completa del responsable, RUC y domicilio.",
            "Tratamientos, finalidades y bases de legitimación.",
            "Destinatarios, transferencias y encargados aplicables.",
            "Plazos o criterios de conservación y medidas de seguridad.",
            "Canales para ejercer derechos, versión, vigencia y aprobación.",
        ),
        "preliminary_sections": (
            {
                "title": "Compromiso institucional",
                "paragraphs": (
                    "VINESA mantiene un programa de protección de datos personales orientado al cumplimiento de la LOPDP mediante medidas técnicas y organizativas.",
                    "Este portal centraliza información de privacidad, avisos y mecanismos para presentar y consultar solicitudes de ejercicio de derechos.",
                    "VINESA comunica privacidad@vinesa.com.ec como canal para ejercer derechos y mantiene una política publicada en "
                    f"{VINESA_PRIVACY_POLICY_URL}.",
                ),
            },
            {
                "title": "Ámbitos identificados",
                "paragraphs": (
                    "La documentación interna identifica tratamientos relacionados con selección y contratación, relaciones laborales, videovigilancia, calificación de clientes o vendedores, calificación de proveedores y contratos de servicios.",
                    "Las finalidades, bases jurídicas, destinatarios, transferencias y plazos de conservación de cada tratamiento todavía deben ser validados antes de publicar la política definitiva.",
                ),
            },
        ),
    },
    {
        "key": "derechos",
        "type": LegalDocument.DocumentType.RIGHTS_NOTICE,
        "summary": "Información oficial para ejercer derechos y presentar reclamos.",
        "requirements": (
            "Catálogo definitivo de derechos aprobado para VINESA.",
            "Datos y canales oficiales del responsable del tratamiento.",
            "Designación y contacto vigente del DPD.",
            "Requisitos, plazos y procedimiento de atención.",
            "Autoridad y canal oficial para presentar reclamaciones.",
        ),
        "preliminary_sections": (
            {
                "title": "Ejercicio de derechos",
                "paragraphs": (
                    "El portal permitirá presentar solicitudes y consultar su estado mediante una referencia y un código de seguimiento enviados al titular.",
                    "La información corporativa revisada comunica actualmente los derechos de acceso, rectificación, eliminación y oposición. Otros derechos permanecerán fuera del contenido público fijo hasta aprobar el catálogo jurídico definitivo.",
                ),
            },
            {
                "title": "Canales y reclamaciones",
                "paragraphs": (
                    "Las solicitudes pueden dirigirse a privacidad@vinesa.com.ec. La identidad y los datos de contacto vigentes del Delegado de Protección de Datos y el canal de reclamaciones todavía deben confirmarse.",
                ),
            },
        ),
    },
    {
        "key": "cookies",
        "type": LegalDocument.DocumentType.COOKIES_POLICY,
        "summary": "Información sobre cookies y tecnologías similares del portal.",
        "requirements": (
            "Inventario real de cookies y tecnologías utilizadas.",
            "Categoría, finalidad, proveedor y duración de cada elemento.",
            "Identificación de cookies necesarias y sujetas a elección.",
            "Mecanismos para aceptar, rechazar y personalizar preferencias.",
            "Versión, fecha de vigencia y responsable de aprobación.",
        ),
        "preliminary_sections": (
            {
                "title": "Gestión de preferencias",
                "paragraphs": (
                    "Antes de activar cookies o tecnologías que requieran elección, el portal deberá informar al usuario y permitir una decisión libre e informada.",
                    "La interfaz deberá ofrecer opciones visibles para aceptar, rechazar o personalizar preferencias y mantener accesible la política de privacidad.",
                ),
            },
            {
                "title": "Inventario pendiente",
                "paragraphs": (
                    "La clasificación definitiva depende del inventario real de cookies, sus proveedores, finalidades y duraciones. Hasta completar ese inventario no se activarán categorías opcionales como si existiera consentimiento.",
                ),
            },
        ),
    },
    {
        "key": "empleados",
        "type": LegalDocument.DocumentType.EMPLOYEE_NOTICE,
        "summary": "Aviso aplicable a relaciones laborales.",
        "requirements": (
            "Tratamientos laborales, finalidades y bases aplicables.",
            "Categorías de datos, destinatarios y conservación.",
            "Canales de información y ejercicio de derechos.",
        ),
        "preliminary_sections": (
            {
                "title": "Ámbito preliminar",
                "paragraphs": (
                    "Este aviso está previsto para el tratamiento de datos personales durante la relación laboral y los procesos administrativos vinculados al personal.",
                    "Las categorías de datos, finalidades, bases jurídicas, destinatarios y periodos de conservación requieren validación laboral y jurídica.",
                ),
            },
        ),
    },
    {
        "key": "candidatos",
        "type": LegalDocument.DocumentType.CANDIDATE_NOTICE,
        "summary": "Aviso aplicable a procesos de selección.",
        "requirements": (
            "Datos tratados durante selección y contratación.",
            "Finalidades, base aplicable y tiempo de conservación.",
            "Canal oficial para consultas y ejercicio de derechos.",
        ),
        "preliminary_sections": (
            {
                "title": "Ámbito preliminar",
                "paragraphs": (
                    "Este aviso está previsto para la recepción y evaluación de información de personas que participan en procesos de selección y eventual contratación.",
                    "El canal de recepción, las finalidades específicas y el tiempo de conservación de candidaturas están pendientes de aprobación.",
                ),
            },
        ),
    },
    {
        "key": "clientes-vendedores",
        "type": LegalDocument.DocumentType.CUSTOMER_VENDOR_NOTICE,
        "summary": "Aviso aplicable a clientes y vendedores.",
        "requirements": (
            "Tratamientos y finalidades aplicables a esta relación.",
            "Bases, destinatarios y criterios de conservación.",
            "Canal oficial para consultas y ejercicio de derechos.",
        ),
        "preliminary_sections": (
            {
                "title": "Ámbito preliminar",
                "paragraphs": (
                    "La documentación revisada contempla procesos de calificación de clientes y vendedores en los que puede tratarse información personal de titulares o representantes.",
                    "En documentación corporativa, VINESA declara como finalidades conocidas la facturación y las comunicaciones de servicio, con conservación vinculada al cumplimiento de obligaciones legales y privacidad@vinesa.com.ec como canal de derechos.",
                    "Las finalidades, bases jurídicas, destinatarios y periodos de conservación todavía deben ser confirmados.",
                ),
            },
        ),
    },
    {
        "key": "proveedores",
        "type": LegalDocument.DocumentType.SUPPLIER_NOTICE,
        "summary": "Aviso aplicable a proveedores y sus representantes.",
        "requirements": (
            "Tratamientos de calificación y gestión contractual.",
            "Finalidades, bases, destinatarios y conservación.",
            "Canal oficial para consultas y ejercicio de derechos.",
        ),
        "preliminary_sections": (
            {
                "title": "Ámbito preliminar",
                "paragraphs": (
                    "La documentación revisada contempla la calificación de proveedores y la gestión de contratos de servicios, incluyendo datos de personas naturales y representantes.",
                    "En documentación de facturación se identifican las finalidades de facturación y comunicaciones de servicio, conservación para obligaciones legales y privacidad@vinesa.com.ec como canal de derechos.",
                    "Las finalidades, bases jurídicas, destinatarios, transferencias y conservación requieren validación antes de publicar el aviso definitivo.",
                ),
            },
        ),
    },
    {
        "key": "videovigilancia",
        "type": LegalDocument.DocumentType.VIDEO_SURVEILLANCE_NOTICE,
        "summary": "Aviso para espacios que utilizan videovigilancia.",
        "requirements": (
            "Responsable, finalidad y base del tratamiento.",
            "Ubicaciones cubiertas y tiempo de conservación.",
            "Destinatarios, medidas y canal de ejercicio de derechos.",
            "Texto breve y ubicación del código QR o aviso visible.",
        ),
        "preliminary_sections": (
            {
                "title": "Aviso preliminar",
                "paragraphs": (
                    "VINESA prevé informar de forma visible cuando un espacio cuente con sistemas de videovigilancia y facilitar el acceso al aviso ampliado, incluso mediante código QR cuando corresponda.",
                    "La finalidad exacta, las ubicaciones cubiertas, el periodo de conservación, los destinatarios y el canal de ejercicio de derechos permanecen pendientes de confirmación.",
                ),
            },
        ),
    },
)

PUBLIC_DOCUMENT_TYPES = {
    item["key"]: item["type"] for item in PUBLIC_DOCUMENTS
}
PUBLIC_DOCUMENT_CONFIG = {item["key"]: item for item in PUBLIC_DOCUMENTS}


def _personalize_preliminary_content(value, setting):
    """Substitutes provisional VINESA references with the active tenant identity."""
    if isinstance(value, str):
        trade_name = setting.trade_name or setting.legal_name
        return (
            value.replace("privacidad@vinesa.com.ec", setting.contact_email)
            .replace(VINESA_PRIVACY_POLICY_URL, "/legal/privacidad/")
            .replace("VINESA", trade_name)
        )
    if isinstance(value, tuple):
        return tuple(_personalize_preliminary_content(item, setting) for item in value)
    if isinstance(value, dict):
        return {key: _personalize_preliminary_content(item, setting) for key, item in value.items()}
    return value


def _legal_payload(document):
    return {
        "id": str(document.id),
        "document_type": {
            "code": document.document_type,
            "label": document.get_document_type_display(),
        },
        "title": document.title,
        "slug": document.slug,
        "version": document.version,
        "content_html": document.content_html,
        "content_sha256": document.content_sha256,
        "effective_from": document.effective_from,
        "effective_to": document.effective_to,
        "is_published": document.is_published,
        "created_by": (
            {"id": str(document.created_by_id), "name": document.created_by.full_name}
            if document.created_by_id
            else None
        ),
        "created_at": document.created_at,
    }


@never_cache
@login_required
@require_GET
def legal_document_list(request):
    if not can_manage_legal(request.user):
        raise PermissionDenied
    form = LegalDocumentFilterForm(request.GET)
    if not form.is_valid():
        return JsonResponse(
            {"errors": form.errors.get_json_data()}, status=400
        )
    queryset = LegalDocument.objects.select_related("created_by")
    if form.cleaned_data.get("document_type"):
        queryset = queryset.filter(
            document_type=form.cleaned_data["document_type"]
        )
    if form.cleaned_data.get("published") is not None:
        queryset = queryset.filter(is_published=form.cleaned_data["published"])
    return JsonResponse(
        {"results": [_legal_payload(item) for item in queryset]},
        json_dumps_params={"ensure_ascii": False},
    )


@never_cache
@login_required
@require_POST
def legal_document_create(request):
    if not can_manage_legal(request.user):
        raise PermissionDenied
    try:
        data = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "El cuerpo JSON no es válido."}, status=400)
    if not isinstance(data, dict):
        return JsonResponse(
            {"error": "El cuerpo JSON debe ser un objeto."}, status=400
        )
    form = LegalDocumentCreateForm(data)
    if not form.is_valid():
        return JsonResponse(
            {"errors": form.errors.get_json_data()}, status=400
        )
    cleaned = form.cleaned_data
    try:
        document = LegalDocumentService.create_draft(
            document_type=cleaned["document_type"],
            title=cleaned["title"],
            slug=cleaned.get("slug"),
            version=cleaned["version"],
            content_html=cleaned["content_html"],
            effective_from=cleaned["effective_from"],
            actor=request.user,
        )
    except (LegalDocumentError, ValueError):
        return JsonResponse(
            {"error": "No fue posible crear el borrador legal."}, status=409
        )
    document = LegalDocument.objects.select_related("created_by").get(pk=document.pk)
    return JsonResponse(_legal_payload(document), status=201)


@never_cache
@login_required
@require_POST
def legal_document_publish(request, document_id):
    if not can_manage_legal(request.user):
        raise PermissionDenied
    document = LegalDocument.objects.filter(pk=document_id).first()
    if document is None:
        raise Http404
    try:
        document = LegalDocumentService.publish(
            document=document, actor=request.user
        )
    except LegalDocumentError:
        if request.POST.get("return_to") == "panel":
            messages.error(request, "La versión legal no puede publicarse.")
            return redirect("legal_content:manage_panel")
        return JsonResponse(
            {"error": "La versión legal no puede publicarse en su estado actual."},
            status=409,
        )
    document = LegalDocument.objects.select_related("created_by").get(pk=document.pk)
    if request.POST.get("return_to") == "panel":
        messages.success(request, "La versión legal fue publicada.")
        return redirect("legal_content:manage_panel")
    return JsonResponse(_legal_payload(document))


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def legal_document_panel(request):
    if not can_manage_legal(request.user):
        raise PermissionDenied
    create_form = LegalDocumentCreateForm(request.POST or None)
    if request.method == "POST" and create_form.is_valid():
        cleaned = create_form.cleaned_data
        try:
            LegalDocumentService.create_draft(
                document_type=cleaned["document_type"],
                title=cleaned["title"],
                slug=cleaned.get("slug"),
                version=cleaned["version"],
                content_html=cleaned["content_html"],
                effective_from=cleaned["effective_from"],
                actor=request.user,
            )
        except (LegalDocumentError, ValueError):
            create_form.add_error(None, "No fue posible crear el borrador legal.")
        else:
            messages.success(request, "El borrador legal fue creado.")
            return redirect("legal_content:manage_panel")
    documents = LegalDocument.objects.select_related("created_by").order_by(
        "document_type", "-effective_from", "-created_at"
    )
    return render(
        request,
        "legal_content/manage_panel.html",
        {
            "documents": documents,
            "create_form": create_form,
            "document_types": LegalDocument.DocumentType.choices,
        },
        status=400 if create_form.errors else 200,
    )


@require_GET
def public_legal_index(request):
    documents = []
    for item in PUBLIC_DOCUMENTS:
        documents.append(
            {
                **item,
                "title": LegalDocument.DocumentType(item["type"]).label,
                "document": LegalDocumentService.current(
                    document_type=item["type"]
                ),
            }
        )
    return render(
        request,
        "legal_content/public_index.html",
        {"documents": documents},
    )


@require_GET
def public_legal_document(request, document_key):
    document_type = PUBLIC_DOCUMENT_TYPES.get(document_key)
    if document_type is None:
        raise Http404
    document = LegalDocumentService.current(document_type=document_type)
    title = LegalDocument.DocumentType(document_type).label
    document_config = PUBLIC_DOCUMENT_CONFIG[document_key]
    setting = SystemSetting.objects.filter(singleton_key=1).first()
    if setting is not None:
        document_config = _personalize_preliminary_content(document_config, setting)
    return render(
        request,
        "legal_content/public_document.html",
        {
            "document": document,
            "document_title": title,
            "document_summary": document_config["summary"],
            "client_requirements": document_config["requirements"],
            "preliminary_sections": document_config["preliminary_sections"],
        },
    )
