import { KeyOutlined, StopOutlined } from "@ant-design/icons";
import { Button, Card, Empty, Popconfirm, Progress, Space, Switch, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { formatDate, integer } from "../../../lib/format";
import type { GatewayKey } from "../schemas";

const { Text } = Typography;

type Props = {
  keys: GatewayKey[];
  onToggle: (key: GatewayKey, enabled: boolean) => void;
  onRevoke: (key: GatewayKey) => void;
};

export function KeysTable({ keys, onToggle, onRevoke }: Props) {
  const columns: ColumnsType<GatewayKey> = [
    {
      title: "密钥",
      width: 230,
      render: (_, key) => (
        <Space direction="vertical" size={1}>
          <Text strong>{key.name}</Text>
          <Space size={[6, 4]} wrap><Text code type="secondary">{key.prefix}••••••</Text><Tag bordered={false}>{key.provider_name}</Tag><Tag color="cyan">{key.model_name || "未绑定模型"}</Tag></Space>
        </Space>
      ),
    },
    { title: "状态", dataIndex: "enabled", width: 88, render: (enabled: boolean) => enabled ? <Tag color="success">运行中</Tag> : <Tag>已停用</Tag> },
    { title: "RPM", dataIndex: "rpm", width: 72 },
    {
      title: "Token 用量",
      width: 160,
      render: (_, key) => {
        const percent = key.token_limit
          ? Math.min(100, Math.round((key.account_tokens_used / key.token_limit) * 100))
          : 0;
        return (
          <Space direction="vertical" size={2} className="usage-cell">
            <Text>{integer.format(key.account_tokens_used)}{key.token_limit ? ` / ${integer.format(key.token_limit)}` : " / 不限"}</Text>
            {key.token_limit ? <Progress percent={percent} showInfo={false} size="small" status={percent >= 100 ? "exception" : "active"} /> : null}
          </Space>
        );
      },
    },
    { title: "最后调用", dataIndex: "last_used_at", width: 116, render: formatDate },
    {
      title: "操作",
      width: 104,
      render: (_, key) => (
        <Space>
          <Switch size="small" checked={key.enabled} onChange={(value) => onToggle(key, value)} aria-label={`${key.name}启用状态`} />
          {key.enabled ? (
            <Popconfirm title="停用这枚密钥？" description="现有客户端将立即无法继续调用。" onConfirm={() => onRevoke(key)} okText="停用" cancelText="取消">
              <Button type="text" danger size="small" icon={<StopOutlined />} aria-label="停用密钥" />
            </Popconfirm>
          ) : null}
        </Space>
      ),
    },
  ];

  return (
    <Card variant="borderless" className="panel-card keys-card" title={<Space><KeyOutlined />访问密钥</Space>} extra={<Text type="secondary">{keys.length} 枚</Text>}>
      <Table rowKey="id" columns={columns} dataSource={keys} pagination={false} scroll={{ x: 770 }} locale={{ emptyText: <Empty description="还没有密钥" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }} />
    </Card>
  );
}
