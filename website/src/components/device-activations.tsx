"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

type Activation = {
  id: string;
  license_id: string;
  device_label: string | null;
  app_version: string | null;
  activated_at: string;
  last_seen_at: string;
};

export function DeviceActivations({
  activations,
  licenseNames,
}: {
  activations: Activation[];
  licenseNames: Record<string, string>;
}) {
  const router = useRouter();
  const [pendingId, setPendingId] = useState("");
  const [error, setError] = useState("");

  async function deactivate(id: string) {
    if (!window.confirm("Deactivate this GODFIN installation? Local finance data will not be deleted.")) {
      return;
    }
    setPendingId(id);
    setError("");
    try {
      const response = await fetch(`/api/license/activations/${id}`, {
        method: "DELETE",
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.message || "Could not deactivate device.");
      router.refresh();
    } catch (deactivationError) {
      setError(
        deactivationError instanceof Error
          ? deactivationError.message
          : "Could not deactivate device.",
      );
    } finally {
      setPendingId("");
    }
  }

  return (
    <section className="account-card" style={{ marginTop: 22 }}>
      <h2>Active devices</h2>
      <p className="lead">
        Each paid lifetime license supports three active installations. Device
        names contain only operating-system and architecture information.
      </p>
      {activations.length ? (
        activations.map((activation) => (
          <div className="device-row" key={activation.id}>
            <div>
              <strong>{activation.device_label || "GODFIN device"}</strong>
              <div className="device-meta">
                {licenseNames[activation.license_id] || "Paid license"} · app{" "}
                {activation.app_version || "unknown"} · last verified{" "}
                {new Date(activation.last_seen_at).toLocaleDateString("en-IN")}
              </div>
            </div>
            <button
              className="button-ghost"
              disabled={pendingId === activation.id}
              onClick={() => deactivate(activation.id)}
              type="button"
            >
              {pendingId === activation.id ? "Deactivating…" : "Deactivate"}
            </button>
          </div>
        ))
      ) : (
        <p className="lead">No active paid installations.</p>
      )}
      {error ? <p className="form-message error">{error}</p> : null}
    </section>
  );
}
