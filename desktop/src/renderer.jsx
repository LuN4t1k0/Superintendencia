import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  CloudDownload,
  Download,
  FileSpreadsheet,
  Play,
  RefreshCw,
  RotateCcw,
  Square,
  Upload,
  X
} from "lucide-react";
import "./styles.css";

const initialStats = {
  totalRows: 0,
  pendingRows: 0,
  processed: 0,
  found: 0,
  empty: 0,
  errors: 0,
  cacheHits: 0,
  remoteQueries: 0
};

function App() {
  const [filePath, setFilePath] = useState("");
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("Selecciona un Excel con una columna RUT.");
  const [logs, setLogs] = useState([]);
  const [stats, setStats] = useState(initialStats);
  const [settings, setSettings] = useState({ batchSize: 3, pauseSeconds: 1.5 });
  const [outputPath, setOutputPath] = useState("");
  const [appInfo, setAppInfo] = useState(null);
  const [updateState, setUpdateState] = useState({ type: "idle", message: "", percent: 0 });
  const [updateDismissed, setUpdateDismissed] = useState(false);

  const progress = useMemo(() => {
    if (!stats.pendingRows) {
      return 0;
    }
    return Math.min(100, Math.round((stats.processed / stats.pendingRows) * 100));
  }, [stats.pendingRows, stats.processed]);

  useEffect(() => {
    window.desktopApi.getAppInfo().then(setAppInfo).catch(() => {});
    return window.desktopApi.onUpdateEvent((event) => {
      setUpdateState((current) => ({
        ...current,
        ...event,
        percent: event.percent ?? current.percent ?? 0
      }));
      if (["available", "downloading", "downloaded", "error"].includes(event.type)) {
        setUpdateDismissed(false);
      }
    });
  }, []);

  useEffect(() => {
    return window.desktopApi.onProcessEvent((event) => {
      if (event.type === "ready") {
        setStats((current) => ({
          ...current,
          totalRows: event.totalRows,
          pendingRows: event.pendingRows
        }));
        setMessage(`${event.pendingRows} filas pendientes de ${event.totalRows} filas encontradas.`);
      }

      if (event.type === "progress") {
        setStats((current) => ({
          ...current,
          processed: event.processed,
          found: event.found,
          empty: event.empty,
          errors: event.errors,
          cacheHits: event.cacheHits,
          remoteQueries: event.remoteQueries
        }));
        setMessage(`Procesando fila ${event.processed} de ${event.pendingRows}: ${event.rut}`);
      }

      if (event.type === "log") {
        setLogs((current) => [event.message, ...current].slice(0, 80));
      }

      if (event.type === "done") {
        setStatus("done");
        setOutputPath(event.outputPath);
        setMessage("Consulta completa. Ya puedes guardar el Excel.");
      }

      if (event.type === "ip_limit") {
        setStatus("waiting_ip");
        setOutputPath(event.outputPath);
        setMessage(
          `Limite de ${event.batchLimit || 90} consultas alcanzado. Reinicia el router y verifica la nueva IP.`
        );
      }

      if (event.type === "ip_check") {
        setMessage(event.message);
      }

      if (event.type === "ip_changed") {
        setStatus("running");
        setMessage(event.message);
      }

      if (event.type === "blocked") {
        setStatus("error");
        setOutputPath(event.outputPath);
        setMessage(event.message);
      }

      if (event.type === "canceled") {
        setStatus("idle");
        if (event.outputPath) {
          setOutputPath(event.outputPath);
        }
        setMessage("Proceso detenido. Puedes guardar el avance.");
      }

      if (event.type === "error") {
        setStatus("error");
        setMessage(event.message);
      }

      if (event.type === "exit" && event.code !== 0 && status !== "error") {
        setStatus("error");
        setMessage("El proceso termino inesperadamente. Revisa el log.");
      }
    });
  }, [status]);

  async function selectFile() {
    const selected = await window.desktopApi.selectFile();
    if (!selected) {
      return;
    }
    setFilePath(selected);
    setStatus("idle");
    setOutputPath("");
    setStats(initialStats);
    setLogs([]);
    setMessage("Archivo listo para procesar.");
  }

  async function startProcess() {
    setStatus("running");
    setOutputPath("");
    setStats(initialStats);
    setLogs([]);
    setMessage("Iniciando motor Python...");

    const result = await window.desktopApi.startProcess({
      inputPath: filePath,
      batchSize: settings.batchSize,
      pauseSeconds: settings.pauseSeconds
    });

    if (!result.ok) {
      setStatus("error");
      setMessage(result.message);
    }
  }

  async function cancelProcess() {
    await window.desktopApi.cancelProcess();
    setStatus("idle");
    setMessage("Proceso detenido.");
  }

  async function verifyIp() {
    setMessage("Verificando la IP publica...");
    const result = await window.desktopApi.verifyIp();
    if (!result.ok) {
      setStatus("error");
      setMessage(result.message);
    }
  }

  async function saveResult() {
    const result = await window.desktopApi.saveResult(outputPath);
    if (result.ok) {
      setMessage(`Resultado guardado en ${result.filePath}`);
    }
  }

  async function checkForUpdates() {
    setUpdateDismissed(false);
    setUpdateState({ type: "checking", message: "Buscando actualizaciones...", percent: 0 });
    const result = await window.desktopApi.checkForUpdates();
    if (!result.ok) {
      setUpdateState({ type: "error", message: result.message, percent: 0 });
    }
  }

  async function downloadUpdate() {
    const result = await window.desktopApi.downloadUpdate();
    if (!result.ok) {
      setUpdateState((current) => ({ ...current, type: "error", message: result.message }));
    }
  }

  async function installUpdate() {
    const result = await window.desktopApi.installUpdate();
    if (!result.ok) {
      setUpdateState((current) => ({ ...current, type: "error", message: result.message }));
    }
  }

  function reset() {
    setStatus("idle");
    setOutputPath("");
    setStats(initialStats);
    setLogs([]);
    setMessage("Selecciona un Excel con una columna RUT.");
  }

  const isRunning = status === "running";
  const isWaitingForIp = status === "waiting_ip";
  const isProcessActive = isRunning || isWaitingForIp;
  const canStart = filePath && !isProcessActive;
  const canSave = outputPath && !isRunning;

  return (
    <main className="shell">
      <section className="topbar">
        <div>
          <p className="eyebrow">AFP Lookup</p>
          <h1>RPA Superintendencia</h1>
          <p className="version-line">
            Version {appInfo?.version || "..."}
          </p>
        </div>
        <div className="topbar-actions">
          {appInfo?.packaged && (
            <button
              className="update-check-button"
              type="button"
              onClick={checkForUpdates}
              disabled={updateState.type === "checking" || updateState.type === "downloading"}
            >
              <RefreshCw aria-hidden="true" />
              Buscar actualizacion
            </button>
          )}
          <div className={`status ${status}`}>{labelForStatus(status)}</div>
        </div>
      </section>

      {shouldShowUpdate(updateState, updateDismissed) && (
        <UpdateNotice
          update={updateState}
          processActive={isProcessActive}
          onDownload={downloadUpdate}
          onInstall={installUpdate}
          onDismiss={() => setUpdateDismissed(true)}
        />
      )}

      <section className="workflow">
        <div className="panel upload-panel">
          <div className="panel-heading">
            <FileSpreadsheet aria-hidden="true" />
            <div>
              <h2>Archivo Excel</h2>
              <p>{filePath ? filePath.split(/[\\/]/).pop() : "Ningun archivo seleccionado"}</p>
            </div>
          </div>
          <button
            className="secondary"
            type="button"
            onClick={selectFile}
            disabled={isProcessActive}
          >
            <Upload aria-hidden="true" />
            Seleccionar Excel
          </button>
        </div>

        <div className="panel settings-panel">
          <h2>Proceso</h2>
          <label>
            RUTs por ciclo
            <input
              type="number"
              min="1"
              max="10"
              value={settings.batchSize}
              disabled={isProcessActive}
              onChange={(event) =>
                setSettings((current) => ({ ...current, batchSize: Number(event.target.value) }))
              }
            />
          </label>
          <label>
            Pausa entre consultas
            <input
              type="number"
              min="0"
              max="5"
              step="0.25"
              value={settings.pauseSeconds}
              disabled={isProcessActive}
              onChange={(event) =>
                setSettings((current) => ({ ...current, pauseSeconds: Number(event.target.value) }))
              }
            />
          </label>
        </div>
      </section>

      <section className="actions">
        <button className="primary" type="button" onClick={startProcess} disabled={!canStart}>
          <Play aria-hidden="true" />
          Iniciar consulta
        </button>
        {isWaitingForIp && (
          <button className="primary" type="button" onClick={verifyIp}>
            Verificar nueva IP
          </button>
        )}
        <button
          className="secondary"
          type="button"
          onClick={cancelProcess}
          disabled={!isProcessActive}
        >
          <Square aria-hidden="true" />
          Detener
        </button>
        <button className="secondary" type="button" onClick={saveResult} disabled={!canSave}>
          <Download aria-hidden="true" />
          Guardar Excel
        </button>
        <button
          className="icon-button"
          type="button"
          onClick={reset}
          disabled={isProcessActive}
          title="Reiniciar"
        >
          <RotateCcw aria-hidden="true" />
        </button>
      </section>

      <section className="progress-section">
        <div className="progress-header">
          <span>{message}</span>
          <strong>{progress}%</strong>
        </div>
        <div className="progress-track">
          <div style={{ width: `${progress}%` }} />
        </div>
      </section>

      <section className="metrics">
        <Metric label="Filas" value={stats.totalRows} />
        <Metric label="Pendientes" value={stats.pendingRows} />
        <Metric label="Procesadas" value={stats.processed} />
        <Metric label="Encontrados" value={stats.found} />
        <Metric label="Sin datos" value={stats.empty} />
        <Metric label="Errores" value={stats.errors} />
        <Metric label="Cache" value={stats.cacheHits} />
        <Metric label="Consultas" value={stats.remoteQueries} />
      </section>

      <section className="log-panel">
        <h2>Log</h2>
        <div className="log-list">
          {logs.length === 0 ? (
            <p className="empty-log">Sin eventos registrados.</p>
          ) : (
            logs.map((line, index) => <p key={`${line}-${index}`}>{line}</p>)
          )}
        </div>
      </section>
    </main>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function UpdateNotice({ update, processActive, onDownload, onInstall, onDismiss }) {
  const isDownloading = update.type === "downloading";
  const isChecking = update.type === "checking";
  const isBusy = isDownloading || isChecking;
  const isReady = update.type === "downloaded";

  return (
    <section className={`update-notice ${update.type}`} aria-live="polite">
      <div className="update-icon">
        {isBusy ? (
          <RefreshCw className="spin" aria-hidden="true" />
        ) : (
          <CloudDownload aria-hidden="true" />
        )}
      </div>
      <div className="update-copy">
        <strong>{updateTitle(update)}</strong>
        <p>{update.message}</p>
        {isDownloading && (
          <div
            className="update-progress"
            aria-label={`Descarga ${Math.round(update.percent || 0)}%`}
          >
            <div style={{ width: `${Math.min(100, update.percent || 0)}%` }} />
          </div>
        )}
      </div>
      <div className="update-actions">
        {update.type === "available" && (
          <button className="primary" type="button" onClick={onDownload}>
            Descargar
          </button>
        )}
        {isReady && (
          <button className="primary" type="button" onClick={onInstall} disabled={processActive}>
            Reiniciar e instalar
          </button>
        )}
        {!isBusy && (
          <button className="icon-button" type="button" onClick={onDismiss} title="Ocultar aviso">
            <X aria-hidden="true" />
          </button>
        )}
      </div>
      {isReady && processActive && (
        <p className="update-process-warning">Termina o detiene el procesamiento para instalar.</p>
      )}
    </section>
  );
}

function shouldShowUpdate(update, dismissed) {
  if (dismissed) {
    return false;
  }
  return ["checking", "available", "downloading", "downloaded", "not-available", "error"].includes(
    update.type
  );
}

function updateTitle(update) {
  if (update.type === "checking") {
    return "Buscando actualizaciones";
  }
  if (update.type === "available") {
    return `Nueva version ${update.version || ""}`.trim();
  }
  if (update.type === "downloading") {
    return `Descargando ${Math.round(update.percent || 0)}%`;
  }
  if (update.type === "downloaded") {
    return "Actualizacion lista";
  }
  if (update.type === "not-available") {
    return "Aplicacion actualizada";
  }
  return "No se pudo actualizar";
}

function labelForStatus(status) {
  if (status === "running") {
    return "Procesando";
  }
  if (status === "done") {
    return "Listo";
  }
  if (status === "error") {
    return "Error";
  }
  if (status === "waiting_ip") {
    return "Esperando nueva IP";
  }
  return "Preparado";
}

createRoot(document.getElementById("root")).render(<App />);
