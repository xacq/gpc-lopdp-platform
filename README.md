# VINESA — Plataforma de Privacidad y Solicitudes LOPDP

Aplicación Django para recepción, seguimiento y gestión interna de solicitudes de derechos de protección de datos. Incluye portal público, autenticación con MFA, expedientes, asignaciones, comunicaciones cifradas, evidencias, retención, reportes, auditoría y administración segura de usuarios y configuración.

## Estado actual

El backend funcional previo a la aplicación final del diseño UI está implementado. La rama activa incluye los flujos públicos y administrativos, controles de permisos, auditoría y paneles operativos. La última regresión completa aprobó 468 pruebas.

## Arranque local en Windows y VS Code

Requisitos: Python 3.13, PostgreSQL y PowerShell. ClamAV es necesario para probar cargas públicas reales; si no está disponible, el sistema rechaza esos archivos de forma segura.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements\base.txt
Copy-Item .env.example .env
```

Edite `.env` y configure como mínimo una clave secreta y `DATABASE_URL`. No use credenciales reales en archivos versionados.

```powershell
python manage.py migrate
python manage.py seed_vinesa_settings
python manage.py createsuperuser
python manage.py runserver
```

También puede abrir **Ejecutar y depurar** en VS Code y seleccionar `Django: servidor local`. El repositorio incluye esa configuración y tareas de verificación.

Rutas principales:

- Portal público: <http://127.0.0.1:8000/>
- Inicio de sesión: <http://127.0.0.1:8000/accounts/login/>
- Dashboard: <http://127.0.0.1:8000/dashboard/>
- Administración nativa: <http://127.0.0.1:8000/admin/>

## Verificación

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --check
python manage.py collectstatic --noinput --dry-run --verbosity 0
python manage.py test --keepdb -v 1
```

En VS Code puede ejecutar las tareas `Django: verificar proyecto` y `Django: pruebas completas`.

## Procesos programados

En producción, programe estos comandos con el usuario de servicio y las mismas variables de entorno que la aplicación:

```powershell
python manage.py process_email_outbox --batch-size 100 --drain
python manage.py queue_deadline_alerts --limit 500
python manage.py detect_retention_events
python manage.py cleanup_temporary_uploads --batch-size 100
```

El outbox se recomienda cada minuto. Los otros procesos deben programarse según el acuerdo operativo; alertas y retención son idempotentes. Consulte [despacho de correo](docs/operations/email_outbox.md) y [cargas públicas](docs/operations/public_uploads.md).

## Producción

Use `config.settings.production`, PostgreSQL, un servidor WSGI/ASGI y un proxy HTTPS. `runserver` es exclusivamente local. Antes de publicar, ejecute `collectstatic`, configure SMTP y ClamAV, proteja `PRIVATE_STORAGE_ROOT`, aplique migraciones y complete el [checklist de publicación](docs/operations/release_checklist.md).

`SECURE_HSTS_INCLUDE_SUBDOMAINS` y `SECURE_HSTS_PRELOAD` permanecen deshabilitados de manera intencional hasta confirmar que todos los subdominios operan permanentemente bajo HTTPS.
