"use strict";

const { flipFuses, FuseV1Options, FuseVersion } = require("@electron/fuses");
const path = require("node:path");

exports.default = async function afterPack(context) {
  const platform = context.electronPlatformName;
  const executableName = platform === "linux"
    ? context.packager.executableName
    : context.packager.appInfo.productFilename;
  const executablePath = platform === "darwin"
    ? path.join(
        context.appOutDir,
        `${executableName}.app`,
        "Contents",
        "MacOS",
        executableName,
      )
    : path.join(
        context.appOutDir,
        platform === "win32" ? `${executableName}.exe` : executableName,
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
