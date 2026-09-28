# Manual para la gestion de usuarios

Este manual explica como crear, revisar y administrar usuarios internos en el sistema de proteccion de datos personales.

Aplica para las cuatro instancias:

- VINESA: `https://privacidad.vinesa.com.ec/accounts/login/`
- VINLITORAL: `https://privacidad.vinlitoral.com.ec/accounts/login/`
- PLUSBRAND: `https://privacidad.plusbrand.com.ec/accounts/login/`
- SERVMULTIMARC: `https://privacidad.laguarda.com.ec/accounts/login/`

Cada empresa tiene su propia base de datos y sus propios usuarios. Un usuario creado en una instancia no queda creado automaticamente en las demas.

## 1. Ingreso al sistema

1. Ingresar a la URL de la empresa correspondiente.
2. Escribir el correo electronico y la contrasena.
3. Completar la verificacion en dos pasos cuando el sistema la solicite.
4. Desde el panel interno, abrir la seccion **Usuarios**.

La seccion de usuarios esta protegida. Para acceder, el sistema puede solicitar una reautenticacion reciente por seguridad.

## 2. Usuarios principales de referencia

Las cuentas principales creadas para la delegada son:

| Empresa | Usuario |
| --- | --- |
| VINESA | `privacidad-vinesa@vinesa.com.ec` |
| VINLITORAL | `privacidad-vinlitoral@vinlitoral.com.ec` |
| PLUSBRAND | `privacidad-plusbrand@laguarda.com.ec` |
| SERVMULTIMARC | `privacidad-servmultimarc@laguarda.com.ec` |

Nombre de referencia: **Maria Elena Teran Barahona**.

No se deben guardar contrasenas en GitHub, documentos compartidos o chats. La contrasena debe conservarse en un gestor seguro de contrasenas.

## 3. Pantalla de usuarios

En la pantalla **Usuarios** se puede revisar:

- Total de usuarios.
- Usuarios activos.
- Usuarios con verificacion en dos pasos habilitada.
- Usuarios bloqueados.
- Nombre del usuario.
- Correo electronico.
- Rol principal.
- Estado: activo o inactivo.
- Estado del segundo factor.
- Ultimo acceso.

Tambien existen filtros para buscar por texto, rol o estado.

## 4. Roles disponibles

El sistema maneja los siguientes roles:

| Rol | Uso recomendado |
| --- | --- |
| Administrador | Gestion tecnica y administrativa del sistema. Debe usarse solo para cuentas autorizadas. |
| Delegado de Proteccion de Datos | Revision y supervision de temas de privacidad y proteccion de datos. |
| Responsable del tratamiento | Seguimiento institucional del tratamiento de datos personales. |
| Operador | Gestion operativa de solicitudes y tareas asignadas. |
| Auditor | Revision y consulta de informacion cuando se requiera trazabilidad. |

Recomendacion: asignar siempre el menor nivel de acceso necesario para la funcion del usuario.

## 5. Crear un nuevo usuario

1. Entrar a **Usuarios**.
2. Seleccionar **+ Nuevo usuario**.
3. Completar:
   - **Correo electronico**.
   - **Nombre completo**.
   - **Rol primario**.
   - **Contrasena inicial**.
   - **Confirmar contrasena**.
4. Seleccionar **Crear usuario**.
5. Entregar la contrasena inicial por un canal seguro.
6. Solicitar al usuario que ingrese y configure su verificacion en dos pasos.

Buenas practicas:

- Usar correos institucionales.
- No compartir cuentas entre varias personas.
- No reutilizar contrasenas.
- Cambiar la contrasena inicial en el primer ingreso si asi lo define la organizacion.

## 6. Cambiar el rol de un usuario

1. Entrar a **Usuarios**.
2. Buscar el usuario.
3. Abrir el menu de acciones de la fila.
4. Seleccionar **Cambiar rol**.
5. Elegir el nuevo **Rol primario**.
6. Seleccionar **Guardar rol**.

Antes de subir privilegios, confirmar que el cambio esta autorizado.

## 7. Restablecer la contrasena

1. Entrar a **Usuarios**.
2. Buscar el usuario.
3. Abrir el menu de acciones.
4. Seleccionar **Restablecer contrasena**.
5. Escribir la nueva contrasena y confirmarla.
6. Seleccionar **Restablecer contrasena**.
7. Comunicar la nueva contrasena por un canal seguro.

Importante: al restablecer la contrasena, el usuario debera configurar nuevamente la verificacion en dos pasos.

## 8. Desbloquear usuario

Si un usuario queda bloqueado por intentos fallidos:

1. Entrar a **Usuarios**.
2. Buscar el usuario.
3. Abrir el menu de acciones.
4. Seleccionar **Desbloquear**.
5. Indicar al usuario que vuelva a intentar el ingreso.

Si el bloqueo se repite, se recomienda restablecer la contrasena y revisar si el usuario esta usando credenciales correctas.

## 9. Desactivar o activar usuario

Cuando una persona ya no debe ingresar al sistema:

1. Entrar a **Usuarios**.
2. Buscar el usuario.
3. Abrir el menu de acciones.
4. Seleccionar **Desactivar**.

Si posteriormente debe recuperar acceso:

1. Buscar el usuario inactivo.
2. Abrir el menu de acciones.
3. Seleccionar **Activar**.

No se recomienda eliminar historiales o registros asociados al usuario. Para mantener trazabilidad, es preferible desactivar la cuenta.

## 10. Verificacion en dos pasos

La columna **Segundo factor** muestra si el usuario ya tiene la verificacion en dos pasos habilitada.

Estados habituales:

- **Habilitado**: el usuario ya configuro su segundo factor.
- **Pendiente**: el usuario todavia debe configurarlo.

La verificacion en dos pasos es obligatoria para proteger el acceso al sistema.

## 11. Recomendaciones de control

- Revisar periodicamente usuarios activos e inactivos.
- Confirmar que cada usuario tenga el rol correcto.
- Desactivar inmediatamente cuentas de personas que ya no colaboran con la empresa.
- Evitar multiples administradores si no son necesarios.
- No compartir usuarios genericos.
- No enviar contrasenas por canales publicos o grupos abiertos.
- Mantener una lista interna de responsables autorizados para pedir altas, bajas o cambios de rol.

## 12. Problemas frecuentes

### El usuario no puede ingresar

Verificar:

- Que el correo este escrito correctamente.
- Que la cuenta este activa.
- Que la contrasena sea correcta.
- Que no este bloqueado por intentos fallidos.
- Que haya completado la verificacion en dos pasos.

### El usuario cambio de telefono o perdio el autenticador

Restablecer la contrasena desde **Usuarios**. Luego el usuario debera configurar nuevamente la verificacion en dos pasos.

### El usuario necesita mas permisos

Cambiar el rol solo si existe autorizacion interna. Si no esta claro que rol corresponde, validar primero con la delegada o el responsable interno.

## 13. Cierre de sesion

Al terminar el trabajo, el usuario debe cerrar sesion desde el sistema, especialmente si usa un equipo compartido o de acceso temporal.
