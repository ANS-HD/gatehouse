import { DeleteOutlined, EditOutlined, EyeOutlined, FolderOpenOutlined, RestOutlined, UploadOutlined } from "@ant-design/icons";
import { Button, Card, Descriptions, Empty, Flex, Input, Modal, Popconfirm, Progress, Select, Space, Statistic, Switch, Tabs, Tag, Typography } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import { compactNumber, formatDate, integer } from "../../../lib/format";
import type { CodexSession, CodexSessionDetail } from "../schemas";

const { Paragraph, Text } = Typography;

type TimelineMessage = CodexSessionDetail["messages"][number];
type TimelineTool = CodexSessionDetail["tool_calls"][number];
type TurnEvent = CodexSessionDetail["turns"][number]["events"][number];

function readablePayload(value: string) {
  const formatField = (key: string, item: unknown) => {
    if (key === "code" && typeof item === "string") {
      const patchSource = item.match(/^const patch = ("(?:\\.|[^"\\])*");/);
      if (patchSource) {
        try {
          return `// apply_patch\n\n${JSON.parse(patchSource[1]) as string}`;
        } catch {
          // Fall through to other formatters.
        }
      }
      const exec = item.match(/tools\.exec_command\((\{[\s\S]*?\})\);\s*text/);
      if (exec) {
        try {
          const options = JSON.parse(exec[1]) as Record<string, unknown>;
          return ["// exec_command", ...Object.entries(options).map(([name, option]) => (
            `${name}:\n${typeof option === "string" ? option : JSON.stringify(option, null, 2)}`
          ))].join("\n\n");
        } catch {
          // Fall back to lightweight source formatting below.
        }
      }
      return item.replaceAll("; ", ";\n");
    }
    return typeof item === "string" ? item : JSON.stringify(item, null, 2);
  };
  try {
    const parsed = JSON.parse(value) as unknown;
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return Object.entries(parsed as Record<string, unknown>).map(([key, item]) => ({
        key,
        value: formatField(key, item),
      }));
    }
    return [{ key: "内容", value: JSON.stringify(parsed, null, 2) }];
  } catch {
    return [{ key: "内容", value: value.replaceAll("\\n", "\n").replaceAll("\\t", "\t") }];
  }
}

function ToolPayload({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <details className="codex-tool-payload">
      <summary>{label}</summary>
      <div className="codex-tool-fields">
        {readablePayload(value).map((field) => (
          <div key={field.key}>
            {field.key !== "内容" ? <Text type="secondary">{field.key}</Text> : null}
            <pre><code>{field.value}</code></pre>
          </div>
        ))}
      </div>
    </details>
  );
}

function MessageCard({ message }: { message: TimelineMessage | TurnEvent }) {
  const role = message.role || "system";
  const text = message.text || "";
  const labels: Record<string, string> = {
    user: "用户请求",
    assistant: "Codex 回复",
    developer: "开发者上下文",
    system: "系统上下文",
  };
  if (role === "system" || role === "developer") {
    return (
      <details className={`codex-system-message ${role}`}>
        <summary>
          <Tag color={role === "developer" ? "gold" : undefined}>{labels[role]}</Tag>
          <Text type="secondary">展开查看发送给模型的配置与环境</Text>
          {message.timestamp ? <Text type="secondary">{formatDate(message.timestamp)}</Text> : null}
        </summary>
        <pre>{text}</pre>
      </details>
    );
  }
  return (
    <section className={`codex-message ${role}`}>
      <Flex justify="space-between" gap={8} wrap="wrap">
        <Tag color={role === "user" ? "blue" : "green"}>{labels[role] || role}</Tag>
        {message.timestamp ? <Text type="secondary">{formatDate(message.timestamp)}</Text> : null}
      </Flex>
      <Paragraph>{text}</Paragraph>
    </section>
  );
}

function ToolCard({ tool }: { tool: TimelineTool | TurnEvent }) {
  return (
    <section className="codex-tool-call">
      <Flex justify="space-between" gap={8} wrap="wrap">
        <Space><Tag color="purple">工具调用</Tag><Text strong>{tool.name || "tool"}</Text></Space>
        <Text type="secondary">{tool.timestamp ? formatDate(tool.timestamp) : tool.status}</Text>
      </Flex>
      <ToolPayload label="调用参数" value={tool.input} />
      <ToolPayload label="返回结果" value={tool.output} />
    </section>
  );
}

function contextPercent(session: CodexSession) {
  if (!session.context_window) return 0;
  return Math.min(100, Math.round((session.context_tokens / session.context_window) * 100));
}

export function CodexLogsPanel({
  sessions,
  allSessions,
  detail,
  loading,
  onUpload,
  onInspect,
  onDelete,
  onRestore,
  onRename,
  onClose,
  onSearch,
}: {
  sessions: CodexSession[];
  allSessions: CodexSession[];
  detail?: CodexSessionDetail;
  loading: boolean;
  onUpload: (files: File[]) => void;
  onInspect: (id: string) => void;
  onDelete: (id: string) => void;
  onRestore: (id: string) => void;
  onRename: (id: string, title: string | null) => void;
  onClose: () => void;
  onSearch: (query: string, project?: string, deleted?: boolean) => void;
}) {
  const fileInput = useRef<HTMLInputElement | null>(null);
  const folderInput = useRef<HTMLInputElement | null>(null);
  const [query, setQuery] = useState("");
  const [project, setProject] = useState<string>();
  const [showDeleted, setShowDeleted] = useState(false);
  const [selectedTurnId, setSelectedTurnId] = useState<string>();
  const projects = useMemo(
    () => Array.from(new Set(allSessions.map((item) => item.cwd).filter(Boolean) as string[])).sort(),
    [allSessions],
  );
  const totals = useMemo(() => ({
    turns: allSessions.reduce((sum, item) => sum + item.turn_count, 0),
    messages: allSessions.reduce((sum, item) => sum + item.message_count, 0),
    tools: allSessions.reduce((sum, item) => sum + item.tool_call_count, 0),
    tokens: allSessions.reduce((sum, item) => sum + item.total_tokens, 0),
  }), [allSessions]);
  useEffect(() => {
    setSelectedTurnId(detail?.turns.at(-1)?.turn_id);
  }, [detail?.session_id]);
  const selectedTurn = useMemo(
    () => detail?.turns.find((turn) => turn.turn_id === selectedTurnId) || detail?.turns.at(-1),
    [detail, selectedTurnId],
  );
  const selectedTurnIndex = useMemo(
    () => detail && selectedTurn ? detail.turns.findIndex((turn) => turn.turn_id === selectedTurn.turn_id) : -1,
    [detail, selectedTurn],
  );
  const priorTurns = useMemo(
    () => detail && selectedTurnIndex > 0 ? detail.turns.slice(0, selectedTurnIndex) : [],
    [detail, selectedTurnIndex],
  );
  const selectedRequests = useMemo(
    () => selectedTurn?.events.filter((event) => event.kind === "message" && event.role === "user") || [],
    [selectedTurn],
  );
  const selectedContextMessages = useMemo(
    () => selectedTurn?.events.filter((event) => event.kind === "message" && (event.role === "system" || event.role === "developer")) || [],
    [selectedTurn],
  );
  const selectedProcessEvents = useMemo(
    () => selectedTurn?.events.filter((event) => !(event.kind === "message" && ["user", "system", "developer"].includes(event.role || ""))) || [],
    [selectedTurn],
  );
  const priorContextTotals = useMemo(() => ({
    messages: priorTurns.reduce((sum, turn) => sum + turn.events.filter((event) => event.kind === "message").length, 0),
    tools: priorTurns.reduce((sum, turn) => sum + turn.events.filter((event) => event.kind === "tool").length, 0),
  }), [priorTurns]);
  const timeline = useMemo(() => {
    if (!detail) return [];
    return [
      ...detail.messages.map((message, index) => ({ kind: "message" as const, index, timestamp: message.timestamp, value: message })),
      ...detail.tool_calls.map((tool, index) => ({ kind: "tool" as const, index, timestamp: tool.timestamp, value: tool })),
    ].sort((a, b) => (a.timestamp || "").localeCompare(b.timestamp || ""));
  }, [detail]);
  return (
    <>
      <Card
        variant="borderless"
        className="panel-card codex-logs-card"
        title="本地 Codex 会话"
        extra={(
          <>
            <input
              ref={fileInput}
              hidden
              multiple
              type="file"
              accept=".jsonl,application/x-ndjson"
              onChange={(event) => {
                onUpload(Array.from(event.target.files || []));
                event.target.value = "";
              }}
            />
            <input
              ref={(element) => {
                folderInput.current = element;
                element?.setAttribute("webkitdirectory", "");
                element?.setAttribute("directory", "");
              }}
              hidden
              multiple
              type="file"
              accept=".jsonl,application/x-ndjson"
              onChange={(event) => {
                onUpload(Array.from(event.target.files || []));
                event.target.value = "";
              }}
            />
            <Space>
              <Button icon={<UploadOutlined />} disabled={loading} onClick={() => fileInput.current?.click()}>
                上传 JSONL
              </Button>
              <Button icon={<FolderOpenOutlined />} loading={loading} onClick={() => folderInput.current?.click()}>
                同步 sessions 文件夹
              </Button>
            </Space>
          </>
        )}
      >
        <div className="codex-summary">
          <Statistic title="会话" value={allSessions.length} />
          <Statistic title="轮次" value={totals.turns} formatter={(value) => compactNumber.format(Number(value))} />
          <Statistic title="工具调用" value={totals.tools} formatter={(value) => compactNumber.format(Number(value))} />
          <Statistic title="Token" value={totals.tokens} formatter={(value) => compactNumber.format(Number(value))} />
        </div>
        <Flex gap={10} className="codex-filters" wrap="wrap">
          <Input.Search
            allowClear
            value={query}
            placeholder="搜索标题、项目、模型和会话正文"
            enterButton="搜索"
            onChange={(event) => setQuery(event.target.value)}
            onSearch={() => onSearch(query, project, showDeleted)}
          />
          <Select
            allowClear
            showSearch
            value={project}
            placeholder="全部项目"
            options={projects.map((value) => ({ value, label: value.split("/").filter(Boolean).pop() || value }))}
            onChange={(value) => {
              setProject(value);
              onSearch(query, value, showDeleted);
            }}
          />
          <Space><Switch checked={showDeleted} onChange={(value) => { setShowDeleted(value); onSearch(query, project, value); }} /><Text type="secondary">回收站</Text></Space>
        </Flex>
        {sessions.length ? (
          <div className="codex-session-list">
            {sessions.map((session) => (
              <div className="codex-session-item" key={session.session_id}>
                <div className="codex-session-main">
                  <Text strong ellipsis={{ tooltip: session.title }}>{session.title}</Text>
                  <Text type="secondary" ellipsis={{ tooltip: session.cwd || undefined }}>
                    {session.cwd || "未知目录"} · {formatDate(session.started_at)}
                  </Text>
                </div>
                <div className="codex-session-metrics">
                  <div><Text type="secondary">模型</Text><Tag>{session.model || session.source}</Tag></div>
                  <div><Text type="secondary">Token</Text><Text>{compactNumber.format(session.total_tokens)}</Text></div>
                  <div><Text type="secondary">轮次</Text><Text>{integer.format(session.turn_count)}</Text></div>
                  <div><Text type="secondary">工具调用</Text><Text>{integer.format(session.tool_call_count)}</Text></div>
                  <div className="codex-context-metric">
                    <Text type="secondary">上下文</Text>
                    {session.context_window ? (
                      <span>
                        <Text>{compactNumber.format(session.context_tokens)} / {compactNumber.format(session.context_window)}</Text>
                        <Progress percent={contextPercent(session)} size="small" showInfo={false} />
                      </span>
                    ) : <Text>—</Text>}
                  </div>
                </div>
                <Space size={2}>
                  {!showDeleted ? <Button
                    type="text"
                    icon={<EyeOutlined />}
                    onClick={() => onInspect(session.session_id)}
                    aria-label="查看 Codex 会话"
                  /> : null}
                  {!showDeleted ? <Button
                    type="text"
                    icon={<EditOutlined />}
                    onClick={() => {
                      const value = window.prompt("会话标题（留空恢复自动标题）", session.title);
                      if (value !== null) onRename(session.session_id, value.trim() || null);
                    }}
                    aria-label="重命名 Codex 会话"
                  /> : null}
                  {showDeleted ? <Button type="text" icon={<RestOutlined />} onClick={() => onRestore(session.session_id)} aria-label="恢复 Codex 会话" /> : null}
                  {!showDeleted ? <Popconfirm title="移到回收站？" onConfirm={() => onDelete(session.session_id)}>
                    <Button type="text" danger icon={<DeleteOutlined />} aria-label="删除 Codex 会话" />
                  </Popconfirm> : null}
                </Space>
              </div>
            ))}
          </div>
        ) : (
          <Empty description="可上传 ~/.codex/sessions 下的 JSONL 文件" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>
      <Modal
        open={Boolean(detail)}
        title={detail?.title || "Codex 会话"}
        width={1000}
        footer={null}
        onCancel={onClose}
        destroyOnClose
      >
        {detail ? (
          <>
            <Flex gap={8} wrap="wrap" className="codex-detail-meta">
              <Tag>{detail.source}</Tag>
              <Text type="secondary">{detail.cwd || "未知目录"}</Text>
              <Text type="secondary">{formatDate(detail.started_at)}</Text>
              {detail.model ? <Tag color="cyan">{detail.model}</Tag> : null}
              <Text type="secondary">{compactNumber.format(detail.total_tokens)} Token</Text>
              <Text type="secondary">{detail.turn_count} 个轮次</Text>
              <Text type="secondary">{detail.tool_call_count} 次工具调用</Text>
              <Text type="secondary">{detail.message_count} 条消息</Text>
              {detail.context_window ? (
                <Text type="secondary">
                  上下文 {compactNumber.format(detail.context_tokens)} / {compactNumber.format(detail.context_window)}（{contextPercent(detail)}%）
                </Text>
              ) : null}
            </Flex>
            <Tabs
              items={[
                {
                  key: "turns",
                  label: `轮次（${detail.turns.length}）`,
                  children: detail.turns.length ? (
                    <div className="codex-turn-layout">
                      <aside className="codex-turn-list">
                        {detail.turns.map((turn) => (
                          <button
                            type="button"
                            className={turn.turn_id === selectedTurn?.turn_id ? "active" : ""}
                            key={turn.turn_id}
                            onClick={() => setSelectedTurnId(turn.turn_id)}
                          >
                            <span><strong>轮次 {turn.sequence}</strong><Tag color={turn.status === "completed" ? "green" : "orange"}>{turn.status === "completed" ? "完成" : "中断"}</Tag></span>
                            <span className="codex-turn-request-preview">
                              {turn.events.find((event) => event.kind === "message" && event.role === "user")?.text || "未记录用户请求"}
                            </span>
                            <small>{turn.started_at ? formatDate(turn.started_at) : "未知时间"}</small>
                            <small>{compactNumber.format(turn.total_tokens)} Token · {turn.tool_call_count} 工具</small>
                          </button>
                        ))}
                      </aside>
                      {selectedTurn ? (
                        <div className="codex-turn-detail">
                          <div className="codex-token-breakdown">
                            {[
                              ["输入", selectedTurn.input_tokens, "input"],
                              ["缓存", selectedTurn.cached_input_tokens, "cached"],
                              ["输出", selectedTurn.output_tokens, "output"],
                              ["推理", selectedTurn.reasoning_tokens, "reasoning"],
                            ].map(([label, value, kind]) => (
                              <div key={String(kind)}>
                                <span><Text type="secondary">{label}</Text><Text>{compactNumber.format(Number(value))}</Text></span>
                                <i className={String(kind)} style={{ width: `${Math.max(2, (Number(value) / Math.max(1, selectedTurn.total_tokens)) * 100)}%` }} />
                              </div>
                            ))}
                          </div>
                          <Flex gap={8} wrap="wrap" className="codex-turn-meta">
                            {selectedTurn.model ? <Tag>{selectedTurn.model}</Tag> : null}
                            {selectedTurn.effort ? <Tag color="blue">推理 {selectedTurn.effort}</Tag> : null}
                            <Text type="secondary">{selectedTurn.message_count} 消息</Text>
                            <Text type="secondary">{selectedTurn.tool_call_count} 工具调用</Text>
                            {selectedTurn.context_window ? <Text type="secondary">上下文窗 {compactNumber.format(selectedTurn.context_window)}</Text> : null}
                          </Flex>
                          <section className="codex-turn-requests">
                            <Flex justify="space-between" align="center" gap={8} wrap="wrap">
                              <Text strong>本轮用户请求</Text>
                              <Text type="secondary">{selectedRequests.length} 条</Text>
                            </Flex>
                            {selectedRequests.length ? selectedRequests.map((request, index) => (
                              <MessageCard message={request} key={`turn-request-${index}`} />
                            )) : <Text type="secondary" className="codex-turn-request-empty">这轮日志没有记录用户请求正文</Text>}
                          </section>
                          {selectedTurn.context ? (
                            <div className="codex-turn-context">
                              <Flex justify="space-between" align="center" gap={8} wrap="wrap">
                                <Text strong>本轮上下文</Text>
                                <Text type="secondary">本轮系统消息 + 运行环境 + 前序轮次共同构成模型输入</Text>
                              </Flex>
                              <Descriptions size="small" column={2} items={[
                                { key: "cwd", label: "工作目录", children: selectedTurn.context.cwd || "—" },
                                { key: "roots", label: "工作区", children: selectedTurn.context.workspace_roots.join("、") || "—" },
                                { key: "date", label: "日期/时区", children: [selectedTurn.context.current_date, selectedTurn.context.timezone].filter(Boolean).join(" · ") || "—" },
                                { key: "approval", label: "审批", children: [selectedTurn.context.approval_policy, selectedTurn.context.approvals_reviewer].filter(Boolean).join(" · ") || "—" },
                                { key: "sandbox", label: "沙箱/权限", children: [selectedTurn.context.sandbox, selectedTurn.context.permission_profile].filter(Boolean).join(" · ") || "—" },
                                { key: "mode", label: "协作模式", children: selectedTurn.context.collaboration_mode || "—" },
                                { key: "personality", label: "人格", children: selectedTurn.context.personality || "—" },
                                { key: "realtime", label: "实时语音", children: selectedTurn.context.realtime_active == null ? "—" : selectedTurn.context.realtime_active ? "开启" : "关闭" },
                                { key: "summary-mode", label: "摘要策略", children: selectedTurn.context.summary_mode || "—" },
                              ]} />
                              <div className="codex-context-content">
                                <Text strong>本轮模型输入内容</Text>
                                <Text type="secondary">以下内容由原始日志重建；发生上下文压缩时，早期内容可能由模型内部压缩窗口替代。</Text>
                                {detail.context?.base_instructions ? (
                                  <details className="codex-context-section">
                                    <summary>
                                      <span>基础系统指令</span>
                                      <Text type="secondary">{detail.context.base_instructions.length.toLocaleString()} 字符</Text>
                                    </summary>
                                    <pre>{detail.context.base_instructions}</pre>
                                  </details>
                                ) : <Text type="secondary">日志未记录基础系统指令</Text>}
                                <details className="codex-context-section" open={selectedContextMessages.length > 0}>
                                  <summary>
                                    <span>本轮系统 / 开发者注入</span>
                                    <Text type="secondary">{selectedContextMessages.length} 条</Text>
                                  </summary>
                                  <div className="codex-context-event-list">
                                    {selectedContextMessages.length ? selectedContextMessages.map((event, index) => (
                                      <MessageCard message={event} key={`context-message-${index}`} />
                                    )) : <Text type="secondary">本轮没有单独注入系统或开发者消息</Text>}
                                  </div>
                                </details>
                                <details className="codex-context-section">
                                  <summary>
                                    <span>前序轮次上下文</span>
                                    <Text type="secondary">{priorTurns.length} 轮 · {priorContextTotals.messages} 消息 · {priorContextTotals.tools} 工具</Text>
                                  </summary>
                                  <div className="codex-context-history">
                                    {priorTurns.length ? priorTurns.map((turn) => {
                                      const request = turn.events.find((event) => event.kind === "message" && event.role === "user");
                                      return (
                                        <details key={`context-turn-${turn.turn_id}`}>
                                          <summary>
                                            <span>轮次 {turn.sequence} · {request?.text || "未记录用户请求"}</span>
                                            <Text type="secondary">{turn.message_count} 消息 · {turn.tool_call_count} 工具</Text>
                                          </summary>
                                          <div className="codex-context-event-list">
                                            {turn.events.map((event, index) => event.kind === "message" ? (
                                              <MessageCard message={event} key={`context-turn-${turn.turn_id}-message-${index}`} />
                                            ) : <ToolCard tool={event} key={`context-turn-${turn.turn_id}-tool-${event.call_id || index}`} />)}
                                          </div>
                                        </details>
                                      );
                                    }) : <Text type="secondary">这是首轮，没有前序对话</Text>}
                                  </div>
                                </details>
                              </div>
                              {selectedTurn.context.summary ? (
                                <details className="codex-context-summary">
                                  <summary>本轮压缩上下文摘要</summary>
                                  <pre>{selectedTurn.context.summary}</pre>
                                </details>
                              ) : null}
                            </div>
                          ) : (
                            <Text type="secondary" className="codex-turn-context-empty">该轮日志没有记录 turn_context</Text>
                          )}
                          <div className="codex-messages codex-turn-events">
                            <Text strong className="codex-turn-timeline-title">响应与执行过程</Text>
                            {selectedProcessEvents.map((event, index) => event.kind === "message" ? (
                              <MessageCard message={event} key={`turn-message-${index}`} />
                            ) : <ToolCard tool={event} key={`turn-tool-${event.call_id || index}`} />)}
                          </div>
                        </div>
                      ) : null}
                    </div>
                  ) : <Empty description="这份日志尚未建立轮次索引，重新上传即可补建" image={Empty.PRESENTED_IMAGE_SIMPLE} />,
                },
                {
                  key: "timeline",
                  label: `全局时间线（${detail.messages.length + detail.tool_calls.length}）`,
                  children: (
                    <div className="codex-messages">
                      {timeline.map((event) => event.kind === "message" ? (
                        <MessageCard message={event.value} key={`message-${event.index}`} />
                      ) : <ToolCard tool={event.value} key={`tool-${event.value.call_id}-${event.index}`} />)}
                    </div>
                  ),
                },
                {
                  key: "context",
                  label: "上下文",
                  children: detail.context ? (
                    <div className="codex-context">
                      <Descriptions bordered size="small" column={1} items={[
                        { key: "model", label: "模型", children: detail.context.model || detail.model || "—" },
                        { key: "effort", label: "推理强度", children: detail.context.effort || "—" },
                        { key: "cwd", label: "工作目录", children: detail.context.cwd || detail.cwd || "—" },
                        { key: "roots", label: "工作区", children: detail.context.workspace_roots.join("、") || "—" },
                        { key: "approval", label: "审批策略", children: detail.context.approval_policy || "—" },
                        { key: "sandbox", label: "沙箱", children: detail.context.sandbox || "—" },
                        { key: "usage", label: "上下文占用", children: detail.context_window ? `${compactNumber.format(detail.context_tokens)} / ${compactNumber.format(detail.context_window)}（${contextPercent(detail)}%）` : "日志未记录" },
                      ]} />
                      {detail.context.summary ? (
                        <details className="codex-context-summary">
                          <summary>压缩上下文摘要</summary>
                          <pre>{detail.context.summary}</pre>
                        </details>
                      ) : null}
                    </div>
                  ) : <Empty description="这份旧日志没有记录 turn_context" image={Empty.PRESENTED_IMAGE_SIMPLE} />,
                },
              ]}
            />
          </>
        ) : null}
      </Modal>
    </>
  );
}
