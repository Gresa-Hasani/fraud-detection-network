export interface PaginatedResponse<T> {
  items: T[];
  limit: number;
  offset: number;
  count: number;
}

export interface Customer {
  customer_id: string;
  full_name: string;
  email: string;
  phone: string;
  country: string;
  city: string;
  kyc_status: string;
  customer_status: string;
  fraud_status: "CLEAR" | "SUSPICIOUS" | "CONFIRMED_FRAUD" | "UNDER_INVESTIGATION";
  registration_date: string;
}

export interface Account {
  account_id: string;
  account_number: string;
  account_type: string;
  currency: string;
  balance: number;
  status: string;
  country: string;
  risk_score: number;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
}

export interface Transaction {
  transaction_id: string;
  amount: number;
  currency: string;
  timestamp: string;
  transaction_type: string;
  channel: string;
  status: string;
  country: string;
  risk_score: number;
  is_flagged: boolean;
}

export interface RiskReason {
  rule_id: string;
  rule_name: string;
  score_contribution: number;
  description: string;
}

export interface RiskAssessment {
  entity_id: string;
  entity_type: string;
  risk_score: number;
  risk_level: string;
  reasons: RiskReason[];
  related_entities: string[];
  calculated_at?: string;
}

export interface FraudAlert {
  alert_id: string;
  alert_type: string;
  rule_id: string;
  severity: string;
  description: string;
  score: number;
  status: string;
  created_at: string;
  entity?: Record<string, unknown> | null;
  entity_labels?: string[];
}

export interface FraudRule {
  rule_id: string;
  name: string;
  description: string;
  weight: number;
}

export interface FraudCase {
  case_id: string;
  title: string;
  description: string;
  case_type: string;
  status: string;
  priority: string;
  created_at: string;
  updated_at: string;
  assigned_to: string;
  resolution?: string | null;
}

export interface GraphNode {
  id: string;
  label: string;
  properties: Record<string, unknown>;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  properties?: Record<string, unknown>;
}

export interface InvestigationGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface DashboardSummary {
  total_customers: number;
  total_accounts: number;
  total_transactions: number;
  flagged_transactions: number;
  open_alerts: number;
  critical_accounts: number;
  communities: number;
  confirmed_fraud_customers: number;
}

export interface CommunitySummary {
  community_id: number;
  member_count: number;
  high_risk_count: number;
  total_balance: number;
}
