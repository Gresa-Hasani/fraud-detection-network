// Uniqueness constraints for all entity identifiers.
// Run once during setup; all statements are idempotent (IF NOT EXISTS).

CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer) REQUIRE c.customer_id IS UNIQUE;

CREATE CONSTRAINT account_id_unique IF NOT EXISTS
FOR (a:Account) REQUIRE a.account_id IS UNIQUE;

CREATE CONSTRAINT transaction_id_unique IF NOT EXISTS
FOR (t:Transaction) REQUIRE t.transaction_id IS UNIQUE;

CREATE CONSTRAINT device_id_unique IF NOT EXISTS
FOR (d:Device) REQUIRE d.device_id IS UNIQUE;

CREATE CONSTRAINT ip_unique IF NOT EXISTS
FOR (ip:IPAddress) REQUIRE ip.ip IS UNIQUE;

CREATE CONSTRAINT merchant_id_unique IF NOT EXISTS
FOR (m:Merchant) REQUIRE m.merchant_id IS UNIQUE;

CREATE CONSTRAINT phone_unique IF NOT EXISTS
FOR (p:PhoneNumber) REQUIRE p.phone IS UNIQUE;

CREATE CONSTRAINT email_unique IF NOT EXISTS
FOR (e:EmailAddress) REQUIRE e.email IS UNIQUE;

CREATE CONSTRAINT address_id_unique IF NOT EXISTS
FOR (a:Address) REQUIRE a.address_id IS UNIQUE;

CREATE CONSTRAINT fraud_case_id_unique IF NOT EXISTS
FOR (f:FraudCase) REQUIRE f.case_id IS UNIQUE;

CREATE CONSTRAINT fraud_alert_id_unique IF NOT EXISTS
FOR (a:FraudAlert) REQUIRE a.alert_id IS UNIQUE;
