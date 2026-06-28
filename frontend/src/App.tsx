import { useState } from "react";
import { Layout } from "./components/Layout";
import { SearchView } from "./components/SearchView";
import { PartnersView } from "./components/PartnersView";
import { VerifyView } from "./components/VerifyView";
import { DashboardView } from "./components/DashboardView";
import { ReportsView } from "./components/ReportsView";
import type { Tab } from "./types";

export function App() {
  const [tab, setTab] = useState<Tab>("dashboard");
  return (
    <Layout tab={tab} onTabChange={setTab}>
      {tab === "dashboard" && <DashboardView onNavigate={setTab} />}
      {tab === "search" && <SearchView />}
      {tab === "partners" && <PartnersView />}
      {tab === "verify" && <VerifyView />}
      {tab === "reports" && <ReportsView />}
    </Layout>
  );
}
