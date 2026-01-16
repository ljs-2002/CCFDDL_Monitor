# CCF Deadline Monitor 🚀

这是一个高度自动化的 CCF 会议监控与学术趋势分析工具。它能够同步 [ccfddl/ccf-deadlines](https://github.com/ccfddl/ccf-deadlines) 的最新动态，并通过 LLM 对 DBLP 历年收录论文进行深度聚类，识别会议的研究趋势。

## ✨ 核心功能

- **🧠 深度学术画像**：基于论文标题提取“问题/领域”导向的标签，并进行高层级研究主题聚类。
- **🔔 智能更新提醒**：实时监控关注领域的会议变动（如新增会议、截稿日期修改等）。一旦触发更新，系统将自动发送提醒通知，并同步附带由 LLM 生成的该会议近 3 年学术研究趋势分析。
- **🔍 交互式即时查询**：通过 GitHub Discussions 或手动触发，随时调取特定会议的深度报告。
- **📢 多通道精准通知**：支持 **PushPlus 微信推送**（Markdown 渲染）和 **SMTP 邮件**。
- **⚡ 高性能并行分析**：采用多线程并发请求 LLM，大幅提升历史论文的分析速度。
- **💾 智能增量缓存**：自动维护私有库中的知识库，命中缓存时仅需约 25 秒即可完成推送。
- **🔐 数据资产私有化**：采用“代码公开+数据私有”架构，保护 LLM Token 的资金投入。

---

## 🛠️ 快速上手

### 第一步：初始化环境与私有库

1. **Fork 本仓库**：点击右上角 `Fork`，将代码仓库同步到您的账号下。
2. **创建私有数据仓**：
   - 新建一个 **Private（私有）** 仓库（例如命名为 `ccf-data-storage`）。
   - 该仓库将专门用于存放生成的数据。
3. **生成访问令牌 (PAT)**：
   - 前往 [GitHub Personal Access Tokens](https://github.com/settings/tokens) (Classic)。
   - 生成一个新 Token（Note 填 `CCF-Monitor-Token`），权限勾选 **`repo`**。**请务必保存好这个字符串**。

---

### 第二步：配置 Secrets （环境变量）

在您的**公开代码仓库**中，进入 `Settings -> Secrets and variables -> Actions`，点击 `New repository secret` 依次添加以下变量：

#### 1. 必填核心配置 (数据与鉴权)
| 变量名 | 说明 | 示例 |
| :--- | :--- | :--- |
| `LLM_API_KEY` | LLM 的授权密钥 | `sk-xxxx...` |
| `DATA_REPO` | **私有数据仓库路径** | `您的用户名/ccf-data-storage` |
| `DATA_REPO_TOKEN` | **第一步中生成的访问令牌 (Classic)** | `ghp_xxxx...` |

#### 2. LLM 与性能设置 (可选)
| 变量名 | 说明 | 默认值 | 示例/建议 |
| :--- | :--- | :--- | :--- |
| `LLM_BASE_URL` | LLM API 的基础地址 | `https://api.openai.com/v1` | `https://api.deepseek.com/v1` |
| `LLM_MODEL` | 使用的模型名称 | `gpt-3.5-turbo` | `deepseek-chat`, `gpt-4o` |
| `MAX_WORKERS` | **LLM 并发请求数** | `10` | 建议 5-10，防止触发 API 频率限制 |
> ⚠️ **并发限制预警**：请根据你的 API 供应商等级调整 `MAX_WORKERS`。如果遇到 `429 Too Many Requests` 报错，请调低此数值（例如设为 3 或 5）。

#### 3. 学术偏好设置 (可选)
| 变量名 | 说明 | 默认值 | 示例/建议 |
| :--- | :--- | :--- | :--- |
| `INTERESTED_AREAS` | **关注领域代码** (逗号分隔) | `AI,NW,DB,SC` | 填 `ALL` 则监控全部领域 |
| `MAX_PAPERS_PER_YEAR` | **每年 DBLP 采样论文数** | `250` | 采样数越大分析越准，但 Token 消耗更多 |

#### 4. 推送通道配置 (可选)
| 变量名 | 说明 | 示例 |
| :--- | :--- | :--- |
| `PUSHPLUS_TOKEN` | [PushPlus](http://www.pushplus.plus/) 微信推送 Token | `a1b2c3...` |
| `SMTP_HOST` | 邮件服务器地址 | `smtp.qq.com` |
| `SMTP_PORT` | 邮件服务器端口 | `465` |
| `SMTP_USER` | 发件人邮箱账号 | `bot@qq.com` |
| `SMTP_PASS` | 邮箱授权码 (非密码) | `abcd efgh ijkl mnop` |
| `RECEIVER_EMAIL` | 接收通知的邮箱 | `user@gmail.com` |

---

### 第三步：运行与日常使用

1. **首次运行（初始化数据）**：
   - 点击 `Actions` -> `CCF Deadline Monitor` -> `Run workflow`。
   - **资源参考**：以关注 `AI, NW, DB, SC` 四个领域为例，使用 `DeepSeek-V3.2` 初始化，并发数设为10，耗时约 **3 小时 50 分钟**，消耗约 **300 万 - 400 万 Token**。请确保额度充足。
2. **日常监控**：程序默认在北京时间 **每天上午 07:00** 自动运行并向微信/邮件发送带收录趋势的变动通知。
3. **手动同步与数据补全**：
   - 若你修改了 `INTERESTED_AREAS`（关注领域），可手动运行 Action。程序会静默补全缺失年份的分析，不会重复发送已处理会议的更新通知。
3. **会议查询**：
    1. **GitHub Discussions 查询**（推荐，支持手机 App）
        - **开启 Discussions**：进入仓库 `Settings` -> `General` -> 勾选 `Discussions`。
        - **创建分类**：进入 `Discussions` 页面，点击左侧 `Categories` 旁的编辑图标，创建一个名为 **Query** 的分类。**推荐将分类形式选为 "Announcement"**。
            - 建议删除其他默认分类。
        - **发起查询**：在 **Query** 分类下发起新讨论，标题格式为：`q: 会议简称`（例如：`q: aaai`）。
        - **即时反馈**：Action 会自动触发，若该会议已在数据库中，**约 25 秒** 后你就能在微信/邮件中收到推送。
        > 📱 **小技巧**：下载 **GitHub 手机客户端**，你可以随时随地发帖查询会议信息。
    2. **手动按钮触发查询**。
        - 在 `Actions` -> `CCF Deadline Monitor` 页面点击右侧的 `Run workflow` 按钮。
        - **弹出框输入**：在弹出的 `conference_name` 输入框中填入会议简称（如 `CVPR`）。

---

## 📂 仓库结构

```text
.
├── .github/workflows/main.yml  # GitHub Actions 自动化配置
├── query.py                    # 核心处理脚本
├── requirements.txt            # Python 依赖
└── README.md                   # 项目说明
```

## 📅 领域代码参考

根据 [ccfddl/ccf-deadlines](https://github.com/ccfddl/ccf-deadlines) 的标准，可用代码如下：

| 代码 | 领域 | 代码 | 领域 |
| :--- | :--- | :--- | :--- |
| `AI` | 人工智能 | `HI` | 人机交互/普适计算 |
| `CG` | 计算机图形学与多媒体 | `MX` | 交叉/综合/新兴 |
| `CT` | 计算机理论 | `NW` | 计算机网络 |
| `DB` | 数据库/数据挖掘/内容检索 | `SC` | 网络与信息安全 |
| `DS` | 体系结构/并行计算/存储 | `SE` | 软件工程/程序设计语言 |

---

## 🙏 鸣谢

- **数据源**：感谢 [ccfddl/ccf-deadlines](https://github.com/ccfddl/ccf-deadlines) 提供的会议数据。


## 🚧 下一步计划
- [ ] 增加 LLM 余额不足导致查询失败的通知；
- [ ] 增加更多推送渠道；
- [ ] 增加更多查询方式；

---
**License**: [MIT](LICENSE)  
**Disclaimer**: 本项目由 AI 辅助生成分析，结果仅供科研参考，具体截稿时间请务必以会议官网为准。