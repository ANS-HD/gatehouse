import { CheckCircleFilled, EyeOutlined, StopOutlined } from "@ant-design/icons";
import { Button, Card, Empty, Pagination, Spin, Typography } from "antd";
import { compactNumber, formatDate, integer } from "../../../lib/format";
import type { Overview, RequestPage } from "../schemas";

const { Text } = Typography;

export function UsagePanel({ overview }: { overview?: Overview }) {
  const max = Math.max(...(overview?.daily.map((item) => item.tokens) || [1]), 1);
  return (
    <Card variant="borderless" className="panel-card usage-panel" title="最近 7 天">
      {overview?.daily.length ? overview.daily.map((day) => (
        <div className="bar-row" key={day.date}>
          <Text type="secondary">{day.date.slice(5)}</Text>
          <div className="bar-track"><span style={{ width: `${Math.max(4, (day.tokens / max) * 100)}%` }} /></div>
          <Text>{compactNumber.format(day.tokens)}</Text>
        </div>
      )) : <Empty description="暂无调用数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
    </Card>
  );
}

export function RecentRequests({ data, page, pageSize, loading, onPageChange, onInspect }: {
  data?: RequestPage;
  page: number;
  pageSize: number;
  loading: boolean;
  onPageChange: (page: number, pageSize: number) => void;
  onInspect: (id: number) => void;
}) {
  return (
    <Card variant="borderless" className="panel-card recent-card" title="最近请求">
      <Spin spinning={loading}>
        <div className="request-list">
          {data?.items.length ? data.items.map((item) => (
            <div className="request-item" key={item.id}>
              <div className={`request-status ${item.status_code < 400 ? "ok" : "error"}`}>
                {item.status_code < 400 ? <CheckCircleFilled /> : <StopOutlined />}
              </div>
              <div className="request-main"><Text strong>{item.endpoint}</Text><Text type="secondary">{item.provider_name} · {item.key_name} · {item.model || "—"}</Text></div>
              <Text className="request-metric">{integer.format(item.total_tokens)} tok</Text>
              <Text className="request-metric">{item.latency_ms} ms</Text>
              <Text type="secondary" className="request-time">{formatDate(item.created_at)}</Text>
              <Button type="text" icon={<EyeOutlined />} onClick={() => onInspect(item.id)} aria-label="查看请求详情" />
            </div>
          )) : <Empty description="成功调用后会显示在这里" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
        </div>
        <Pagination
          className="log-pagination"
          current={page}
          pageSize={pageSize}
          total={data?.total ?? 0}
          showSizeChanger
          pageSizeOptions={[10, 20, 50, 100]}
          showTotal={(total) => `共 ${total} 条请求`}
          onChange={onPageChange}
          disabled={loading}
        />
      </Spin>
    </Card>
  );
}
