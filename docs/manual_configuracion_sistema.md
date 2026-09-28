# Manual de configuracion del sistema

Este manual explica como revisar y actualizar la configuracion institucional de
cada instancia del portal de privacidad.

## 1. Acceso

1. Ingrese a la URL administrativa de la empresa.
2. Inicie sesion con usuario autorizado.
3. Complete la verificacion en dos pasos.
4. Abra `Configuracion`.
5. Si el sistema solicita reautenticacion, vuelva a ingresar su contrasena.

URLs administrativas:

| Empresa | URL |
| --- | --- |
| VINESA | `https://privacidad.vinesa.com.ec/accounts/login/` |
| VINLITORAL | `https://privacidad.vinlitoral.com.ec/accounts/login/` |
| PLUSBRAND | `https://privacidad.plusbrand.com.ec/accounts/login/` |
| SERVMULTIMARC | `https://privacidad.laguarda.com.ec/accounts/login/` |

## 2. Configuracion institucional

En la seccion `Datos institucionales` revise:

- Razon social.
- Nombre comercial.
- RUC.
- Dominio.

En la seccion `Canales oficiales` revise:

- Telefono.
- Correo de privacidad.
- Direccion.

Estos datos alimentan automaticamente la pagina publica de contacto, el pie de
pagina, los documentos legales generados desde plantillas y la identidad visible
de la empresa.

Datos actuales aprobados:

| Empresa | RUC | Razon social | Telefono |
| --- | --- | --- | --- |
| VINESA | `1792049598001` | `VINOS Y ESPIRITUOSOS VINESA S.A.` | `022409508` |
| VINLITORAL | `0992716428001` | `VINOS Y ESPIRITUOSOS DEL LITORAL VINLITORAL S.A.` | `043917838` |
| PLUSBRAND | `1792288916001` | `CORPORACION PLUSBRAND DEL ECUADOR CIA. LTDA.` | `2908679222` |
| SERVMULTIMARC | `0992870230001` | `SERVICIOS MULTIMARCAS UNIDAS SERVMULTIMARC CIA. LTDA.` | `044540469` |

Correos de privacidad:

- `privacidad-vinesa@vinesa.com.ec`
- `privacidad-vinlitoral@vinlitoral.com.ec`
- `privacidad-plusbrand@laguarda.com.ec`
- `privacidad-servmultimarc@laguarda.com.ec`

## 3. Responsable del tratamiento

En `Responsable del tratamiento` configure:

- Nombre del responsable.
- Correo del responsable.
- Telefono del responsable.

Normalmente el responsable corresponde a la razon social de la empresa. El
correo puede ser el canal oficial de privacidad si no existe otro canal
especifico aprobado.

## 4. Delegado de Proteccion de Datos

En `Delegado de Proteccion de Datos` configure:

- Nombre del DPD.
- Correo del DPD.
- Telefono del DPD, si aplica.

Dato aprobado:

```text
María Elena Terán Barahona
```

Use el correo de privacidad de cada empresa como canal del DPD, salvo que se
apruebe una direccion especifica distinta.

## 5. Branding

En `Branding y Colores` puede administrar:

- Logotipo institucional.
- Favicon o icono del navegador.
- URL externa de logotipo, si no se sube archivo.
- URL externa de favicon, si no se sube archivo.

Recomendaciones:

- Preferir archivos PNG o SVG con fondo transparente.
- Verificar la vista previa antes de guardar.
- Mantener favicon cuadrado y simple.
- No usar enlaces externos si el archivo puede cargarse directamente al sistema.

## 6. Paleta de colores

La paleta usa codigos hexadecimales con formato:

```text
#RRGGBB
```

Campos disponibles:

- Color primario.
- Color secundario.
- Color de acento.
- Fondo general.
- Estado activo/presionado.
- Separadores.
- Bordes y formularios.
- Texto secundario.
- Exito.
- Informacion.
- Advertencia.
- Error o rechazo.

Puede escribir el codigo hexadecimal o elegir el color desde el recuadro. La
muestra de combinacion activa permite revisar rapidamente primario, secundario y
acento.

## 7. Parametros generales

En `Parametros generales` revise:

- Prefijo de solicitudes.
- Zona horaria.

El prefijo ayuda a identificar referencias de expedientes por empresa. No lo
cambie si ya existen solicitudes creadas, salvo autorizacion expresa.

La zona horaria recomendada es:

```text
America/Guayaquil
```

## 8. Canal de reclamos

En `Canal de reclamos` configure:

- Autoridad de control.
- URL del canal oficial.
- Instrucciones para el usuario.

Valores recomendados:

```text
Autoridad: Superintendencia de Protección de Datos Personales
URL: https://servicios.spdp.gob.ec/denuncia
```

Texto sugerido:

```text
Los reclamos o denuncias ante la autoridad de control pueden presentarse a través del portal oficial de denuncias de la SPDP. Contacto general SPDP: info@spdp.gob.ec / (593) 24700047.
```

## 9. Guardar cambios

Despues de modificar la configuracion:

1. Pulse `Guardar cambios`.
2. Confirme que aparezca el mensaje de configuracion guardada.
3. Revise la pagina publica de inicio.
4. Revise `Contacto`.
5. Revise `Avisos` si el cambio afecta documentos legales.

Si los cambios no aparecen inmediatamente, actualice el navegador con recarga
forzada.

## 10. Cambios que requieren republicar documentos

Debe publicar una nueva version legal cuando cambien datos usados por las
plantillas de documentos, por ejemplo:

- Razon social.
- RUC.
- Direccion.
- Telefono.
- Correo de privacidad.
- DPD.
- Canal de reclamos.

El comando de publicacion debe ejecutarse en el servidor con una nueva version,
por ejemplo:

```bash
python manage.py import_public_legal_documents --legal-version 1.3 --publish
```

En Docker se ejecuta por instancia usando el archivo `.env` correspondiente.

## 11. Buenas practicas

- Realizar cambios en una empresa a la vez.
- Verificar datos con documentos oficiales antes de guardar.
- No cambiar prefijos si ya existen expedientes.
- No cargar imagenes de origen desconocido.
- Mantener los correos de privacidad aprobados.
- Registrar internamente cualquier cambio relevante.
- Revisar pagina publica y login despues de guardar branding.

## 12. Escalamiento

Solicite soporte tecnico si:

- El formulario no guarda.
- Un color no se refleja en la interfaz.
- El logo o favicon no carga.
- Aparece error de permisos.
- La informacion publica no coincide con la configuracion guardada.
- Se requiere republicar documentos legales y no se tiene acceso al servidor.
