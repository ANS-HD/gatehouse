import { Form, Input, InputNumber, Modal, Select, Switch } from "antd";
import { useEffect } from "react";
import type { Provider } from "../../providers/schemas";
import type { AdminUser, AdminUserForm } from "../schemas";

export function UserModal({ open, user, providers, loading, onClose, onSubmit }: {
  open: boolean;
  user?: AdminUser;
  providers: Provider[];
  loading: boolean;
  onClose: () => void;
  onSubmit: (value: AdminUserForm) => void;
}) {
  const [form] = Form.useForm<AdminUserForm>();
  useEffect(() => {
    if (!open) return;
    form.resetFields();
    form.setFieldsValue({
      email: user?.email || "",
      password: "",
      enabled: user?.enabled ?? true,
      rpm_limit: user?.rpm_limit ?? 30,
      token_limit: user?.token_limit ?? null,
      model_ids: user?.allowed_model_ids ?? [],
    });
  }, [form, open, user]);

  const options = providers.filter((provider) => provider.enabled).map((provider) => ({
    label: provider.name,
    options: provider.models.map((model) => ({ label: model.name, value: model.id })),
  }));

  return (
    <Modal title={user ? `配置 ${user.email}` : "新增用户"} open={open} onCancel={onClose} onOk={() => form.submit()} okText="保存" cancelText="取消" confirmLoading={loading} destroyOnClose>
      <Form form={form} layout="vertical" onFinish={onSubmit} requiredMark={false}>
        <Form.Item name="email" label="邮箱" rules={[{ required: true, type: "email", message: "请输入有效邮箱" }]}><Input disabled={Boolean(user)} autoComplete="email" /></Form.Item>
        <Form.Item name="password" label={user ? "重置密码" : "初始密码"} rules={user ? [{ min: 8, message: "密码至少需要 8 个字符" }] : [{ required: true, min: 8, message: "密码至少需要 8 个字符" }]} extra={user ? "留空表示不修改密码。" : "至少 8 个字符。"}><Input.Password autoComplete="new-password" /></Form.Item>
        <Form.Item name="enabled" label="允许登录和调用" valuePropName="checked"><Switch /></Form.Item>
        <Form.Item name="model_ids" label="允许使用的模型" extra="未选择模型时，该用户不能创建可调用的密钥。"><Select mode="multiple" options={options} placeholder="选择模型" optionFilterProp="label" /></Form.Item>
        <Form.Item name="rpm_limit" label="账户每分钟请求数" rules={[{ required: true }]}><InputNumber min={1} max={10_000} precision={0} className="full-width" /></Form.Item>
        <Form.Item name="token_limit" label="账户 Token 总额度" extra="该额度由用户名下全部密钥共享，留空表示不限。"><InputNumber min={1} precision={0} className="full-width" placeholder="不限" /></Form.Item>
      </Form>
    </Modal>
  );
}
