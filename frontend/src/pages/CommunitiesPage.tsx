import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { ErrorState, LoadingState } from "../components/QueryState";
import { getCommunities } from "../services/api";

export function CommunitiesPage() {
  const [minSize, setMinSize] = useState(5);

  const communities = useQuery({
    queryKey: ["communities", minSize],
    queryFn: () => getCommunities({ min_size: minSize, limit: 25 }),
  });

  return (
    <div>
      <h1>Fraud Communities</h1>
      <p className="muted">
        Louvain communities (see Graph Data Science pipeline) that contain at least one confirmed-fraud account.
        Membership alone is not proof of fraud -- open a member in the Graph Explorer to investigate.
      </p>

      <div className="filters">
        <label>
          Minimum community size:{" "}
          <input type="number" min={2} value={minSize} onChange={(e) => setMinSize(Number(e.target.value) || 2)} />
        </label>
      </div>

      <div className="card">
        {communities.isLoading ? (
          <LoadingState />
        ) : communities.isError ? (
          <ErrorState error={communities.error} />
        ) : communities.data && communities.data.length > 0 ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>Community</th>
                <th>Accounts</th>
                <th>Confirmed-fraud members</th>
                <th>Open in explorer</th>
              </tr>
            </thead>
            <tbody>
              {communities.data.map((c) => (
                <tr key={c.community_id}>
                  <td>#{c.community_id}</td>
                  <td>{c.member_count}</td>
                  <td>{c.critical_member_count}</td>
                  <td>
                    {c.account_ids[0] && (
                      <Link className="link-id" to={`/accounts/${c.account_ids[0]}`}>
                        {c.account_ids[0]} &rarr;
                      </Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">
            No suspicious communities found at this size threshold. Run <code>make analyze-graph</code> (Louvain
            community detection) and <code>make detect-fraud</code> if this looks wrong.
          </p>
        )}
      </div>
    </div>
  );
}
