import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  type PieLabelRenderProps,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ErrorState, LoadingState } from "../components/QueryState";
import { StatTile } from "../components/StatTile";
import { getAlertsByRule, getAlertsBySeverity, getCommunitySummary, getDashboard, getRiskDistribution } from "../services/api";
import { riskColor, severityColor } from "../utils/format";

export function Dashboard() {
  const dashboard = useQuery({ queryKey: ["dashboard"], queryFn: getDashboard });
  const riskDist = useQuery({ queryKey: ["risk-distribution"], queryFn: getRiskDistribution });
  const alertsByRule = useQuery({ queryKey: ["alerts-by-rule"], queryFn: getAlertsByRule });
  const alertsBySeverity = useQuery({ queryKey: ["alerts-by-severity"], queryFn: getAlertsBySeverity });
  const communities = useQuery({ queryKey: ["community-summary", 8], queryFn: () => getCommunitySummary(8) });

  if (dashboard.isLoading) return <LoadingState label="Loading dashboard..." />;
  if (dashboard.isError) return <ErrorState error={dashboard.error} />;
  const d = dashboard.data!;

  return (
    <div>
      <h1>Dashboard</h1>

      <div className="grid grid-stats">
        <StatTile label="Total customers" value={d.total_customers} />
        <StatTile label="Total accounts" value={d.total_accounts} />
        <StatTile label="Total transactions" value={d.total_transactions} />
        <StatTile label="Flagged transactions" value={d.flagged_transactions} />
        <StatTile label="Open fraud alerts" value={d.open_alerts} />
        <StatTile label="Critical-risk accounts" value={d.critical_accounts} />
        <StatTile label="Detected communities" value={d.communities} />
        <StatTile label="Confirmed fraud customers" value={d.confirmed_fraud_customers} />
      </div>

      <div className="grid grid-2" style={{ marginTop: "1rem" }}>
        <div className="card">
          <h2>Account risk distribution</h2>
          {riskDist.isLoading ? (
            <LoadingState />
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie
                  data={riskDist.data}
                  dataKey="count"
                  nameKey="risk_level"
                  cx="50%"
                  cy="50%"
                  outerRadius={90}
                  label={(entry: PieLabelRenderProps) => {
                    const e = entry as unknown as { risk_level: string; count: number };
                    return `${e.risk_level}: ${e.count}`;
                  }}
                >
                  {(riskDist.data ?? []).map((entry) => (
                    <Cell key={entry.risk_level} fill={riskColor(entry.risk_level)} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="card">
          <h2>Fraud alerts by severity</h2>
          {alertsBySeverity.isLoading ? (
            <LoadingState />
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie
                  data={alertsBySeverity.data}
                  dataKey="count"
                  nameKey="severity"
                  cx="50%"
                  cy="50%"
                  outerRadius={90}
                  label={(entry: PieLabelRenderProps) => {
                    const e = entry as unknown as { severity: string; count: number };
                    return `${e.severity}: ${e.count}`;
                  }}
                >
                  {(alertsBySeverity.data ?? []).map((entry) => (
                    <Cell key={entry.severity} fill={severityColor(entry.severity)} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      <div className="grid grid-2" style={{ marginTop: "1rem" }}>
        <div className="card">
          <h2>Fraud alerts by rule</h2>
          {alertsByRule.isLoading ? (
            <LoadingState />
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={alertsByRule.data}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="rule_id" fontSize={11} />
                <YAxis fontSize={11} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="count" fill="#2563eb" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="card">
          <h2>Top fraud communities</h2>
          {communities.isLoading ? (
            <LoadingState />
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={communities.data} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" fontSize={11} allowDecimals={false} />
                <YAxis type="category" dataKey="community_id" fontSize={11} width={70} />
                <Tooltip />
                <Bar dataKey="member_count" fill="#7c3aed" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}
