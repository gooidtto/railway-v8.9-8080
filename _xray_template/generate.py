import json, os
from pathlib import Path

def E(k, d=None, required=False):
    v=os.getenv(k,d)
    if required and not v: raise SystemExit("ERROR: missing "+k)
    return v

kind=E("PROTOCOL","xhttp")
port=int(E("XRAY_PORT","10085"))
cfg=Path(E("XRAY_CONFIG","/etc/xray/config.json"))
uuid=E("UUID",required=True)
private=E("PRIVATE_KEY",required=True)
decryption=E("VLESS_DECRYPTION",required=True)
target=E("REALITY_TARGET","www.cloudflare.com:443")
sni=E("REALITY_SNI",target.rsplit(":",1)[0])
sid=E("SHORT_ID","50175c035ee132")

ss={"network":"tcp" if kind=="vision" else "xhttp","security":"reality",
    "realitySettings":{"show":False,"target":target,"xver":0,"serverNames":[sni],
                       "privateKey":private,"shortIds":[sid]}}
client={"id":uuid,"flow":"xtls-rprx-vision"} if kind=="vision" else {"id":uuid}
if kind=="xhttp":
    ss["xhttpSettings"]={"path":E("XHTTP_PATH","/xhttp"),"mode":E("XHTTP_MODE","auto")}

config={"log":{"loglevel":E("XRAY_LOGLEVEL","info")},
        "inbounds":[{"listen":"127.0.0.1","port":port,"protocol":"vless",
                     "settings":{"clients":[client],"decryption":decryption},
                     "streamSettings":ss}],
        "outbounds":[{"protocol":"freedom","tag":"direct"}]}
cfg.parent.mkdir(parents=True,exist_ok=True)
tmp=str(cfg)+".tmp"
Path(tmp).write_text(json.dumps(config,indent=2)+"\n",encoding="utf-8")
os.chmod(tmp,0o600); os.replace(tmp,cfg)
