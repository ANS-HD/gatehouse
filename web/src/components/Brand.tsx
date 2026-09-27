import { ApiOutlined } from "@ant-design/icons";
import { Space, Typography } from "antd";

const { Text } = Typography;

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Space size={12}>
      <div className={`brand-mark${compact ? " brand-mark-small" : ""}`}>
        <ApiOutlined />
      </div>
      {compact ? (
        <div>
          <Text strong className="product-name">Gatehouse</Text>
          <Text className="product-label">API 网关</Text>
        </div>
      ) : null}
    </Space>
  );
}

