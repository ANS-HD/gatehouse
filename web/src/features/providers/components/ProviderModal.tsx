import { ReloadOutlined } from "@ant-design/icons";
import { Alert, Button, Form, Input, Modal, Select, Switch, Typography } from "antd";
import { useEffect, useRef, useState } from "react";
import { providersApi } from "../api";
import type { Provider, ProviderForm } from "../schemas";

type ProviderPreset = Pick<ProviderForm, "name" | "protocol" | "base_url"> & {
  label: string;
  models?: string[];
};

const qwenModels = ["qwen-plus", "qwen-flash", "qwen-max", "qwen-long"];
const presets: ProviderPreset[] = [
  { label: "OpenAI", name: "OpenAI", protocol: "openai", base_url: "https://api.openai.com/v1" },
  { label: "DeepSeek", name: "DeepSeek", protocol: "openai", base_url: "https://api.deepseek.com/v1" },
  { label: "阿里云百炼 / 通义千问（北京）", name: "阿里云百炼（北京）", protocol: "openai", base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1", models: qwenModels },
  { label: "阿里云百炼 / 通义千问（新加坡）", name: "阿里云百炼（新加坡）", protocol: "openai", base_url: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", models: qwenModels },
  { label: "Moonshot / Kimi", name: "Moonshot", protocol: "openai", base_url: "https://api.moonshot.cn/v1" },
  { label: "硅基流动", name: "SiliconFlow", protocol: "openai", base_url: "https://api.siliconflow.cn/v1" },
  { label: "Groq", name: "Groq", protocol: "openai", base_url: "https://api.groq.com/openai/v1" },
  { label: "xAI", name: "xAI", protocol: "openai", base_url: "https://api.x.ai/v1" },
  { label: "OpenRouter", name: "OpenRouter", protocol: "openai", base_url: "https://openrouter.ai/api/v1" },
  { label: "Anthropic", name: "Anthropic", protocol: "anthropic", base_url: "https://api.anthropic.com/v1" },
];

type Props = {
  open: boolean;
  loading: boolean;
  provider?: Provider;
  onClose: () => void;
  onSubmit: (data: ProviderForm) => void;
};

export function ProviderModal({ open, loading, provider, onClose, onSubmit }: Props) {
  const [form] = Form.useForm<ProviderForm>();
  const baseUrl: string | undefined = Form.useWatch("base_url", form);
  const protocol = Form.useWatch("protocol", form);
  const apiKey: string | undefined = Form.useWatch("api_key", form);
  const selectedModels: string[] = Form.useWatch("models", form) ?? [];
  const [discoveredModels, setDiscoveredModels] = useState<string[]>([]);
  const [discovering, setDiscovering] = useState(false);
  const [discoveryError, setDiscoveryError] = useState<string>();
  const discoveryVersion = useRef(0);
  const preset = presets.find((item) => item.base_url === baseUrl?.trim().replace(/\/+$/, "") && item.protocol === protocol);
  const modelOptions = Array.from(new Set([
    ...(discoveredModels.length ? discoveredModels : preset?.models ?? []),
    ...selectedModels,
  ])).map((value) => ({ value, label: value }));

  useEffect(() => {
    if (!open) return;
    form.resetFields();
    form.setFieldsValue(
      provider
        ? { ...provider, models: provider.models.map((item) => item.name), api_key: "" }
        : { protocol: "openai", enabled: true, name: "", base_url: "", api_key: "", models: [] },
    );
  }, [form, open, provider]);

  useEffect(() => {
    discoveryVersion.current += 1;
    setDiscoveredModels([]);
    setDiscoveryError(undefined);
    setDiscovering(false);
  }, [apiKey, baseUrl, open, protocol, provider?.id]);

  const selectPreset = (value: string) => {
    const preset = presets[Number(value)];
    if (preset) form.setFieldsValue({ name: preset.name, protocol: preset.protocol, base_url: preset.base_url, api_key: "", models: [] });
  };

  const discoverModels = async () => {
    const version = ++discoveryVersion.current;
    setDiscovering(true);
    setDiscoveryError(undefined);
    try {
      await form.validateFields(["protocol", "base_url", ...(!provider ? ["api_key"] : [])]);
      if (version !== discoveryVersion.current) return;
      const values = form.getFieldsValue();
      const result = await providersApi.discoverModels({
        provider_id: provider?.id,
        protocol: values.protocol,
        base_url: values.base_url.trim(),
        api_key: values.api_key?.trim() || undefined,
      });
      if (version === discoveryVersion.current) setDiscoveredModels(result.models);
    } catch (error) {
      if (version === discoveryVersion.current) {
        setDiscoveryError(error instanceof Error ? error.message : "请先填写有效的上游地址和 API Key");
      }
    } finally {
      if (version === discoveryVersion.current) setDiscovering(false);
    }
  };

  return (
    <Modal title={provider ? "编辑供应商" : "添加供应商"} open={open} onCancel={onClose} onOk={() => form.submit()} okText="保存" cancelText="取消" confirmLoading={loading} destroyOnClose>
      <Form form={form} layout="vertical" onFinish={onSubmit} requiredMark={false}>
        {!provider ? <Form.Item label="快速选择"><Select placeholder="选择常用服务商或手动填写" onChange={selectPreset} options={presets.map((item, index) => ({ label: item.label, value: String(index) }))} /></Form.Item> : null}
        <Form.Item name="name" label="名称" rules={[{ required: true, message: "请输入名称" }]}><Input placeholder="例如 DeepSeek" maxLength={64} /></Form.Item>
        <Form.Item name="protocol" label="接口协议" rules={[{ required: true }]}><Select options={[{ label: "OpenAI 兼容", value: "openai" }, { label: "Anthropic 原生", value: "anthropic" }]} /></Form.Item>
        <Form.Item name="base_url" label="上游 Base URL" rules={[{ required: true, type: "url", message: "请输入完整 URL" }]} extra={preset?.models ? "阿里云 Key 需与地域匹配；也可填写百炼控制台提供的空间专属地址，保留 /compatible-mode/v1。" : "需包含版本路径，例如 /v1。"}><Input placeholder="https://api.example.com/v1" /></Form.Item>
        <Form.Item name="api_key" label="上游 API Key" rules={provider ? [] : [{ required: true, message: "请输入 API Key" }]} extra={provider ? "留空表示继续使用原密钥。" : "加密后保存在服务端，不会返回到浏览器。"}><Input.Password autoComplete="new-password" placeholder={provider ? "不修改" : "sk-..."} /></Form.Item>
        <div className="provider-model-toolbar">
          <label htmlFor="provider-models">允许使用的模型</label>
          <Button type="link" size="small" icon={<ReloadOutlined />} loading={discovering} disabled={!baseUrl || (!apiKey?.trim() && !provider)} onClick={() => void discoverModels()}>获取模型列表</Button>
        </div>
        {discoveryError ? <Alert className="provider-model-notice" type="warning" showIcon message={discoveryError} /> : null}
        {discoveredModels.length ? <Typography.Text className="provider-model-notice" type="secondary">已获取 {discoveredModels.length} 个模型，请下拉选择后保存。</Typography.Text> : null}
        <Form.Item name="models" rules={[{ required: true, message: "至少配置一个模型" }]} extra="支持搜索、多选，或输入模型 ID 后按回车。常用模型的可用性取决于上游权限；移除模型会使绑定密钥失效。">
          <Select
            id="provider-models"
            aria-label="允许使用的模型"
            mode="tags"
            showSearch
            maxCount={100}
            tokenSeparators={[",", " "]}
            options={modelOptions}
            loading={discovering}
            placeholder="下拉选择模型，或输入模型 ID"
            notFoundContent="填写 API Key 后点击「获取模型列表」，也可手动输入"
          />
        </Form.Item>
        <Form.Item name="enabled" label="立即启用" valuePropName="checked"><Switch /></Form.Item>
      </Form>
    </Modal>
  );
}
