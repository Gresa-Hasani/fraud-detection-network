// Indexes for properties that are commonly filtered or sorted on by the
// investigation API and fraud-detection rules. All idempotent.

CREATE INDEX customer_fraud_status IF NOT EXISTS FOR (c:Customer) ON (c.fraud_status);
CREATE INDEX customer_country IF NOT EXISTS FOR (c:Customer) ON (c.country);

CREATE INDEX account_risk_level IF NOT EXISTS FOR (a:Account) ON (a.risk_level);
CREATE INDEX account_status IF NOT EXISTS FOR (a:Account) ON (a.status);

CREATE INDEX transaction_timestamp IF NOT EXISTS FOR (t:Transaction) ON (t.timestamp);
CREATE INDEX transaction_is_flagged IF NOT EXISTS FOR (t:Transaction) ON (t.is_flagged);
CREATE INDEX transaction_risk_score IF NOT EXISTS FOR (t:Transaction) ON (t.risk_score);

CREATE INDEX fraud_alert_severity IF NOT EXISTS FOR (a:FraudAlert) ON (a.severity);
CREATE INDEX fraud_alert_status IF NOT EXISTS FOR (a:FraudAlert) ON (a.status);

CREATE INDEX fraud_case_status IF NOT EXISTS FOR (f:FraudCase) ON (f.status);

CREATE INDEX device_fingerprint IF NOT EXISTS FOR (d:Device) ON (d.fingerprint);

CREATE INDEX ip_country IF NOT EXISTS FOR (ip:IPAddress) ON (ip.country);
