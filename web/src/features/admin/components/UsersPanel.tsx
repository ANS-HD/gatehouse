import { EditOutlined, PlusOutlined, TeamOutlined } from "@ant-design/icons";
import { Button, Card, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { formatDate, integer } from "../../../lib/format";
import type { Provider } from "../../providers/schemas";
import type { AdminUser } from "../schemas";

const { Text } = Typography;

export function UsersPanel({ users, providers, onAdd, onEdit }: {
  users: AdminUser[];
  providers: Provider[];
  onAdd: () => void;
  onEdit: (user: AdminUser) => void;
}) {
  const modelNames = new Map(providers.flatMap((provider) =>
    provider.models.map((model) => [model.id, model.name] as const),
  ));
  const columns: ColumnsType<AdminUser> = [
    { title: "用户", render: (_, user) => <Space direction="vertical" size={1}><Text strong>{user.email}</Text><Text type="secondary">{formatDate(user.created_at)}</Text></Space> },
    { title: "状态", width: 90, render: (_, user) => user.is_admin ? <Tag color="gold">管理员</Tag> : user.enabled ? <Tag color="success">启用</Tag> : <Tag>停用</Tag> },
    { title: "授权模型", width: 280, render: (_, user) => user.is_admin ? <Tag color="gold">全部模型</Tag> : <Space size={[4, 4]} wrap>{user.allowed_model_ids.length ? user.allowed_model_ids.map((id) => <Tag key={id}>{modelNames.get(id) || "已移除模型"}</Tag>) : <Text type="secondary">未授权</Text>}</Space> },
    { title: "RPM", dataIndex: "rpm_limit", width: 70 },
    { title: "Token 用量", width: 150, render: (_, user) => <Text>{integer.format(user.total_tokens)}{user.token_limit ? ` / ${integer.format(user.token_limit)}` : " / 不限"}</Text> },
    { title: "请求", dataIndex: "requests_count", width: 80, render: integer.format },
    { title: "密钥", dataIndex: "active_keys", width: 70 },
    { title: "操作", width: 70, render: (_, user) => <Button type="text" icon={<EditOutlined />} disabled={user.is_admin} onClick={() => onEdit(user)} aria-label={`编辑${user.email}`} /> },
  ];
  return (
    <Card variant="borderless" className="panel-card users-card" title={<Space><TeamOutlined />用户与授权</Space>} extra={<Space><Text type="secondary">按 Token 用量排序</Text><Button type="text" icon={<PlusOutlined />} onClick={onAdd}>新增用户</Button></Space>}>
      <Table rowKey="id" columns={columns} dataSource={users} pagination={{ pageSize: 8, hideOnSinglePage: true }} scroll={{ x: 1050 }} />
    </Card>
  );
}
