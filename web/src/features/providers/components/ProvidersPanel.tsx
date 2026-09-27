import { CloudServerOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, Card, Space, Switch, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { Provider } from "../schemas";

const { Text } = Typography;

type Props = {
  providers: Provider[];
  onAdd: () => void;
  onEdit: (provider: Provider) => void;
  onToggle: (provider: Provider, enabled: boolean) => void;
};

export function ProvidersPanel({ providers, onAdd, onEdit, onToggle }: Props) {
  const columns: ColumnsType<Provider> = [
    { title: "供应商", render: (_, item) => <Space direction="vertical" size={1}><Text strong>{item.name}</Text><Text type="secondary" className="provider-url">{item.base_url}</Text></Space> },
    { title: "协议", dataIndex: "protocol", width: 130, render: (value: Provider["protocol"]) => <Tag color={value === "anthropic" ? "purple" : "cyan"}>{value === "anthropic" ? "Anthropic" : "OpenAI 兼容"}</Tag> },
    { title: "模型", width: 280, render: (_, item) => <Space size={[4, 4]} wrap>{item.models.map((model) => <Tag key={model.id}>{model.name}</Tag>)}</Space> },
    { title: "状态", dataIndex: "enabled", width: 92, render: (enabled: boolean) => enabled ? <Tag color="success">可用</Tag> : <Tag>停用</Tag> },
    { title: "操作", width: 116, render: (_, item) => <Space><Switch size="small" checked={item.enabled} onChange={(value) => onToggle(item, value)} /><Button type="text" size="small" icon={<EditOutlined />} onClick={() => onEdit(item)} /></Space> },
  ];
  return (
    <Card variant="borderless" className="panel-card providers-card" title={<Space><CloudServerOutlined />上游供应商</Space>} extra={<Button type="text" icon={<PlusOutlined />} onClick={onAdd}>添加</Button>}>
      <Table rowKey="id" columns={columns} dataSource={providers} pagination={false} scroll={{ x: 620 }} />
    </Card>
  );
}
