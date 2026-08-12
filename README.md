# Railway Xray v8.9-R — Dual Protocol + Single-Service 8080

本仓库当前采用 **单服务统一 8080 Gateway** 架构：Railway HTTP Domain 与 Railway TCP Proxy 都进入 `8080`，Gateway 再按首包协议把流量转发到本机 Xray。

## 当前测试基线

- `8080`：唯一公网 Gateway；同时承载 HTTP/HTTPS Domain 与 Railway TCP Proxy
- `10087`：Xray 私有 VLESS + XHTTP + REALITY inbound，只监听本机
- `10086`：Xray 私有 VLESS + XHTTP HTTP inbound，只监听本机
- Railway TCP Proxy：**Target/Application Port 必须设置为 `8080`**

```text
HTTPS Domain
railway-v89-8080-production.up.railway.app:443
                    |
                    v
                  :8080
              unified gateway
               |       |
              /        +-- /health
                       +-- /sub/<token>
                       +-- HTTP XHTTP -> 127.0.0.1:10086

Railway TCP Proxy
<railway-tcp-domain>:<external-port>
                    |
                    v
                  :8080
                    |
             protocol classify
               |            |
          TLS/REALITY       HTTP/XHTTP
               |            |
               v            v
        127.0.0.1:10087  127.0.0.1:10086
               |
               v
       Xray VLESS/REALITY
```

## Railway Networking 设置

1. Service Root Directory：仓库根目录 `/`
2. 使用根目录 `Dockerfile`
3. HTTP/HTTPS Domain Target Port：`8080`
4. **REALITY 的 Railway TCP Proxy Target/Application Port：`8080`**
5. 不要把 Railway TCP Proxy 指向 `10085`、`10086` 或 `10087`；这些是容器内部端口
6. Railway Volume（推荐）挂载到 `/data`，用于持久化 UUID、REALITY key、VLESS ML-KEM-768 material 和 subscription token

## TCP Proxy Endpoint

多个 Railway TCP Proxy 同时存在时，不依赖自动变量猜测正确节点。优先明确设置：

```text
XRAY_TCP_PROXY_HOST=<TCP Proxy 外部域名>
XRAY_TCP_PROXY_PORT=<TCP Proxy 外部端口>
```

例如：

```text
XRAY_TCP_PROXY_HOST=maglev.proxy.rlwy.net
XRAY_TCP_PROXY_PORT=50192
```

程序生成 REALITY 订阅时使用该公网 endpoint；Gateway 内部统一接收端口仍然是 `8080`。

## 订阅

```text
https://<RAILWAY_PUBLIC_DOMAIN>/sub/<persistent-token>
```

正常情况下订阅包含两个节点：

1. HTTPS + XHTTP：`<public-domain>:443`
2. Railway TCP Proxy + XHTTP + REALITY：`<tcp-proxy-host>:<tcp-proxy-port>`

第二个节点的公网 host/port **不能写成 `127.0.0.1`、`10087` 或其他内部端口**。

如果没有可用的公网 TCP endpoint，程序应 fail closed，而不是生成一个看似正常但实际不可达的节点。

## 当前日志诊断

最新日志已经证明统一 Gateway 本身可以正确工作：

- `GET /health` 被识别为 HTTP
- TLS ClientHello 被识别为 `tls-reality` 并连接 `127.0.0.1:10087`
- XHTTP GET/POST 被识别为 HTTP 并连接 `127.0.0.1:10086`
- XHTTP 存在成功的 `RELAY_END`

因此看到 `ML-KEM-768 handshake failed > chacha20poly1305: message authentication failed` 时，应优先检查**客户端使用的订阅是否来自当前 `/data` 的 ML-KEM-768 encryption material**，而不是继续修改 8080 Gateway 路由。旧订阅、旧 Volume 或混用不同部署生成的节点参数，都可能造成该错误。

## 验收标准

部署后检查：

```text
TCP subscription endpoint: <指定 TCP Proxy>
Railway TCP application port: 8080
Xray ready; unified-gateway=8080 reality=10087 xhttp=10086
```

然后：

1. `GET /health` → `200 OK`
2. `GET /sub/<token>` → `200`，返回 Base64 VLESS subscription
3. 订阅必须包含 HTTPS + XHTTP 节点
4. 订阅必须包含 Railway TCP Proxy + REALITY + XHTTP 节点
5. Railway TCP Proxy 日志必须能看到 `8080` Gateway 接收到 TLS ClientHello
6. 日志应出现 `UPSTREAM_CONNECTED ... target=127.0.0.1:10087 kind=tls-reality`
7. XHTTP 日志应出现 `UPSTREAM_CONNECTED ... target=127.0.0.1:10086 kind=http-xhttp`
8. 只有在 Gateway 已正确转发后，才继续判断 ML-KEM-768 / VLESS authentication 参数

## 重要设计约束

- 不修改已经验证正常的 HTTPS/XHTTP 节点参数来修复 REALITY。
- 不把 Railway 外部 TCP port 当作容器内部 port。
- `8080` 是 Railway 公网 Gateway；`10086/10087` 只用于容器内部通信。
- UUID、REALITY key、ML-KEM-768 material、订阅 token 必须通过 `/data` 持久化。
- 生成的 `client.json` 使用 Xray 当前 `realitySettings.publicKey` 字段。
- `XRAY_TCP_PROXY_HOST/PORT` 优先作为 REALITY 公网 endpoint。
