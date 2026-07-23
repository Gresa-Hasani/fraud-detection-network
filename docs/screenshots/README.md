# Screenshots

Not included as static images in this repository (this build was produced in a sandboxed,
headless environment without a working screenshot tool) -- every page was instead verified
live against the real backend and database via automated browser inspection (DOM content,
network requests, console errors) during development. See the demo workflow in the main
README for the exact steps to reproduce these views yourself:

- Dashboard (`/`) -- summary stat tiles + risk distribution, alert severity, alerts-by-rule,
  and top-communities charts.
- Account investigation (`/accounts/:accountId`) -- details, owner, risk score & reasons,
  recent transactions, counterparties, connected devices/IPs, Cytoscape graph explorer,
  shortest path to confirmed fraud.
- Customer investigation (`/customers/:customerId`) -- profile (masked PII), accounts,
  devices, linked customers, fraud proximity, graph explorer.
- Fraud alerts (`/alerts`) -- filterable/sortable alert table with a "run detection now"
  action.
- Fraud communities (`/communities`) -- Louvain community list with a link into the graph
  explorer for each.
- Investigations (`/investigations`, `/investigations/:caseId`) -- case creation, status
  workflow, and case graph.

To capture your own: `make start` (or run backend + frontend directly), seed and detect
fraud (`make seed && make detect-fraud`), then screenshot each route above.
