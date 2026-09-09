# Docker local por empresa

La misma imagen se ejecuta una vez por empresa. Cada proyecto Compose crea su
propia base PostgreSQL y sus propios volúmenes de archivos. No comparta archivos
`.env`, claves criptográficas, bases ni volúmenes entre empresas.

## Instancias locales configuradas

| Marca | Archivo de entorno | Puerto | Proyecto/base interna |
| --- | --- | ---: | --- |
| VINESA | `deploy/docker.env` | 8080 | `gpc-lopdp-vinesa` |
| PLUSBRAND | `deploy/plusbrand.env` | 8081 | `gpc-lopdp-empresa2` |
| SERVMULTIMARC | `deploy/servmultimarc.env` | 8082 | `gpc-lopdp-empresa3` |
| VINLITORAL | `deploy/vinlitoral.env` | 8083 | `gpc-lopdp-empresa4` |

Los identificadores internos `empresa2`, `empresa3` y `empresa4` se conservan
para reutilizar los volúmenes PostgreSQL existentes. La identidad visible, el
emisor MFA, los recursos gráficos y la paleta corresponden a cada marca.

El administrador nativo de Django (`/admin/`) está deshabilitado en todas las
instancias Docker mediante `DJANGO_ADMIN_ENABLED=False`. La administración se
realiza exclusivamente desde los paneles propios de la plataforma.

## VINESA piloto

1. Genere el entorno local con secretos independientes:

   ```powershell
   .\deploy\init_docker_env.ps1
   ```

2. Revise `deploy/docker.env` y luego construya e inicie la instalación:

   ```powershell
   docker compose --env-file deploy/docker.env up --build -d
   docker compose --env-file deploy/docker.env ps
   ```

3. Inicialice VINESA y cree el administrador dentro del contenedor:

   ```powershell
   docker compose --env-file deploy/docker.env exec web python manage.py seed_vinesa_settings
   docker compose --env-file deploy/docker.env exec web python manage.py createsuperuser
   ```

4. Abra `http://localhost:8080/` y configure logo y colores en
   `http://localhost:8080/settings/`.

La base Docker es nueva; el usuario y los datos de la instalación local fuera
de Docker no se copian automáticamente.

## ClamAV para cargas públicas

El ejecutable está incluido, pero necesita firmas actualizadas. Ejecute antes
de probar adjuntos:

```powershell
docker compose --env-file deploy/docker.env run --rm --user root --entrypoint freshclam web
docker compose --env-file deploy/docker.env restart web
```

Si ClamAV no está operativo, la carga se rechaza de forma segura.

## Comandos habituales

```powershell
docker compose --env-file deploy/docker.env logs -f web
docker compose --env-file deploy/docker.env exec web python manage.py check
docker compose --env-file deploy/docker.env exec web python manage.py test -v 1
docker compose --env-file deploy/docker.env down
```

No utilice `down -v` salvo que quiera eliminar definitivamente la base y los
archivos de esa empresa.

## Replicar otra empresa

Genere un entorno con secretos, puerto y base independientes, y levante el
mismo código con otro nombre de proyecto Compose:

```powershell
.\deploy\init_docker_env.ps1 -OutputPath deploy/empresa2.env -HttpPort 8081 -TenantSlug empresa2 -MfaIssuer "EMPRESA 2" -DefaultFromEmail privacidad@empresa2.local
docker compose --env-file deploy/empresa2.env up -d
```

Ejemplo mínimo para la segunda empresa:

```env
TENANT_ENV_FILE=deploy/empresa2.env
HTTP_PORT=8081
PUBLIC_SITE_URL=http://localhost:8081
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8081
POSTGRES_DB=gpc_lopdp_empresa2
POSTGRES_USER=gpc_lopdp_empresa2
DATABASE_URL=postgresql://gpc_lopdp_empresa2:CLAVE@db:5432/gpc_lopdp_empresa2
MFA_TOTP_ISSUER=EMPRESA2
```

No ejecute `seed_vinesa_settings` para otras empresas. Cree el superusuario,
ingrese a `/settings/` y registre los datos institucionales, colores y archivos
de identidad visual correspondientes.

Para una configuración provisional reproducible puede ejecutar:

```powershell
docker compose --env-file deploy/empresa2.env exec web python manage.py seed_tenant_settings --legal-name "Empresa 2 S.A." --trade-name "EMPRESA 2" --ruc 0000000000002 --domain empresa2.local --contact-email privacidad@empresa2.local --request-prefix E2
```
