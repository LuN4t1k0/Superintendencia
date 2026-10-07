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

## Firma Authenticode Windows

El instalador Windows se puede publicar sin firma, pero SmartScreen mostrara advertencias fuertes hasta que exista reputacion de editor. Para produccion usa un certificado Authenticode OV o EV emitido por una CA reconocida.

Flujo recomendado:

```bash
# Exportar el certificado a PFX desde Windows/macOS y convertirlo a base64
base64 -i certificado.pfx | pbcopy
```

Luego carga estos secrets en GitHub Actions:

- `WIN_CSC_LINK`: contenido base64 del `.pfx` o una URL privada al `.pfx`.
- `WIN_CSC_KEY_PASSWORD`: password del `.pfx`.

El workflow ya expone esos secrets a `electron-builder`. Cuando existen, `electron-builder` firma el instalador NSIS y los binarios Windows durante `npm run dist -- --win --publish always`.

Notas practicas:

- Un certificado EV suele reducir friccion de SmartScreen mas rapido, pero requiere token/hardware o proveedor compatible.
- Un certificado OV tambien firma correctamente, pero la reputacion de SmartScreen se construye con descargas/uso.
- Nunca commitear `.pfx`, passwords ni certificados privados al repo.

## Pendientes de credenciales

- GitHub Actions usa `GITHUB_TOKEN` para publicar releases.
- Windows queda firmado automaticamente cuando existan `WIN_CSC_LINK` y `WIN_CSC_KEY_PASSWORD`.

## CI/CD

El workflow `.github/workflows/desktop-release.yml` construye Windows cuando se publica un tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Secrets esperados:

- `LICENSE_SERVER_URL`
- `WIN_CSC_LINK` y `WIN_CSC_KEY_PASSWORD` cuando exista certificado de firma Windows.
