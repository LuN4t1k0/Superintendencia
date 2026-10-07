# AFP Lookup Desktop

Cliente Electron para uso interno. La app valida una licencia, muestra una interfaz React y ejecuta un motor Python interno para consultar y completar el Excel.

## Desarrollo

```bash
cd desktop
npm install
PYTHON_BIN=../.venv/bin/python npm run dev
```

Si `python3` no apunta al entorno correcto, usa:

```bash
PYTHON_BIN=/ruta/a/python npm run dev
```

## Licencias internas

Configura el endpoint con:

```bash
APP_ID=afp-lookup
LICENSE_SERVER_URL=https://licencias.interno.ejemplo
```

Electron llamara:

```text
POST /licenses/validate
```

Payload:

```json
{
  "appId": "afp-lookup",
  "token": "licencia-ingresada",
  "deviceId": "hash-del-equipo",
  "appVersion": "0.1.0",
  "platform": "darwin"
}
```

Respuesta esperada:

```json
{
  "valid": true,
  "company": "Empresa Interna",
  "user": "usuario@empresa.cl"
}
```

Si el servidor rechaza o revoca la licencia, debe responder `valid: false` o un status HTTP no exitoso. La app permite operar offline por `LICENSE_OFFLINE_GRACE_DAYS` dias desde la ultima validacion correcta.

## Distribucion

```bash
npm run dist
```

Antes de empaquetar, el script `prepare:runtime` crea `desktop/python-runtime` e instala Chromium en `desktop/ms-playwright`. Esos directorios se incluyen como recursos de Electron para que la app no dependa del Python instalado por el usuario.

Para updates reales, publicar releases versionados en GitHub y firmar los binarios de macOS/Windows. En produccion no conviene distribuir builds sin firma.

## Build local

```bash
npm run prepare:runtime
npm run pack
```

El build final queda en `desktop/dist/`.

`npm run pack` y `npm run dist` generan `src/config.generated.json` desde las variables de entorno. En produccion define `LICENSE_SERVER_URL` y `APP_ID` antes de construir para que la app empaquetada sepa donde validar licencias.

## Pendientes de credenciales Windows

- Windows: certificado de firma Authenticode.
- Updates: GitHub Actions usa `GITHUB_TOKEN` para publicar releases.

## CI/CD

El workflow `.github/workflows/desktop-release.yml` construye Windows cuando se publica un tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Secrets esperados:

- `LICENSE_SERVER_URL`
- `WIN_CSC_LINK` y `WIN_CSC_KEY_PASSWORD` cuando exista certificado de firma Windows.
