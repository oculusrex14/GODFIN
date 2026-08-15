"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("godfinDesktop", Object.freeze({
  restoreBackup: (restoreToken) => ipcRenderer.invoke(
    "godfin:restore-backup",
    restoreToken,
  ),
}));
