SECTION_HELP = {
    "dashboard": {
        "title": "Panel de control",
        "purpose": (
            "Resume el estado operativo de los expedientes visibles para tu "
            "perfil y ayuda a priorizar la revisión diaria."
        ),
        "process": [
            "Revisa los indicadores de expedientes activos, por vencer y vencidos.",
            "Consulta las últimas solicitudes recibidas.",
            "Abre el expediente que requiera revisión o seguimiento.",
        ],
        "checks": [
            "Prioriza expedientes vencidos o próximos a vencer.",
            "Verifica si existen solicitudes sin asignar.",
            "Usa Reportes para análisis consolidado, no para revisar datos personales.",
        ],
    },
    "cases": {
        "title": "Expedientes",
        "purpose": (
            "Permite consultar, filtrar y abrir solicitudes de ejercicio de "
            "derechos para gestionar su ciclo de atención."
        ),
        "process": [
            "Filtra por referencia, derecho, estado o asignación.",
            "Abre el expediente para revisar identidad, solicitud, plazos e historial.",
            "Usa las acciones disponibles para asignar, solicitar aclaración, aplicar extensión o resolver.",
        ],
        "checks": [
            "Confirma el expediente correcto antes de registrar acciones.",
            "Revisa identidad y documentos antes de emitir una respuesta.",
            "Controla la fecha límite del expediente.",
        ],
    },
    "case_detail": {
        "title": "Detalle del expediente",
        "purpose": (
            "Centraliza la información de una solicitud: derecho ejercido, "
            "estado, identidad, contenido, plazos, comunicaciones y evidencias."
        ),
        "process": [
            "Revisa el resumen del expediente y su estado actual.",
            "Valida identidad y documentos de soporte cuando corresponda.",
            "Registra comunicaciones, aclaraciones, extensión o resolución según el avance.",
        ],
        "checks": [
            "No respondas sin validar identidad cuando sea necesario.",
            "Documenta toda decisión relevante en el expediente.",
            "Antes de cerrar, verifica que la respuesta sea coherente con el derecho solicitado.",
        ],
    },
    "assignments": {
        "title": "Asignaciones",
        "purpose": (
            "Ayuda a distribuir expedientes entre usuarios responsables y "
            "controlar la carga operativa."
        ),
        "process": [
            "Identifica expedientes sin responsable o próximos a vencer.",
            "Selecciona un expediente o usa asignación masiva si corresponde.",
            "Asigna al usuario con capacidad y competencia para gestionarlo.",
        ],
        "checks": [
            "Evita sobrecargar a un solo responsable.",
            "Revisa vencimientos antes de reasignar.",
            "Las reasignaciones quedan registradas para trazabilidad.",
        ],
    },
    "communications": {
        "title": "Comunicaciones",
        "purpose": (
            "Registra mensajes enviados y recibidos asociados a expedientes, "
            "manteniendo trazabilidad de la atención al titular."
        ),
        "process": [
            "Selecciona el expediente correcto.",
            "Elige correo saliente o comunicación entrante.",
            "Completa tipo, asunto, mensaje y canal cuando aplique.",
            "Marca visible para el titular solo si el contenido puede ser consultado por él.",
        ],
        "checks": [
            "Verifica destinatario y asunto antes de registrar un correo saliente.",
            "No marques como visible información interna o datos de terceros.",
            "Si un correo queda pendiente o fallido, revisa la configuración de envío.",
        ],
    },
    "evidence": {
        "title": "Evidencias e identidad",
        "purpose": (
            "Permite revisar documentos adjuntos y registrar verificaciones "
            "de identidad asociadas al expediente."
        ),
        "process": [
            "Revisa los documentos adjuntos del expediente.",
            "Valida si el solicitante es titular o representante autorizado.",
            "Registra método, resultado y notas de la verificación.",
        ],
        "checks": [
            "No apruebes identidad si la información no es suficiente.",
            "No descargues archivos marcados como infectados o fallidos sin revisión técnica.",
            "Mantén las notas breves y enfocadas en el criterio de validación.",
        ],
    },
    "users": {
        "title": "Usuarios",
        "purpose": (
            "Permite crear cuentas internas, asignar roles, restablecer "
            "contraseñas y controlar el estado de acceso."
        ),
        "process": [
            "Busca o crea el usuario institucional.",
            "Asigna el rol primario según su función.",
            "Activa, desactiva, desbloquea o restablece contraseña cuando corresponda.",
        ],
        "checks": [
            "Usa el menor privilegio necesario.",
            "No compartas cuentas entre varias personas.",
            "Restablecer contraseña obliga a configurar nuevamente el segundo factor.",
        ],
    },
    "settings": {
        "title": "Configuración",
        "purpose": (
            "Administra datos institucionales, responsables, canales oficiales, "
            "branding y parámetros que se reflejan en el portal público."
        ),
        "process": [
            "Actualiza datos institucionales y canales de contacto.",
            "Revisa responsables, delegado y canal de reclamos.",
            "Ajusta colores, logotipo o elementos de marca cuando sea necesario.",
            "Guarda cambios y revisa la página pública relacionada.",
        ],
        "checks": [
            "Los cambios pueden afectar textos visibles para el público.",
            "Verifica correos, teléfonos, RUC y razón social antes de guardar.",
            "Mantén coherencia entre configuración y contenido legal publicado.",
        ],
    },
    "legal_content": {
        "title": "Contenido legal",
        "purpose": (
            "Permite crear borradores y publicar versiones vigentes de avisos "
            "y políticas visibles en el portal."
        ),
        "process": [
            "Selecciona el tipo de documento legal.",
            "Crea un borrador con título, versión, vigencia y contenido HTML.",
            "Revisa el contenido antes de publicarlo.",
            "Publica solo la versión aprobada.",
        ],
        "checks": [
            "Publicar una versión puede reemplazar la versión pública anterior.",
            "No publiques textos pendientes de aprobación jurídica.",
            "Verifica que enlaces, títulos y datos de contacto estén actualizados.",
        ],
    },
    "reports": {
        "title": "Reportes",
        "purpose": (
            "Muestra métricas agregadas sobre expedientes sin exponer datos "
            "personales del titular."
        ),
        "process": [
            "Define rango de fechas y filtros necesarios.",
            "Revisa métricas por estado, derecho y tiempo de atención.",
            "Exporta CSV solo cuando se requiera análisis externo.",
        ],
        "checks": [
            "Los reportes son agregados y no reemplazan la revisión del expediente.",
            "Valida filtros antes de compartir resultados.",
            "Protege los archivos exportados según las reglas internas.",
        ],
    },
    "audit": {
        "title": "Auditoría",
        "purpose": (
            "Permite consultar eventos relevantes del sistema para trazabilidad, "
            "control interno y cumplimiento."
        ),
        "process": [
            "Filtra por fecha, actor, acción, entidad u origen.",
            "Abre el detalle del evento cuando necesites contexto.",
            "Exporta CSV solo si se requiere revisión formal.",
        ],
        "checks": [
            "La auditoría es un registro de control, no un espacio de edición.",
            "No compartas exportaciones sin autorización.",
            "Usa identificadores de correlación para rastrear eventos relacionados.",
        ],
    },
    "retention": {
        "title": "Retención",
        "purpose": (
            "Permite revisar eventos del ciclo de vida de datos y aprobar, "
            "rechazar o preparar reintentos sin ejecutar eliminaciones desde la web."
        ),
        "process": [
            "Revisa eventos pendientes y su acción propuesta.",
            "Filtra por estado, acción o entidad.",
            "Aprueba, rechaza o prepara reintento según el caso.",
        ],
        "checks": [
            "La ejecución material permanece separada y controlada.",
            "No apruebes eventos sin validar el contexto.",
            "Las decisiones quedan registradas para trazabilidad.",
        ],
    },
}
