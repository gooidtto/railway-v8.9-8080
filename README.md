# Railway Xray v8.9-R — Dual Protocol + Single-Service 8080

本仓库保留原有的 **三服务双协议架构**，同时新增经过修复的 **Root 单服务 XHTTP/REALITY 8080 部署模式**。

## 推荐：Root 单服务 8080 模式

如果目标是先把 Railway 上的 **网站 + `/health` + 订阅 + XHTTP/REALITY + TCP Proxy** 稳定跑通，直接把本仓库根目录作为 Railway Service 的 Root Directory 即可。

根目录模式包含：

- `Dockerfile` — 固定 Xray Core 镜像并使用 Python 3.12 Alpine 运行辅助服务
- `scripts/start.sh` — 生成并持久化 UUID、REALITY 密钥、ML-KEM-768 VLESS Encryption 和订阅 token
- `scripts/health_proxy.py` — `8080` 公共监听器；网站、健康检查、订阅和 XHTTP 透明转发共用一个入口
- `scripts/generate.py` — 生成 Xray XHTTP + REALITY 配置以及标准 Base64 VLESS 订阅
- `web/site/` — 3D Science Network 网站
- `railway.toml` — 强制使用 Root `Dockerfile`，健康检查 `/health`

### Root 单服务端口模型

```text
Railway HTTP Domain ─────┐
                         │
Railway TCP Proxy :外部端口 ──> :8080 health_proxy
                                      │
                                      ├── /health
                                      ├── /sub/<token>
                                      ├── /api/network-info
                                      ├── 静态网站
                                      └── /xhttp/* ──> 127.0.0.1:10085 Xray
```

Xray 只监听 `127.0.0.1:10085`，公共 `8080` 由 health proxy 统一接入。这样 Railway HTTP Domain 与 TCP Proxy 可以同时指向同一个 Service；Railway 官方支持 HTTP 与 TCP 在同一 Service 上共存。citeturn2search2

### Railway 设置

1. Service Root Directory：仓库根目录 `/`
2. 不要把 Root Directory 设置成 `vision`、`xhttp` 或 `web`
3. Generate 一个 HTTP/HTTPS Domain
4. 为同一个 Service 创建 TCP Proxy，Target/Application Port 填 `8080`
5. 保留 Railway 自动注入的 `PORT`、`RAILWAY_TCP_PROXY_DOMAIN`、`RAILWAY_TCP_PROXY_PORT`
6. 如需持久化身份和订阅 token，挂载 Railway Volume 到 `/data`

Railway 会提供 `RAILWAY_TCP_PROXY_DOMAIN`、`RAILWAY_TCP_PROXY_PORT`，因此不需要手工把 TCP Proxy 外部地址写死在代码里。citeturn2search0

订阅地址会写入 Volume 的 `/data/subscription_url.txt`，格式为：

```text
https://<RAILWAY_PUBLIC_DOMAIN>/sub/<persistent-token>
```

## 原有三服务模式

仓库仍然支持原来的三服务结构：

- `vision/` — VLESS + TCP + XTLS Vision + REALITY
- `xhttp/` — VLESS + XHTTP + REALITY
- `web/` — 3D 网站 + `/health` + 双节点订阅

分别设置 Root Directory：

- `/vision`
- `/xhttp`
- `/web`

两个 Xray Service 分别配置 TCP Proxy，Target 都指向内部 `8080`；Web Service 使用普通 HTTPS Domain。

## 为什么增加 Root 单服务模式

此前的部署失败日志显示 Railway 在仓库根目录使用 Railpack，并报告 `Script start.sh not found`，随后无法识别项目类型。fileciteturn10file0

本修复分支在仓库根目录补齐 `Dockerfile`、`railway.toml` 和完整 `scripts/`，让根目录成为一个自包含 Docker 部署单元。Railway 官方文档说明，根目录存在名为 `Dockerfile` 的文件时会使用 Dockerfile 构建；也可以通过 Config as Code 明确指定 `DOCKERFILE`。citeturn1search0turn1search2

## 重要修复

- 修复公共 `8080` 代理对 HTTP/XHTTP 请求头结束符判断错误的问题。
- Xray 与公共 HTTP/TCP 入口分离：`127.0.0.1:10085` → `0.0.0.0:8080`。
- Xray 启动前执行 `xray run -test -config`。
- 等待 Xray 实际监听后才创建 `/data/.xray-ready`。
- `/health` 在 Xray 未就绪时返回 `503`，就绪后返回 `200`。
- UUID、REALITY key、ML-KEM-768 material、订阅 token 均可通过 Volume 持久化。
- Railway TCP Proxy Host/Port 自动读取，不再要求手工复制外部端口。
- 删除/忽略 `__pycache__`、`.pyc`、临时文件，避免污染 Docker build context。

## 订阅

Root 单服务模式提供：

```text
https://<PUBLIC_DOMAIN>/sub/<TOKEN>
```

返回标准 Base64 VLESS subscription，节点为：

```text
VLESS + XHTTP + REALITY + ML-KEM-768
```

Railway TCP Proxy 的外部端口由 Railway 分配，客户端必须使用 Railway 提供的 **外部 Host + 外部 Port**，不能把内部 `8080` 当成客户端端口。citeturn2search2

## 测试顺序

1. `/health` 返回 `200 OK`
2. 3D 网站首页正常打开
3. `/sub/<token>` 返回 Base64 内容
4. 解码订阅，确认 `host:port` 是 Railway TCP Proxy 的外部地址
5. 单独测试 XHTTP 节点
6. 最后再考虑启用原有三服务双协议模式
