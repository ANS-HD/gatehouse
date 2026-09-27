import { KeyOutlined } from "@ant-design/icons";
import { Card, Col, Row, Statistic } from "antd";
import { compactNumber } from "../../../lib/format";
import type { Overview } from "../schemas";

export function OverviewCards({ overview }: { overview?: Overview }) {
  const summary = overview?.summary;
  return (
    <Row gutter={[16, 16]} className="stats-grid">
      <Col xs={12} lg={6}>
        <Card variant="borderless"><Statistic title="有效密钥" value={summary?.active_keys || 0} prefix={<KeyOutlined />} /></Card>
      </Col>
      <Col xs={12} lg={6}>
        <Card variant="borderless"><Statistic title="24h 请求" value={summary?.requests_24h || 0} /></Card>
      </Col>
      <Col xs={12} lg={6}>
        <Card variant="borderless"><Statistic title="24h Token" value={compactNumber.format(summary?.tokens_24h || 0)} /></Card>
      </Col>
      <Col xs={12} lg={6}>
        <Card variant="borderless">
          <Statistic title="24h 错误" value={summary?.errors_24h || 0} valueStyle={{ color: summary?.errors_24h ? "#ff8b94" : undefined }} />
        </Card>
      </Col>
    </Row>
  );
}
