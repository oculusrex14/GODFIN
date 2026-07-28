"use client";

import { Apple, Laptop, MonitorDown } from "lucide-react";
import { useEffect, useState } from "react";

import { trackAnalytics } from "@/components/privacy-analytics";

type OperatingSystem = "mac" | "windows" | "linux";

const downloads: Array<{
  id: OperatingSystem;
  name: string;
  label: string;
  env: string | undefined;
  icon: typeof Apple;
}> = [
  {
    id: "mac",
    name: "macOS",
    label: "Apple silicon + Intel",
    env: process.env.NEXT_PUBLIC_MAC_DOWNLOAD_URL,
    icon: Apple,
  },
  {
    id: "windows",
    name: "Windows",
    label: "Windows 10 or newer",
    env: process.env.NEXT_PUBLIC_WINDOWS_DOWNLOAD_URL,
    icon: MonitorDown,
  },
  {
    id: "linux",
    name: "Linux",
    label: "AppImage",
    env: process.env.NEXT_PUBLIC_LINUX_DOWNLOAD_URL,
    icon: Laptop,
  },
];

function detectOperatingSystem(): OperatingSystem {
  const value = navigator.userAgent.toLowerCase();
  if (value.includes("win")) return "windows";
  if (value.includes("linux")) return "linux";
  return "mac";
}

export function DownloadChooser() {
  const [detected, setDetected] = useState<OperatingSystem>("mac");

  useEffect(() => {
    setDetected(detectOperatingSystem());
  }, []);

  const primary = downloads.find((download) => download.id === detected)!;

  return (
    <div className="download-panel">
      <div className="download-card">
        <primary.icon size={30} color="#c9f36b" />
        <h2 style={{ marginTop: 24 }}>GODFIN for {primary.name}</h2>
        <p>
          Version {process.env.NEXT_PUBLIC_APP_VERSION || "0.1.0"} ·{" "}
          {primary.label}. The app runs locally and creates its database on your
          device.
        </p>
        {primary.env ? (
          <a
            className="button"
            href={primary.env}
            onClick={() => trackAnalytics("download", {
              platform: primary.id,
              placement: "primary",
            })}
          >
            Download for {primary.name}
          </a>
        ) : (
          <button className="button" disabled>
            Signed build coming with v1.0
          </button>
        )}
      </div>
      <div>
        <h3>Other platforms</h3>
        <div className="os-list">
          {downloads.map(({ id, name, label, env, icon: Icon }) => (
            <a
              aria-disabled={!env}
              className={`os-item${id === detected ? " detected" : ""}`}
              href={env || undefined}
              onClick={() => {
                if (env) {
                  trackAnalytics("download", {
                    platform: id,
                    placement: "other_platforms",
                  });
                }
              }}
              key={id}
            >
              <Icon size={20} />
              <strong>{name}</strong>
              <span>{env ? label : "Not released"}</span>
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}
