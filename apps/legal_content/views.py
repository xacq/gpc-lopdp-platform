from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.legal_content.models import LegalDocument
from apps.legal_content.services.documents import LegalDocumentService


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
    },
)

PUBLIC_DOCUMENT_TYPES = {
    item["key"]: item["type"] for item in PUBLIC_DOCUMENTS
}
PUBLIC_DOCUMENT_CONFIG = {item["key"]: item for item in PUBLIC_DOCUMENTS}


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
    return render(
        request,
        "legal_content/public_document.html",
        {
            "document": document,
            "document_title": title,
            "document_summary": document_config["summary"],
            "client_requirements": document_config["requirements"],
        },
    )
