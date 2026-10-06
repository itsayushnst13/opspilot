import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Layout from "./components/Layout";
import { Spinner } from "./components/ui";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import RfqList from "./pages/RfqList";
import RfqDetail from "./pages/RfqDetail";
import Quality from "./pages/Quality";
import Documents from "./pages/Documents";
import KnowledgeBase from "./pages/KnowledgeBase";
import Audit from "./pages/Audit";
import Evaluations from "./pages/Evaluations";

export default function App() {
  const { user, loading } = useAuth();
  if (loading) return <div className="p-8"><Spinner /></div>;
  if (!user) return <Login />;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/rfq" element={<RfqList />} />
        <Route path="/rfq/:id" element={<RfqDetail />} />
        <Route path="/quality" element={<Quality />} />
        <Route path="/quality/:id" element={<Quality />} />
        <Route path="/documents" element={<Documents />} />
        <Route path="/documents/:id" element={<Documents />} />
        <Route path="/knowledge-base" element={<KnowledgeBase />} />
        <Route path="/audit" element={<Audit />} />
        <Route path="/evaluations" element={<Evaluations />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  );
}
