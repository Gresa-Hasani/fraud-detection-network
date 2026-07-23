import axios from "axios";
import type {
  Account,
  Customer,
  DashboardSummary,
  FraudAlert,
  FraudCase,
  FraudRule,
  InvestigationGraph,
  PaginatedResponse,
  RiskAssessment,
  Transaction,
} from "../types";

const baseURL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

export const api = axios.create({ baseURL });

export interface ApiErrorBody {
  error: { code: string; message: string; details: Record<string, unknown>; request_id: string };
}

// Customers ------------------------------------------------------------
export const listCustomers = (params: { limit?: number; offset?: number; fraud_status?: string }) =>
  api.get<PaginatedResponse<Customer>>("/customers", { params }).then((r) => r.data);

export const getCustomer = (id: string) => api.get<Customer>(`/customers/${id}`).then((r) => r.data);
export const getCustomerAccounts = (id: string) => api.get<Account[]>(`/customers/${id}/accounts`).then((r) => r.data);
export const getCustomerDevices = (id: string) =>
  api.get<Record<string, unknown>[]>(`/customers/${id}/devices`).then((r) => r.data);
export const getCustomerConnections = (id: string) =>
  api.get<Record<string, unknown>[]>(`/customers/${id}/connections`).then((r) => r.data);
export const getCustomerFraudPath = (id: string) =>
  api.get<Record<string, unknown>>(`/customers/${id}/fraud-path`).then((r) => r.data);

// Accounts ---------------------------------------------------------------
export const listAccounts = (params: { limit?: number; offset?: number; risk_level?: string; status?: string }) =>
  api.get<PaginatedResponse<Account>>("/accounts", { params }).then((r) => r.data);

export const getAccount = (id: string) => api.get<Account>(`/accounts/${id}`).then((r) => r.data);
export const getAccountTransactions = (id: string, params: { limit?: number; offset?: number }) =>
  api.get<PaginatedResponse<Transaction>>(`/accounts/${id}/transactions`, { params }).then((r) => r.data);
export const getAccountNetwork = (id: string, params: { depth?: number; limit?: number }) =>
  api.get<InvestigationGraph>(`/accounts/${id}/network`, { params }).then((r) => r.data);
export const getAccountRisk = (id: string) => api.get<RiskAssessment>(`/accounts/${id}/risk`).then((r) => r.data);
export const getAccountCounterparties = (id: string) =>
  api.get<Record<string, unknown>[]>(`/accounts/${id}/counterparties`).then((r) => r.data);

// Transactions -------------------------------------------------------------
export const listFlaggedTransactions = (params: { limit?: number; offset?: number }) =>
  api.get<PaginatedResponse<Transaction>>("/transactions/flagged", { params }).then((r) => r.data);

export const getTransaction = (id: string) => api.get<Transaction>(`/transactions/${id}`).then((r) => r.data);

// Fraud ----------------------------------------------------------------
export const listFraudAlerts = (params: { limit?: number; offset?: number; status?: string; severity?: string }) =>
  api.get<PaginatedResponse<FraudAlert>>("/fraud/alerts", { params }).then((r) => r.data);

export const listFraudRules = () => api.get<FraudRule[]>("/fraud/rules").then((r) => r.data);
export const runDetection = () => api.post<Record<string, unknown>>("/fraud/run-detection").then((r) => r.data);
export const getFraudStatistics = () => api.get<Record<string, unknown>>("/fraud/statistics").then((r) => r.data);
export interface FraudCommunity {
  community_id: number;
  member_count: number;
  critical_member_count: number;
  account_ids: string[];
}

export const getCommunities = (params: { min_size?: number; limit?: number }) =>
  api.get<FraudCommunity[]>("/fraud/communities", { params }).then((r) => r.data);

// Investigations ---------------------------------------------------------
export const listInvestigations = (params: { limit?: number; offset?: number; status?: string }) =>
  api.get<PaginatedResponse<FraudCase>>("/investigations", { params }).then((r) => r.data);

export const createInvestigation = (payload: {
  title: string;
  description?: string;
  alert_ids?: string[];
  account_ids?: string[];
  customer_ids?: string[];
}) => api.post<FraudCase>("/investigations", payload).then((r) => r.data);

export const getInvestigation = (id: string) => api.get<FraudCase>(`/investigations/${id}`).then((r) => r.data);
export const getInvestigationGraph = (id: string) =>
  api.get<InvestigationGraph>(`/investigations/${id}/graph`).then((r) => r.data);
export const updateInvestigation = (id: string, payload: Record<string, unknown>) =>
  api.patch<FraudCase>(`/investigations/${id}`, payload).then((r) => r.data);

// Analytics ----------------------------------------------------------------
export const getDashboard = () => api.get<DashboardSummary>("/analytics/dashboard").then((r) => r.data);
export const getRiskDistribution = () =>
  api.get<{ risk_level: string; count: number }[]>("/analytics/risk-distribution").then((r) => r.data);
export const getAlertsByRule = () =>
  api.get<{ rule_id: string; count: number }[]>("/analytics/alerts-by-rule").then((r) => r.data);
export const getAlertsBySeverity = () =>
  api.get<{ severity: string; count: number }[]>("/analytics/alerts-by-severity").then((r) => r.data);
export const getTopRiskyAccounts = (limit = 10) =>
  api
    .get<{ account_id: string; risk_score: number; risk_level: string }[]>("/analytics/top-risky-accounts", {
      params: { limit },
    })
    .then((r) => r.data);
export const getCommunitySummary = (limit = 10) =>
  api.get<{ community_id: number; member_count: number }[]>("/analytics/community-summary", { params: { limit } }).then((r) => r.data);
