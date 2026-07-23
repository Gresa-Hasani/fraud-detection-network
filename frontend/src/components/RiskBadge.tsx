import { riskColor } from "../utils/format";

export function RiskBadge({ level }: { level: string }) {
  return (
    <span className="badge" style={{ background: riskColor(level) }}>
      {level}
    </span>
  );
}
