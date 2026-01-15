# CCF Deadline Monitor 🚀

这是一个高度自动化的 CCF 会议监控与学术趋势分析工具。它能够同步 [ccfddl/ccf-deadlines](https://github.com/ccfddl/ccf-deadlines) 的最新动态，并通过 LLM 对 DBLP 历年收录论文进行深度聚类，识别会议的研究趋势。

## ✨ 项目核心功能

- **精准更新监控**：自动识别新会议年份、截稿日期变动。
- **AI 学术画像**：基于论文标题提取“问题/领域”导向的标签，并进行高层级研究主题聚类。
- **双通道通知**：支持 **PushPlus 微信推送**（Markdown 格式）和 **SMTP 邮件通知**（纯文本格式）。
- **智能过滤**：仅针对你感兴趣的领域（如 AI, NW, SC）进行分析，节省 Token。
- **自动持久化**：在 GitHub 上自动维护会议知识库，避免重复分析。

## 🛠️ 如何使用

1. **Fork 本仓库**。
2. **配置 Secrets**：在仓库 `Settings -> Secrets and variables -> Actions` 中点击 `New repository secret`，添加下表中的变量。
3. **运行 Action**：点击 `Actions` 选项卡，手动运行一次 `CCF Deadline Monitor` 工作流。
    - 第一次运行需要较长时间来收集历史会议数据。
    - 第一次运行完成不会发送微信推送/邮件通知。

> ⚠️ **注意**：
> 1. 请确保你的 LLM API Key 有足够的额度来处理 DBLP 论文数据，否则可能导致请求失败。
> 2. 第一次运行需要较多Token，请注意你的Token余额情况。
>

## ⚙️ 环境变量配置 (Secrets)

项目会根据配置自动判断通知通道。**若对应的配置项（如 PUSHPLUS_TOKEN 或 SMTP 信息）不完整，系统将自动跳过该通知通道。**

### 1. 核心配置 (必须)
| 变量名 | 说明 | 默认值 | 示例 |
| :--- | :--- | :--- | :--- |
| `LLM_API_KEY` | LLM 的授权密钥 | - | `sk-xxxx...` |
| `LLM_BASE_URL` | LLM API 的基础地址 | `https://api.openai.com/v1` | `https://api.deepseek.com/v1` |
| `LLM_MODEL` | 使用的模型名称 | `gpt-3.5-turbo` | `gpt-4o`, `deepseek-chat` |

### 2. 微信推送配置 (可选)
| 变量名 | 说明 | 示例 |
| :--- | :--- | :--- |
| `PUSHPLUS_TOKEN` | [PushPlus](http://www.pushplus.plus/) 官网获取的 Token | `a1b2c3d4...` |

### 3. 邮件通知配置 (可选)
| 变量名 | 说明 | 示例 |
| :--- | :--- | :--- |
| `SMTP_HOST` | 邮件服务器地址 | `smtp.qq.com` |
| `SMTP_PORT` | 邮件服务器端口 (通常 SSL 为 465) | `465` |
| `SMTP_USER` | 发件人邮箱账号 | `bot@qq.com` |
| `SMTP_PASS` | **邮箱授权码** (非网页登录密码) | `abcd efgh ijkl mnop` |
| `RECEIVER_EMAIL` | 接收通知的邮箱地址 | `user@gmail.com` |

### 4. 偏好配置 (可选)
| 变量名 | 说明 | 默认值 |
| :--- | :--- | :--- |
| `INTERESTED_AREAS` | 关注领域代码，逗号分隔。填 `ALL` 则关注全部。 | `AI,NW,DB,SC` |
| `MAX_PAPERS_PER_YEAR`| 每年 DBLP 采样的最大论文数量 | `250` |

#### 领域代码参考

- 来自[ccfddl/ccf-deadlines](https://github.com/ccfddl/ccf-deadlines)

| 代码 | 领域 |
| :--- | :--- |
| `AI` | 人工智能 |
| `CG` | 计算机图形学与多媒体 |
| `CT` | 计算机理论 |
| `DB` | 数据库/数据挖掘/内容检索 |
| `DS` | 计算机体系结构/并行与分布计算/存储系统|
| `HI` | 人机交互/普适计算 |
| `MX` | 交叉/综合/新兴 |
| `NW` | 计算机网络 |
| `SC` | 网络与信息安全 |
| `SE` | 软件工程/系统软件/程序设计语言 |

## 📂 仓库结构

```text
.
├── .github/workflows/main.yml  # GitHub Actions 自动化配置
├── data/
│   ├── state.json              # [自动生成] 会议更新指纹库
│   └── knowledge_base.json     # [自动生成] AI 学术趋势知识库
├── query.py                    # 核心处理脚本
├── requirements.txt            # Python 依赖
└── README.md                   # 项目说明文档
```

## 📅 自动化频率
- 自动执行：脚本默认北京时间 每天上午 07:00 自动执行（对应 UTC 23:00）。
    - 可以自行修改Action配置来调整自动化时间。
- 手动执行：在 GitHub Actions 页面点击 Run workflow 即可立即触发同步。

## 🙏 鸣谢
- 数据源提供：[ccfddl/ccf-deadlines](https://github.com/ccfddl/ccf-deadlines)
- 本项目旨在为科研人员提供便捷的会议截稿与领域趋势提醒。

## 🚧 下一步计划
- 并行化处理以提升首次运行速度
- LLM余额不足时推送/邮件提醒