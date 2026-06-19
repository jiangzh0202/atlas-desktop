#!/usr/bin/env python3
"""
元策·擎天 — 客户站一键部署
支持两种模式：
  模式1（子域名）:  python3 deploy_client.py --slug enong --company "恩同动力"
  模式2（自定义域名）: python3 deploy_client.py --domain syenter.com --slug enong --company "SY Enter"

客户 DNS 配置要求（自定义域名）：
  将域名的 A 记录指向: 111.229.196.22
  （TTL 建议设 600，生效后再执行本脚本做 SSL）
"""

import sys, os, subprocess, argparse, shutil
from pathlib import Path

# ─── 常量 ───
ATLAS_PORTAL = "http://127.0.0.1:3093"
SERVER_IP = "111.229.196.22"
DEFAULT_ADMIN = "admin@traceclaw.cn"

# ─── nginx 模板 ───
NGINX_TEMPLATE = """# {company} — 元策·擎天
server {{
    listen 80;
    server_name {server_names};

    root {site_dir};
    index index.html;

    # 图片等静态资源缓存
    location /images/ {{
        expires 30d;
        add_header Cache-Control "public, immutable";
    }}

    # ─── 元策·擎天 引擎代理 ───
    location /login       {{ proxy_pass {portal}; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto $scheme; }}
    location /admin       {{ proxy_pass {portal}; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto $scheme; }}
    location /dashboard   {{ proxy_pass {portal}; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto $scheme; }}
    location /quotation   {{ proxy_pass {portal}; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto $scheme; }}
    location /procurement {{ proxy_pass {portal}; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto $scheme; }}
    location /parts       {{ proxy_pass {portal}; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto $scheme; }}
    location /history     {{ proxy_pass {portal}; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto $scheme; }}
    location /stock       {{ proxy_pass {portal}; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto $scheme; }}
    location /customers   {{ proxy_pass {portal}; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto $scheme; }}
    location /rules       {{ proxy_pass {portal}; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto $scheme; }}
    location /agents      {{ proxy_pass {portal}; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto $scheme; }}
    location /trade       {{ proxy_pass {portal}; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto $scheme; }}
    location /pricing     {{ proxy_pass {portal}; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto $scheme; }}
    location /api/        {{ proxy_pass {portal}; proxy_set_header Host $host; proxy_set_header X-Real-IP $remote_addr; proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; proxy_set_header X-Forwarded-Proto $scheme; }}
    location = /atlas.js  {{ proxy_pass {portal}; proxy_set_header Host $host; }}
    location = /style.css {{ proxy_pass {portal}; proxy_set_header Host $host; }}
    location = /logout    {{ proxy_pass {portal}; proxy_set_header Host $host; }}

    # SPA fallback
    location / {{
        try_files $uri $uri/ /index.html;
    }}
}}

# HTTPS 版本（SSL 签发后由 certbot 自动追加）
"""


def main():
    parser = argparse.ArgumentParser(description="元策·擎天 客户站一键部署")
    parser.add_argument("--slug", required=True, help="客户短标识（如 enong），用于目录名和子域名")
    parser.add_argument("--company", required=True, help="公司展示名称（如 恩同动力）")
    parser.add_argument("--domain", default=None, help="客户自有域名（如 syenter.com）。不传则使用 slug.traceclaw.cn")
    parser.add_argument("--company-id", default=None, help="Atlas 中的 company_id（默认自动生成 COMPANY-{slug}）")
    parser.add_argument("--email", default=None, help="管理员邮箱（certbot 紧急联系人）")
    parser.add_argument("--skip-ssl", action="store_true", help="跳过 SSL 签发（DNS 未就绪时使用）")
    parser.add_argument("--dry-run", action="store_true", help="仅打印配置，不执行")

    args = parser.parse_args()

    if not args.email:
        args.email = f"admin@{args.slug}.com" if not args.domain else f"admin@{args.domain}"

    # 计算域名
    if args.domain:
        primary_domain = args.domain
        server_names = f"{args.domain} www.{args.domain}"
        config_filename = args.domain.replace(".", "_")
    else:
        primary_domain = f"{args.slug}.traceclaw.cn"
        server_names = primary_domain
        config_filename = args.slug

    site_dir = f"/srv/clients/{args.slug}"
    nginx_path = f"/etc/nginx/sites-available/{config_filename}"
    enable_link = f"/etc/nginx/sites-enabled/{config_filename}"

    print(f"""
╔══════════════════════════════════════════╗
║  元策·擎天 客户站部署                     ║
╠══════════════════════════════════════════╣
║  公司: {args.company:<33}║
║  标识: {args.slug:<33}║
║  域名: {primary_domain:<33}║
║  目录: {site_dir:<33}║
╚══════════════════════════════════════════╝
""")

    if args.dry_run:
        print("[DRY RUN] 仅预览，不执行。\n")
        nginx_conf = NGINX_TEMPLATE.format(
            company=args.company,
            server_names=server_names,
            site_dir=site_dir,
            portal=ATLAS_PORTAL
        )
        print(nginx_conf)
        return

    # ─── Step 1: 创建网站目录 ───
    os.makedirs(site_dir, exist_ok=True)
    print(f"[1/5] ✅ 目录已创建: {site_dir}")

    # ─── Step 2: 写入首页模板 ───
    index_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{args.company}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;color:#1a1a2e;background:#f8f9fa}}
nav{{display:flex;align-items:center;padding:16px 40px;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.08);position:sticky;top:0;z-index:10}}
nav .logo{{font-size:20px;font-weight:700}}
nav .logo span{{color:#7ecf5e}}
nav .links{{margin-left:auto;display:flex;gap:24px;align-items:center}}
nav a{{text-decoration:none;color:#555;font-size:14px}}
nav .btn{{background:linear-gradient(135deg,#7ecf5e,#5cb85c);color:#fff;padding:10px 24px;border-radius:10px;font-weight:600;text-decoration:none;transition:all .3s}}
nav .btn:hover{{transform:translateY(-1px);box-shadow:0 4px 16px rgba(126,207,94,.3)}}
.hero{{text-align:center;padding:120px 40px 60px}}
.hero h1{{font-size:48px;font-weight:800;margin-bottom:16px}}
.hero p{{font-size:18px;color:#666;max-width:600px;margin:0 auto 40px;line-height:1.8}}
footer{{text-align:center;padding:40px;color:#999;font-size:13px;border-top:1px solid #eee}}
</style>
</head>
<body>
<nav>
  <div class="logo">{args.company}</div>
  <div class="links">
    <a href="#">首页</a>
    <a href="#">产品</a>
    <a href="#">关于</a>
    <a href="/login" class="btn">管理后台</a>
  </div>
</nav>
<section class="hero">
  <h1>{args.company}</h1>
  <p>由 元策·擎天 AI 引擎驱动<br>智能报价 · 采购管理 · 库存预警</p>
  <a href="/login" class="btn" style="display:inline-block">进入管理后台 →</a>
</section>
<footer>© 2026 {args.company} | Powered by 元策·擎天</footer>
</body>
</html>"""
    with open(os.path.join(site_dir, "index.html"), "w") as f:
        f.write(index_html)
    print(f"[2/5] ✅ 首页模板已写入: {site_dir}/index.html")

    # ─── Step 3: 写 nginx 配置 ───
    nginx_conf = NGINX_TEMPLATE.format(
        company=args.company,
        server_names=server_names,
        site_dir=site_dir,
        portal=ATLAS_PORTAL
    )
    with open(nginx_path, "w") as f:
        f.write(nginx_conf)
    print(f"[3/5] ✅ nginx 配置已写入: {nginx_path}")

    # ─── Step 4: 启用站点 ───
    if not os.path.exists(enable_link):
        os.symlink(nginx_path, enable_link)
        print(f"[4/5] ✅ 已启用: {enable_link}")
    else:
        print(f"[4/5] ⚠️ 已存在: {enable_link}（跳过 symlink）")

    # 测试并重载 nginx
    subprocess.run(["nginx", "-t"], check=True)
    subprocess.run(["systemctl", "reload", "nginx"], check=True)
    print(f"[4/5] ✅ nginx 已重载")

    # ─── Step 5: SSL 证书 ───
    if not args.skip_ssl:
        print(f"[5/5] 🔐 正在签发 SSL（{primary_domain}）…")
        try:
            # 对于自定义域名，先确保 HTTP 可达再签发
            cert_domains = f"-d {primary_domain}"
            if args.domain:
                cert_domains += f" -d www.{args.domain}"

            result = subprocess.run(
                ["certbot", "--nginx", *cert_domains.split(),
                 "--non-interactive", "--agree-tos",
                 "-m", args.email,
                 "--redirect"],
                timeout=120, capture_output=True, text=True
            )
            if result.returncode == 0:
                print(f"[5/5] ✅ SSL 已签发: https://{primary_domain}")
            else:
                print(f"[5/5] ⚠️ SSL 失败: {result.stderr[-200:]}")
                print(f"      DNS 可能未生效，稍后手动执行：")
                print(f"      sudo certbot --nginx -d {primary_domain}" + 
                      (f" -d www.{args.domain}" if args.domain else ""))
        except subprocess.TimeoutExpired:
            print(f"[5/5] ⚠️ SSL 超时，稍后手动执行 certbot")
        except Exception as e:
            print(f"[5/5] ⚠️ SSL 异常: {e}")
    else:
        print(f"[5/5] ⏭️ 跳过 SSL（--skip-ssl）")

    # ─── 总结 ───
    print(f"""
┌──────────────────────────────────────────┐
│  🎉 部署完成！                            │
├──────────────────────────────────────────┤
│  官网:     http://{primary_domain}           │
│  后台:     http://{primary_domain}/admin    │
│  登录:     http://{primary_domain}/login    │
│                                          │""")
    if args.domain:
        print(f"""│  📌 DNS 设置（给客户）:                  │
│    类型: A  名称: @  值: {SERVER_IP} │
│    类型: A  名称: www  值: {SERVER_IP} │
│    TTL: 600（生效后执行 certbot）          │""")
    print(f"""│                                          │
│  📁 网站文件: {site_dir}/index.html
│  ⚙️  nginx:   {nginx_path}
└──────────────────────────────────────────┘
""")


if __name__ == "__main__":
    main()
