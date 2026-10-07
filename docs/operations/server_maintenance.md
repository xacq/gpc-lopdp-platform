# Mantenimiento del servidor

Guía operativa para el servidor Ubuntu que ejecuta las instancias Docker de la
plataforma LOPDP.

## Alcance

Esta guía cubre tareas básicas de seguridad y operación:

- estado de Ubuntu Pro / ESM;
- firewall;
- respaldos;
- monitoreo de servicios;
- disco y logs.

No incluya contraseñas, tokens, respaldos reales ni archivos `.env` con
credenciales dentro del repositorio.

## Ubuntu Pro / ESM

Ubuntu puede mostrar el mensaje:

```text
Expanded Security Maintenance for Applications is not enabled.
```

Esto no bloquea la operación de la plataforma. Significa que el servidor no
está asociado a una suscripción Ubuntu Pro para recibir mantenimiento extendido
de ciertos paquetes.

Verificar estado:

```bash
sudo pro status
```

Si el servidor cuenta con token de Ubuntu Pro, puede activarse con:

```bash
sudo pro attach TOKEN
sudo pro enable esm-apps
sudo pro enable esm-infra
sudo pro status
```

Esta activación es recomendable para seguridad a largo plazo, pero no es
requisito inmediato para operar la plataforma si el sistema se mantiene
actualizado con `apt`.

## Actualizaciones del sistema

Revisión periódica:

```bash
sudo apt update
sudo apt upgrade
```

Verificar si un reinicio está pendiente:

```bash
test -f /var/run/reboot-required && cat /var/run/reboot-required || echo "Sin reinicio pendiente"
```

## Firewall

La plataforma se expone por Nginx en los puertos públicos HTTP/HTTPS. Docker
publica cada instancia solo en `127.0.0.1`, por lo que no debe exponerse
directamente cada puerto interno.

Reglas mínimas recomendadas:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status verbose
```

Si `Nginx Full` no existe en el servidor, use:

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

No abra los puertos internos de las instancias (`8080`, `8081`, `8082`,
`8083`) hacia internet. Deben seguir enlazados a `127.0.0.1`.

Verificar:

```bash
grep -A2 'ports:' compose.yaml
```

Debe mostrar:

```yaml
ports:
  - "127.0.0.1:${HTTP_PORT:-8080}:80"
```

## Backups

Realice respaldos antes de cambios importantes y de forma periódica.

Directorio sugerido en el servidor:

```bash
sudo mkdir -p /opt/backups/gpc-lopdp
sudo chown "$USER":"$USER" /opt/backups/gpc-lopdp
chmod 700 /opt/backups/gpc-lopdp
```

Respaldos manuales por instancia:

```bash
cd /opt/gpc-lopdp-platform
BACKUP_DIR=/opt/backups/gpc-lopdp
STAMP=$(date +%Y%m%d-%H%M%S)

docker compose --env-file deploy/vinesa.env exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$BACKUP_DIR/vinesa-$STAMP.sql"
docker compose --env-file deploy/vinlitoral.env exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$BACKUP_DIR/vinlitoral-$STAMP.sql"
docker compose --env-file deploy/plusbrand.env exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$BACKUP_DIR/plusbrand-$STAMP.sql"
docker compose --env-file deploy/servmultimarc.env exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$BACKUP_DIR/servmultimarc-$STAMP.sql"

gzip "$BACKUP_DIR"/*-"$STAMP".sql
```

Verificar archivos:

```bash
ls -lh /opt/backups/gpc-lopdp
```

Eliminar respaldos antiguos, por ejemplo mayores a 30 días:

```bash
find /opt/backups/gpc-lopdp -type f -name "*.sql.gz" -mtime +30 -delete
```

Los respaldos deben copiarse periódicamente fuera del servidor.

## Monitoreo de servicios

Verificar todas las instancias:

```bash
cd /opt/gpc-lopdp-platform
docker compose --env-file deploy/vinesa.env ps
docker compose --env-file deploy/vinlitoral.env ps
docker compose --env-file deploy/plusbrand.env ps
docker compose --env-file deploy/servmultimarc.env ps
```

Cada instancia debe mostrar:

- `db` saludable;
- `web` saludable;
- `proxy` activo;
- `email-worker` activo.

Revisar logs recientes del worker:

```bash
docker compose --env-file deploy/vinesa.env logs --tail=50 email-worker
docker compose --env-file deploy/vinlitoral.env logs --tail=50 email-worker
docker compose --env-file deploy/plusbrand.env logs --tail=50 email-worker
docker compose --env-file deploy/servmultimarc.env logs --tail=50 email-worker
```

Revisar Nginx:

```bash
sudo nginx -t
sudo systemctl status nginx --no-pager
```

Revisar Docker:

```bash
sudo systemctl status docker --no-pager
docker stats --no-stream
```

## Disco y logs

Ver uso de disco:

```bash
df -h
du -sh /opt/gpc-lopdp-platform
du -sh /opt/backups/gpc-lopdp 2>/dev/null || true
docker system df
```

Revisar memoria:

```bash
free -h
```

Limpieza segura de Docker:

```bash
docker image prune -f
docker builder prune -f
```

No ejecute en producción:

```bash
docker compose down -v
docker volume prune
docker system prune --volumes
```

Estos comandos pueden eliminar bases de datos y archivos persistentes.

## SSL

Ver certificados activos:

```bash
sudo certbot certificates
```

Probar renovación:

```bash
sudo certbot renew --dry-run
```

## Checklist mensual

```text
[ ] apt update / apt upgrade revisado
[ ] reinicio pendiente revisado
[ ] ufw activo
[ ] nginx activo y configuración válida
[ ] docker activo
[ ] 4 instancias con db/web/proxy/email-worker activos
[ ] logs email-worker sin errores repetidos
[ ] backups generados y copiados fuera del servidor
[ ] disco con espacio suficiente
[ ] docker image prune ejecutado si aplica
[ ] certbot renew --dry-run sin errores
[ ] Ubuntu Pro/ESM revisado como mejora no bloqueante
```
