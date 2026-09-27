import { CopyOutlined } from "@ant-design/icons";
import { Button, Form, Input, Modal, Select, Typography } from "antd";
import { useEffect } from "react";
import type { Provider } from "../../providers/schemas";
import type { KeyCreated, KeyForm } from "../schemas";

const { Text } = Typography;

type CreateProps = {
  open: boolean;
  loading: boolean;
  onClose: () => void;
  onSubmit: (data: KeyForm) => void;
  providers: Provider[];
  rpmLimit: number;
  tokenLimit: number | null;
};

export function CreateKeyModal({ open, loading, providers, rpmLimit, tokenLimit, onClose, onSubmit }: CreateProps) {
  const [form] = Form.useForm<KeyForm>();
  const providerId = Form.useWatch("provider_id", form);
  const models = providers.find((item) => item.id === providerId)?.models ?? [];

  useEffect(() => {
    if (!open) return;
    const provider = providers.find((item) => item.enabled && item.models.length);
    form.resetFields();
    form.setFieldsValue({ provider_id: provider?.id, model_id: provider?.models[0]?.id });
  }, [form, open, providers]);

  return (
    <Modal title="创建访问密钥" open={open} onCancel={onClose} onOk={() => form.submit()} okText="创建" cancelText="取消" confirmLoading={loading} destroyOnClose>
      <Form form={form} layout="vertical" onFinish={onSubmit} requiredMark={false} preserve={false} onValuesChange={(changed) => { if ("provider_id" in changed) form.setFieldValue("model_id", undefined); }}>
        <Form.Item name="name" label="名称" extra="用于识别调用方，例如 web-prod。"><Input placeholder="web-prod" maxLength={64} /></Form.Item>
        <Form.Item name="provider_id" label="上游供应商" rules={[{ required: true, message: "请选择供应商" }]}><Select placeholder="选择供应商" options={providers.filter((item) => item.enabled && item.models.length).map((item) => ({ label: item.name, value: item.id }))} /></Form.Item>
        <Form.Item name="model_id" label="授权模型" rules={[{ required: true, message: "请选择模型" }]}><Select placeholder="选择管理员分配的模型" options={models.map((item) => ({ label: item.name, value: item.id }))} /></Form.Item>
        <Text type="secondary">账户额度：{rpmLimit} RPM · Token {tokenLimit ? tokenLimit.toLocaleString() : "不限"}。额度由管理员统一分配。</Text>
      </Form>
    </Modal>
  );
}

export function KeySecretModal({ created, onClose, onCopy }: { created?: KeyCreated; onClose: () => void; onCopy: (value: string) => void }) {
  return (
    <Modal title="密钥创建成功" open={Boolean(created)} onCancel={onClose} footer={<Button type="primary" onClick={onClose}>我已保存</Button>} closable={false} maskClosable={false}>
      <div className="secret-box"><Text code>{created?.key}</Text><Button type="text" icon={<CopyOutlined />} onClick={() => created && onCopy(created.key)} aria-label="复制密钥" /></div>
      <Text type="warning">完整密钥只显示这一次。关闭前请复制并安全保存。</Text>
    </Modal>
  );
}
