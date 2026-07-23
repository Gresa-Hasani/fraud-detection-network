import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { GraphView } from "../components/GraphView";
import { ErrorState, LoadingState } from "../components/QueryState";
import { RiskBadge } from "../components/RiskBadge";
import {
  getAccountNetwork,
  getCustomer,
  getCustomerAccounts,
  getCustomerConnections,
  getCustomerDevices,
  getCustomerFraudPath,
} from "../services/api";
import { formatDate } from "../utils/format";

export function CustomerPage() {
  const { customerId = "" } = useParams();

  const customer = useQuery({ queryKey: ["customer", customerId], queryFn: () => getCustomer(customerId) });
  const accounts = useQuery({ queryKey: ["customer-accounts", customerId], queryFn: () => getCustomerAccounts(customerId) });
  const devices = useQuery({ queryKey: ["customer-devices", customerId], queryFn: () => getCustomerDevices(customerId) });
  const connections = useQuery({
    queryKey: ["customer-connections", customerId],
    queryFn: () => getCustomerConnections(customerId),
  });
  const fraudPath = useQuery({
    queryKey: ["customer-fraud-path", customerId],
    queryFn: () => getCustomerFraudPath(customerId),
    retry: false,
  });

  const firstAccountId = accounts.data?.[0]?.account_id;
  const network = useQuery({
    queryKey: ["customer-network", firstAccountId],
    queryFn: () => getAccountNetwork(firstAccountId as string, { depth: 2, limit: 150 }),
    enabled: Boolean(firstAccountId),
  });

  if (customer.isLoading) return <LoadingState label="Loading customer..." />;
  if (customer.isError) return <ErrorState error={customer.error} />;
  const c = customer.data!;

  return (
    <div>
      <h1>
        {c.full_name} <RiskBadge level={c.fraud_status === "CLEAR" ? "LOW" : c.fraud_status === "CONFIRMED_FRAUD" ? "CRITICAL" : "MEDIUM"} />
      </h1>

      <div className="grid grid-2">
        <div className="card">
          <h2>Customer profile</h2>
          <dl>
            <div className="inspector-row">
              <dt>Customer ID</dt>
              <dd>{c.customer_id}</dd>
            </div>
            <div className="inspector-row">
              <dt>Email</dt>
              <dd>{c.email}</dd>
            </div>
            <div className="inspector-row">
              <dt>Phone</dt>
              <dd>{c.phone}</dd>
            </div>
            <div className="inspector-row">
              <dt>Country / City</dt>
              <dd>
                {c.country} / {c.city}
              </dd>
            </div>
            <div className="inspector-row">
              <dt>KYC status</dt>
              <dd>{c.kyc_status}</dd>
            </div>
            <div className="inspector-row">
              <dt>Fraud status</dt>
              <dd>{c.fraud_status}</dd>
            </div>
            <div className="inspector-row">
              <dt>Registered</dt>
              <dd>{formatDate(c.registration_date)}</dd>
            </div>
          </dl>
        </div>

        <div className="card">
          <h2>Fraud proximity</h2>
          {fraudPath.isLoading ? (
            <LoadingState />
          ) : fraudPath.isError ? (
            <p className="muted">No path to a confirmed fraud entity found.</p>
          ) : (
            <p>
              <strong>{String((fraudPath.data as Record<string, unknown>)?.hops)}</strong> hop(s) to a confirmed fraud
              customer.
            </p>
          )}
          <h2 style={{ marginTop: "1rem" }}>Linked customers</h2>
          {connections.isLoading ? (
            <LoadingState />
          ) : connections.data && connections.data.length > 0 ? (
            <ul style={{ paddingLeft: "1.1rem", margin: 0 }}>
              {(connections.data as unknown as Record<string, unknown>[]).map((conn, i) => (
                <li key={i}>
                  <Link className="link-id" to={`/customers/${conn.customer_id}`}>
                    {String(conn.customer_id)}
                  </Link>{" "}
                  via {String(conn.link_type)} ({String(conn.shared_value)})
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No shared-address or shared-phone links found.</p>
          )}
        </div>
      </div>

      <div className="card">
        <h2>Accounts</h2>
        {accounts.isLoading ? (
          <LoadingState />
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Type</th>
                <th>Status</th>
                <th>Risk</th>
              </tr>
            </thead>
            <tbody>
              {accounts.data?.map((acc) => (
                <tr key={acc.account_id}>
                  <td>
                    <Link className="link-id" to={`/accounts/${acc.account_id}`}>
                      {acc.account_id}
                    </Link>
                  </td>
                  <td>{acc.account_type}</td>
                  <td>{acc.status}</td>
                  <td>
                    <RiskBadge level={acc.risk_level} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2>Devices</h2>
        {devices.isLoading ? (
          <LoadingState />
        ) : (
          <ul style={{ paddingLeft: "1.1rem", margin: 0 }}>
            {(devices.data as unknown as Record<string, unknown>[])?.map((row, i) => (
              <li key={i}>
                {String((row.d as Record<string, unknown>)?.device_id)} — used {String(row.usage_count)} times
              </li>
            ))}
          </ul>
        )}
      </div>

      {network.data && (
        <div className="card">
          <h2>Graph explorer</h2>
          <p className="muted">Network around this customer's primary account ({firstAccountId}).</p>
          <GraphView graph={network.data} />
        </div>
      )}
    </div>
  );
}
