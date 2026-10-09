import { useCallback, useEffect, useState } from "react";
import { ApiOutlined, CopyOutlined, DashboardOutlined, LogoutOutlined, PlusOutlined, ReloadOutlined, UserOutlined } from "@ant-design/icons";
import { App, Button, Card, Flex, Layout, Space, Spin, Typography } from "antd";
import { ZodError } from "zod";
import { Brand } from "../../components/Brand";
import { ApiError } from "../../lib/api-client";
import { adminApi } from "../admin/api";
import { UserModal } from "../admin/components/UserModal";
import { UsersPanel } from "../admin/components/UsersPanel";
import { adminUserCreateSchema, adminUserFormSchema, type AdminUser, type AdminUserForm } from "../admin/schemas";
import { authApi } from "../auth/api";
import { useAuth } from "../auth/AuthProvider";
import { providersApi } from "../providers/api";
import { ProviderModal } from "../providers/components/ProviderModal";
import { ProvidersPanel } from "../providers/components/ProvidersPanel";
import { providerFormSchema, type Provider, type ProviderForm } from "../providers/schemas";
import { dashboardApi } from "./api";
import { RecentRequests, UsagePanel } from "./components/ActivityPanels";
import { CodexLogsPanel } from "./components/CodexLogsPanel";
import { KeySecretModal, CreateKeyModal } from "./components/KeyModals";
import { KeysTable } from "./components/KeysTable";
import { OverviewCards } from "./components/OverviewCards";
import { RequestDetailModal } from "./components/RequestDetailModal";
import { keyFormSchema, type CodexSession, type CodexSessionDetail, type GatewayKey, type KeyCreated, type KeyForm, type Overview, type RequestDetail } from "./schemas";

const { Header, Content } = Layout;
const { Text, Title } = Typography;

export function DashboardPage() {
  const { message } = App.useApp();
  const { user, logout, syncUser } = useAuth();
  const [overview, setOverview] = useState<Overview>();
  const [keys, setKeys] = useState<GatewayKey[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [created, setCreated] = useState<KeyCreated>();
  const [creating, setCreating] = useState(false);
  const [providerOpen, setProviderOpen] = useState(false);
  const [editingProvider, setEditingProvider] = useState<Provider>();
  const [savingProvider, setSavingProvider] = useState(false);
  const [editingUser, setEditingUser] = useState<AdminUser>();
  const [userOpen, setUserOpen] = useState(false);
  const [savingUser, setSavingUser] = useState(false);
  const [requestDetail, setRequestDetail] = useState<RequestDetail>();
  const [detailLoading, setDetailLoading] = useState(false);
  const [codexSessions, setCodexSessions] = useState<CodexSession[]>([]);
  const [allCodexSessions, setAllCodexSessions] = useState<CodexSession[]>([]);
  const [codexDetail, setCodexDetail] = useState<CodexSessionDetail>();
  const [codexLoading, setCodexLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nextCurrentUser, nextOverview, nextKeys, nextProviders, nextUsers, nextCodexSessions] = await Promise.all([
        authApi.me(),
        dashboardApi.overview(),
        dashboardApi.keys(),
        providersApi.list(),
        user?.is_admin ? adminApi.users() : Promise.resolve([]),
        dashboardApi.codexSessions(),
      ]);
      syncUser(nextCurrentUser);
      setOverview(nextOverview);
      setKeys(nextKeys);
      setProviders(nextProviders);
      setUsers(nextUsers);
      setCodexSessions(nextCodexSessions);
      setAllCodexSessions(nextCodexSessions);
    } catch (error) {
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) logout();
      else message.error(error instanceof Error ? error.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [logout, message, syncUser, user?.is_admin]);

  useEffect(() => void load(), [load]);

  const createKey = async (values: KeyForm) => {
    try {
      setCreating(true);
      const result = await dashboardApi.createKey(
        keyFormSchema.parse(values),
      );
      setCreated(result);
      setCreateOpen(false);
      await load();
    } catch (error) {
      message.error(
        error instanceof ZodError
          ? error.issues[0]?.message
          : error instanceof Error
            ? error.message
            : "创建失败",
      );
    } finally {
      setCreating(false);
    }
  };

  const toggleKey = async (key: GatewayKey, enabled: boolean) => {
    try {
      const updated = await dashboardApi.updateKey(key.id, { enabled });
      setKeys((items) => items.map((item) => (item.id === key.id ? updated : item)));
      message.success(enabled ? "密钥已启用" : "密钥已停用");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "更新失败");
    }
  };

  const revokeKey = async (key: GatewayKey) => {
    try {
      await dashboardApi.revokeKey(key.id);
      await load();
      message.success("密钥已停用");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "停用失败");
    }
  };

  const saveProvider = async (values: ProviderForm) => {
    try {
      setSavingProvider(true);
      const data = providerFormSchema.parse(values);
      if (editingProvider) {
        const update = { ...data };
        if (!update.api_key) delete update.api_key;
        await providersApi.update(editingProvider.id, update);
      } else {
        if (!data.api_key) throw new Error("请输入上游 API Key");
        await providersApi.create({ ...data, api_key: data.api_key });
      }
      setProviderOpen(false);
      setEditingProvider(undefined);
      await load();
      message.success(editingProvider ? "供应商已更新" : "供应商已添加");
    } catch (error) {
      message.error(error instanceof ZodError ? error.issues[0]?.message : error instanceof Error ? error.message : "保存失败");
    } finally {
      setSavingProvider(false);
    }
  };

  const toggleProvider = async (provider: Provider, enabled: boolean) => {
    try {
      const updated = await providersApi.update(provider.id, { enabled });
      setProviders((items) => items.map((item) => item.id === provider.id ? updated : item));
      message.success(enabled ? "供应商已启用" : "供应商已停用");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "更新失败");
    }
  };

  const saveUser = async (values: AdminUserForm) => {
    try {
      setSavingUser(true);
      const data = adminUserFormSchema.parse({
        ...values,
        token_limit: values.token_limit || null,
        model_ids: values.model_ids || [],
      });
      if (editingUser) {
        const { email: _, password, ...changes } = data;
        const updated = await adminApi.updateUser(
          editingUser.id,
          password ? { ...changes, password } : changes,
        );
        setUsers((items) => items.map((item) => item.id === updated.id ? updated : item));
      } else {
        const createdUser = await adminApi.createUser(adminUserCreateSchema.parse(data));
        setUsers((items) => [...items, createdUser]);
      }
      setUserOpen(false);
      setEditingUser(undefined);
      message.success(editingUser ? "用户权限已更新" : "用户已创建");
    } catch (error) {
      message.error(error instanceof ZodError ? error.issues[0]?.message : error instanceof Error ? error.message : "保存失败");
    } finally {
      setSavingUser(false);
    }
  };

  const copy = async (value: string) => {
    await navigator.clipboard.writeText(value);
    message.success("已复制");
  };

  const inspectRequest = async (id: number) => {
    try {
      setDetailLoading(true);
      setRequestDetail(await dashboardApi.requestDetail(id));
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取详情失败");
    } finally {
      setDetailLoading(false);
    }
  };

  const uploadCodexLogs = async (files: File[]) => {
    const jsonlFiles = files.filter((file) => file.name.toLowerCase().endsWith(".jsonl"));
    if (!jsonlFiles.length) {
      message.warning("所选内容中没有 JSONL 会话文件");
      return;
    }
    try {
      setCodexLoading(true);
      const results = [];
      for (const [index, file] of jsonlFiles.entries()) {
        message.open({
          key: "codex-folder-upload",
          type: "loading",
          content: `正在同步 ${index + 1} / ${jsonlFiles.length}：${file.name}`,
          duration: 0,
        });
        results.push(await dashboardApi.importCodexSession(file));
      }
      const nextSessions = await dashboardApi.codexSessions();
      setCodexSessions(nextSessions);
      setAllCodexSessions(nextSessions);
      const changed = results.filter((item) => item.status !== "unchanged").length;
      message.open({
        key: "codex-folder-upload",
        type: "success",
        content: `已处理 ${results.length} 个文件，新增或更新 ${changed} 个会话`,
      });
    } catch (error) {
      message.open({
        key: "codex-folder-upload",
        type: "error",
        content: error instanceof Error ? error.message : "Codex 日志上传失败",
      });
    } finally {
      setCodexLoading(false);
    }
  };

  const inspectCodexSession = async (id: string) => {
    try {
      setCodexLoading(true);
      setCodexDetail(await dashboardApi.codexSessionDetail(id));
    } catch (error) {
      message.error(error instanceof Error ? error.message : "读取 Codex 会话失败");
    } finally {
      setCodexLoading(false);
    }
  };

  const deleteCodexSession = async (id: string) => {
    try {
      await dashboardApi.deleteCodexSession(id);
      setCodexSessions((items) => items.filter((item) => item.session_id !== id));
      setAllCodexSessions((items) => items.filter((item) => item.session_id !== id));
      if (codexDetail?.session_id === id) setCodexDetail(undefined);
      message.success("已删除上传的 Codex 会话");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "删除失败");
    }
  };

  const restoreCodexSession = async (id: string) => {
    try {
      await dashboardApi.restoreCodexSession(id);
      setCodexSessions((items) => items.filter((item) => item.session_id !== id));
      const nextSessions = await dashboardApi.codexSessions();
      setAllCodexSessions(nextSessions);
      message.success("会话已恢复");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "恢复失败");
    }
  };

  const renameCodexSession = async (id: string, title: string | null) => {
    try {
      const updated = await dashboardApi.renameCodexSession(id, title);
      const replace = (items: CodexSession[]) => items.map((item) => item.session_id === id ? updated : item);
      setCodexSessions(replace);
      setAllCodexSessions(replace);
      if (codexDetail?.session_id === id) setCodexDetail({ ...codexDetail, title: updated.title });
      message.success("会话标题已更新");
    } catch (error) {
      message.error(error instanceof Error ? error.message : "重命名失败");
    }
  };

  const baseUrl = `${window.location.origin}/v1`;
  return (
    <Layout className="app-shell">
      <Header className="topbar">
        <Flex align="center" justify="space-between" gap={16}>
          <Brand compact />
          <Space>
            <span className="user-chip"><UserOutlined /> {user?.email}</span>
            <Button type="text" icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>
            <Button type="text" icon={<LogoutOutlined />} onClick={logout}>退出</Button>
          </Space>
        </Flex>
      </Header>

      <Content className="content">
        <div className="page-heading">
          <div><span className="eyebrow"><DashboardOutlined /> OVERVIEW</span><Title level={1}>网关运行概览</Title></div>
          <Button type="primary" size="large" icon={<PlusOutlined />} disabled={!providers.some((item) => item.enabled && item.models.length)} onClick={() => setCreateOpen(true)}>创建密钥</Button>
        </div>

        <Spin spinning={loading && !overview}>
          <OverviewCards overview={overview} />
          {user?.is_admin ? <ProvidersPanel providers={providers} onAdd={() => { setEditingProvider(undefined); setProviderOpen(true); }} onEdit={(provider) => { setEditingProvider(provider); setProviderOpen(true); }} onToggle={toggleProvider} /> : null}
          {user?.is_admin ? <UsersPanel users={users} providers={providers} onAdd={() => { setEditingUser(undefined); setUserOpen(true); }} onEdit={(value) => { setEditingUser(value); setUserOpen(true); }} /> : null}
          <div className="dashboard-panels">
            <KeysTable keys={keys} onToggle={toggleKey} onRevoke={revokeKey} />
            <UsagePanel overview={overview} />
          </div>
          <Card variant="borderless" className="panel-card endpoint-card">
            <div><Text type="secondary">API Base URL</Text><div className="endpoint-value"><ApiOutlined /><Text code>{baseUrl}</Text></div></div>
            <Button icon={<CopyOutlined />} onClick={() => copy(baseUrl)}>复制地址</Button>
          </Card>
          <RecentRequests overview={overview} onInspect={inspectRequest} />
          <CodexLogsPanel
            sessions={codexSessions}
            allSessions={allCodexSessions}
            detail={codexDetail}
            loading={codexLoading}
            onUpload={uploadCodexLogs}
            onInspect={inspectCodexSession}
            onDelete={deleteCodexSession}
            onRestore={restoreCodexSession}
            onRename={renameCodexSession}
            onClose={() => setCodexDetail(undefined)}
            onSearch={async (query, project, deleted) => {
              try {
                setCodexLoading(true);
                setCodexSessions(await dashboardApi.codexSessions(query, project, deleted));
              } catch (error) {
                message.error(error instanceof Error ? error.message : "搜索失败");
              } finally {
                setCodexLoading(false);
              }
            }}
          />
        </Spin>
      </Content>

      <CreateKeyModal open={createOpen} loading={creating} providers={providers} rpmLimit={user?.rpm_limit ?? 30} tokenLimit={user?.token_limit ?? null} onClose={() => setCreateOpen(false)} onSubmit={createKey} />
      <KeySecretModal created={created} onClose={() => setCreated(undefined)} onCopy={copy} />
      <ProviderModal open={providerOpen} loading={savingProvider} provider={editingProvider} onClose={() => { setProviderOpen(false); setEditingProvider(undefined); }} onSubmit={saveProvider} />
      <UserModal open={userOpen} user={editingUser} providers={providers} loading={savingUser} onClose={() => { setUserOpen(false); setEditingUser(undefined); }} onSubmit={saveUser} />
      <RequestDetailModal detail={requestDetail} loading={detailLoading} onClose={() => { setRequestDetail(undefined); setDetailLoading(false); }} />
    </Layout>
  );
}
