# Railway Xray v8.9-R — Dual Protocol + Single-Service 8080

本仓库保留原有的 **三服务双协议架构**，同时提供经过修复的 **Root 单服务 XHTTP/REALITY 模式**。

## 推荐：Root 单服务模式

目标是把 Railway 上的 **网站 + `/health` + 订阅 + XHTTP/REALITY + TCP Proxy** 分成两个明确的内部端口：

- `8080`：HTTP Domain → 网站、`/health`、`/sub/<token>`
- `10085`：TCP Proxy → Xray 原始 TCP/TLS/XHTTP 流量

这避免让 Railway TCP Proxy 的原始 XHTTP/REALITY 流量先经过 HTTP 分流器。

### 端口模型

```text
Railway HTTPS Domain ───────────────> :8080 health_proxy
                                      ├── /
                                      ├── /health
                                      └── /sub/<token>

Railway TCP Proxy :外部端口 ────────> :10085 Xray
                                      └── VLESS + XHTTP + REALITY
```

Xray 现在监听 `0.0.0.0:10085`，公共 HTTP 入口仍由 `health_proxy` 监听 `0.0.0.0:8080`。

Railway 官方支持同一个 Service 同时暴露 HTTP Domain 和 TCP Proxy；TCP Proxy 的目标端口可以独立指定。citeturn2search0turn2search6

### Railway 必须这样设置

1. Service Root Directory：仓库根目录 `/`
2. 使用根目录 `Dockerfile`
3. HTTP/HTTPS Domain 的 Target Port：`8080`
4. 同一个 Service 创建 TCP Proxy
5. **TCP Proxy 的 Application/Target Port：`10085`**
6. 保留 Railway 自动注入的 `PORT`、`RAILWAY_TCP_PROXY_DOMAIN`、`RAILWAY_TCP_PROXY_PORT`
7. 如需持久化身份和订阅 token，挂载 Railway Volume 到 `/data`

注意：**GitHub 代码提交可以触发 Railway 重新部署，但 TCP Proxy 的 Application/Target Port 是 Railway Service Networking 设置，不会因为 GitHub 代码变化自动从 `8080` 改成 `10085`。必须在 Railway 的 TCP Proxy 设置中确认一次。** Railway 官方文档明确要求创建 TCP Proxy 时指定内部 application port；`RAILWAY_TCP_APPLICATION_PORT` 也会反映该设置。citeturn2search0turn2search2

如果 Railway 当前仍显示：

```text
TCP Proxy: thomas.proxy.rlwy.net:56144
Application Port: 8080
```

请把 **Application Port 改为 `10085`**。

外部客户端仍使用 Railway 分配的 **Host + 外部 Port**，不要使用内部 `10085`。

### 订阅

订阅地址仍然是：

```text
https://<RAILWAY_PUBLIC_DOMAIN>/sub/<persistent-token>
```

返回标准 Base64 VLESS subscription：

```text
VLESS + XHTTP + REALITY + ML-KEM-768
```

`SERVER_HOST` / `SERVER_PORT` 自动使用 Railway 提供的 `RAILWAY_TCP_PROXY_DOMAIN` / `RAILWAY_TCP_PROXY_PORT`，因此 TCP Proxy 外部地址发生变化时，重新部署后订阅会自动生成新的外部地址。citeturn2search2

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
- HTTP Domain 和 TCP Proxy 使用独立内部端口。
- TCP Proxy 不再依赖 Python HTTP/TCP 分流器处理 XHTTP/REALITY 首包。
- Xray 启动前执行 `xray run -test -config`。
- 等待 Xray 实际监听后才创建 `/data/.xray-ready`。
- `/health` 在 Xray 未就绪时返回 `503`，就绪后返回 `200`。
- UUID、REALITY key、ML-KEM-768 material、订阅 token 均可通过 Volume 持久化。
- 生成的 `client.json` 使用 Xray 当前的 `realitySettings.publicKey` 字段。
- Railway TCP Proxy Host/Port 自动读取，不再要求手工把外部端口写死。

## 为什么这样改

最新生产日志已经证明：

```text
[tcp-proxy] ACCEPT ... upstream=127.0.0.1:10085 ready=True
```

但客户端对应连接没有任何首包：

```text
[tcp-proxy] ACCEPT peer=100.64.0.5:45766 ...
[tcp-proxy] ERROR peer=100.64.0.5:45766 type=TimeoutError detail=timed out
```

也就是说连接到达了 Railway Service，但原始客户端数据没有进入 Xray。让 TCP Proxy 直接连接 Xray 的 `10085` 可以移除这个额外的协议分流层，缩短链路并使问题边界清晰。

## 测试顺序

1. Railway HTTP Domain Target Port = `8080`
2. Railway TCP Proxy Application/Target Port = `10085`
3. `/health` 返回 `200 OK`
4. `/sub/<token>` 返回 Base64 内容
5. 导入订阅，确认节点仍使用 `thomas.proxy.rlwy.net:<Railway外部TCP端口>`
6. 测试 XHTTP 节点
7. 查看 Railway 日志，应看到 Xray `0.0.0.0:10085` 正常监听
8. 如果 TCP Proxy 直接到 Xray 后仍失败，再根据 Xray REALITY/VLESS 握手日志继续定位
