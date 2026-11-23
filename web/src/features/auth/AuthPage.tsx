import { useCallback, useEffect, useState } from "react";
import { LockOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, Form, Input, Tabs, Typography } from "antd";
import { ZodError } from "zod";
import { Brand } from "../../components/Brand";
import { ApiError } from "../../lib/api-client";
import { authApi } from "./api";
import { useAuth } from "./AuthProvider";
import {
  loginFormSchema,
  registerFormSchema,
  type LoginForm,
  type RegisterForm,
} from "./schemas";

const { Text, Title } = Typography;

const TEST_ACCOUNT: LoginForm = {
  email: "admin@163.com",
  password: "12345678",
};

export function AuthPage() {
  const { message } = App.useApp();
  const { complete } = useAuth();
  const [loading, setLoading] = useState(false);
  const [registrationEnabled, setRegistrationEnabled] = useState(false);
  const [configLoading, setConfigLoading] = useState(true);
  const [configError, setConfigError] = useState(false);
  const [mode, setMode] = useState("login");

  const loadConfig = useCallback(async () => {
    setConfigLoading(true);
    setConfigError(false);
    try {
      const config = await authApi.config();
      setRegistrationEnabled(config.registration_enabled);
    } catch {
      setConfigError(true);
    } finally {
      setConfigLoading(false);
    }
  }, []);

  useEffect(() => { void loadConfig(); }, [loadConfig]);

  const submit = async (mode: "login" | "register", values: unknown) => {
    try {
      setLoading(true);
      const auth =
        mode === "login"
          ? await authApi.login(loginFormSchema.parse(values))
          : await authApi.register(registerFormSchema.parse(values));
      if (mode === "register") message.success("注册成功，欢迎使用 Gatehouse");
      complete(auth);
    } catch (error) {
      if (error instanceof ApiError) {
        const errors: Record<number, string> = mode === "register" ? {
          403: "当前未开放注册，请联系管理员",
          409: "该邮箱已注册，请使用已有账户登录",
          429: "注册尝试过于频繁，请稍后再试",
        } : {
          401: "邮箱或密码不正确",
          403: "该账户已停用，请联系管理员",
          429: "登录尝试过于频繁，请稍后再试",
        };
        message.error(errors[error.status] || error.message);
        return;
      }
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
        <Title level={2}>{mode === "register" ? "创建 Gatehouse 账户" : "访问 Gatehouse"}</Title>
        <Text type="secondary">{mode === "register" ? "注册后即可登录，模型使用权限由管理员分配。" : "登录账户，管理你的网关密钥与使用记录。"}</Text>
        <Tabs
          className="auth-tabs"
          activeKey={mode}
          onChange={setMode}
          items={[
            {
              key: "login",
              label: "登录",
              children: <>
                <LoginForm loading={loading} onSubmit={(data) => submit("login", data)} />
                {registrationEnabled ? <Button type="link" block disabled={loading} onClick={() => setMode("register")}>还没有账户？立即注册</Button> : null}
              </>,
            },
            ...(registrationEnabled ? [{
              key: "register",
              label: "注册",
              children: <>
                <RegisterFormView loading={loading} onSubmit={(data) => submit("register", data)} />
                <Button type="link" block disabled={loading} onClick={() => setMode("login")}>已有账户？返回登录</Button>
              </>,
            }] : []),
          ]}
        />
        {configLoading ? <Text type="secondary">正在加载注册设置…</Text> : configError ? (
          <Alert type="warning" showIcon message="注册设置加载失败" action={<Button size="small" onClick={() => void loadConfig()}>重试</Button>} />
        ) : !registrationEnabled ? <Text type="secondary">当前未开放注册，请联系管理员创建账户。</Text> : null}
      </Card>
    </main>
  );
}

function LoginForm({ loading, onSubmit }: { loading: boolean; onSubmit: (data: LoginForm) => void }) {
  const [form] = Form.useForm<LoginForm>();

  return (
    <Form name="login" form={form} layout="vertical" onFinish={onSubmit} requiredMark={false} className="login-form">
      <Form.Item name="email" label="邮箱" rules={[{ required: true, message: "请输入邮箱" }, { type: "email", transform: (value?: string) => value?.trim(), message: "请输入有效邮箱" }, { max: 254, message: "邮箱最多 254 个字符" }]}><Input size="large" autoComplete="email" placeholder="you@example.com" /></Form.Item>
      <Form.Item name="password" label="密码" rules={[{ required: true, message: "请输入密码" }, { max: 256, message: "密码最多 256 个字符" }]}><Input.Password size="large" autoComplete="current-password" placeholder="输入密码" /></Form.Item>
      <Button type="primary" htmlType="submit" size="large" loading={loading} block>登录</Button>
      <section className="test-account" aria-label="测试账号">
        <div className="test-account-header">
          <Text strong>体验账号</Text>
          <Button type="link" size="small" disabled={loading} onClick={() => form.setFieldsValue(TEST_ACCOUNT)}>一键填入</Button>
        </div>
        <dl className="test-account-credentials">
          <div><dt>账号</dt><dd>{TEST_ACCOUNT.email}</dd></div>
          <div><dt>密码</dt><dd>{TEST_ACCOUNT.password}</dd></div>
        </dl>
      </section>
    </Form>
  );
}

function RegisterFormView({ loading, onSubmit }: { loading: boolean; onSubmit: (data: RegisterForm) => void }) {
  return (
    <Form name="register" layout="vertical" onFinish={onSubmit} requiredMark={false} className="login-form">
      <Form.Item name="email" label="邮箱" rules={[{ required: true, message: "请输入邮箱" }, { type: "email", transform: (value?: string) => value?.trim(), message: "请输入有效邮箱" }, { max: 254, message: "邮箱最多 254 个字符" }]}><Input size="large" autoComplete="email" placeholder="you@example.com" /></Form.Item>
      <Form.Item name="password" label="密码" extra="至少 8 个字符" rules={[{ required: true, message: "请设置密码" }, { min: 8, message: "密码至少需要 8 个字符" }, { max: 256, message: "密码最多 256 个字符" }]}><Input.Password size="large" autoComplete="new-password" placeholder="设置密码" /></Form.Item>
      <Form.Item name="confirmPassword" label="确认密码" dependencies={["password"]} rules={[
        { required: true, message: "请再次输入密码" },
        ({ getFieldValue }) => ({
          validator(_, value: string) {
            return !value || getFieldValue("password") === value
              ? Promise.resolve()
              : Promise.reject(new Error("两次输入的密码不一致"));
          },
        }),
      ]}><Input.Password size="large" autoComplete="new-password" placeholder="再次输入密码" /></Form.Item>
      <Button type="primary" htmlType="submit" size="large" loading={loading} block>注册并登录</Button>
    </Form>
  );
}
