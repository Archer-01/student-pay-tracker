import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Dashboard } from "./routes/Dashboard";
import { StudentsList } from "./routes/StudentsList";
import { StudentDetail } from "./routes/StudentDetail";
import { EnrollStudent } from "./routes/EnrollStudent";
import { MonthlyReport } from "./routes/MonthlyReport";
import { ClassesList } from "./routes/ClassesList";
import { ClassDetail } from "./routes/ClassDetail";
import { PacksGrid } from "./routes/PacksGrid";
import { AnnualReport } from "./routes/AnnualReport";
import { LeaversWithDebt } from "./routes/LeaversWithDebt";
import { NotFound } from "./routes/NotFound";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="students" element={<StudentsList />} />
        <Route path="students/new" element={<EnrollStudent />} />
        <Route path="students/:id" element={<StudentDetail />} />
        <Route path="classes" element={<ClassesList />} />
        <Route path="classes/:id" element={<ClassDetail />} />
        <Route path="packs" element={<PacksGrid />} />
        <Route path="reports/monthly" element={<MonthlyReport />} />
        <Route path="reports/annual" element={<AnnualReport />} />
        <Route path="debts" element={<LeaversWithDebt />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
