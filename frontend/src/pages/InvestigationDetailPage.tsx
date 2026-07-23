import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { GraphView } from "../components/GraphView";
import { ErrorState, LoadingState } from "../components/QueryState";
import { getInvestigation, getInvestigationGraph, updateInvestigation } from "../services/api";
import { formatDate } from "../utils/format";

const STATUSES = ["OPEN", "IN_REVIEW", "ESCALATED", "RESOLVED", "FALSE_POSITIVE"];

export function InvestigationDetailPage() {
  const { caseId = "" } = useParams();
  const queryClient = useQueryClient();

  const caseQuery = useQuery({ queryKey: ["investigation", caseId], queryFn: () => getInvestigation(caseId) });
  const graphQuery = useQuery({ queryKey: ["investigation-graph", caseId], queryFn: () => getInvestigationGraph(caseId) });

  async function handleStatusChange(status: string) {
    await updateInvestigation(caseId, { status });
    await queryClient.invalidateQueries({ queryKey: ["investigation", caseId] });
  }

  if (caseQuery.isLoading) return <LoadingState label="Loading case..." />;
  if (caseQuery.isError) return <ErrorState error={caseQuery.error} />;
  const c = caseQuery.data!;

  return (
    <div>
      <h1>{c.title}</h1>
      <div className="card">
        <dl>
          <div className="inspector-row">
            <dt>Case ID</dt>
            <dd>{c.case_id}</dd>
          </div>
          <div className="inspector-row">
            <dt>Description</dt>
            <dd>{c.description || "-"}</dd>
          </div>
          <div className="inspector-row">
            <dt>Priority</dt>
            <dd>{c.priority}</dd>
          </div>
          <div className="inspector-row">
            <dt>Assigned to</dt>
            <dd>{c.assigned_to}</dd>
          </div>
          <div className="inspector-row">
            <dt>Created</dt>
            <dd>{formatDate(c.created_at)}</dd>
          </div>
          <div className="inspector-row">
            <dt>Updated</dt>
            <dd>{formatDate(c.updated_at)}</dd>
          </div>
        </dl>
        <div className="filters">
          <label>
            Status:{" "}
            <select value={c.status} onChange={(e) => handleStatusChange(e.target.value)}>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <div className="card">
        <h2>Case graph</h2>
        {graphQuery.isLoading ? (
          <LoadingState />
        ) : graphQuery.isError ? (
          <ErrorState error={graphQuery.error} />
        ) : (
          <GraphView graph={graphQuery.data!} />
        )}
      </div>
    </div>
  );
}
