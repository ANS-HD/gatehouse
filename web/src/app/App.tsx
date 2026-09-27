import { lazy, Suspense } from "react";
import { useAuth } from "../features/auth/AuthProvider";

const AuthPage = lazy(() =>
  import("../features/auth/AuthPage").then((module) => ({ default: module.AuthPage })),
);
const DashboardPage = lazy(() =>
  import("../features/dashboard/DashboardPage").then((module) => ({
    default: module.DashboardPage,
  })),
);

export default function App() {
  const { authenticated } = useAuth();
  return (
    <Suspense fallback={<div className="route-loading" aria-label="页面加载中" />}>
      {authenticated ? <DashboardPage /> : <AuthPage />}
    </Suspense>
  );
}
