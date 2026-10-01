# Cargas públicas seguras

Los documentos públicos admitidos son PDF, JPG y PNG, con un máximo de 25 MB
por archivo y tres campos de carga por solicitud. El servidor limita la carga
en memoria y valida extensión, MIME declarado y firma binaria.

Cada archivo pasa por el backend configurado en
`PUBLIC_UPLOAD_MALWARE_SCANNER`. El backend predeterminado ejecuta ClamAV por
stdin, sin crear copias temporales en texto plano. Si el escáner no está
instalado, excede el tiempo o devuelve un estado desconocido, la carga se
rechaza de forma cerrada.

Configure `CLAMAV_EXECUTABLE` con la ruta del ejecutable `clamscan` y valide su
funcionamiento antes de habilitar el portal. Los archivos aceptados se guardan
cifrados bajo `PRIVATE_STORAGE_ROOT`, que debe estar fuera de `MEDIA_ROOT` y
`STATIC_ROOT`.

Las cargas temporales se ligan a la sesión mediante HMAC y expiran. Programe
periódicamente:

```powershell
.\.venv\Scripts\python.exe manage.py cleanup_temporary_uploads --batch-size 100
```

El comando elimina únicamente almacenamiento temporal expirado no promovido y
solo muestra contadores; no imprime nombres, rutas, tokens ni datos del
expediente.
