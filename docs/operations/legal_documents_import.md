# Importacion de documentos legales publicos

Los HTML ubicados en `legal_documents/` son plantillas Django. No contienen una
empresa fija: usan la configuracion activa de cada instancia (`SystemSetting`)
para renderizar razon social, direccion, telefono, dominio y correo de
privacidad.

## Correos aprobados

| Instancia | Correo de privacidad |
| --- | --- |
| VINESA | `privacidad-vinesa@vinesa.com.ec` |
| VINLITORAL | `privacidad-vinlitoral@vinlitoral.com.ec` |
| PLUSBRAND | `privacidad-plusbrand@laguarda.com.ec` |
| SERVMULTIMARC | `privacidad-servmultimarc@laguarda.com.ec` |

Actualice primero la configuracion institucional de cada instancia para que los
documentos se rendericen con el correo correcto.

## Comando de importacion

```bash
python manage.py import_public_legal_documents --legal-version 1.0 --publish
```

El comando crea y publica:

- Politica de Proteccion de Datos Personales
- Aviso Clientes
- Aviso Empleados
- Aviso Candidatos
- Aviso Proveedores
- Aviso Videovigilancia
- Derechos y Contacto
- Politica de Cookies

Si ya se importo la version indicada anteriormente, el comando omite los
documentos existentes y crea solo los documentos faltantes de esa misma version.

## Servidor

Ejecute una vez por instancia:

```bash
docker compose --env-file deploy/vinesa.env exec web python manage.py import_public_legal_documents --legal-version 1.0 --publish
docker compose --env-file deploy/vinlitoral.env exec web python manage.py import_public_legal_documents --legal-version 1.0 --publish
docker compose --env-file deploy/plusbrand.env exec web python manage.py import_public_legal_documents --legal-version 1.0 --publish
docker compose --env-file deploy/servmultimarc.env exec web python manage.py import_public_legal_documents --legal-version 1.0 --publish
```
