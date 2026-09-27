# Gatehouse

一个自托管的多供应商 AI API 网关。服务端加密保存上游 API Key，对客户端签发绑定模型的独立网关 Key，并提供模型授权、账户级限流、Token 额度与使用统计。

内置两类协议：

- OpenAI 兼容：OpenAI、DeepSeek、Moonshot/Kimi、硅基流动、Groq、xAI、OpenRouter，以及其他兼容服务。
- Anthropic 原生：支持 Messages API 和官方 Anthropic SDK。

## 本地启动

1. 复制配置并生成安全密钥：

   ```bash
   cp .env.example .env
   openssl rand -hex 32
   ```

2. 将结果写入 `.env` 的 `SESSION_SECRET`，同时设置 `ADMIN_EMAIL` 和强管理员密码。`OPENAI_API_KEY` 可选；填写后会在首次启动时自动创建 OpenAI 供应商。
3. 启动：

   ```bash
   docker compose up -d --build
   ```

4. 打开 `http://127.0.0.1:8080`。默认只监听本机回环地址，避免把未启用 HTTPS 的管理后台直接暴露到公网。

生产环境在 8080 端口前配置域名与 HTTPS。仓库提供了 Caddy 示例：

```bash
sudo cp deploy/Caddyfile.example /etc/caddy/Caddyfile
# 将 gateway.example.com 替换为你的域名后重载 Caddy
sudo systemctl reload caddy
```

防火墙只开放 80/443，不要直接暴露 FastAPI 的 8000 端口。若确实需要直接公开 8080，可自行修改 `docker-compose.yml` 的 Web 端口映射。

首次启动会根据 `ADMIN_EMAIL` 和 `ADMIN_PASSWORD` 创建或更新管理员账户。登录后，管理员先配置供应商及允许使用的模型，再到“用户与授权”中为普通用户分配模型、RPM 和共享 Token 总额度。普通用户可在登录页注册；如不希望开放注册，将 `REGISTRATION_ENABLED` 设置为 `false`。

管理员可以直接新增用户，也可以在编辑用户时填写新密码完成重置。密码至少 8 个字符。

## 调用网关

创建网关 Key 时选择一个已获授权的供应商和模型。服务端会强制校验请求中的 `model`，密钥不能调用其他模型。OpenAI 兼容客户端把 `base_url` 指向 `https://你的域名/v1`，API Key 使用网关生成的 `gw_...`：

```bash
curl https://你的域名/v1/responses \
  -H "Authorization: Bearer gw_xxx" \
  -H "Content-Type: application/json" \
  -d '{"model":"你所选供应商支持的模型","input":"你好"}'
```

DeepSeek 等只支持 Chat Completions 的服务商可以直接调用同一个网关地址：

```bash
curl https://你的域名/v1/chat/completions \
  -H "Authorization: Bearer gw_xxx" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"你好"}]}'
```

Anthropic 原生 SDK 将 API Key 设置为 `gw_...`，Base URL 指向网关域名（不附加 `/v1`）；SDK 发出的 `/v1/messages` 会被转发到绑定的 Anthropic 上游。

OpenAI 兼容协议默认开放 `responses`、`chat/completions`、`embeddings`、`models`、`moderations`、`images` 和 `audio`，可通过 `ALLOWED_PATH_PREFIXES` 调整。Anthropic 协议开放 `messages` 和 `models`。

出于安全考虑，上游地址默认必须使用 HTTPS。本地联调 HTTP 模拟服务时可以临时设置 `ALLOW_INSECURE_UPSTREAMS=true`，生产环境不要开启。

## 详细请求日志

最近请求右侧的查看按钮可以打开请求与响应详情，包括请求方法、查询参数、请求头、请求正文、响应头和响应正文。正文与请求头使用 `SESSION_SECRET` 派生的密钥加密保存。

```dotenv
DETAILED_LOGGING_ENABLED=true
DETAILED_LOG_RETENTION_DAYS=7
DETAILED_LOG_MAX_BYTES=65536
```

认证头、Cookie、密码、Token 和 API Key 会在写入前替换为 `[REDACTED]`。JSON 或文本正文最多保存配置的字节数，二进制正文只记录类型和大小。服务每 6 小时清理一次超过保留期限的正文与请求头，统计元数据仍会保留。

## 备份与恢复

备份脚本使用 SQLite 在线备份接口生成一致性快照，并同时保存部署配置：

```bash
./deploy/backup.sh
```

备份默认写入 `./backups/<UTC 时间>/`，权限为仅当前用户可读。建议再把该目录同步到加密的异机存储。恢复前先停止服务，将备份的 `gateway.db` 放回数据卷，并确保使用同一份 `.env`；`SESSION_SECRET` 丢失后，上游密钥和详细日志将无法解密。

## 开发

服务端按职责拆分：

```text
server/app/
├── api/            # FastAPI 依赖和 HTTP 路由
├── core/           # 配置、签名与密钥安全
├── schemas/        # Pydantic 请求/响应模型
├── services/       # 多协议供应商转发与限流
├── storage/        # SQLite 初始化和数据访问
└── main.py         # 应用创建与生命周期
```

前端按功能拆分：

```text
web/src/
├── app/             # 根组件和全局 Provider
├── components/      # 跨功能复用组件
├── features/
│   ├── auth/        # 登录、注册和会话状态
│   ├── admin/       # 用户、额度和模型授权管理
│   ├── dashboard/   # 密钥、统计和调用记录
│   └── providers/   # 上游供应商配置
├── lib/             # API 客户端、格式化和存储
└── styles/          # 全局主题与响应式样式
```

服务端：

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
```

前端：

```bash
cd web
npm install
npm run dev
```

前端开发服务器会把 `/api`、`/v1` 和 `/health` 代理到 `http://localhost:8000`。

## 安全说明

- 上游 API Key 使用 AES-GCM 加密保存，永远不会返回给浏览器或下游客户端；`SESSION_SECRET` 同时是加密根密钥，部署后不可随意更换。
- 详细请求和响应日志同样使用 AES-GCM 加密，并按照配置的保留期限自动清理。
- 网关 Key 仅保存 SHA-256 摘要，完整密钥只在创建时显示一次。
- 用户密码使用带随机盐的 `scrypt` 保存，服务端不存储明文密码。
- 会话采用短期 HMAC 签名令牌；浏览器仅保存在 `sessionStorage`。
- 每个账户只能查看和管理自己的网关 Key、额度与调用记录；普通用户只能看到管理员分配的模型。
- RPM 和 Token 总额度按账户计算，由管理员配置，同一账户下的全部网关 Key 共享额度。
- 有限 Token 账户会在请求发往上游前原子预留额度，避免并发请求共同越过上限。建议客户端显式设置 `max_output_tokens`、`max_completion_tokens` 或 `max_tokens`；未设置时按 `DEFAULT_TOKEN_RESERVATION` 预留。若成功响应没有返回 usage，则以预留量计费。
- 单机内存限流适用于默认单实例部署；多实例部署应改用 Redis 等共享限流器。
- 默认部署是单实例 SQLite，适合个人或小团队使用；高可用、多节点或高并发部署需要外部数据库和共享限流组件。
