import { Form, Input, Modal, Select, Switch } from "antd";
import { useEffect } from "react";
import type { Provider, ProviderForm } from "../schemas";

const presets = [
  { label: "OpenAI", name: "OpenAI", protocol: "openai", base_url: "https://api.openai.com/v1" },
  { label: "DeepSeek", name: "DeepSeek", protocol: "openai", base_url: "https://api.deepseek.com/v1" },
  { label: "Moonshot / Kimi", name: "Moonshot", protocol: "openai", base_url: "https://api.moonshot.cn/v1" },
  { label: "硅基流动", name: "SiliconFlow", protocol: "openai", base_url: "https://api.siliconflow.cn/v1" },
  { label: "Groq", name: "Groq", protocol: "openai", base_url: "https://api.groq.com/openai/v1" },
  { label: "xAI", name: "xAI", protocol: "openai", base_url: "https://api.x.ai/v1" },
  { label: "OpenRouter", name: "OpenRouter", protocol: "openai", base_url: "https://openrouter.ai/api/v1" },
  { label: "Anthropic", name: "Anthropic", protocol: "anthropic", base_url: "https://api.anthropic.com/v1" },
] as const;

type Props = {
  open: boolean;
  loading: boolean;
  provider?: Provider;
  onClose: () => void;
  onSubmit: (data: ProviderForm) => void;
};

export function ProviderModal({ open, loading, provider, onClose, onSubmit }: Props) {
  const [form] = Form.useForm<ProviderForm>();

  useEffect(() => {
    if (!open) return;
    form.setFieldsValue(
      provider
        ? { ...provider, models: provider.models.map((item) => item.name), api_key: "" }
        : { protocol: "openai", enabled: true, name: "", base_url: "", api_key: "", models: [] },
    );
  }, [form, open, provider]);

  const selectPreset = (value: string) => {
    const preset = presets[Number(value)];
    if (preset) form.setFieldsValue({ ...preset });
  };

  return (
    <Modal title={provider ? "编辑供应商" : "添加供应商"} open={open} onCancel={onClose} onOk={() => form.submit()} okText="保存" cancelText="取消" confirmLoading={loading} destroyOnClose>
      <Form form={form} layout="vertical" onFinish={onSubmit} requiredMark={false}>
        {!provider ? <Form.Item label="快速选择"><Select placeholder="选择常用服务商或手动填写" onChange={selectPreset} options={presets.map((item, index) => ({ label: item.label, value: String(index) }))} /></Form.Item> : null}
        <Form.Item name="name" label="名称" rules={[{ required: true, message: "请输入名称" }]}><Input placeholder="例如 DeepSeek" maxLength={64} /></Form.Item>
        <Form.Item name="protocol" label="接口协议" rules={[{ required: true }]}><Select options={[{ label: "OpenAI 兼容", value: "openai" }, { label: "Anthropic 原生", value: "anthropic" }]} /></Form.Item>
        <Form.Item name="base_url" label="上游 Base URL" rules={[{ required: true, type: "url", message: "请输入完整 URL" }]} extra="需包含版本路径，例如 /v1。"><Input placeholder="https://api.example.com/v1" /></Form.Item>
        <Form.Item name="api_key" label="上游 API Key" rules={provider ? [] : [{ required: true, message: "请输入 API Key" }]} extra={provider ? "留空表示继续使用原密钥。" : "加密后保存在服务端，不会返回到浏览器。"}><Input.Password autoComplete="new-password" placeholder={provider ? "不修改" : "sk-..."} /></Form.Item>
        <Form.Item name="models" label="允许使用的模型" rules={[{ required: true, message: "至少配置一个模型" }]} extra="输入模型 ID 后按回车，例如 gpt-4.1-mini。移除模型后，绑定它的密钥会立即失效。"><Select mode="tags" tokenSeparators={[",", " "]} placeholder="输入模型 ID 并按回车" /></Form.Item>
        <Form.Item name="enabled" label="立即启用" valuePropName="checked"><Switch /></Form.Item>
      </Form>
    </Modal>
  );
}
