# Deployment Checklist

## Vision service
- [ ] Root Directory = `/vision`
- [ ] TCP Proxy target = `8080`
- [ ] Persistent Volume = `/data`
- [ ] `REALITY_TARGET` / `REALITY_SNI` 可达
- [ ] 启动日志出现 `protocol=vision`
- [ ] `xray run -test` 成功

## XHTTP service
- [ ] Root Directory = `/xhttp`
- [ ] TCP Proxy target = `8080`
- [ ] Persistent Volume = `/data`
- [ ] `XHTTP_PATH=/xhttp`
- [ ] `XHTTP_MODE=auto`
- [ ] 启动日志出现 `protocol=xhttp`
- [ ] `xray run -test` 成功

## Web service
- [ ] Root Directory = `/web`
- [ ] HTTPS Domain 已生成
- [ ] `/health` 返回 `OK`
- [ ] `SUB_TOKEN` 已设置
- [ ] 两套 UUID / public key / TCP Proxy host/port 已填写
- [ ] `/sub/<token>` 返回 Base64 文本

## Client
- [ ] Vision 节点单独测试
- [ ] XHTTP 节点单独测试
- [ ] 双节点订阅测试


## Xray Service 关键设置（修正版）
- [ ] 不设置 Healthcheck Path
- [ ] 不额外启动 HTTP health server
- [ ] Xray 监听 `0.0.0.0:8080`
- [ ] TCP Proxy Target = `8080`
- [ ] 不手工设置 `PORT` 时，让 Railway 自动注入
