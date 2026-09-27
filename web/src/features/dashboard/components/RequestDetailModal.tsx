import { Alert, Descriptions, Modal, Spin, Tabs, Tag, Typography } from "antd";
import { formatDate, integer } from "../../../lib/format";
import type { RequestDetail } from "../schemas";

const { Text, Title } = Typography;

function LogBlock({ title, value }: { title: string; value: string | null }) {
  return (
    <section className="log-block">
      <Text type="secondary">{title}</Text>
      <pre>{value || "未记录或已超过保留期限"}</pre>
    </section>
  );
}

export function RequestDetailModal({
  detail,
  loading,
  onClose,
}: {
  detail?: RequestDetail;
  loading: boolean;
  onClose: () => void;
}) {
  return (
    <Modal title="请求详情" open={Boolean(detail) || loading} onCancel={onClose} footer={null} width={900} destroyOnClose>
      <Spin spinning={loading}>
        {detail ? (
          <>
            <Descriptions size="small" column={{ xs: 1, sm: 2 }} className="request-descriptions">
              <Descriptions.Item label="供应商">{detail.provider_name}</Descriptions.Item>
              <Descriptions.Item label="密钥">{detail.key_name}</Descriptions.Item>
              <Descriptions.Item label="请求"><Text code>{detail.method} {detail.endpoint}</Text></Descriptions.Item>
              <Descriptions.Item label="状态"><Tag color={detail.status_code < 400 ? "success" : "error"}>{detail.status_code}</Tag></Descriptions.Item>
              <Descriptions.Item label="模型">{detail.model || "—"}</Descriptions.Item>
              <Descriptions.Item label="时间">{formatDate(detail.created_at)}</Descriptions.Item>
              <Descriptions.Item label="Token">{integer.format(detail.input_tokens)} 输入 / {integer.format(detail.output_tokens)} 输出</Descriptions.Item>
              <Descriptions.Item label="耗时">{detail.latency_ms} ms</Descriptions.Item>
            </Descriptions>
            {detail.detail_truncated ? <Alert type="warning" showIcon message="日志内容超过大小限制，部分内容已截断。" /> : null}
            {detail.error ? <Alert type="error" showIcon message={detail.error} /> : null}
            <Tabs
              className="detail-tabs"
              items={[
                {
                  key: "request",
                  label: "请求",
                  children: <><LogBlock title="查询参数" value={detail.query_string} /><LogBlock title="请求头" value={detail.request_headers} /><LogBlock title="请求正文" value={detail.request_body} /></>,
                },
                {
                  key: "response",
                  label: "响应",
                  children: <><LogBlock title="响应头" value={detail.response_headers} /><LogBlock title="响应正文" value={detail.response_body} /></>,
                },
              ]}
            />
          </>
        ) : <div className="detail-loading"><Title level={5}>正在读取加密日志…</Title></div>}
      </Spin>
    </Modal>
  );
}
