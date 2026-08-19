from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.legal_content.models import LegalDocument
from apps.legal_content.services.documents import LegalDocumentService


PUBLIC_DOCUMENT_TYPES = {
    "privacidad": LegalDocument.DocumentType.PRIVACY_POLICY,
    "derechos": LegalDocument.DocumentType.RIGHTS_NOTICE,
    "cookies": LegalDocument.DocumentType.COOKIES_POLICY,
    "empleados": LegalDocument.DocumentType.EMPLOYEE_NOTICE,
    "candidatos": LegalDocument.DocumentType.CANDIDATE_NOTICE,
    "clientes-vendedores": LegalDocument.DocumentType.CUSTOMER_VENDOR_NOTICE,
    "proveedores": LegalDocument.DocumentType.SUPPLIER_NOTICE,
    "videovigilancia": LegalDocument.DocumentType.VIDEO_SURVEILLANCE_NOTICE,
}


@require_GET
def public_legal_document(request, document_key):
    document_type = PUBLIC_DOCUMENT_TYPES.get(document_key)
    if document_type is None:
        raise Http404
    document = LegalDocumentService.current(document_type=document_type)
    title = LegalDocument.DocumentType(document_type).label
    return render(
        request,
        "legal_content/public_document.html",
        {
            "document": document,
            "document_title": title,
        },
    )
