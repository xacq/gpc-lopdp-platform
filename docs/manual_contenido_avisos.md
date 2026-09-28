# Manual de contenido de avisos y politicas

Este manual explica como administrar los documentos publicados en la pagina
`Avisos y politicas` del portal.

## 1. Acceso al modulo

1. Ingrese al panel administrativo de la empresa.
2. Complete la verificacion en dos pasos.
3. Abra `Contenido legal`.
4. Use el boton `Ver portal legal` para revisar la pagina publica de avisos.

La pagina publica de avisos esta disponible en:

```text
/legal/
```

Ejemplo:

```text
https://privacidad.vinesa.com.ec/legal/
```

## 2. Estados visibles en el portal

En la pagina publica cada tarjeta puede mostrarse como:

- `Vigente`: existe una version publicada y activa.
- `Pendiente`: no existe todavia una version publicada para ese documento.

Un documento en borrador no aparece como vigente hasta que se publique.

## 3. Tipos de documento

El sistema maneja estos tipos:

| Tipo | Uso |
| --- | --- |
| Politica de Privacidad | Politica general de tratamiento de datos personales. |
| Derechos y Contacto | Informacion para ejercer derechos y presentar reclamos. |
| Politica de Cookies | Uso de cookies tecnicas y tecnologias similares. |
| Aviso Empleados | Aviso para relaciones laborales. |
| Aviso Candidatos | Aviso para procesos de seleccion. |
| Aviso Clientes/Vendedores | Aviso para clientes, vendedores o relaciones comerciales equivalentes. |
| Aviso Proveedores | Aviso para proveedores y representantes. |
| Aviso Videovigilancia | Aviso para espacios con camaras de seguridad. |
| Otro | Documento excepcional no cubierto por los tipos anteriores. |

## 4. Crear un borrador

En `Contenido legal`, seccion `Crear borrador`, complete:

- Tipo de documento.
- Titulo.
- Slug, si aplica.
- Version.
- Vigente desde.
- Contenido HTML.

Luego pulse `Guardar borrador`.

El borrador queda registrado, pero no reemplaza el documento publico hasta que
se publique.

## 5. Versiones

Use versiones consecutivas para mantener trazabilidad. Ejemplos:

```text
1.0
1.1
1.2
2.0
```

Recomendacion:

- Cambios menores de datos institucionales: `1.1`, `1.2`, etc.
- Cambios sustanciales de texto legal: `2.0`.

No reutilice una version ya creada para el mismo tipo de documento.

## 6. Fecha de vigencia

El campo `Vigente desde` define desde cuando aplica la version.

Buenas practicas:

- Usar fecha y hora actual si el documento se aprueba para publicacion inmediata.
- Usar fecha futura solo si la publicacion debe entrar en vigencia despues.
- Verificar que la nueva fecha sea posterior a la version vigente anterior.

Al publicar una nueva version, el sistema puede cerrar automaticamente la
vigencia de la version anterior del mismo tipo.

## 7. Publicar un documento

En la tabla `Documentos registrados`:

1. Ubique el borrador.
2. Revise tipo, titulo, version y vigencia.
3. Pulse `Publicar`.
4. Abra `Ver portal legal`.
5. Confirme que la tarjeta aparezca como `Vigente`.

Una vez publicado, el documento se muestra en la pagina publica.

## 8. HTML permitido

El contenido se sanitiza antes de guardarse. El sistema conserva solo HTML
seguro y simple.

Etiquetas recomendadas:

```html
<h2>Titulo de seccion</h2>
<h3>Subtitulo</h3>
<p>Parrafo de contenido.</p>
<strong>Texto destacado</strong>
<em>Texto enfatizado</em>
<ul>
  <li>Elemento de lista</li>
</ul>
<ol>
  <li>Paso numerado</li>
</ol>
<a href="https://ejemplo.com">Enlace</a>
<a href="mailto:correo@empresa.com">Correo</a>
<blockquote>Cita o nota destacada.</blockquote>
```

Evite pegar directamente contenido desde Word con estilos, tablas, imagenes,
colores o clases CSS. El sistema eliminara elementos no permitidos.

## 9. Reglas para editar texto legal

Antes de publicar:

- Verifique razon social, RUC, direccion, telefono y correo.
- Confirme que el texto fue aprobado por la persona responsable.
- Revise que los enlaces funcionen.
- Revise que no existan referencias a otra empresa.
- Revise que el correo de privacidad corresponda a la instancia correcta.

No publique contenido legal sin aprobacion institucional.

## 10. Plantillas importadas desde el servidor

El sistema tambien puede publicar documentos desde plantillas versionadas en el
repositorio.

Comando base:

```bash
python manage.py import_public_legal_documents --legal-version 1.3 --publish
```

En Docker debe ejecutarse por instancia. Ejemplo:

```bash
docker compose --env-file deploy/vinesa.env exec web python manage.py import_public_legal_documents --legal-version 1.3 --publish
```

Este mecanismo es util cuando:

- Se actualiza el mismo texto en las 4 empresas.
- Se cambian datos institucionales usados por las plantillas.
- Se quiere mantener consistencia entre instancias.

## 11. Documentos y configuracion institucional

Algunos documentos toman datos desde `Configuracion`, por ejemplo:

- Razon social.
- Nombre comercial.
- Direccion.
- Telefono.
- Correo de privacidad.
- DPD.
- Canal de reclamos.

Si cambia alguno de esos datos, publique una nueva version de documentos para
que el contenido legal refleje la informacion actual.

## 12. Revision posterior a la publicacion

Despues de publicar:

1. Abra la pagina `Avisos`.
2. Abra el documento publicado.
3. Verifique titulo, version y fecha de vigencia.
4. Revise el contenido completo.
5. Verifique enlaces y correos.
6. Compare que no existan datos de otra empresa.

## 13. Buenas practicas

- Crear primero un borrador.
- Revisar el contenido antes de publicar.
- Usar HTML simple.
- No usar tablas si no son indispensables.
- No copiar contenido con formato visual complejo.
- No publicar versiones de prueba en produccion.
- Mantener numeracion de versiones consistente.
- Documentar internamente quien aprobo cada cambio.

## 14. Escalamiento

Solicite soporte tecnico si:

- El borrador no se guarda.
- El contenido se guarda pero desaparecen secciones.
- Un documento publicado no aparece como vigente.
- El sistema rechaza la publicacion.
- Se requiere convertir documentos Word a HTML limpio.
- Se requiere publicar masivamente en las 4 empresas.
