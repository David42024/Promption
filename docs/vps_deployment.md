# Despliegue en incuovh

Promption utiliza el clon `/home/incutiicito/Promption` y servicios systemd del
usuario `incutiicito`. La web escucha en `127.0.0.1:3100`, el filtro en
`127.0.0.1:8100` y el chat en `127.0.0.1:8101`. Las conversaciones y el estado
de seguridad se guardan en SQLite bajo `~/.local/share/promption`.

## Preparación

1. Instalar uv desde su [sitio oficial](https://docs.astral.sh/uv/getting-started/installation/).
2. En la raíz del clon: `uv venv --python 3.13 .venv` y
   `uv pip install --python .venv/bin/python -r requirements-api.txt`.
3. En `chat-service`: `uv pip install --python ../.venv/bin/python -r requirements.txt`.
4. Crear `~/.config/promption` con permisos 700. Usar las tres secciones de
   `deploy/production.env.example` en `filter.env`, `chat.env` y `web.env`,
   con permisos 600 y claves reales diferentes. El token interno y las claves
   compartidas deben coincidir entre los servicios correspondientes.
5. En `packages/ai-sdk`: `npm ci --no-audit --no-fund` para resolver los
   peers de la librería enlazada. En `demo`: `npm ci --no-audit --no-fund`, cargar `web.env` en el entorno
   y ejecutar `npm run build`. Para los archivos generados durante este
   despliegue se puede cargar con `set -a; . ~/.config/promption/web.env; set +a`.
6. Ejecutar `bash deploy/install-user-services.sh` desde la raíz del clon.

## Publicación

En Cloudflare, crear el registro A `promption` hacia `148.113.236.79` con
**proxy activado** y HTTPS **Full (strict)** para ese hostname. Si hace falta
ajustar el modo, usar una [Configuration Rule de Cloudflare](https://developers.cloudflare.com/rules/configuration-rules/settings/)
que coincida únicamente con `promption.incubunt.com`, para conservar el modo
de los otros sitios. El certificado de origen existente
incluye `*.incubunt.com`; solo se utiliza desde el nuevo sitio, sin sustituirlo.
Este certificado no es válido para navegadores que se conectan directamente
al VPS sin Cloudflare.

Una vez preparados y comprobados los servicios, ejecutar:

```bash
sudo bash /home/incutiicito/Promption/deploy/activate-nginx.sh
```

El script crea únicamente el sitio `promption.incubunt.com`, comprueba nginx,
recarga su configuración y habilita la permanencia de los servicios del
usuario tras cerrar SSH. Si la validación falla, retira el sitio recién creado.
Si el sitio ya existe, se detiene para evitar reemplazar una configuración.
Los puentes `/api/ai/` solo están disponibles por la conexión interna local.

## Operación

```bash
systemctl --user status promption-{filter,chat,web}
journalctl --user -u promption-chat -n 100 --no-pager
systemctl --user restart promption-filter promption-chat promption-web
curl --fail http://127.0.0.1:8100/api/v1/health
curl --fail http://127.0.0.1:8101/health
.venv/bin/python deploy/verify-local.py
```

`deploy/verify-local.py --restart-check` comprueba además que el historial
sobrevive al reinicio del servicio de chat. Las comprobaciones no consultan
OpenAI ni otros proveedores de modelos; crean conversaciones demo locales.

Para actualizar: comprobar cambios locales, actualizar el clon, instalar sus
dependencias, reconstruir `demo` con `web.env` cargado y reiniciar exclusivamente
los tres servicios de Promption. No ejecutar comandos generales para detener
Docker ni modificar `incubunt_web_backend.service` o el sitio nginx `default`.
Respaldar `~/.config/promption`, `~/.local/share/promption` y los archivos de
configuración y modelos antes de una actualización. Los respaldos contienen
secretos y deben conservarse con permisos privados.

El dashboard académico escucha en `127.0.0.1:8510`; no se expone públicamente.
Para habilitarlo, instalar `requirements-dashboard.txt`, copiar `filter.env` a
`dashboard.env` con permisos 600 y ejecutar nuevamente el instalador de
servicios. Se abre mediante un túnel SSH:

```bash
ssh -L 8510:127.0.0.1:8510 incuovh
```

Abrir `http://localhost:8510` mientras esa conexión esté abierta. Su servicio
es `promption-dashboard`; utiliza el mismo entorno Python aislado.

Para retirar únicamente la publicación de Promption:

```bash
sudo rm /etc/nginx/sites-enabled/promption.incubunt.com
sudo nginx -t && sudo systemctl reload nginx
systemctl --user disable --now promption-filter promption-chat promption-web promption-dashboard
```

No eliminar la base SQLite ni los secretos al retirar la publicación.
