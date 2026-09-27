import { Navigate, Route, Routes } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Layout } from "./components/Layout";
import { LoadingState } from "./components/ui";
import { Login } from "./routes/Login";
import { useAuth } from "./lib/authContext";
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

/**
 * The gate. Signed out, the only thing that renders is the login screen — including for a deep
 * link like /students/3, which is why this is a tree swap rather than a redirect: there is no URL
 * to preserve or restore, and the address bar keeps the page the teacher was heading for.
 *
 * This is convenience, not security. Every figure on every page comes from a gated API call, so a
 * reader who bypassed this would get a shell full of 401s.
 */
export default function App() {
  const { user } = useAuth();
  const { t } = useTranslation();

  // `undefined` means the /auth/me probe is still in flight. Rendering the login form here would
  // flash it on every reload for someone who is already signed in.
  if (user === undefined) return <LoadingState label={t("auth.checking")} />;
  if (user === null) return <Login />;

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
        {/* /reports is the nav destination so both report views highlight it; the month view
            is the one you want nine times out of ten. */}
        <Route path="reports" element={<Navigate to="/reports/monthly" replace />} />
        <Route path="reports/monthly" element={<MonthlyReport />} />
        <Route path="reports/annual" element={<AnnualReport />} />
        <Route path="debts" element={<LeaversWithDebt />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
