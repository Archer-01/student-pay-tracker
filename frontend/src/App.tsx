import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Dashboard } from "./routes/Dashboard";
import { StudentsList } from "./routes/StudentsList";
import { StudentDetail } from "./routes/StudentDetail";
import { EnrollStudent } from "./routes/EnrollStudent";
import { MonthlyReport } from "./routes/MonthlyReport";
import { NotFound } from "./routes/NotFound";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="students" element={<StudentsList />} />
        <Route path="students/new" element={<EnrollStudent />} />
        <Route path="students/:id" element={<StudentDetail />} />
        <Route path="reports/monthly" element={<MonthlyReport />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
