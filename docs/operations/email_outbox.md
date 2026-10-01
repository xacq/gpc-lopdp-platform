# Despacho del outbox de correo

Las comunicaciones se almacenan cifradas en PostgreSQL antes del envío. El
despacho debe ejecutarse como un proceso separado del servidor web para no
bloquear la interfaz si el SMTP demora o falla.

## Producción con Docker

El `compose.yaml` incluye el servicio `email-worker`. Este worker procesa la
cola automáticamente cada 60 segundos para la empresa indicada por el archivo
`.env` usado al levantar la instancia:

```bash
docker compose --env-file deploy/vinesa.env up -d --build
docker compose --env-file deploy/vinesa.env logs -f email-worker
```

El mismo patrón aplica a cada empresa. Si el servidor o Docker reinicia, el
worker vuelve a levantarse con `restart: unless-stopped`.

Variables opcionales:

- `EMAIL_WORKER_BATCH_SIZE`: cantidad máxima por lote; por defecto `100`.
- `EMAIL_WORKER_INTERVAL_SECONDS`: intervalo entre ciclos; por defecto `60`.

## Ejecución manual

Para diagnóstico o despacho puntual puede ejecutarse:

```powershell
.\.venv\Scripts\python.exe manage.py process_email_outbox --batch-size 100 --drain
```

El comando procesa únicamente correos `PENDING` y reintentos `FAILED` cuyo
plazo ya venció. Respeta `COMMUNICATION_MAX_ATTEMPTS` y aplica el backoff
configurado por `COMMUNICATION_RETRY_MINUTES`.

Puede haber más de una ejecución concurrente: el bloqueo de fila de PostgreSQL
y la idempotencia de `NotificationService.process_email()` evitan el doble
envío.

La salida del comando contiene exclusivamente contadores. No muestra UUID de
expedientes, referencias, destinatarios, asuntos, cuerpos ni códigos.

## Configuración

Configure las variables `EMAIL_*`, `DEFAULT_FROM_EMAIL`,
`COMMUNICATION_MAX_ATTEMPTS` y `COMMUNICATION_RETRY_MINUTES` en el entorno de
la instalación. No almacene credenciales SMTP en el repositorio.

Antes de habilitar el programador, pruebe el backend de correo en el ambiente
correspondiente y confirme que los registros pasan de `PENDING` a `SENT` o a
`FAILED` con un error sanitizado.
