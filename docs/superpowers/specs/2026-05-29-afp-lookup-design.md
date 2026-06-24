# AFP Affiliation Lookup — Design Spec
**Date:** 2026-05-29
**Status:** Approved

## Overview

A standalone tool that automatiza la consulta de afiliación AFP en la Superintendencia de Pensiones (spensiones.cl). El usuario sube un Excel con RUTs, la app consulta cada RUT uno a uno y devuelve el mismo Excel con la columna **AFP 2** completada.

Proyecto completamente independiente de previred — directorio propio, repo propio, deploy propio.

## User Experience (3 pasos)

**Paso 1 — Subir archivo**
- El usuario sube el Excel (.xlsx)
- La app detecta automáticamente la columna de RUTs y muestra cuántos encontró
- Botón "▶ Iniciar consulta" para comenzar

**Paso 2 — Procesando**
- Barra de progreso en tiempo real: `X / N RUTs consultados`
- Estimación de tiempo restante
- Los resultados van apareciendo a medida que se procesan
- ~2 segundos por RUT → 100 RUTs ≈ 3-4 minutos

**Paso 3 — Descargar**
- Botón para descargar el Excel con columna AFP 2 completada
- Resumen: cuántos OK, cuántos sin datos, cuántos con error
- Botón "↩ Nueva consulta" para reiniciar

**Resultados posibles por RUT:**
- AFP encontrada → nombre de la AFP (ej. `HABITAT`, `CAPITAL`, `CUPRUM`)
- RUT no encontrado → `SIN DATOS`
- Error de red → `ERROR`

## Architecture

Proyecto en `~/Documents/desarrollo/SuperIntendencia/`:

```
SuperIntendencia/
  app.py                        ← Streamlit UI, 3 pasos
  bot/
    __init__.py
    scraper.py                  ← Playwright: consulta spensiones.cl, extrae AFP
    excel.py                    ← openpyxl: lee RUTs, escribe AFP 2
  requirements.txt
  tests/
    test_scraper.py
    test_excel.py
  docs/
    superpowers/
      specs/                    ← este archivo
      plans/                    ← plan de implementación (próximo paso)
```

## Module Responsibilities

### `bot/scraper.py`

- Abre **una sola instancia de browser** al inicio y la reutiliza para todas las consultas
- `normalize_rut(rut: str) -> str` — elimina puntos y guión: `"15.800.185-3"` o `"15800185-3"` → `"158001853"`
- `extract_afp(text: str) -> str | None` — parsea el texto de resultado buscando el patrón `"incorporado(a) a AFP XXXX"` con regex; retorna solo el nombre sin prefijo (ej. `"HABITAT"`, no `"AFP HABITAT"`)
- `query_rut(page, rut: str) -> str` — llena el formulario, hace click en Buscar, espera resultado, retorna nombre AFP o `"SIN DATOS"` / `"ERROR"`
- Pausa de **1.5 segundos** entre consultas para no saturar el servidor
- Retry automático una vez si hay error de red

### `bot/excel.py`

- `read_ruts(file_bytes) -> tuple[Workbook, int, list[int]]` — carga el Excel, detecta la columna RUT (busca el primer header que contenga "rut" case-insensitive), retorna el workbook, el índice de columna RUT, y las filas con datos
- `write_afp(ws, row: int, col_afp2: int, value: str)` — escribe el valor en la columna AFP 2 de la fila indicada
- `find_or_create_afp2_column(ws) -> int` — busca columna "AFP 2" en el header; si no existe, la crea al final
- `to_bytes(wb) -> bytes` — serializa el workbook a bytes para descarga en Streamlit sin guardar en disco

### `app.py`

- Procesa RUTs secuencialmente en el hilo principal de Streamlit
- Usa `st.session_state` para mantener el progreso entre reruns
- El browser Playwright se abre al iniciar el paso 2 y se cierra al terminar (paso 3)
- Sin threading complejo — el procesamiento bloquea el servidor Streamlit por usuario (aceptable para 1-2 usuarios simultáneos)

## RUT Format

- El Excel trae RUTs en formato `15800185-3` (con guión, sin puntos)
- El sitio spensiones.cl espera `158001853` (sin puntos ni guión)
- `normalize_rut` maneja ambos formatos: con o sin puntos, con o sin guión

## Rate Limiting & Restrictions

- Probado: el reCAPTCHA visible es v3 (invisible badge) — **no bloquea la automatización**
- Pausa de 1.5 segundos entre consultas como buena práctica
- No se detectaron restricciones de rate limiting en pruebas manuales
- Si el sitio bloquea en el futuro: aumentar la pausa a 3-5 segundos

## Distribution

Mismo patrón que previred:

- **Railway:** deploy web con su propia URL para acceso desde browser
- **Windows launcher:** `SuperIntendencia-launcher/` — mismo mecanismo que `previred-launcher`, genera `SuperIntendencia.exe`
- **GitHub Actions:** workflow que construye el `.exe` en runner Windows sin necesitar máquina Windows
- **Descarga:** página de bienvenida (paso 0) con botón de descarga del `.exe` + opción "Continuar en navegador"

El launcher es un proyecto separado que se implementa después de que la app esté funcionando.

## Out of Scope

- Procesamiento paralelo de RUTs (implementar si los volúmenes superan 500+)
- Soporte para otros formatos de entrada (CSV, texto plano)
- Historial de consultas previas
- El launcher Windows (segunda fase, después de validar la app)
