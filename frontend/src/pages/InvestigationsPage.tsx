import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { ErrorState, LoadingState } from "../components/QueryState";
import { createInvestigation, listInvestigations } from "../services/api";
import { formatDate } from "../utils/format";

export function InvestigationsPage() {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const queryClient = useQueryClient();

  const cases = useQuery({ queryKey: ["investigations"], queryFn: () => listInvestigations({ limit: 25 }) });

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setCreating(true);
    try {
      await createInvestigation({ title, description });
      setTitle("");
      setDescription("");
      await queryClient.invalidateQueries({ queryKey: ["investigations"] });
    } finally {
      setCreating(false);
    }
  }

  return (
    <div>
      <h1>Investigations</h1>

      <div className="card">
        <h2>New investigation case</h2>
        <form onSubmit={handleCreate} style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <input
            style={{ flex: "1 1 240px", padding: "0.5rem", borderRadius: 6, border: "1px solid #cbd5e1" }}
            placeholder="Case title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <input
            style={{ flex: "2 1 320px", padding: "0.5rem", borderRadius: 6, border: "1px solid #cbd5e1" }}
            placeholder="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <button type="submit" className="btn" disabled={creating}>
            {creating ? "Creating..." : "Create case"}
          </button>
        </form>
      </div>

      <div className="card">
        {cases.isLoading ? (
          <LoadingState />
        ) : cases.isError ? (
          <ErrorState error={cases.error} />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Case</th>
                <th>Title</th>
                <th>Status</th>
                <th>Priority</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {cases.data?.items.map((c) => (
                <tr key={c.case_id}>
                  <td>
                    <Link className="link-id" to={`/investigations/${c.case_id}`}>
                      {c.case_id}
                    </Link>
                  </td>
                  <td>{c.title}</td>
                  <td>{c.status}</td>
                  <td>{c.priority}</td>
                  <td>{formatDate(c.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
