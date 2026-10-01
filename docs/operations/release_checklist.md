# Checklist de publicación

## 1. Configuración y secretos

- [ ] Crear variables de entorno desde `.env.example`; no copiar credenciales al repositorio.
- [ ] Generar `DJANGO_SECRET_KEY` única, extensa y aleatoria.
- [ ] Definir `DJANGO_ALLOWED_HOSTS` con dominios explícitos.
- [ ] Configurar `DATABASE_URL`, SMTP, remitente y parámetros de reintento.
- [ ] Configurar zona horaria `America/Guayaquil` y datos institucionales aprobados.
- [ ] Verificar que `DJANGO_DEBUG=False` y usar `config.settings.production`.

## 2. Infraestructura y seguridad

- [ ] Terminar TLS en el proxy y enviar correctamente `X-Forwarded-Proto`.
- [ ] Confirmar cookies `Secure`, redirección HTTPS y cabeceras de seguridad.
- [ ] Mantener HSTS de subdominios/preload desactivado hasta validar todos los subdominios; activar únicamente mediante decisión de infraestructura.
- [ ] Instalar y probar ClamAV; confirmar la ruta `CLAMAV_EXECUTABLE`.
- [ ] Crear `PRIVATE_STORAGE_ROOT` fuera de contenido público, con permisos exclusivos del usuario de servicio y respaldo cifrado.
- [ ] Restringir acceso de red a PostgreSQL, SMTP y servicios internos.

## 3. Base de datos y archivos

- [ ] Crear un respaldo verificable antes de aplicar cambios.
- [ ] Ejecutar `python manage.py migrate --check` y luego `python manage.py migrate`.
- [ ] Ejecutar `python manage.py seed_vinesa_settings` y revisar los valores con el cliente.
- [ ] Ejecutar `python manage.py collectstatic --noinput`.
- [ ] Confirmar que el servidor web entrega `STATIC_ROOT` y nunca publica el almacenamiento privado.

## 4. Procesos operativos

- [ ] Confirmar que el servicio Docker `email-worker` está activo por cada instancia.
- [ ] Programar `queue_deadline_alerts --limit 500` con frecuencia acordada.
- [ ] Programar `detect_retention_events` diariamente.
- [ ] Programar `cleanup_temporary_uploads --batch-size 100` diariamente.
- [ ] Monitorizar código de salida, duración y contadores sin registrar datos personales.
- [ ] Definir responsable y procedimiento para aprobar/rechazar retención desde el panel.

## 5. Validación antes de liberar

```powershell
python manage.py check --deploy --settings=config.settings.production
python manage.py makemigrations --check --dry-run
python manage.py migrate --check
python manage.py collectstatic --noinput --dry-run --verbosity 0
python manage.py test --keepdb -v 1
```

- [ ] Resolver todos los errores; aceptar W005/W021 solo mientras la decisión HSTS anterior esté documentada.
- [ ] Probar portal, páginas legales, creación y consulta pública de solicitudes.
- [ ] Probar login, MFA, cierre de sesión y recuperación administrativa.
- [ ] Probar cada rol con permisos permitidos y denegados.
- [ ] Probar Dashboard, expedientes, asignaciones, comunicaciones, reportes, auditoría, usuarios, configuración, evidencias y retención.
- [ ] Probar correo con un destinatario controlado y confirmar transición del outbox.
- [ ] Probar una carga limpia y el rechazo de archivo inválido/escáner no disponible.

## 6. Publicación y reversión

- [ ] Registrar versión, commit, responsable, fecha y ventana de cambio.
- [ ] Detener trabajos programados durante migraciones incompatibles.
- [ ] Publicar, aplicar migraciones y reiniciar procesos de aplicación y workers.
- [ ] Ejecutar pruebas de humo con cuentas sin datos reales.
- [ ] Mantener artefacto anterior y procedimiento de reversión de aplicación.
- [ ] Revertir base de datos únicamente con un plan probado; nunca asumir que todas las migraciones son reversibles.
- [ ] Confirmar métricas, errores, correo y espacio de almacenamiento después de publicar.
