import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { AccountPage } from "./pages/AccountPage";
import { CommunitiesPage } from "./pages/CommunitiesPage";
import { CustomerPage } from "./pages/CustomerPage";
import { Dashboard } from "./pages/Dashboard";
import { FraudAlertsPage } from "./pages/FraudAlertsPage";
import { InvestigationDetailPage } from "./pages/InvestigationDetailPage";
import { InvestigationsPage } from "./pages/InvestigationsPage";
import { SearchPage } from "./pages/SearchPage";

function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="accounts/:accountId" element={<AccountPage />} />
        <Route path="customers/:customerId" element={<CustomerPage />} />
        <Route path="alerts" element={<FraudAlertsPage />} />
        <Route path="communities" element={<CommunitiesPage />} />
        <Route path="investigations" element={<InvestigationsPage />} />
        <Route path="investigations/:caseId" element={<InvestigationDetailPage />} />
      </Route>
    </Routes>
  );
}

export default App;
