# Railway Xray v8.9-R — Dual Protocol + Single-Service 8080

本仓库保留原有的 **三服务双协议架构**，同时提供经过修复的 **Root 单服务 XHTTP/REALITY 模式**。

## 当前测试基线：Root 单服务模式

当前生产验证目标是把 Railway 上的 HTTP/HTTPS 与原始 REALITY TCP 明确分开：

- `8080`：HTTP Domain → 网站、`/health`、`/sub/<token>`，以及已验证正常的 HTTPS + XHTTP 入口
- `10085`：Xray 原始 TCP → VLESS + XHTTP + REALITY
- `10086`：Xray 内部 HTTP XHTTP upstream，只允许本机 `127.0.0.1` 访问，不创建 Railway TCP Proxy

```text
HTTPS Domain
railway-v89-8080-production.up.railway.app:443
                    |
                    v
                  :8080
              health_proxy
               |       |
              /        +-- /health
                       +-- /sub/<token>
                       +-- /xhttp -> 127.0.0.1:10086 -> Xray

TCP Proxy
<railway-tcp-domain>:<external-port>
                    |
                    v
                  :10085
                    |
                    v
            Xray VLESS/XHTTP/REALITY
```

### Railway Networking 必须这样设置

1. Service Root Directory：仓库根目录 `/`
2. 使用根目录 `Dockerfile`
3. HTTP/HTTPS Domain Target Port：`8080`
4. **只为 REALITY 创建一个 TCP Proxy，Application/Target Port：`10085`**
5. 不要创建 TCP Proxy → `10086`
6. 不要把 TCP Proxy → `8080` 当作 REALITY 节点
7. Railway Volume（推荐）挂载到 `/data`，用于持久化 UUID、REALITY key、VLESS Encryption material 和 subscription token

### REALITY TCP Proxy 的环境变量

Railway 当前服务存在多个 TCP Proxy 时，不要依赖 Railway 的通用 `RAILWAY_TCP_PROXY_*` 自动变量来猜选哪一个。明确设置：

```text
XRAY_TCP_PROXY_HOST=<TCP Proxy 的外部域名>
XRAY_TCP_PROXY_PORT=<TCP Proxy 的外部端口>
```

例如：

```text
XRAY_TCP_PROXY_HOST=maglev.proxy.rlwy.net
XRAY_TCP_PROXY_PORT=50192
```

程序会优先使用这两个变量生成 REALITY 订阅节点。`SERVER_HOST` / `SERVER_PORT` 仍可作为兼容性覆盖，但不建议再使用指向 `8080` 的旧 TCP Proxy。

### 订阅

订阅地址：

```text
https://<RAILWAY_PUBLIC_DOMAIN>/sub/<persistent-token>
```

当同时存在 HTTPS Domain 与 `XRAY_TCP_PROXY_HOST/PORT` 时，订阅顺序为：

1. HTTPS + XHTTP（当前已验证正常）
2. REALITY + XHTTP（当前专项测试目标）

如果没有可用的 REALITY TCP endpoint，程序不会生成一个假的 TCP 节点。

### 测试验收标准

部署后首先检查日志：

```text
TCP subscription endpoint: <指定的 TCP Proxy>
Railway TCP application port reported: ...; Xray port: 10085
Xray ready; HTTP port=8080; Xray TCP port=10085 listen=0.0.0.0
```

然后：

1. `GET /health` → `200 OK`
2. `GET /sub/<token>` → `200`，返回 Base64 VLESS subscription
3. 订阅中的 HTTPS 节点 → 已验证正常
4. 订阅中的 REALITY 节点必须使用 `XRAY_TCP_PROXY_HOST:XRAY_TCP_PROXY_PORT`
5. REALITY 客户端测试时，Railway 日志必须出现 Xray `10085` 的实际入站连接
6. 只有在 `10085` 已收到 REALITY ClientHello 后，才继续判断 REALITY / ML-KEM-768 / XHTTP 协议层

## 原有三服务模式

仓库仍然支持原来的三服务结构：

- `vision/` — VLESS + TCP + XTLS Vision + REALITY
- `xhttp/` — VLESS + XHTTP + REALITY
- `web/` — 3D 网站 + `/health` + 双节点订阅

分别设置 Root Directory：

- `/vision`
- `/xhttp`
- `/web`

## 重要修复

- 修复公共入口 HTTP Header CRLF 判断错误。
- Xray 从 `127.0.0.1:10085` 改为 `0.0.0.0:10085`，允许 Railway TCP Proxy 直接访问。
- HTTP Domain 与 Xray REALITY TCP 使用独立内部端口。
- XHTTP HTTP 请求在方法限制前先路由到 `127.0.0.1:10086`。
- Xray 启动前执行 `xray run -test -config`。
- 等待 Xray 实际监听后才创建 `/data/.xray-ready`。
- `/health` 在 Xray 未就绪时返回 `503`，就绪后返回 `200`。
- UUID、REALITY key、ML-KEM-768 material、订阅 token 均可通过 Volume 持久化。
- 生成的 `client.json` 使用 Xray 当前的 `realitySettings.publicKey` 字段。
- `XRAY_TCP_PROXY_HOST/PORT` 优先作为 REALITY 公网 endpoint，避免多个 Railway TCP Proxy 时选错 `8080` 入口。
- 没有可用的公网 endpoint 时订阅生成 fail closed，不生成一个看似正常但不可达的节点。

## 当前测试基线

**已验证：** HTTPS Domain → 8080 → XHTTP → VLESS → 外网出站正常。

**本轮测试：** Railway TCP Proxy → 10085 → Xray REALITY + XHTTP。

不要为了测试 REALITY 修改已经验证正常的 HTTPS/XHTTP 节点参数。