import { useCallback, useEffect, useRef, useState, type ComponentRef } from "react";
import { CommentOutlined, CopyOutlined, DashboardOutlined, LogoutOutlined, PlusOutlined, ReloadOutlined, RobotOutlined, SendOutlined, StopOutlined, UserOutlined } from "@ant-design/icons";
import { Alert, App, Button, Empty, Input, Layout, Select, Space, Spin, Tag, Typography } from "antd";
import { Brand } from "../../components/Brand";
import { ApiError } from "../../lib/api-client";
import { integer } from "../../lib/format";
import { authApi } from "../auth/api";
import { useAuth } from "../auth/AuthProvider";
import { dashboardApi } from "../dashboard/api";
import type { GatewayKey } from "../dashboard/schemas";
import { providersApi } from "../providers/api";
import { sendChat, type ChatTurn } from "./api";
import { readChat, saveChat, type ChatMessage } from "./storage";

const { Header } = Layout;
const { Text, Title } = Typography;
const suggestions = ["用三句话介绍一下自己", "帮我理清一个问题的思路", "帮我检查一段代码"];

export function ChatPage() {
  const { user, logout, syncUser } = useAuth();
  const { message } = App.useApp();
  const userId = user?.id ?? "";
  const [saved] = useState(() => readChat(userId));
  const [messages, setMessages] = useState<ChatMessage[]>(saved.messages);
  const [keyId, setKeyId] = useState<string | undefined>(saved.keyId);
  const [maxOutputTokens, setMaxOutputTokens] = useState(saved.maxOutputTokens);
  const [keys, setKeys] = useState<GatewayKey[]>([]);
  const [hasModels, setHasModels] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string>();
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const controller = useRef<AbortController>();
  const input = useRef<ComponentRef<typeof Input.TextArea>>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const mounted = useRef(true);
  const selectedKey = keys.find((key) => key.id === keyId) ?? keys[0];

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(undefined);
    try {
      const [currentUser, allKeys, providers] = await Promise.all([
        authApi.me(), dashboardApi.keys(), providersApi.list(),
      ]);
      if (!mounted.current) return;
      syncUser(currentUser);
      setHasModels(providers.some((provider) => provider.enabled && provider.models.length));
      const available = allKeys.filter((key) => key.enabled && key.model_name && providers.some(
        (provider) => provider.id === key.provider_id && provider.enabled
          && provider.models.some((model) => model.id === key.model_id),
      ));
      setKeys(available);
      setKeyId((current) => available.some((key) => key.id === current) ? current : available[0]?.id);
    } catch (error) {
      if (!mounted.current) return;
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) logout();
      else setLoadError(error instanceof Error ? error.message : "加载模型失败");
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [logout, syncUser]);

  useEffect(() => {
    mounted.current = true;
    void load();
    return () => { mounted.current = false; controller.current?.abort(); };
  }, [load]);

  useEffect(() => {
    const timer = window.setTimeout(() => saveChat(userId, { keyId, maxOutputTokens, messages }), 150);
    return () => window.clearTimeout(timer);
  }, [userId, keyId, maxOutputTokens, messages]);

  useEffect(() => {
    if (stickToBottom.current && scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [messages, sending]);

  const run = async (history: ChatMessage[]) => {
    if (!selectedKey || controller.current) return;
    const turns: ChatTurn[] = history.filter((item) => item.content.trim())
      .map(({ role, content }) => ({ role, content }));
    if (turns.length > 200) { message.warning("对话过长，请新建对话后继续"); return; }
    const abort = new AbortController();
    controller.current = abort;
    const assistantId = crypto.randomUUID();
    const model = `${selectedKey.model_name} · ${selectedKey.provider_name}`;
    let answer = "";
    setMessages([...history, { id: assistantId, role: "assistant", content: "", model }]);
    setSending(true);
    stickToBottom.current = true;
    const update = (changes: Partial<ChatMessage>) => {
      if (mounted.current) setMessages((items) => items.map((item) => item.id === assistantId ? { ...item, ...changes } : item));
    };
    try {
      const result = await sendChat(selectedKey.id, turns, maxOutputTokens, abort.signal, (text) => {
        answer += text;
        update({ content: answer });
      });
      if (!answer.trim()) throw new Error("模型未返回文本回复，可提高回复长度后重试");
      update({ totalTokens: result.totalTokens, limited: result.limited });
    } catch (error) {
      if (abort.signal.aborted) update({ stopped: true });
      else if (error instanceof ApiError && error.status === 401) logout();
      else update({ error: error instanceof Error ? error.message : "发送失败，请重试" });
    } finally {
      if (controller.current === abort) controller.current = undefined;
      if (mounted.current) { setSending(false); input.current?.focus(); }
    }
  };

  const send = () => {
    const content = draft.trim();
    if (!content || !selectedKey || controller.current) return;
    if (messages.filter((item) => item.content.trim()).length >= 200) {
      message.warning("对话过长，请新建对话后继续");
      return;
    }
    setDraft("");
    void run([...messages, { id: crypto.randomUUID(), role: "user", content }]);
  };

  const retry = () => {
    const lastUser = messages.map((item) => item.role).lastIndexOf("user");
    if (lastUser !== -1) void run(messages.slice(0, lastUser + 1));
  };

  const copy = async (content: string) => {
    try { await navigator.clipboard.writeText(content); message.success("已复制"); }
    catch { message.error("复制失败，请手动选择内容复制"); }
  };

  return (
    <Layout className="app-shell chat-shell">
      <Header className="topbar">
        <div className="chat-header">
          <Brand compact />
          <Space>
            <span className="user-chip"><UserOutlined /> {user?.email}</span>
            <Button href="/" disabled={sending} icon={<DashboardOutlined />} aria-label="返回控制台">控制台</Button>
            <Button type="text" icon={<LogoutOutlined />} aria-label="退出登录" onClick={logout}>退出</Button>
          </Space>
        </div>
      </Header>
      <main className="chat-workspace">
        <div className="chat-page-heading">
          <div><span className="eyebrow">GATEHOUSE CHAT</span><Title level={2}>在线聊天</Title></div>
          <Button aria-label="新建对话" icon={<PlusOutlined />} disabled={sending || !messages.length} onClick={() => {
            setMessages([]); setDraft(""); stickToBottom.current = true; input.current?.focus();
          }}>新建对话</Button>
        </div>
        <section className="chat-surface" aria-label="聊天工作区">
          <div className="chat-toolbar">
            <div className="chat-model-picker">
              <label htmlFor="chat-model">聊天模型</label>
              <Select
                id="chat-model"
                aria-label="聊天模型"
                showSearch
                optionFilterProp="label"
                value={selectedKey?.id}
                placeholder={loading ? "正在加载模型…" : "请选择可用模型"}
                loading={loading}
                disabled={sending || loading || !keys.length}
                onChange={setKeyId}
                options={keys.map((key) => ({ value: key.id, label: `${key.model_name} · ${key.provider_name} · ${key.name}` }))}
              />
            </div>
            <div className="chat-length-picker">
              <label htmlFor="chat-length">回复长度</label>
              <Select id="chat-length" aria-label="回复长度" value={maxOutputTokens} disabled={sending} onChange={setMaxOutputTokens} options={[
                { value: 512, label: "简短 · 512 Token" },
                { value: 2048, label: "标准 · 2048 Token" },
                { value: 4096, label: "较长 · 4096 Token" },
              ]} />
            </div>
            <Button type="text" icon={<ReloadOutlined />} aria-label="刷新可用模型" disabled={sending} loading={loading} onClick={() => void load()} />
          </div>
          {loadError ? <Alert className="chat-load-error" type="error" showIcon message={loadError} action={<Button size="small" onClick={() => void load()}>重试</Button>} /> : null}
          <div className="chat-scroll" ref={scroll} role="log" aria-label="聊天消息" aria-live="polite" aria-busy={sending} onScroll={() => {
            const element = scroll.current;
            if (element) stickToBottom.current = element.scrollHeight - element.clientHeight - element.scrollTop < 80;
          }}>
            {loading && !keys.length ? <div className="chat-empty"><Spin size="large" /></div> : !keys.length && !loadError ? (
              <div className="chat-empty">
                <Empty description={hasModels ? "先创建一枚绑定模型的访问密钥，即可开始聊天" : "暂无可用模型，请联系管理员分配模型权限"} />
                {hasModels ? <Button type="primary" href="/">前往控制台创建密钥</Button> : <Button href="/">返回控制台</Button>}
              </div>
            ) : !messages.length ? (
              <div className="chat-empty">
                <div className="chat-welcome-icon"><CommentOutlined /></div>
                <Title level={2}>想聊点什么？</Title>
                <Text type="secondary">选择模型，开始一段对话。</Text>
                <div className="chat-suggestions">{suggestions.map((text) => <Button key={text} disabled={!selectedKey} onClick={() => { setDraft(text); input.current?.focus(); }}>{text}</Button>)}</div>
              </div>
            ) : (
              <div className="chat-message-list">{messages.map((item, index) => (
                <article className={`chat-message chat-message-${item.role}`} key={item.id}>
                  <div className="chat-avatar">{item.role === "user" ? <UserOutlined /> : <RobotOutlined />}</div>
                  <div className="chat-message-main">
                    <div className="chat-message-heading"><Text strong>{item.role === "user" ? "你" : item.model || "助手"}</Text>{item.content ? <Button type="text" size="small" aria-label="复制消息" icon={<CopyOutlined />} onClick={() => void copy(item.content)} /> : null}</div>
                    <div className="chat-message-body">{item.content || (sending && index === messages.length - 1 ? <Space><Spin size="small" /><Text type="secondary">正在思考…</Text></Space> : <Text type="secondary">{item.stopped ? "已停止生成" : "未收到回复"}</Text>)}</div>
                    {item.error ? <div className="chat-message-error" role="alert">{item.error}</div> : null}
                    {item.stopped && item.content ? <Text type="secondary" className="chat-message-note">已停止生成</Text> : null}
                    {item.limited ? <Text type="warning" className="chat-message-note">回复已达长度上限，可提高回复长度后重试</Text> : null}
                    {item.totalTokens ? <Text type="secondary" className="chat-message-note">{integer.format(item.totalTokens)} Token</Text> : null}
                    {item.role === "assistant" && index === messages.length - 1 && !sending && (item.error || item.stopped || item.limited) ? <Button size="small" type="link" aria-label="重新生成" icon={<ReloadOutlined />} onClick={retry}>重新生成</Button> : null}
                  </div>
                </article>
              ))}</div>
            )}
          </div>
          <div className="chat-composer">
            <Input.TextArea
              id="chat-input"
              ref={input}
              aria-label="聊天输入框"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={selectedKey ? "输入消息，开始聊天…" : "选择可用模型后开始聊天"}
              autoSize={{ minRows: 2, maxRows: 6 }}
              maxLength={32_000}
              disabled={!selectedKey || loading}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
                  event.preventDefault(); send();
                }
              }}
            />
            <div className="chat-composer-footer">
              <Text type="secondary">Enter 发送 · Shift + Enter 换行</Text>
              {sending ? <Button aria-label="停止生成" icon={<StopOutlined />} onClick={() => controller.current?.abort()}>停止生成</Button> : <Button type="primary" aria-label="发送消息" icon={<SendOutlined />} disabled={!draft.trim() || !selectedKey || loading} onClick={send}>发送</Button>}
            </div>
          </div>
        </section>
        <div className="chat-page-note"><Tag bordered={false}>多轮对话</Tag><Text type="secondary">对话保留在当前浏览器标签页，调用计入账户额度与请求记录。</Text></div>
      </main>
    </Layout>
  );
}
