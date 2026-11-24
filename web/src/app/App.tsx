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
const ChatPage = lazy(() =>
  import("../features/chat/ChatPage").then((module) => ({ default: module.ChatPage })),
);

export default function App() {
  const { authenticated } = useAuth();
  return (
    <Suspense fallback={<div className="route-loading" aria-label="页面加载中" />}>
      {authenticated ? (window.location.pathname.replace(/\/+$/, "") === "/chat" ? <ChatPage /> : <DashboardPage />) : <AuthPage />}
    </Suspense>
  );
}
