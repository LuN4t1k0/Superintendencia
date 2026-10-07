const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("licenseApi", {
  activate: (token) => ipcRenderer.invoke("license:activate", token)
});

contextBridge.exposeInMainWorld("desktopApi", {
  selectFile: () => ipcRenderer.invoke("file:select"),
  saveResult: (sourcePath) => ipcRenderer.invoke("file:saveResult", sourcePath),
  startProcess: (options) => ipcRenderer.invoke("process:start", options),
  cancelProcess: () => ipcRenderer.invoke("process:cancel"),
  onProcessEvent: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("process:event", listener);
    return () => ipcRenderer.removeListener("process:event", listener);
  }
});
