#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sing-box-yg 五协议 VPN 一键部署工具

在全新 Ubuntu VPS 上部署 Vless-Reality / Vmess-WS / Hysteria2 / Tuic-v5 / AnyTLS，
并输出订阅链接与节点卡片 HTML。

用法:
    # 全新部署(纯 IP 免域名、自签证书、随机端口)
    python deploy.py --host 1.2.3.4 --port 22 --user root --password xxx

    # 指定订阅密码 + 开启 BBR
    python deploy.py --host 1.2.3.4 --password xxx --sub-pass mypass --bbr

    # 机器已装过, 只想重新开订阅 + 刷新节点卡片
    python deploy.py --host 1.2.3.4 --password xxx --skip-install

    # 密码走环境变量, 不落命令行历史
    export VPN_PASS=xxx
    python deploy.py --host 1.2.3.4

依赖: pip install -r requirements.txt
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request

try:
    import paramiko
except ImportError:
    sys.exit("缺少依赖, 请先执行: pip install -r requirements.txt")

from cards import build_html, PROTO_ORDER, PROTO_CN, port_of

SB_URL = "https://raw.githubusercontent.com/yonggekkk/sing-box-yg/main/sb.sh"


# --------------------------------------------------------------------------
# SSH
# --------------------------------------------------------------------------
class VPS:
    def __init__(self, host, port, user, password):
        self.host = host
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(host, port=port, username=user, password=password,
                            timeout=30, banner_timeout=30, auth_timeout=30,
                            allow_agent=False, look_for_keys=False)

    def run(self, cmd, timeout=120, idle=90):
        """执行命令, 返回输出。idle = 无新输出的空闲秒数上限"""
        chan = self.client.get_transport().open_session()
        chan.settimeout(timeout)
        chan.get_pty(term="xterm", width=200, height=60)
        chan.exec_command(cmd)

        buf = b""
        last = time.time()
        while True:
            if chan.recv_ready():
                data = chan.recv(65536)
                if not data:
                    break
                buf += data
                last = time.time()
            elif chan.exit_status_ready():
                while chan.recv_ready():
                    buf += chan.recv(65536)
                break
            else:
                if time.time() - last > idle:
                    buf += b"\n[!] idle timeout\n"
                    break
                time.sleep(0.3)
        return buf.decode("utf-8", "ignore")

    def close(self):
        try:
            self.client.close()
        except Exception:
            pass


# --------------------------------------------------------------------------
# 步骤
# --------------------------------------------------------------------------
def step(msg):
    print(f"\n> {msg}", flush=True)


def probe(vps):
    out = vps.run(
        "cat /etc/os-release | grep PRETTY_NAME; uname -m; "
        "curl -s4 --max-time 8 ip.sb; echo; "
        "curl -sI --max-time 10 https://github.com | head -1; "
        "ls -d /etc/s-box 2>/dev/null || echo 'NOT_INSTALLED'", timeout=90)
    info = {"raw": out}
    m = re.search(r'PRETTY_NAME="([^"]+)"', out)
    info["os"] = m.group(1) if m else "未知"
    info["arch"] = out.split("\n")[1].strip() if len(out.split("\n")) > 1 else "?"
    info["ip"] = ""
    for line in out.split("\n"):
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", line.strip()):
            info["ip"] = line.strip()
            break
    info["github"] = "可达" if "200" in out else "不可达(可能装不上内核!)"
    info["installed"] = "NOT_INSTALLED" not in out
    return info


def install(vps, core, cert, ports):
    """非交互安装。输入顺序: 主菜单1 → 关防火墙 → 内核 → 证书 → 端口"""
    seq = ["1", "1",
           "1" if core == "latest" else "2",
           "1" if cert == "selfsign" else "2"]
    if ports:
        seq.append("2")
        seq.extend(ports)
    else:
        seq.append("1")
    stdin = "\\n".join(seq) + "\\n"
    cmd = (f"export DEBIAN_FRONTEND=noninteractive; "
           f"curl -Ls {SB_URL} -o /root/sb.sh && chmod +x /root/sb.sh && "
           f"printf '{stdin}' | bash /root/sb.sh 2>&1")
    return vps.run(cmd, timeout=900, idle=240)


def verify(vps):
    out = vps.run("systemctl is-active sing-box; ss -tunlp | grep sing-box; "
                  "/etc/s-box/sing-box version 2>/dev/null | head -1", timeout=60)
    return out


def setup_subscription(vps, sub_pass, sub_port=None):
    """菜单 3 → 8 → 1: 重置安装本地 IP 订阅。sub_port 不传则随机(地址会变)"""
    stdin = f"3\\n8\\n1\\n{sub_pass}\\n{sub_port or ''}\\n"
    return vps.run(f"printf '{stdin}' | sb 2>&1", timeout=240, idle=120)


def run_bbr(vps):
    return vps.run("printf '11\\n\\n' | sb 2>&1", timeout=600, idle=180)


def parse_subs(text):
    """从脚本输出里抓三条订阅链接"""
    subs = {}
    for u in re.findall(r"http://[^\s'\"`]+", text):
        if "/clmi.yaml" in u:
            subs["clash"] = u
        elif "/sbox.json" in u:
            subs["singbox"] = u
        elif "/jhsub.txt" in u:
            subs["aggregate"] = u
    return subs


def fetch_nodes(agg_url):
    """从聚合订阅抓取各协议分享链接"""
    req = urllib.request.Request(agg_url, headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=20) as r:
        text = r.read().decode("utf-8")
    nodes = {}
    for line in text.split("\n"):
        line = line.strip()
        for p in PROTO_ORDER:
            if line.startswith(p + "://"):
                nodes.setdefault(p, line)
    return nodes


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="sing-box-yg 五协议 VPN 一键部署")
    ap.add_argument("--host", required=True, help="VPS IP 或域名")
    ap.add_argument("--port", type=int, default=22, help="SSH 端口 (默认 22)")
    ap.add_argument("--user", default="root", help="SSH 用户名 (默认 root)")
    ap.add_argument("--password", default=os.environ.get("VPN_PASS"),
                    help="SSH 密码 (建议用 VPN_PASS 环境变量)")
    ap.add_argument("--sub-pass", default="kiwi2026", help="订阅链接路径密码")
    ap.add_argument("--sub-port", type=int, default=None,
                    help="订阅服务端口。不指定则每次随机(订阅地址会变), 建议固定")
    ap.add_argument("--core", choices=["latest", "1.10.7"], default="latest",
                    help="内核版本 (1.10.7 支持 geosite 分流但无 AnyTLS)")
    ap.add_argument("--cert", choices=["selfsign", "acme"], default="selfsign",
                    help="证书方式 (selfsign=纯IP免域名, acme=需域名)")
    ap.add_argument("--ports", nargs=5, metavar="P",
                    help="自定义 5 个端口, 顺序: vless vmess hy2 tuic anytls")
    ap.add_argument("--skip-install", action="store_true",
                    help="跳过安装, 只重开订阅 + 刷新卡片")
    ap.add_argument("--bbr", action="store_true",
                    help="开启 BBR+FQ 加速 (会重启 VPS)")
    ap.add_argument("--out", default="machines", help="输出目录 (默认 machines/)")
    args = ap.parse_args()

    if not args.password:
        sys.exit("需要 SSH 密码: 用 --password 或设置 VPN_PASS 环境变量")
    os.makedirs(args.out, exist_ok=True)

    vps = VPS(args.host, args.port, args.user, args.password)
    try:
        step("探测机器")
        info = probe(vps)
        print(f"  系统: {info['os']}  架构: {info['arch']}")
        print(f"  出口IP: {info['ip']}   GitHub: {info['github']}")
        print(f"  已安装: {'是' if info['installed'] else '否'}")

        if not args.skip_install:
            if info["installed"]:
                sys.exit("这台机器已装过 sing-box (存在 /etc/s-box)。"
                         "要重装请先在 VPS 上执行 sb → 2 卸载, "
                         "或加 --skip-install 只重开订阅。")
            if "不可达" in info["github"]:
                print("  警告: GitHub 不可达, 内核很可能下载失败")

            step("安装 sing-box (约 2-3 分钟)")
            out = install(vps, args.core, args.cert, args.ports)
            if "安装成功" not in out:
                tail = "\n".join(out.strip().split("\n")[-15:])
                sys.exit(f"安装未成功, 末尾输出:\n{tail}")
            print("  安装成功")
            for line in out.split("\n"):
                if "端口：" in line or "端口:" in line:
                    print("   " + line.strip())
            if args.bbr:
                step("开启 BBR+FQ (会重启)")
                run_bbr(vps)

        step("验证服务")
        v = verify(vps)
        print("  状态: " + (v.strip().split("\n")[0] if v else "未知"))
        for line in v.split("\n"):
            if "sing-box" in line and ("LISTEN" in line or "UNCONN" in line):
                print("   " + " ".join(line.split()[:5]))

        step("配置本地 IP 订阅")
        sub_out = setup_subscription(vps, args.sub_pass, args.sub_port)
        subs = parse_subs(sub_out)
        if not subs.get("aggregate"):
            sys.exit("未能解析出订阅链接, 原始输出:\n" +
                     "\n".join(sub_out.strip().split("\n")[-20:]))
        for k, label in [("clash", "Clash/Mihomo"), ("singbox", "Sing-box"),
                         ("aggregate", "聚合通用")]:
            print(f"  {label}: {subs.get(k, '-')}")

        step("抓取节点链接")
        nodes = fetch_nodes(subs["aggregate"])
        if not nodes:
            sys.exit("订阅里没有解析到节点, 请检查聚合链接")
        for p in PROTO_ORDER:
            if p in nodes:
                print(f"  {PROTO_CN[p]:24s} 端口 {port_of(nodes[p])}")

        step("生成节点卡片")
        machine = {
            "host": args.host,
            "ip": info["ip"] or args.host,
            "ssh_port": args.port,
            "sub_pass": args.sub_pass,
            "sub_port": args.sub_port,
            "subscriptions": subs,
            "nodes": nodes,
            "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        html_path = os.path.join(args.out, f"nodes-{args.host}.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(build_html(machine))
        json_path = os.path.join(args.out, f"machine-{args.host}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(machine, f, ensure_ascii=False, indent=2)
        print(f"  HTML: {html_path}")
        print(f"  JSON: {json_path}")

        print("\n完成。用上面的订阅链接导入客户端即可。")
    finally:
        vps.close()


if __name__ == "__main__":
    main()
