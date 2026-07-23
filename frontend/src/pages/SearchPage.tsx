import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { getTransaction } from "../services/api";

export function SearchPage() {
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const q = query.trim();
    if (!q) return;

    if (q.startsWith("CUS-")) {
      navigate(`/customers/${q}`);
      return;
    }
    if (q.startsWith("ACC-")) {
      navigate(`/accounts/${q}`);
      return;
    }
    if (q.startsWith("TX-")) {
      setBusy(true);
      try {
        const tx = await getTransaction(q);
        navigate(`/accounts/${(tx as unknown as Record<string, unknown>).from_account_id ?? q}`);
      } catch {
        setError(`Transaction ${q} was not found.`);
      } finally {
        setBusy(false);
      }
      return;
    }
    setError(
      "Enter a Customer ID (CUS-...), Account ID (ACC-...), or Transaction ID (TX-...). " +
        "Device/IP/email/phone lookups are available from within an account's Graph Explorer.",
    );
  }

  return (
    <div>
      <h1>Investigation Search</h1>
      <p className="muted">Search by customer ID, account ID, or transaction ID.</p>
      <form className="search-box" onSubmit={handleSearch}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. CUS-000123, ACC-000456, TX-0001234"
        />
        <button type="submit" disabled={busy}>
          {busy ? "Searching..." : "Search"}
        </button>
      </form>
      {error && (
        <div className="card" style={{ marginTop: "1rem", borderColor: "#e8590c" }}>
          {error}
        </div>
      )}
    </div>
  );
}
