import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Download, FileSpreadsheet, Play, RotateCcw, Square, Upload } from "lucide-react";
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
  const [updateMessage, setUpdateMessage] = useState("");

  const progress = useMemo(() => {
    if (!stats.pendingRows) {
      return 0;
    }
    return Math.min(100, Math.round((stats.processed / stats.pendingRows) * 100));
  }, [stats.pendingRows, stats.processed]);

  useEffect(() => {
    window.desktopApi.getAppInfo().then(setAppInfo).catch(() => {});
    return window.desktopApi.onUpdateEvent((event) => {
      setUpdateMessage(event.message || "");
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
        setStatus("done");
        setOutputPath(event.outputPath);
        setMessage("Limite por IP alcanzado. Guarda el avance, cambia la IP y vuelve a procesar ese archivo.");
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

  async function saveResult() {
    const result = await window.desktopApi.saveResult(outputPath);
    if (result.ok) {
      setMessage(`Resultado guardado en ${result.filePath}`);
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
  const canStart = filePath && !isRunning;
  const canSave = outputPath && !isRunning;

  return (
    <main className="shell">
      <section className="topbar">
        <div>
          <p className="eyebrow">AFP Lookup</p>
          <h1>RPA Superintendencia</h1>
          <p className="version-line">
            Version {appInfo?.version || "..."}{updateMessage ? ` · ${updateMessage}` : ""}
          </p>
        </div>
        <div className={`status ${status}`}>{labelForStatus(status)}</div>
      </section>

      <section className="workflow">
        <div className="panel upload-panel">
          <div className="panel-heading">
            <FileSpreadsheet aria-hidden="true" />
            <div>
              <h2>Archivo Excel</h2>
              <p>{filePath ? filePath.split(/[\\/]/).pop() : "Ningun archivo seleccionado"}</p>
            </div>
          </div>
          <button className="secondary" type="button" onClick={selectFile} disabled={isRunning}>
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
              disabled={isRunning}
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
              disabled={isRunning}
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
        <button className="secondary" type="button" onClick={cancelProcess} disabled={!isRunning}>
          <Square aria-hidden="true" />
          Detener
        </button>
        <button className="secondary" type="button" onClick={saveResult} disabled={!canSave}>
          <Download aria-hidden="true" />
          Guardar Excel
        </button>
        <button className="icon-button" type="button" onClick={reset} disabled={isRunning} title="Reiniciar">
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
  return "Preparado";
}

createRoot(document.getElementById("root")).render(<App />);
