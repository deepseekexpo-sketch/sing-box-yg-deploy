#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成节点卡片 HTML（单文件，内嵌二维码，可直接双击打开）

供 deploy.py 调用，也可单独使用:
    python cards.py machine-1.2.3.4.json
"""

import base64
import html
import io
import json
import re
import sys

try:
    import qrcode
except ImportError:
    sys.exit("缺少依赖: pip install qrcode[pil]")

PROTO_ORDER = ["vless", "hysteria2", "tuic", "anytls", "vmess"]
PROTO_CN = {
    "vless": "Vless-Reality-Vision",
    "hysteria2": "Hysteria-2",
    "tuic": "Tuic-v5",
    "anytls": "AnyTLS",
    "vmess": "Vmess-WS",
}
PROTO_TRANSPORT = {"vless": "TCP", "vmess": "TCP", "anytls": "TCP",
                   "hysteria2": "UDP", "tuic": "UDP"}
PROTO_NOTE = {
    "vless": "伪装 apple.com，抗探测最强，日常首选",
    "hysteria2": "UDP 拥塞控制，弱网和高丢包线路下速度最快",
    "tuic": "基于 QUIC，0-RTT 握手，延迟低",
    "anytls": "新协议，TLS 指纹接近正常 HTTPS",
    "vmess": "标准端口，可再配置 CDN 优选 IP 抗封锁",
}
PROTO_CLIENT = {
    "vless": "v2rayN / NekoBox / Shadowrocket / sing-box",
    "hysteria2": "v2rayN / v2rayNG / NekoBox / Shadowrocket / sing-box",
    "tuic": "v2rayN / NekoBox / Shadowrocket",
    "anytls": "v2rayN / NekoBox / Shadowrocket",
    "vmess": "v2rayN / v2rayNG / NekoBox / Shadowrocket",
}

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VPN 节点卡片 · {ip}</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;padding:32px 24px 64px;background:#f6f7f9;color:#1a1a1a;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}}
.wrap{{max-width:920px;margin:0 auto}}
h1{{font-size:24px;margin:0 0 6px}}
.sub{{color:#666;font-size:14px;margin-bottom:28px}}
.meta{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:28px}}
.meta div{{background:#fff;border:1px solid #e4e6ea;border-radius:10px;padding:12px 14px}}
.meta span{{display:block;color:#888;font-size:12px;margin-bottom:4px}}
.meta b{{font-size:14px;font-weight:600;word-break:break-all}}
.card{{background:#fff;border:1px solid #e4e6ea;border-radius:14px;padding:20px;margin-bottom:18px}}
.card-head{{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}}
h2{{font-size:17px;margin:0 0 8px}}
.badge{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:5px;
 background:#e8f0fe;color:#1967d2;margin-right:6px;font-weight:600}}
.badge.gray{{background:#f0f1f3;color:#555}}
.qr{{width:110px;height:110px;border:1px solid #e4e6ea;border-radius:8px;flex-shrink:0}}
.note{{margin:14px 0 4px;font-size:13px;color:#444}}
.client{{margin:0;font-size:12px;color:#888}}
.linkbox{{background:#f6f7f9;border:1px solid #e4e6ea;border-radius:8px;padding:10px 12px;margin:12px 0 10px}}
code{{font-family:ui-monospace,Consolas,monospace;font-size:11.5px;word-break:break-all;line-height:1.5;color:#333}}
button.copy{{background:#1a1a1a;color:#fff;border:0;border-radius:7px;padding:7px 16px;font-size:13px;cursor:pointer}}
button.copy:hover{{background:#333}}
button.copy.sm{{padding:5px 12px;font-size:12px}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e4e6ea;border-radius:12px;overflow:hidden}}
td{{padding:12px 14px;border-bottom:1px solid #eef0f2;font-size:13px;vertical-align:middle}}
tr:last-child td{{border-bottom:0}}
td.k{{width:170px;color:#555;font-weight:600;white-space:nowrap}}
h3{{font-size:16px;margin:32px 0 12px}}
.tip{{background:#fffbea;border:1px solid #f5e6a8;border-radius:12px;padding:14px 16px;
 font-size:13px;line-height:1.8;color:#5c4a00}}
.tip b{{color:#332a00}}
</style>
</head>
<body>
<div class="wrap">
  <h1>VPN 节点卡片</h1>
  <div class="sub">Sing-box 五协议共存 · 更新于 {updated}</div>

  <div class="meta">
    <div><span>服务器 IP</span><b>{ip}</b></div>
    <div><span>UUID（密码）</span><b>{uuid}</b></div>
    <div><span>订阅密码</span><b>{sub_pass}</b></div>
    <div><span>服务状态</span><b>运行中</b></div>
  </div>

  <h3>订阅链接（推荐，一次导入全部节点）</h3>
  <table>{subs}</table>

  <h3>单协议节点</h3>
  {cards}

  <h3>使用提示</h3>
  <div class="tip">
    <b>手机（Shadowrocket / NekoBox / Clash）</b>：直接用「Sing-box 订阅」或「Clash 订阅」链接导入，也可以扫上面的码。<br>
    <b>电脑（v2rayN / Clash Verge）</b>：订阅 → 新建订阅 → 粘贴链接 → 更新订阅。<br>
    <b>选哪个协议</b>：日常刷网页看视频用 <b>Vless-Reality</b>；网络丢包严重、晚高峰卡顿换 <b>Hysteria-2</b>；延迟敏感（游戏/SSH）试 <b>Tuic-v5</b>。<br>
    <b>管理命令</b>：SSH 连上后输入 <code>sb</code> 进管理菜单 —— 9 查看节点、4 改端口、3-9 配 CDN 优选 IP、11 开 BBR、2 卸载。<br>
    <b>重新生成这张卡片</b>：<code>python cards.py machine-{ip}.json</code>
  </div>
</div>
<script>
function cp(id, btn){{
  const t = document.getElementById(id).innerText;
  navigator.clipboard.writeText(t).then(()=>{{
    const o = btn.innerText; btn.innerText='已复制';
    setTimeout(()=>btn.innerText=o, 1500);
  }});
}}
</script>
</body>
</html>"""


def b64_qr(data: str) -> str:
    qr = qrcode.QRCode(version=None, box_size=6, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1a1a1a", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def port_of(link: str) -> str:
    if link.startswith("vmess://"):
        try:
            raw = link.split("://", 1)[1]
            raw += "=" * (-len(raw) % 4)
            return str(json.loads(base64.b64decode(raw).decode()).get("port", "?"))
        except Exception:
            return "?"
    m = re.search(r"@[^:]+:(\d+)", link)
    return m.group(1) if m else "?"


def uuid_of(nodes: dict) -> str:
    link = nodes.get("vless") or nodes.get("hysteria2") or ""
    m = re.search(r"://([0-9a-fA-F-]{36})", link)
    return m.group(1) if m else "-"


def build_html(machine: dict) -> str:
    nodes = machine.get("nodes", {})
    subs = machine.get("subscriptions", {})

    sub_rows = []
    for i, (label, key) in enumerate([
            ("Clash / Mihomo 订阅", "clash"),
            ("Sing-box 订阅", "singbox"),
            ("聚合节点订阅(通用)", "aggregate")]):
        url = subs.get(key, "-")
        sub_rows.append(
            f'<tr><td class="k">{label}</td><td><code id="s{i}">{html.escape(url)}</code></td>'
            f'<td><button class="copy sm" onclick="cp(\'s{i}\', this)">复制</button></td></tr>')
    subs_html = "".join(sub_rows)

    cards = []
    for p in PROTO_ORDER:
        link = nodes.get(p)
        if not link:
            continue
        port = port_of(link)
        cards.append(f"""
  <div class="card">
    <div class="card-head">
      <div>
        <h2>{PROTO_CN[p]}</h2>
        <span class="badge">{PROTO_TRANSPORT[p]}</span>
        <span class="badge gray">端口 {port}</span>
      </div>
      <img class="qr" src="data:image/png;base64,{b64_qr(link)}" alt="qr">
    </div>
    <p class="note">{PROTO_NOTE[p]}</p>
    <p class="client">适用客户端：{PROTO_CLIENT[p]}</p>
    <div class="linkbox"><code id="l{p}">{html.escape(link)}</code></div>
    <button class="copy" onclick="cp('l{p}', this)">复制链接</button>
  </div>""")

    return TEMPLATE.format(
        ip=machine.get("ip", "-"),
        updated=machine.get("updated", "-"),
        uuid=uuid_of(nodes),
        sub_pass=machine.get("sub_pass", "-"),
        subs=subs_html,
        cards="".join(cards),
    )


def main():
    if len(sys.argv) < 2:
        sys.exit("用法: python cards.py machine-<ip>.json [输出.html]")
    with open(sys.argv[1], encoding="utf-8") as f:
        machine = json.load(f)
    out = sys.argv[2] if len(sys.argv) > 2 else f"nodes-{machine.get('ip', 'out')}.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(build_html(machine))
    print(f"已生成: {out}")


if __name__ == "__main__":
    main()
