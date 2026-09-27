import type { ReactNode } from "react";
import { App, ConfigProvider, theme } from "antd";
import zhCN from "antd/locale/zh_CN";
import { AuthProvider } from "../features/auth/AuthProvider";

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: "#62e8c6",
          colorInfo: "#62e8c6",
          colorBgBase: "#07111f",
          colorTextBase: "#eef7ff",
          borderRadius: 10,
          fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        },
        components: {
          Card: { colorBgContainer: "#0c1929" },
          Table: { headerBg: "#0a1625", colorBgContainer: "transparent" },
          Modal: { contentBg: "#0c1929", headerBg: "#0c1929" },
        },
      }}
    >
      <App><AuthProvider>{children}</AuthProvider></App>
    </ConfigProvider>
  );
}

