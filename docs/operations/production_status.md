# Estado actual de producción

Última actualización: 2026-10-07.

Este documento resume el estado operativo validado del servidor de producción.
No debe incluir contraseñas, tokens, respaldos ni datos personales.

## Servidor

- Sistema operativo: Ubuntu 26.04.1 LTS.
- IP pública: `146.190.39.31`.
- Ubuntu Pro / ESM: no adjunto a suscripción Ubuntu Pro.
- Ubuntu Pro / ESM queda documentado como recomendación no bloqueante.
- No había actualizaciones inmediatas pendientes al momento de la revisión.

## Firewall

`ufw` fue activado y quedó con política restrictiva:

- entrada por defecto: denegar;
- salida por defecto: permitir;
- SSH permitido;
- HTTP/HTTPS por Nginx permitidos.

Reglas activas validadas:

```text
80,443/tcp (Nginx Full) ALLOW IN Anywhere
22/tcp (OpenSSH)        ALLOW IN Anywhere
```

También quedaron activas las reglas equivalentes para IPv6.

## Instancias Docker

Las cuatro instancias se validaron activas:

- VINESA;
- VINLITORAL;
- PLUSBRAND;
- SERVMULTIMARC.

En cada instancia se verificó:

- `db` activo y saludable;
- `web` activo y saludable;
- `proxy` activo;
- `email-worker` activo.

Puertos internos publicados en localhost:

```text
VINESA:       127.0.0.1:8080 -> 80
PLUSBRAND:    127.0.0.1:8081 -> 80
SERVMULTIMARC:127.0.0.1:8082 -> 80
VINLITORAL:   127.0.0.1:8083 -> 80
```

Los puertos internos no están expuestos directamente a internet; el acceso
público pasa por Nginx y HTTPS.

## Dominios y SSL

Certificados activos con Certbot:

```text
privacidad.vinesa.com.ec
privacidad.vinlitoral.com.ec
privacidad.plusbrand.com.ec
privacidad.laguarda.com.ec
```

Fechas de expiración observadas durante la revisión:

```text
privacidad.vinesa.com.ec:      2026-12-08
privacidad.vinlitoral.com.ec:  2026-12-08
privacidad.plusbrand.com.ec:   2026-12-20
privacidad.laguarda.com.ec:    2026-12-20
```

La prueba de renovación se ejecutó correctamente:

```bash
sudo certbot renew --dry-run
```

Resultado: las renovaciones simuladas fueron exitosas para los cuatro
certificados.

## Correo

Se estandarizó el canal de comunicación con cuentas `@appscvl.com`.

Cada instancia cuenta con:

- configuración SMTP SSL;
- puerto SMTP `465`;
- `email-worker` activo;
- contenido legal y canal visible actualizados según el nuevo pipeline de
  comunicación;
- pruebas funcionales de solicitud, verificación, seguimiento y respuesta del
  delegado.

La entregabilidad puede depender de reputación del dominio y del proveedor de
correo destino, aunque las pruebas técnicas de autenticación SMTP fueron
validadas durante la configuración.

## Datos operativos de prueba

La operación de prueba de VINESA fue limpiada para dejar en cero los datos de
interacción de solicitudes, conservando configuración, usuarios, roles,
contenido legal, SMTP, logos, paleta y parámetros del sistema.

La limpieza se limitó a datos operativos de solicitudes:

- solicitudes;
- titulares;
- representantes;
- comunicaciones;
- adjuntos;
- temporales;
- tokens y registros asociados;
- historial operativo relacionado.

No se ejecutó limpieza en las otras tres instancias porque no se habían
registrado solicitudes de prueba.

## Backups

Se creó el directorio de respaldos:

```text
/opt/backups/gpc-lopdp
```

Permisos aplicados:

```text
700
```

Se generó un primer respaldo de las bases de datos de las cuatro instancias.
Los respaldos deben copiarse periódicamente fuera del servidor.

## Disco y recursos

Estado observado durante la revisión:

- disco raíz con uso aproximado de 12%;
- memoria y swap en rangos normales;
- proyecto local con bajo uso de espacio;
- volúmenes Docker dentro de rango normal;
- existía espacio recuperable en imágenes y caché de Docker.

Se ejecutó o se dejó indicado como seguro:

```bash
docker image prune -f
docker builder prune -f
```

No usar en producción:

```bash
docker compose down -v
docker volume prune
docker system prune --volumes
```

Estos comandos pueden eliminar datos persistentes.

## Estado final

Al cierre de esta revisión:

- plataforma operativa para las cuatro empresas;
- firewall activo;
- HTTPS validado;
- renovación SSL simulada exitosamente;
- workers de correo activos;
- respaldos configurados;
- documentación operativa actualizada.

Pendiente recomendado:

- definir política formal de backups externos;
- revisar Ubuntu Pro / ESM como mejora futura;
- mantener revisión mensual según `server_maintenance.md`.
