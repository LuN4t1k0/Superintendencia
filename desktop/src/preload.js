const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("licenseApi", {
  activate: (token) => ipcRenderer.invoke("license:activate", token)
});

contextBridge.exposeInMainWorld("desktopApi", {
  getAppInfo: () => ipcRenderer.invoke("app:getInfo"),
  selectFile: () => ipcRenderer.invoke("file:select"),
  saveResult: (sourcePath) => ipcRenderer.invoke("file:saveResult", sourcePath),
  startProcess: (options) => ipcRenderer.invoke("process:start", options),
  cancelProcess: () => ipcRenderer.invoke("process:cancel"),
  onUpdateEvent: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("update:event", listener);
    return () => ipcRenderer.removeListener("update:event", listener);
  },
  onProcessEvent: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("process:event", listener);
    return () => ipcRenderer.removeListener("process:event", listener);
  }
});
