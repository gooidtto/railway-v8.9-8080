# Railway Xray v8.9-R — Dual Protocol Integrated

以现有 Railway Xray 项目为核心，升级为 **两种 VLESS 协议共存的三服务架构**：

- `vision/` — VLESS + TCP + XTLS Vision + REALITY
- `xhttp/` — VLESS + XHTTP + REALITY
- `web/` — 原有 3D 网站 + `/health` + 受保护的双节点订阅

## Railway 部署结构

必须创建 3 个 Railway Services，并分别设置 Root Directory：

- `/vision`
- `/xhttp`
- `/web`

### 1. Vision
部署后给 `vision` 添加 TCP Proxy，Target 指向内部 `8080`。

### 2. XHTTP
部署后给 `xhttp` 添加 TCP Proxy，Target 指向内部 `8080`。

### 3. Web
普通 HTTPS Domain，监听 `8080`。

## Web 环境变量

把两个 Xray Service 启动日志中的参数和 Railway TCP Proxy 的外部 Host/Port 填入：

```text
SUB_TOKEN=<随机长字符串>
VISION_ENCRYPTION=<vision 服务启动日志中的 VLESS_ENCRYPTION>\nXHTTP_ENCRYPTION=<xhttp 服务启动日志中的 VLESS_ENCRYPTION>\n
VISION_UUID=<vision 日志 UUID>
VISION_HOST=<vision TCP Proxy host>
VISION_PORT=<vision TCP Proxy public port>
VISION_PUBLIC_KEY=<vision REALITY_PUBLIC_KEY>
VISION_SNI=<vision REALITY_SNI>
VISION_SHORT_ID=<vision REALITY_SHORT_ID>

XHTTP_UUID=<xhttp 日志 UUID>
XHTTP_HOST=<xhttp TCP Proxy host>
XHTTP_PORT=<xhttp TCP Proxy public port>
XHTTP_PUBLIC_KEY=<xhttp REALITY_PUBLIC_KEY>
XHTTP_SNI=<xhttp REALITY_SNI>
XHTTP_SHORT_ID=<xhttp REALITY_SHORT_ID>

XHTTP_PATH=/xhttp
XHTTP_MODE=auto
```

> 注意：Railway TCP Proxy 的 **外部端口** 由 Railway 分配，客户端不能直接使用 `8080/8080`。

## 订阅

Web 服务部署完成后：

```text
https://<WEB_DOMAIN>/sub/<SUB_TOKEN>
```

返回的是标准 Base64 VLESS subscription，里面同时包含两个节点：

1. `VLESS-TCP-Vision-REALITY`
2. `VLESS-XHTTP-REALITY`

## 推荐测试顺序

1. 先单独测试 Vision 节点。
2. 再单独测试 XHTTP 节点。
3. 最后测试 `/sub/<token>`。
4. 确认客户端可以解析订阅后，再做双节点切换测试。

本项目没有让 Web 服务代理 Xray 流量；两个 Xray 服务各自通过 Railway TCP Proxy 暴露，避免 HTTP 网站层与 TCP 代理层互相干扰。

## 端口约定

Vision Service：Xray 内部监听 `8080`，Railway TCP Proxy Target = `8080`。
XHTTP Service：Xray 内部监听 `8080`，Railway TCP Proxy Target = `8080`。

两个 Service 是独立容器，因此可以同时使用内部端口 `8080`。
Web Service 的 HTTP 监听也使用 `8080`，但它位于独立 Service，因此不冲突。


## 重要：Xray Service 的 8080 修正版

Vision 和 XHTTP 都直接让 Xray 监听 `0.0.0.0:8080`。
不要再在同一 Service 内启动 HTTP health server，也不要把 Railway Healthcheck Path 设置为 `/health`。

Railway TCP Proxy 的 Target Port：
- vision → `8080`
- xhttp → `8080`

Railway 会自动提供 `PORT`；本项目在 Xray Service 中将其作为 Xray 监听端口使用。
Railway 官方文档也要求应用监听 Railway 提供的 `PORT`，TCP Proxy 则配置到该内部端口。citeturn0search0turn0search1
