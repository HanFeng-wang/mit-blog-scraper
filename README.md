# MIT Admissions Blog Scraper

一个使用 Playwright 和 DrissionPage 分别实现的博客爬虫 Demo。两个脚本抓取
MIT Admissions 博客列表、进入每篇文章提取正文与图片，并输出字段相同的
CSV 文件，便于对比两种浏览器自动化实现。

目标站点：<https://mitadmissions.org/blogs/>

## 功能

- 使用 Playwright 与 DrissionPage 两套独立脚本，实现相同的抓取结果。
- 抓取文章标题、作者、Disqus 评论数、发布时间、正文和正文图片 URL。
- 支持多页抓取、文章数量限制、自定义输出路径和抓取间隔。
- 默认使用 1 页并在文章之间等待，减少对目标站点的请求压力。
- 支持显示浏览器和本地 HTTP 代理，便于排查页面或 Disqus 加载问题。
- 输出 UTF-8 BOM CSV，可直接用 Excel 打开中文和换行内容。

## 抓取字段

CSV 表头固定为：

`Title | Author | Comment Count | Time | Article Content | Images In Article`

| 字段 | 内容 |
| --- | --- |
| `Title` | 文章标题 |
| `Author` | 文章作者 |
| `Comment Count` | Disqus 评论数；未获取成功时写入 `N/A` |
| `Time` | 页面展示的发布日期，例如 `November 18, 2026` |
| `Article Content` | 正文纯文本，保留段落换行 |
| `Images In Article` | 正文图片 URL，每行一个，已去重 |

## 技术栈

- Python 3.11+
- Playwright 1.65.2
- DrissionPage 4.1.1.4
- Chrome、Edge 或 Playwright Chromium
- CSV 标准库

## 环境要求

运行前需要安装 Python，并能够访问 MIT Admissions 博客和 Disqus。Playwright
默认使用系统 Chrome；DrissionPage 会优先查找系统 Chrome，再尝试 Edge。没有
系统浏览器时，可以安装 Playwright 自带的 Chromium。

在 PowerShell 中确认 Python 版本：

```powershell
python --version
```

## 安装

克隆项目并安装依赖：

```powershell
git clone https://github.com/HanFeng-wang/mit-blog-scraper.git
cd mit-blog-scraper

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS 或 Linux 使用以下虚拟环境激活命令：

```bash
source .venv/bin/activate
```

如果没有系统 Chrome，可安装 Playwright Chromium：

```powershell
python -m playwright install chromium
```

## 运行

默认抓取最新 1 页，并生成各自的 CSV：

```powershell
python playwright_scraper.py
python drissionpage_scraper.py
```

输出文件：

- `output/playwright_blogs.csv`
- `output/drissionpage_blogs.csv`

如果使用 Playwright 自带 Chromium，将浏览器通道指定为空：

```powershell
python playwright_scraper.py --channel ""
```

DrissionPage 找不到浏览器时，可以显式指定 Chrome 或 Edge 路径：

```powershell
python drissionpage_scraper.py --browser-path "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

## 代理与 Disqus

页面正文通常可以直接抓取，但评论数由第三方 Disqus 提供。网络无法访问
Disqus 时，评论数字段会输出 `N/A`，脚本不会把未知值伪装成 `0`。如果需要
通过本地代理访问，先开启代理，再运行脚本：

```powershell
python playwright_scraper.py --proxy http://127.0.0.1:7892 --comment-timeout 20
python drissionpage_scraper.py --proxy http://127.0.0.1:7892 --comment-timeout 20
```

请将端口替换为本机代理的实际 HTTP 端口。浏览器能够继承系统代理时，直接运行
脚本即可；如果显式使用 `--proxy` 后出现 `ERR_PROXY_CONNECTION_FAILED`，先检查
系统代理是否开启、端口是否匹配，或去掉 `--proxy` 重新运行。

两种实现读取评论数的方式不同：

- Playwright 等待列表页中的 `.tease__comment-text` 完成渲染。
- DrissionPage 先读取页面中的 Disqus identifier，再批量请求
  `https://mitadmissions.disqus.com/count-data.js` 作为回退。

## 常用参数

两个脚本共享大部分参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--pages` | `1` | 抓取列表页数 |
| `--limit` | 不限 | 最多抓取的文章数 |
| `--output` | 各自的 `output/*.csv` | 自定义 CSV 输出路径 |
| `--delay` | `0.5` | 文章之间的基础等待秒数 |
| `--comment-timeout` | `8` | 等待或请求 Disqus 评论数的超时秒数 |
| `--timeout` | `60` | 页面加载超时秒数 |
| `--headed` | 关闭 | 显示浏览器窗口 |
| `--proxy` | 无 | 本地代理 URL |

示例：

```powershell
python playwright_scraper.py --pages 2 --limit 20 --output output/custom.csv
python drissionpage_scraper.py --pages 2 --limit 20 --headed
```

Playwright 额外支持 `--channel`，DrissionPage 额外支持 `--browser-path`。

## 当前结果

仓库内的两份 CSV 是基于默认配置抓取的同一批 16 篇文章。两个实现采用不同的
浏览器控制方式，但字段顺序和内容一致，方便直接检查最终交付结果。

## 项目结构

```text
mit-blog-scraper/
├── playwright_scraper.py       # Playwright 实现
├── drissionpage_scraper.py     # DrissionPage 实现
├── scraper_common.py           # URL、文本、去重和 CSV 公共函数
├── requirements.txt
├── output/
│   ├── playwright_blogs.csv
│   └── drissionpage_blogs.csv
├── .gitignore
└── README.md
```

## 已知限制

- 目标站点调整 HTML 结构后，CSS 选择器可能需要同步更新。
- Disqus 是第三方服务，加载失败、超时或限流时评论数会变为 `N/A`。
- 抓取内容取决于执行时网站的已发布文章，CSV 结果不是固定快照。
- 全站页数较多；默认只抓 1 页，批量扩大范围时建议保留文章间隔。
- 正文保存为纯文本，图片字段保存 URL，不下载图片文件。

## 说明

本项目用于笔试和能力演示，不包含数据库、定时任务或数据持久化服务。
`.venv/`、`__pycache__/` 和 Python 编译缓存不会提交到 Git。
