# Docker local por empresa

La misma imagen se ejecuta una vez por empresa. Cada proyecto Compose crea su
propia base PostgreSQL y sus propios volúmenes de archivos. No comparta archivos
`.env`, claves criptográficas, bases ni volúmenes entre empresas.

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

Copie el ejemplo a otro archivo, cambie todos los identificadores, secretos,
puerto y URL, y levante otro proyecto Compose:

```powershell
Copy-Item deploy/docker.env.example deploy/empresa2.env
docker compose --env-file deploy/empresa2.env -p gpc-lopdp-empresa2 up --build -d
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
