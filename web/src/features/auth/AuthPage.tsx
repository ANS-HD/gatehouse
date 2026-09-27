import { useEffect, useState } from "react";
import { LockOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { App, Button, Card, Form, Input, Tabs, Typography } from "antd";
import { ZodError } from "zod";
import { Brand } from "../../components/Brand";
import { authApi } from "./api";
import { useAuth } from "./AuthProvider";
import {
  loginFormSchema,
  registerFormSchema,
  type LoginForm,
  type RegisterForm,
} from "./schemas";

const { Text, Title } = Typography;

export function AuthPage() {
  const { message } = App.useApp();
  const { complete } = useAuth();
  const [loading, setLoading] = useState(false);
  const [registrationEnabled, setRegistrationEnabled] = useState(false);

  useEffect(() => {
    void authApi.config().then((value) => setRegistrationEnabled(value.registration_enabled));
  }, []);

  const submit = async (mode: "login" | "register", values: unknown) => {
    try {
      setLoading(true);
      const auth =
        mode === "login"
          ? await authApi.login(loginFormSchema.parse(values))
          : await authApi.register(registerFormSchema.parse(values));
      complete(auth);
    } catch (error) {
      message.error(
        error instanceof ZodError
          ? error.issues[0]?.message
          : error instanceof Error
            ? error.message
            : "操作失败",
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="login-shell">
      <section className="login-brand" aria-label="Gatehouse">
        <Brand />
        <div>
          <span className="eyebrow">PRIVATE AI CONTROL PLANE</span>
          <h1>
            <span>多个模型供应商，</span>
            <span>一个统一入口。</span>
          </h1>
          <p>统一接入 OpenAI 兼容与 Anthropic 原生接口，每个账户拥有独立网关密钥、调用额度与使用记录。</p>
        </div>
        <div className="security-note">
          <SafetyCertificateOutlined /> 用户数据与网关密钥相互隔离
        </div>
      </section>

      <Card className="login-card" variant="borderless">
        <div className="login-icon"><LockOutlined /></div>
        <Title level={2}>访问 Gatehouse</Title>
        <Text type="secondary">登录已有账户，或创建一个新账户。</Text>
        <Tabs
          className="auth-tabs"
          items={[
            {
              key: "login",
              label: "登录",
              children: <LoginForm loading={loading} onSubmit={(data) => submit("login", data)} />,
            },
            ...(registrationEnabled ? [{
              key: "register",
              label: "注册",
              children: <RegisterFormView loading={loading} onSubmit={(data) => submit("register", data)} />,
            }] : []),
          ]}
        />
      </Card>
    </main>
  );
}

function LoginForm({ loading, onSubmit }: { loading: boolean; onSubmit: (data: LoginForm) => void }) {
  return (
    <Form layout="vertical" onFinish={onSubmit} requiredMark={false} className="login-form">
      <Form.Item name="email" label="邮箱"><Input size="large" autoComplete="email" placeholder="you@example.com" /></Form.Item>
      <Form.Item name="password" label="密码"><Input.Password size="large" autoComplete="current-password" placeholder="输入密码" /></Form.Item>
      <Button type="primary" htmlType="submit" size="large" loading={loading} block>登录</Button>
    </Form>
  );
}

function RegisterFormView({ loading, onSubmit }: { loading: boolean; onSubmit: (data: RegisterForm) => void }) {
  return (
    <Form layout="vertical" onFinish={onSubmit} requiredMark={false} className="login-form">
      <Form.Item name="email" label="邮箱"><Input size="large" autoComplete="email" placeholder="you@example.com" /></Form.Item>
      <Form.Item name="password" label="密码" extra="至少 8 个字符"><Input.Password size="large" autoComplete="new-password" placeholder="设置密码" /></Form.Item>
      <Form.Item name="confirmPassword" label="确认密码"><Input.Password size="large" autoComplete="new-password" placeholder="再次输入密码" /></Form.Item>
      <Button type="primary" htmlType="submit" size="large" loading={loading} block>创建账户</Button>
    </Form>
  );
}
