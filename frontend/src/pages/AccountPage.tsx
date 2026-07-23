import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { GraphView } from "../components/GraphView";
import { ErrorState, LoadingState } from "../components/QueryState";
import { RiskBadge } from "../components/RiskBadge";
import {
  getAccount,
  getAccountCounterparties,
  getAccountNetwork,
  getAccountRisk,
  getAccountTransactions,
  getCustomerFraudPath,
} from "../services/api";
import { formatCurrency, formatDate, maskAccountNumber } from "../utils/format";

export function AccountPage() {
  const { accountId = "" } = useParams();
  const [depth, setDepth] = useState(2);

  const account = useQuery({ queryKey: ["account", accountId], queryFn: () => getAccount(accountId) });
  const risk = useQuery({ queryKey: ["account-risk", accountId], queryFn: () => getAccountRisk(accountId) });
  const transactions = useQuery({
    queryKey: ["account-transactions", accountId],
    queryFn: () => getAccountTransactions(accountId, { limit: 20 }),
  });
  const network = useQuery({
    queryKey: ["account-network", accountId, depth],
    queryFn: () => getAccountNetwork(accountId, { depth, limit: 150 }),
  });
  const counterparties = useQuery({
    queryKey: ["account-counterparties", accountId],
    queryFn: () => getAccountCounterparties(accountId),
  });

  if (account.isLoading) return <LoadingState label="Loading account..." />;
  if (account.isError) return <ErrorState error={account.error} />;
  const a = account.data!;

  const owner = network.data?.nodes.find((n) => n.label === "Customer");
  const devices = network.data?.nodes.filter((n) => n.label === "Device") ?? [];
  const ips = network.data?.nodes.filter((n) => n.label === "IPAddress") ?? [];

  return (
    <div>
      <h1>
        Account {a.account_id} <RiskBadge level={a.risk_level} />
      </h1>

      <div className="grid grid-2">
        <div className="card">
          <h2>Account details</h2>
          <dl>
            <div className="inspector-row">
              <dt>Account number</dt>
              <dd>{maskAccountNumber(a.account_number)}</dd>
            </div>
            <div className="inspector-row">
              <dt>Type</dt>
              <dd>{a.account_type}</dd>
            </div>
            <div className="inspector-row">
              <dt>Status</dt>
              <dd>{a.status}</dd>
            </div>
            <div className="inspector-row">
              <dt>Balance</dt>
              <dd>{formatCurrency(a.balance, a.currency)}</dd>
            </div>
            <div className="inspector-row">
              <dt>Country</dt>
              <dd>{a.country}</dd>
            </div>
            {owner && (
              <div className="inspector-row">
                <dt>Owner</dt>
                <dd>
                  <Link className="link-id" to={`/customers/${owner.id}`}>
                    {owner.id}
                  </Link>
                </dd>
              </div>
            )}
          </dl>
        </div>

        <div className="card">
          <h2>Risk score & reasons</h2>
          {risk.isLoading ? (
            <LoadingState />
          ) : risk.isError ? (
            <ErrorState error={risk.error} />
          ) : (
            <>
              <p style={{ fontSize: "1.8rem", fontWeight: 700, margin: "0 0 0.25rem" }}>
                {risk.data!.risk_score} <RiskBadge level={risk.data!.risk_level} />
              </p>
              {risk.data!.reasons.length === 0 ? (
                <p className="muted">No fraud rules have flagged this account.</p>
              ) : (
                <ul style={{ paddingLeft: "1.1rem", margin: 0 }}>
                  {risk.data!.reasons.map((r) => (
                    <li key={r.rule_id} style={{ marginBottom: "0.4rem" }}>
                      <strong>
                        {r.rule_id} {r.rule_name}
                      </strong>{" "}
                      (+{r.score_contribution}) — {r.description}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      </div>

      <div className="card">
        <h2>Recent transactions</h2>
        {transactions.isLoading ? (
          <LoadingState />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Type</th>
                <th>Amount</th>
                <th>Timestamp</th>
                <th>Flagged</th>
              </tr>
            </thead>
            <tbody>
              {transactions.data?.items.map((t) => (
                <tr key={t.transaction_id}>
                  <td className="link-id">{t.transaction_id}</td>
                  <td>{t.transaction_type}</td>
                  <td>{formatCurrency(t.amount, t.currency)}</td>
                  <td>{formatDate(t.timestamp)}</td>
                  <td>{t.is_flagged ? "🚩" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="grid grid-2">
        <div className="card">
          <h2>Counterparties</h2>
          {counterparties.isLoading ? (
            <LoadingState />
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Transfers</th>
                  <th>Volume</th>
                </tr>
              </thead>
              <tbody>
                {(counterparties.data as Record<string, unknown>[] | undefined)?.map((c) => (
                  <tr key={String(c.counterparty_id)}>
                    <td>
                      <Link className="link-id" to={`/accounts/${c.counterparty_id}`}>
                        {String(c.counterparty_id)}
                      </Link>
                    </td>
                    <td>{String(c.outgoing_count)}</td>
                    <td>{formatCurrency(Number(c.outgoing_amount))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="card">
          <h2>Connected devices & IPs</h2>
          <p className="muted">From the current graph neighborhood (depth {depth}).</p>
          <strong>Devices</strong>
          <ul style={{ margin: "0.25rem 0 0.75rem", paddingLeft: "1.1rem" }}>
            {devices.length === 0 && <li className="muted">None in range</li>}
            {devices.map((d) => (
              <li key={d.id}>
                {d.id} {d.properties.is_emulator ? "· emulator" : ""} {d.properties.is_rooted ? "· rooted" : ""}
              </li>
            ))}
          </ul>
          <strong>IP addresses</strong>
          <ul style={{ margin: "0.25rem 0 0", paddingLeft: "1.1rem" }}>
            {ips.length === 0 && <li className="muted">None in range</li>}
            {ips.map((ip) => (
              <li key={ip.id}>
                {ip.id} {ip.properties.is_vpn ? "· VPN" : ""} {ip.properties.is_proxy ? "· proxy" : ""}
                {ip.properties.is_tor ? "· Tor" : ""}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="card">
        <div className="filters">
          <h2 style={{ marginBottom: 0 }}>Transaction network</h2>
          <label>
            Depth:{" "}
            <select value={depth} onChange={(e) => setDepth(Number(e.target.value))}>
              <option value={1}>1</option>
              <option value={2}>2</option>
              <option value={3}>3</option>
            </select>
          </label>
        </div>
        {network.isLoading ? (
          <LoadingState label="Building investigation subgraph..." />
        ) : network.isError ? (
          <ErrorState error={network.error} />
        ) : (
          <GraphView graph={network.data!} highlightNodeIds={[accountId]} />
        )}
      </div>

      <FraudPathCard accountId={accountId} customerId={owner?.id} />
    </div>
  );
}

function FraudPathCard({ customerId }: { accountId: string; customerId?: string }) {
  const path = useQuery({
    queryKey: ["fraud-path", customerId],
    queryFn: () => getCustomerFraudPath(customerId as string),
    enabled: Boolean(customerId),
    retry: false,
  });

  if (!customerId) return null;

  return (
    <div className="card">
      <h2>Shortest path to confirmed fraud</h2>
      {path.isLoading ? (
        <LoadingState />
      ) : path.isError ? (
        <p className="muted">No path to a confirmed fraud entity found within the search bound.</p>
      ) : (
        <p>
          <strong>{String((path.data as Record<string, unknown>)?.hops)}</strong> hop(s) from this account's owner to a
          confirmed fraud customer.
        </p>
      )}
    </div>
  );
}
