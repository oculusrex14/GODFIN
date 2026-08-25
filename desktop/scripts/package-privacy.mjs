import { readFile, stat } from "node:fs/promises";
import path from "node:path";

const forbiddenNames = new Set([
  "credentials.json",
  "gmail_credentials.json",
  "token.json",
  "token.pickle",
  "client_secret.json",
]);
const forbiddenExtensions = new Set([
  ".db",
  ".db3",
  ".sqlite",
  ".sqlite3",
  ".pdf",
  ".xls",
  ".xlsx",
  ".csv",
]);
const forbiddenPathParts = new Set([
  "backups",
  "statements",
  "private-fixtures",
]);

export async function assertPackagePrivacy(
  files,
  {
    forbiddenMarkers = process.env.GODFIN_FORBIDDEN_ACCOUNT_ENDINGS
      ?.split(",")
      .map((value) => value.trim())
      .filter(Boolean) || [],
  } = {},
) {
  const pathViolations = [];
  for (const file of files) {
    const normalized = file.split(path.sep).map((part) => part.toLowerCase());
    const basename = path.basename(file).toLowerCase();
    const isKnownDependencyAsset = normalized.join("/").includes(
      "_internal/matplotlib/mpl-data/",
    );
    if (
      forbiddenNames.has(basename)
      || (
        forbiddenExtensions.has(path.extname(basename))
        && !isKnownDependencyAsset
      )
      || normalized.some((part) => forbiddenPathParts.has(part))
    ) {
      pathViolations.push(file);
    }
  }
  if (pathViolations.length) {
    throw new Error(
      `Package privacy check found ${pathViolations.length} forbidden data file(s).`,
    );
  }

  if (!forbiddenMarkers.length) return;
  for (const file of files) {
    const fileStats = await stat(file);
    if (!fileStats.isFile()) continue;
    const content = await readFile(file);
    if (
      forbiddenMarkers.some((marker) =>
        content.includes(Buffer.from(marker, "utf8"))
      )
    ) {
      throw new Error(
        "Package privacy check found a forbidden private account marker.",
      );
    }
  }
}
