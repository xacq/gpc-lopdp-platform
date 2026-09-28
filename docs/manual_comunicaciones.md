# Manual para comunicaciones

Este manual explica como registrar, revisar y dar seguimiento a las comunicaciones asociadas a los expedientes de derechos de proteccion de datos personales.

Aplica para las cuatro instancias:

- VINESA: `https://privacidad.vinesa.com.ec/accounts/login/`
- VINLITORAL: `https://privacidad.vinlitoral.com.ec/accounts/login/`
- PLUSBRAND: `https://privacidad.plusbrand.com.ec/accounts/login/`
- SERVMULTIMARC: `https://privacidad.laguarda.com.ec/accounts/login/`

Cada empresa tiene su propio historial de comunicaciones. La informacion registrada en una instancia no se comparte automaticamente con las demas.

## 1. Objetivo de la seccion

La seccion **Comunicaciones** permite mantener un historial de mensajes vinculados a expedientes.

Sirve para:

- registrar correos salientes;
- registrar comunicaciones recibidas por correo, telefono, fisico, portal u otro canal;
- consultar el estado de los mensajes;
- dejar trazabilidad de las interacciones con el titular;
- marcar si una comunicacion sera visible para el titular.

## 2. Ingreso

1. Ingresar al sistema de la empresa correspondiente.
2. Iniciar sesion con correo, contrasena y verificacion en dos pasos.
3. Abrir la opcion **Comunicaciones** en el menu interno.

Tambien se puede ingresar desde el detalle de un expediente, en la seccion **Canales relacionados**, seleccionando **Comunicaciones**.

## 3. Panel principal

En la parte superior se muestran indicadores generales:

- **Total comunicaciones**: total acumulado de comunicaciones registradas.
- **Recibidas**: comunicaciones entrantes.
- **Enviadas**: comunicaciones salientes procesadas.
- **Con error**: comunicaciones que fallaron o estan pendientes de reintento.

Debajo se muestra el listado de comunicaciones con:

- fecha;
- expediente;
- direccion;
- canal;
- tipo;
- estado;
- visibilidad para el titular.

## 4. Direcciones de comunicacion

El sistema maneja tres direcciones:

| Direccion | Significado |
| --- | --- |
| Entrante | Comunicacion recibida desde el titular u otro contacto relacionado. |
| Saliente | Comunicacion generada por el sistema o por un usuario hacia el titular. |
| Sistema | Comunicacion automatica generada internamente. |

## 5. Canales disponibles

Los canales disponibles son:

| Canal | Uso |
| --- | --- |
| Correo electronico | Mensajes enviados o recibidos por email. |
| Portal | Comunicaciones realizadas desde el portal. |
| Telefono | Llamadas o contactos telefonicos. |
| Fisico | Documentos entregados o recibidos fisicamente. |
| Otro | Cualquier canal no incluido en los anteriores. |

## 6. Tipos de comunicacion

El sistema permite clasificar las comunicaciones con los siguientes tipos:

- Acuse de recepcion.
- Aviso de asignacion.
- Solicitud de informacion.
- Recordatorio de aclaracion.
- Aviso de extension.
- Alerta de vencimiento.
- Respuesta.
- Rechazo.
- Aviso de archivo.
- Aviso de cancelacion.
- Portabilidad disponible.
- Informacion de reclamacion.
- Alerta de fallo de entrega.
- Otro.

Usar el tipo que mejor describa el contenido real de la comunicacion. Si no existe una categoria especifica, seleccionar **Otro**.

## 7. Registrar una comunicacion saliente

Usar esta opcion cuando el sistema debe dejar registro de un correo enviado al titular u otro destinatario relacionado con el expediente.

1. Entrar a **Comunicaciones**.
2. Abrir **+ Registrar comunicacion**.
3. Seleccionar la pestana **Correo saliente**.
4. Completar:
   - **Expediente**.
   - **Tipo**.
   - **Destinatario**.
   - **Asunto**.
   - **Mensaje**.
5. Marcar **Visible para el titular** solo si el mensaje debe aparecer en la vista publica o de seguimiento del titular.
6. Seleccionar **Registrar y poner en cola**.

Importante: el registro queda en cola para envio. Si el correo SMTP de la instancia aun no esta configurado, el sistema puede registrar la comunicacion pero no enviarla realmente al destinatario.

## 8. Registrar una comunicacion entrante

Usar esta opcion para dejar constancia de una llamada, correo recibido, documento fisico u otra comunicacion que llego a la empresa.

1. Entrar a **Comunicaciones**.
2. Abrir **+ Registrar comunicacion**.
3. Seleccionar la pestana **Comunicacion entrante**.
4. Completar:
   - **Expediente**.
   - **Canal**.
   - **Tipo**.
   - **Contacto**.
   - **Asunto**.
   - **Mensaje**.
5. Marcar **Visible para el titular** solo si corresponde.
6. Seleccionar **Registrar comunicacion**.

La comunicacion entrante queda registrada con estado **Recibido**.

## 9. Visibilidad para el titular

El campo **Visible para el titular** define si la comunicacion puede mostrarse al titular en los canales de seguimiento.

Recomendacion:

- Marcarlo cuando el mensaje forma parte de la informacion que el titular puede consultar.
- No marcarlo cuando contiene notas internas, datos operativos, analisis internos o informacion que no debe exponerse publicamente.

Antes de marcar una comunicacion como visible, revisar que el texto no incluya informacion interna o datos personales de terceros.

## 10. Estados de entrega

Los estados posibles son:

| Estado | Significado |
| --- | --- |
| Pendiente | La comunicacion esta registrada y pendiente de procesamiento. |
| Procesando | El sistema esta intentando procesar el envio. |
| Enviado | El mensaje fue enviado por el sistema. |
| Entregado | El proveedor confirmo entrega, si aplica. |
| Fallido | Hubo un error en el envio o procesamiento. |
| Recibido | Comunicacion entrante registrada. |
| Cancelado | Comunicacion cancelada o no procesada. |

Si existen muchas comunicaciones en estado **Fallido** o **Pendiente**, revisar la configuracion de correo de la instancia.

## 11. Filtros

El panel permite filtrar por:

- direccion;
- canal;
- estado.

Tambien existen filtros internos por expediente, tipo, fecha y visibilidad cuando se usa la consulta tecnica/API.

Usar los filtros para ubicar rapidamente comunicaciones de un expediente o revisar errores de envio.

## 12. Relacion con expedientes

Cada comunicacion debe estar vinculada a un expediente.

Desde el detalle del expediente se puede acceder a comunicaciones relacionadas. Esto permite revisar en contexto:

- mensajes enviados al titular;
- solicitudes de aclaracion;
- respuestas recibidas;
- avisos de extension;
- comunicaciones de cierre o rechazo;
- historial de seguimiento.

## 13. Buenas practicas de redaccion

Al redactar comunicaciones:

- usar lenguaje claro y respetuoso;
- incluir el numero de expediente cuando aplique;
- evitar abreviaturas internas;
- indicar claramente si se solicita informacion adicional;
- no incluir datos personales innecesarios;
- revisar destinatario, asunto y mensaje antes de registrar;
- no usar la seccion para notas internas si el mensaje se marcara visible para el titular.

## 14. Buenas practicas de trazabilidad

- Registrar toda comunicacion relevante asociada al expediente.
- Registrar llamadas telefonicas importantes como comunicacion entrante.
- Registrar documentos fisicos recibidos o entregados.
- Usar el tipo correcto de comunicacion.
- Evitar duplicar registros.
- Verificar estados fallidos antes de asumir que un correo fue enviado.

## 15. Problemas frecuentes

### El correo queda pendiente

Puede ocurrir si el envio esta en cola o si el correo SMTP no esta configurado. Revisar la configuracion de correo de la instancia.

### El correo aparece como fallido

Verificar:

- que el destinatario sea correcto;
- que la configuracion SMTP este activa;
- que el proveedor de correo permita el envio;
- que no exista bloqueo por autenticacion o permisos.

### No aparece la opcion para registrar comunicacion

Puede deberse a permisos del usuario o a que no existen expedientes gestionables para ese usuario.

### No encuentro una comunicacion

Revisar filtros activos. Si hay filtros aplicados, seleccionar **Limpiar** y volver a buscar.

## 16. Recomendacion final

La seccion de comunicaciones debe usarse como bitacora formal del expediente. Todo mensaje importante enviado o recibido durante la gestion de una solicitud debe quedar registrado para mantener trazabilidad y soporte ante revisiones internas o externas.
