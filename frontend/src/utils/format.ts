export function formatCurrency(amount: number, currency = "EUR"): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(amount);
}

export function formatDate(iso: string): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

export function maskAccountNumber(accountNumber: string): string {
  if (!accountNumber || accountNumber.length < 4) return "****";
  return `**** **** ${accountNumber.slice(-4)}`;
}

const RISK_COLORS: Record<string, string> = {
  LOW: "#2f9e44",
  MEDIUM: "#f08c00",
  HIGH: "#e8590c",
  CRITICAL: "#c92a2a",
};

export function riskColor(level: string): string {
  return RISK_COLORS[level] ?? "#868e96";
}

const SEVERITY_COLORS: Record<string, string> = {
  LOW: "#2f9e44",
  MEDIUM: "#f08c00",
  HIGH: "#e8590c",
  CRITICAL: "#c92a2a",
};

export function severityColor(level: string): string {
  return SEVERITY_COLORS[level] ?? "#868e96";
}
