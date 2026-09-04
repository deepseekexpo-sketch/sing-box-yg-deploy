# sing-box-yg-deploy

一台命令，在全新 Ubuntu VPS 上部署 **sing-box 五协议代理**，并自动输出订阅链接和节点卡片。

基于上游脚本 [yonggekkk/sing-box-yg](https://github.com/yonggekkk/sing-box-yg)（原仓库名 `sing-box_hysteria2_tuic_argo_reality` 会自动跳转）。本仓库只做三件事：**把交互式菜单变成非交互命令**、**自动开订阅**、**生成好看的节点卡片**。

仓库地址：https://github.com/deepseekexpo-sketch/sing-box-yg-deploy

> 与 [vpn-deploy-kit](https://github.com/deepseekexpo-sketch/vpn-deploy-kit) 的区别：那个是 3x-ui 面板 + Reality/Hysteria2 双协议；这个是 sing-box 五协议，无面板、更轻。

## 部署出什么

| 协议 | 传输 | 说明 |
|---|---|---|
| Vless-Reality-Vision | TCP | 伪装 apple.com，抗探测最强，日常首选 |
| Hysteria-2 | UDP | UDP 拥塞控制，高丢包线路下最快 |
| Tuic-v5 | UDP | 基于 QUIC，0-RTT，延迟低 |
| AnyTLS | TCP | 新协议，TLS 指纹接近正常 HTTPS |
| Vmess-WS | TCP | 标准端口，可再挂 CDN 优选 IP |

外加三条本地 IP 订阅链接（Clash / Sing-box / 聚合通用）。

## 快速开始

```bash
git clone https://github.com/deepseekexpo-sketch/sing-box-yg-deploy.git
cd sing-box-yg-deploy
pip install -r requirements.txt

# 最简：纯 IP、免域名、自签证书、随机端口
python deploy.py --host 1.2.3.4 --port 22 --user root --password '你的密码'

# 固定订阅端口（强烈建议，否则每次订阅地址都会变）
python deploy.py --host 1.2.3.4 --password 'xxx' --sub-port 54887
```

跑完会在 `machines/` 下生成：
- `machine-<ip>.json` —— 机器与节点原始数据
- `nodes-<ip>.html` —— 节点卡片，双击打开，含二维码和一键复制

之后想重新出卡片，不用连服务器：

```bash
python cards.py machines/machine-1.2.3.4.json
```

## 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--host` | 必填 | VPS IP 或域名 |
| `--port` | 22 | SSH 端口 |
| `--user` | root | SSH 用户名 |
| `--password` | `$VPN_PASS` | SSH 密码，建议用环境变量避免进命令行历史 |
| `--sub-pass` | kiwi2026 | 订阅链接路径密码 |
| `--sub-port` | 随机 | 订阅服务端口。**建议固定**，不固定每次重跑订阅地址都会变 |
| `--core` | latest | `latest` 最新正式版；`1.10.7` 支持 geosite 分流但无 AnyTLS |
| `--cert` | selfsign | `selfsign` 纯 IP 免域名；`acme` 需域名证书 |
| `--ports` | 随机 | 自定义 5 个端口，顺序：vless vmess hy2 tuic anytls |
| `--skip-install` | 关 | 跳过安装，只重开订阅 + 刷新卡片（机器已装过时用） |
| `--bbr` | 关 | 开启 BBR+FQ 加速（**会重启 VPS**） |
| `--out` | machines | 输出目录 |

密码走环境变量：

```bash
export VPN_PASS='你的密码'
python deploy.py --host 1.2.3.4
```

## 服务器要求

- Ubuntu / Debian / CentOS / Alpine（**不支持 Arch**）
- amd64 或 arm64
- 能访问 GitHub（否则 sing-box 内核下载失败）
- 未装过 sing-box（已装会拒绝重跑，先 `--skip-install` 或到服务器上 `sb` → `2` 卸载）

## 日常管理

SSH 连上服务器，输入 `sb` 进管理菜单：

| 菜单 | 作用 |
|---|---|
| 9 | 刷新并查看所有节点和订阅链接 |
| 4 | 更改主端口 / 添加多端口跳跃复用 |
| 3-2 | 更换全协议 UUID、Vmess path |
| 3-3 | 设置 Argo 临时 / 固定隧道 |
| 3-9 | Vmess 设置 CDN 优选 IP（抗封锁） |
| 11 | 一键原版 BBR+FQ 加速 |
| 2 | 卸载 |

改完端口后，本地重跑一次 `--skip-install` 就能刷新卡片。

## 非交互原理

脚本原本要手动选 5 次，这里用 `printf` 喂进去：

```
1  主菜单：安装
1  关闭防火墙、放通端口
1  内核：latest（2 = 1.10.7）
1  证书：自签（2 = Acme 域名证书）
1  端口：随机（2 = 自定义，会再依次问 5 个端口）
```

订阅则是 `3 → 8 → 1 → <密码> → <端口>`。

**输入个数必须精确**，多出来的会被末尾主菜单吃掉，触发重复安装。

## 踩坑

| 症状 | 原因 | 处理 |
|---|---|---|
| 装完提示"未安装" | 内核下载失败 | 确认 VPS 能访问 GitHub，重跑（脚本幂等） |
| 端口随机后连不上 | 随机端口在 10000-65535 | 脚本已自动关防火墙；阿里云/腾讯云等还需后台安全组放行 |
| 提示"不是双栈VPS" | 纯 IPv4 机器 | 正常提示，不是错误 |
| Vmess 端口是 8880/8080/2052 等 | 脚本专为 CDN 优选留的标准端口 | 正常 |
| apt 阶段卡住 | 缺 `DEBIAN_FRONTEND=noninteractive` | 部署脚本已处理，手动跑时需自己 export |
| 重跑后旧订阅链接失效 | 订阅服务被重置，端口也随机变了 | 加 `--sub-port` 固定 |

## 安全

- 命令行传密码会进 shell history，生产环境用 `VPN_PASS` 环境变量
- `machines/` 下的产物含真实 IP 和节点链接，已被 `.gitignore` 排除，**不要手动 force add**
- 上游脚本为第三方代码，执行前建议自行审一遍 `sb.sh`

## 许可

上游 sing-box-yg 脚本遵循其自身许可；本仓库脚本可自由使用。
