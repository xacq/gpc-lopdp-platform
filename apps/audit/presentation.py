from __future__ import annotations

import re


ACTION_LABELS = {
    "AUTH_PRIMARY_FACTOR_ACCEPTED": "Primer factor de autenticación aceptado",
    "AUTH_PRIMARY_FACTOR_REJECTED": "Primer factor de autenticación rechazado",
    "AUTH_MFA_ACCEPTED": "Verificación en dos pasos aceptada",
    "AUTH_MFA_REJECTED": "Verificación en dos pasos rechazada",
    "MFA_DEVICE_REVOKED": "Dispositivo de verificación revocado",
    "USER_CREATED": "Usuario creado",
    "USER_PRIMARY_ROLE_CHANGED": "Rol principal del usuario cambiado",
    "USER_ACTIVATED": "Usuario activado",
    "USER_DEACTIVATED": "Usuario desactivado",
    "USER_ACCOUNT_UNLOCKED": "Cuenta de usuario desbloqueada",
    "USER_PASSWORD_RESET": "Contraseña del usuario restablecida",
    "RIGHTS_REQUEST_ASSIGNED": "Solicitud de derechos asignada",
    "PUBLIC_REQUEST_EMAIL_VERIFIED": "Correo de la solicitud pública verificado",
    "PUBLIC_TRACKING_CODE_REISSUED": "Código público de seguimiento reenviado",
    "REQUEST_COMMUNICATION_RECEIVED": "Comunicación de la solicitud recibida",
    "PORTABILITY_EXPORT_GENERATED": "Exportación de portabilidad generada",
    "PORTABILITY_EXPORT_DOWNLOADED": "Exportación de portabilidad descargada",
    "PORTABILITY_EXPORT_REVOKED": "Exportación de portabilidad revocada",
    "IDENTITY_VERIFICATION_RECORDED": "Verificación de identidad registrada",
    "PUBLIC_TEMPORARY_UPLOAD_CREATED": "Carga temporal pública creada",
    "PUBLIC_TEMPORARY_UPLOAD_PROMOTED": "Carga temporal pública incorporada",
    "LEGAL_DOCUMENT_DRAFT_CREATED": "Borrador de documento legal creado",
    "LEGAL_DOCUMENT_PUBLISHED": "Documento legal publicado",
    "NOTICE_DELIVERY_RECORDED": "Entrega de aviso registrada",
    "SYSTEM_SETTINGS_CREATED": "Configuración del sistema creada",
    "SYSTEM_SETTINGS_UPDATED": "Configuración del sistema actualizada",
    "REPORT_EXPORTED": "Reporte exportado",
    "REQUEST_CREATED": "Solicitud creada",
    "SYSTEM_BOOTSTRAP": "Inicialización del sistema",
}

ENTITY_LABELS = {
    "USER": "Usuario",
    "MFA_DEVICE": "Dispositivo de verificación",
    "RIGHTS_REQUEST": "Solicitud de derechos",
    "REQUEST_COMMUNICATION": "Comunicación de solicitud",
    "TEMPORARY_UPLOAD": "Carga temporal",
    "REQUEST_ATTACHMENT": "Adjunto de solicitud",
    "IDENTITY_VERIFICATION": "Verificación de identidad",
    "IDENTITYVERIFICATION": "Verificación de identidad",
    "LEGAL_DOCUMENT": "Documento legal",
    "LEGALDOCUMENT": "Documento legal",
    "NOTICE_DELIVERY": "Entrega de aviso",
    "NOTICEDELIVERY": "Entrega de aviso",
    "SYSTEM_SETTING": "Configuración del sistema",
    "PORTABILITY_EXPORT": "Exportación de portabilidad",
    "REPORT": "Reporte",
    "SYSTEM": "Sistema",
}

SOURCE_LABELS = {
    "WEB": "Sitio web",
    "API": "API",
    "CELERY": "Procesamiento en segundo plano",
    "SIGNAL": "Señal del sistema",
    "COMMAND": "Comando",
    "SYSTEM": "Sistema",
}

TOKEN_LABELS = {
    "ACCOUNT": "cuenta",
    "ACTION": "acción",
    "ACTIVATED": "activado",
    "APPROVED": "aprobado",
    "ASSIGNED": "asignado",
    "ATTACHMENT": "adjunto",
    "AUTH": "autenticación",
    "CANCELLED": "cancelado",
    "CHANGED": "cambiado",
    "CLOSED": "cerrado",
    "COMMUNICATION": "comunicación",
    "CREATED": "creado",
    "DEACTIVATED": "desactivado",
    "DELETED": "eliminado",
    "DELIVERY": "entrega",
    "DEVICE": "dispositivo",
    "DOCUMENT": "documento",
    "DOWNLOADED": "descargado",
    "DRAFT": "borrador",
    "EMAIL": "correo electrónico",
    "EXECUTED": "ejecutado",
    "EXPORT": "exportación",
    "FAILED": "fallido",
    "GENERATED": "generado",
    "IDENTITY": "identidad",
    "LEGAL": "legal",
    "NOTICE": "aviso",
    "PASSWORD": "contraseña",
    "PRIMARY": "principal",
    "PROMOTED": "incorporado",
    "PUBLIC": "público",
    "RECEIVED": "recibido",
    "RECORDED": "registrado",
    "REJECTED": "rechazado",
    "REPORT": "reporte",
    "REQUEST": "solicitud",
    "RESET": "restablecido",
    "REVOKED": "revocado",
    "RIGHTS": "derechos",
    "ROLE": "rol",
    "SETTINGS": "configuración",
    "SYSTEM": "sistema",
    "TEMPORARY": "temporal",
    "UNLOCKED": "desbloqueado",
    "UPDATED": "actualizado",
    "UPLOAD": "carga",
    "USER": "usuario",
    "VERIFICATION": "verificación",
    "VERIFIED": "verificado",
}


def _normalized_identifier(value: str | None) -> str:
    expanded = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value or "")
    return re.sub(r"[^A-Za-z0-9]+", "_", expanded).strip("_").upper()


def identifier_label(value: str | None, *, labels: dict[str, str] | None = None) -> str:
    normalized = _normalized_identifier(value)
    if not normalized:
        return "—"
    if labels and normalized in labels:
        return labels[normalized]
    words = [TOKEN_LABELS.get(token, token.lower()) for token in normalized.split("_")]
    return " ".join(words).capitalize()


def action_label(value: str | None) -> str:
    return identifier_label(value, labels=ACTION_LABELS)


def entity_label(value: str | None) -> str:
    return identifier_label(value, labels=ENTITY_LABELS)


def source_label(value: str | None) -> str:
    return identifier_label(value, labels=SOURCE_LABELS)


def chain_scope_label(value: str | None) -> str:
    normalized = _normalized_identifier(value)
    if normalized == "GLOBAL":
        return "Global"
    return identifier_label(value)
