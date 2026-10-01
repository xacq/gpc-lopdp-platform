# GPC LOPDP Platform

Plataforma Django para recibir, dar seguimiento y gestionar internamente
solicitudes de ejercicio de derechos previstos en la LOPDP ecuatoriana.

Incluye portal público, expedientes, verificación de identidad, evidencias,
plazos, resoluciones, comunicaciones cifradas, auditoría, reportes y gestión
segura de usuarios. Puede operar varias empresas con bases de datos,
volúmenes y archivos de configuración aislados.

## Funcionalidades principales

- Solicitudes públicas de acceso, rectificación y actualización, eliminación,
  oposición, portabilidad y suspensión del tratamiento.
- Referencia y códigos seguros para verificar correo y consultar solicitudes.
- Gestión de expedientes: asignación, revisión, aclaraciones, extensión,
  resolución y cierre.
- Causales de resolución LOPDP según el tipo de resultado.
- Cola de correos SMTP, comunicaciones y trazabilidad de entrega.
- Evidencias protegidas, cifrado de datos sensibles, auditoría y MFA.

## Documentación

- [Manual operativo para la empresa](docs/manual_propietario_empresa.md)
- [Docker local por empresa](docs/operations/docker_local.md)
- [Despacho de correo](docs/operations/email_outbox.md)
- [Cargas públicas](docs/operations/public_uploads.md)
- [Checklist de publicación](docs/operations/release_checklist.md)

### Entrega formal

- [Acta de entrega y aceptación](docs/entrega/acta_entrega_aceptacion.md)
- [Ficha técnica confidencial por empresa](docs/entrega/ficha_tecnica_empresa.md)
- [Checklist de puesta en producción](docs/entrega/checklist_puesta_produccion.md)

El manual operativo para propietarios y personal de cada empresa debe
mantenerse separado de este README. No incluya en el repositorio credenciales,
datos personales, respaldos ni información de acceso a servidores.

## Inicio local en Windows

Requiere Python 3.13, PostgreSQL y PowerShell. ClamAV es necesario para probar
cargas públicas reales; si no está disponible, el sistema rechaza los archivos
por seguridad.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements\base.txt
Copy-Item .env.example .env
```

Configure en `.env` al menos `DJANGO_SECRET_KEY` y `DATABASE_URL`. No use
credenciales reales en archivos versionados.

```powershell
python manage.py migrate
python manage.py seed_lopdp_rights
python manage.py seed_resolution_reasons
python manage.py createsuperuser
python manage.py runserver
```

Rutas principales:

- Portal público: <http://127.0.0.1:8000/>
- Inicio de sesión: <http://127.0.0.1:8000/accounts/login/>
- Panel: <http://127.0.0.1:8000/dashboard/>
- Administración nativa, si está habilitada: <http://127.0.0.1:8000/admin/>

## Verificación

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --check
python manage.py collectstatic --noinput --dry-run --verbosity 0
python manage.py test --keepdb -v 1
```

## Docker multiempresa

Cada empresa usa su propio archivo de entorno y sus propios volúmenes. En la
instalación actual los archivos son:

- `deploy/vinesa.env`
- `deploy/plusbrand.env`
- `deploy/servmultimarc.env`
- `deploy/vinlitoral.env`

Ejemplo de operación para una empresa:

```bash
docker compose --env-file deploy/vinesa.env up --build -d
docker compose --env-file deploy/vinesa.env exec web python manage.py check
```

Tras una instalación nueva o una actualización de catálogo, ejecute:

```bash
python manage.py seed_lopdp_rights
python manage.py seed_resolution_reasons
```

Consulte la guía Docker para operaciones completas, respaldos y actualización
de instancias.

## Correo y procesos programados

Cada empresa debe configurar su propio SMTP y `DEFAULT_FROM_EMAIL` en su
archivo `.env`. Los correos salientes se almacenan primero en una cola y, en
Docker, se envían automáticamente con el servicio `email-worker` incluido en
`compose.yaml`.

Para diagnosticar o forzar un despacho puntual:

```bash
python manage.py process_email_outbox --batch-size 100 --drain
```

También deben programarse las alertas de plazo, retención y limpieza de cargas
temporales según el procedimiento operativo definido para cada empresa.

## Producción y seguridad

Use `config.settings.production`, PostgreSQL, HTTPS y un proxy inverso. Antes
de publicar, configure SMTP y ClamAV, proteja el almacenamiento privado,
aplique migraciones, realice respaldos y complete el checklist de publicación.

No ejecute `docker compose down -v` en producción: elimina volúmenes de datos.
