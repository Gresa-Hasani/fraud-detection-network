import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { ErrorState, LoadingState } from "../components/QueryState";
import { RiskBadge } from "../components/RiskBadge";
import { listFraudAlerts, runDetection } from "../services/api";
import { formatDate } from "../utils/format";

export function FraudAlertsPage() {
  const [severity, setSeverity] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const limit = 20;
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<Record<string, unknown> | null>(null);

  const alerts = useQuery({
    queryKey: ["fraud-alerts", severity, status, offset],
    queryFn: () =>
      listFraudAlerts({
        limit,
        offset,
        severity: severity || undefined,
        status: status || undefined,
      }),
  });

  async function handleRunDetection() {
    setRunning(true);
    try {
      const result = await runDetection();
      setRunResult(result);
      await alerts.refetch();
    } finally {
      setRunning(false);
    }
  }

  return (
    <div>
      <h1>Fraud Alerts</h1>

      <div className="filters">
        <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
          <option value="">All severities</option>
          <option value="LOW">LOW</option>
          <option value="MEDIUM">MEDIUM</option>
          <option value="HIGH">HIGH</option>
          <option value="CRITICAL">CRITICAL</option>
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          <option value="OPEN">OPEN</option>
          <option value="IN_REVIEW">IN_REVIEW</option>
          <option value="RESOLVED">RESOLVED</option>
          <option value="FALSE_POSITIVE">FALSE_POSITIVE</option>
        </select>
        <button type="button" className="btn" onClick={handleRunDetection} disabled={running}>
          {running ? "Running detection..." : "Run detection now"}
        </button>
      </div>

      {runResult && (
        <div className="card">
          <strong>Detection run complete:</strong> {String(runResult.total_signals)} signals,{" "}
          {String(runResult.alerts_created)} new alerts, {String(runResult.entities_scored)} entities scored (
          {String(runResult.duration_seconds)}s).
        </div>
      )}

      <div className="card">
        {alerts.isLoading ? (
          <LoadingState />
        ) : alerts.isError ? (
          <ErrorState error={alerts.error} />
        ) : (
          <>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Alert ID</th>
                  <th>Rule</th>
                  <th>Entity</th>
                  <th>Severity</th>
                  <th>Score</th>
                  <th>Status</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {alerts.data?.items.map((alert) => {
                  const entity = alert.entity as Record<string, unknown> | undefined;
                  const entityId = entity
                    ? (entity.account_id ?? entity.customer_id ?? entity.device_id ?? entity.ip)
                    : undefined;
                  const entityLabel = alert.entity_labels?.[0];
                  return (
                    <tr key={alert.alert_id}>
                      <td className="link-id">{alert.alert_id}</td>
                      <td>{alert.rule_id}</td>
                      <td>
                        {entityLabel === "Account" && entityId ? (
                          <Link className="link-id" to={`/accounts/${entityId}`}>
                            {String(entityId)}
                          </Link>
                        ) : entityLabel === "Customer" && entityId ? (
                          <Link className="link-id" to={`/customers/${entityId}`}>
                            {String(entityId)}
                          </Link>
                        ) : (
                          <span>{String(entityId ?? "-")}</span>
                        )}
                      </td>
                      <td>
                        <RiskBadge level={alert.severity} />
                      </td>
                      <td>{alert.score}</td>
                      <td>{alert.status}</td>
                      <td>{formatDate(alert.created_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="filters" style={{ marginTop: "0.75rem" }}>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - limit))}
              >
                Previous
              </button>
              <span className="muted">
                Showing {offset + 1}–{offset + (alerts.data?.items.length ?? 0)}
              </span>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={(alerts.data?.items.length ?? 0) < limit}
                onClick={() => setOffset(offset + limit)}
              >
                Next
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
