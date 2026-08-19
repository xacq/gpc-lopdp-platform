# Despacho del outbox de correo

Las comunicaciones se almacenan cifradas en PostgreSQL antes del envío. El
proceso operativo debe ejecutar periódicamente:

```powershell
.\.venv\Scripts\python.exe manage.py process_email_outbox --batch-size 100 --drain
```

El comando procesa únicamente correos `PENDING` y reintentos `FAILED` cuyo
plazo ya venció. Respeta `COMMUNICATION_MAX_ATTEMPTS` y aplica el backoff
configurado por `COMMUNICATION_RETRY_MINUTES`.

Se recomienda programarlo cada minuto mediante el mecanismo del servidor
(Programador de tareas de Windows, systemd timer, cron o equivalente). Puede
haber más de una ejecución concurrente: el bloqueo de fila de PostgreSQL y la
idempotencia de `NotificationService.process_email()` evitan el doble envío.

La salida del comando contiene exclusivamente contadores. No muestra UUID de
expedientes, referencias, destinatarios, asuntos, cuerpos ni códigos.

## Configuración

Configure las variables `EMAIL_*`, `DEFAULT_FROM_EMAIL`,
`COMMUNICATION_MAX_ATTEMPTS` y `COMMUNICATION_RETRY_MINUTES` en el entorno de
la instalación. No almacene credenciales SMTP en el repositorio.

Antes de habilitar el programador, pruebe el backend de correo en el ambiente
correspondiente y confirme que los registros pasan de `PENDING` a `SENT` o a
`FAILED` con un error sanitizado.
