# Servidor central de licencias

Servidor reutilizable para validar licencias de multiples aplicaciones Electron o desktop.
Cada licencia pertenece a un `appId`, por lo que una licencia emitida para una app no sirve para otra.

## Uso local

```bash
python license_server/server.py init
python license_server/server.py app --app-id afp-lookup --name "AFP Lookup"
python license_server/server.py create --app-id afp-lookup --label "Operaciones" --max-devices 3
python license_server/server.py serve --host 127.0.0.1 --port 8787
```

La app Electron se prueba contra este servidor con:

```bash
cd desktop
APP_ID=afp-lookup LICENSE_SERVER_URL=http://127.0.0.1:8787 npm run dev
```

## Revocar

```bash
python license_server/server.py revoke --app-id afp-lookup --token lic_TOKEN
```

## Ver estado

```bash
python license_server/server.py list --app-id afp-lookup
```

## Railway

El servidor puede desplegarse como servicio independiente desde esta carpeta:

```bash
cd license_server
railway up -y --name afp-license-server
railway domain --port 8080
railway add --database postgres
```

Variables esperadas en produccion:

- `DATABASE_URL=${{Postgres.DATABASE_URL}}`
- `DEFAULT_APP_ID=afp-lookup`
- `ADMIN_TOKEN=<token-largo-aleatorio>`

Postgres es la fuente de datos persistente. SQLite queda solo como fallback local para tests/desarrollo.

## Administracion HTTP

Los endpoints administrativos requieren:

```text
Authorization: Bearer <ADMIN_TOKEN>
```

Crear licencia:

```bash
curl -X POST "$LICENSE_SERVER_URL/admin/licenses" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"appId":"afp-lookup","label":"Operaciones","maxDevices":3}'
```

Listar licencias:

```bash
curl "$LICENSE_SERVER_URL/admin/licenses?appId=afp-lookup" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

Revocar licencia:

```bash
curl -X POST "$LICENSE_SERVER_URL/admin/licenses/revoke" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"appId":"afp-lookup","token":"lic_TOKEN"}'
```

Registrar una nueva aplicacion:

```bash
curl -X POST "$LICENSE_SERVER_URL/admin/apps" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"appId":"otra-app","name":"Otra App"}'
```

Validacion desde una app cliente:

```json
{
  "appId": "afp-lookup",
  "token": "lic_TOKEN",
  "deviceId": "hash-equipo",
  "appVersion": "0.1.0",
  "platform": "win32"
}
```

Para produccion, usar siempre HTTPS.
