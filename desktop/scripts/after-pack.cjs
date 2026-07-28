"use strict";

const { flipFuses, FuseV1Options, FuseVersion } = require("@electron/fuses");
const path = require("node:path");

exports.default = async function afterPack(context) {
  const executableName = context.packager.appInfo.productFilename;
  const executablePath = process.platform === "darwin"
    ? path.join(
        context.appOutDir,
        `${executableName}.app`,
        "Contents",
        "MacOS",
        executableName,
      )
    : path.join(
        context.appOutDir,
        process.platform === "win32" ? `${executableName}.exe` : executableName,
      );

  await flipFuses(executablePath, {
    version: FuseVersion.V1,
    [FuseV1Options.RunAsNode]: false,
    [FuseV1Options.EnableCookieEncryption]: true,
    [FuseV1Options.EnableNodeOptionsEnvironmentVariable]: false,
    [FuseV1Options.EnableNodeCliInspectArguments]: false,
    [FuseV1Options.EnableEmbeddedAsarIntegrityValidation]: true,
    [FuseV1Options.OnlyLoadAppFromAsar]: true,
  });
};
