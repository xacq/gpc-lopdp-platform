# Checklist de puesta en producción

Complete una copia por cada empresa antes de entregar la instancia.

## 1. Infraestructura y seguridad

- [ ] Dominio público resuelve correctamente.
- [ ] HTTPS funciona y el certificado es válido.
- [ ] La base de datos no está expuesta públicamente.
- [ ] Los volúmenes de base de datos, medios y almacenamiento privado persisten.
- [ ] Existe un respaldo verificable de la base de datos y de los archivos necesarios.
- [ ] No se almacenan secretos, contraseñas ni llaves en GitHub.
- [ ] Se confirmó que no se ejecutará `docker compose down -v` en producción.

## 2. Configuración de la empresa

- [ ] Razón social, nombre comercial, RUC, dominio y datos de contacto revisados.
- [ ] Logo, colores y contenido público aprobados.
- [ ] Aviso de privacidad y contenido legal revisados por la empresa.
- [ ] Se cargaron los seis derechos LOPDP.
- [ ] Se cargaron las catorce causales de resolución.
- [ ] Existe al menos un superusuario activo y un responsable/DPD designado.
- [ ] MFA fue configurado por los usuarios administrativos.

## 3. Correo

- [ ] SMTP configurado con cuenta institucional de la empresa.
- [ ] `DEFAULT_FROM_EMAIL` coincide con el remitente autorizado.
- [ ] Se realizó una prueba controlada de envío y recepción.
- [ ] La cola de correo se ejecuta periódicamente.
- [ ] Un correo pendiente pasa a enviado o se registra correctamente como fallido.

## 4. Prueba funcional controlada

- [ ] Se presentó una solicitud de prueba con un correo controlado.
- [ ] Se verificó el correo del titular y se recibió referencia/códigos.
- [ ] La solicitud aparece en Expedientes.
- [ ] Se asignó e inició revisión.
- [ ] Se verificó la visualización de derechos, identidad, adjuntos y plazos.
- [ ] Se comprobó el selector de causales sin registrar una resolución de prueba en un expediente real.
- [ ] Se registró y envió una comunicación de prueba.
- [ ] Se confirmó la consulta pública con referencia y códigos.
- [ ] Se revisó el registro de auditoría.

## 5. Operación y entrega

- [ ] Se entregó el Manual operativo para la empresa.
- [ ] Se entregó la ficha técnica confidencial al responsable autorizado.
- [ ] Se definieron contactos de soporte y escalamiento.
- [ ] Se revisó el proceso de respaldo y restauración.
- [ ] Se firmó el Acta de entrega y aceptación.

## Resultado

| Empresa | Dominio | Fecha | Responsable | Resultado |
| --- | --- | --- | --- | --- |
| `________________` | `________________` | `____ / ____ / ______` | `________________` | `☐ Aprobada` / `☐ Pendiente` |

## Hallazgos o pendientes

`__________________________________________________________________________`

`__________________________________________________________________________`
