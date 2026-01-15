import argparse
import json
import os
import re
import smtplib
import time
import urllib
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.header import Header
from email.mime.text import MIMEText

import requests
import yaml
from dateutil import parser as date_parser
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_fixed

# --- 配置与环境读取 ---
CCF_PATH = "ccf-repo/conference"
DATA_DIR = "data"
STATE_FILE = os.path.join(DATA_DIR, "state.json")
KB_FILE = os.path.join(DATA_DIR, "knowledge_base.json")
INTERESTED_AREAS = os.environ.get("INTERESTED_AREAS", "AI,NW,DB,SC").split(",")
MAX_PAPERS_PER_YEAR = int(os.environ.get("MAX_PAPERS_PER_YEAR", "250"))

# LLM 配置
LLM_API_KEY = os.environ.get("LLM_API_KEY")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-3.5-turbo")
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN")

client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
CCF_SUB_MAP = {
    "AI": "人工智能 (AI)",
    "NW": "计算机网络 (NW)",
    "SE": "软件工程/系统软件/程序设计语言 (SE)",
    "DB": "数据库/数据挖掘/内容检索 (DB)",
    "CT": "计算机科学理论 (CT)",
    "SC": "网络与信息安全 (SC)",
    "CG": "计算机图形学与多媒体 (CG)",
    "HI": "人机交互/普适计算 (HI)",
    "MX": "交叉/综合/新兴 (MX)",
    "DS": "计算机体系结构/并行与分布计算/存储系统 (DS)",  # 有些旧数据可能有
}


# --- 模块 1: 时区处理 ---
def get_timezone_offset(tz_str):
    tz = tz_str.strip().upper() if tz_str else "UTC"
    alias_map = {"AOE": -12, "EST": -5, "EDT": -4, "CST": 8, "JST": 9}
    if tz in alias_map:
        return alias_map[tz]
    try:
        if tz.startswith("UTC"):
            part = tz.replace("UTC", "")
            if not part:
                return 0
            return int(part)
    except:
        pass
    return 0


def convert_to_cst(date_str, timezone_str):
    """
    将会议当地时间转换为北京时间 (UTC+8)
    """
    if not date_str or date_str == "TBD":
        return "TBD"

    try:
        dt = date_parser.parse(date_str)
        offset = get_timezone_offset(timezone_str)
        # 原理：原始时间 - 原时区偏移 + 8 (CST偏移)
        # 例如 AoE (-12) 1日 23:59 -> UTC 2日 11:59 -> CST 2日 19:59
        cst_time = dt - timedelta(hours=offset) + timedelta(hours=8)
        return cst_time.strftime("%Y-%m-%d %H:%M:%S (CST)")
    except Exception as e:
        print(
            f"   [Error] Date parse error: {e} for date_str: {date_str} and timezone_str: {timezone_str}"
        )
        return f"{date_str} (Parse Error)"


# --- 模块 2: DBLP 数据获取 ---
def fetch_dblp_papers(dblp_venue_key, year, limit=1000):
    """
    获取论文标题和链接
    dblp_venue_key: 例如 'iwqos', 'iccv'
    year: 例如 2022
    """
    print(
        f"   [DBLP] Fetching venue:'{dblp_venue_key}' year:'{year}' (Limit: {limit})..."
    )
    papers = []

    try:
        # 修正：使用标准的 query string 语法: "venue:<name> year:<year>"
        # 并进行 URL 编码
        q_str = f"venue:{dblp_venue_key} year:{year}"
        query_encoded = urllib.parse.quote(q_str)

        url = (
            f"https://dblp.org/search/publ/api?q={query_encoded}&h={limit}&format=json"
        )

        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        print(f"   [DBLP] {data.get('result', {}).get('status', '')}")

        hits = data.get("result", {}).get("hits", {}).get("hit", [])

        if not hits:
            print(f"   [DBLP] No hits found for {q_str}")

        for hit in hits:
            info = hit.get("info", {})
            title = info.get("title", "No Title")

            # 提取链接：优先取 DOI (ee), 其次取 DBLP 页面 (url)
            link = ""
            ee = info.get("ee")
            if isinstance(ee, list):
                link = ee[0]
            elif isinstance(ee, str):
                link = ee
            else:
                link = info.get("url", "")

            papers.append({"title": title, "link": link})

        time.sleep(1.5)  # 遵守 DBLP API 礼仪
    except Exception as e:
        print(f"   [Error] DBLP fetch failed: {e}")

    return papers


# --- 模块 3: LLM 分析流程 ---
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def llm_stage1_extract_tags(papers_batch):
    papers_text = "\n".join(
        [f"[{i + 1}] {p['title']}" for i, p in enumerate(papers_batch)]
    )

    # Framework: CO-STAR
    prompt = f"""
    # Context: Senior CS Taxonomist analyzing conference papers.
    # Objective: Extract 1-5 academic tags per paper.
    # Constraints: 
    - Focus: 'Problem/Task' and 'Context/Domain' (e.g., "Encrypted Traffic Classification", "BGP Security").
    - Exclude: Generic methods like GNN, CNN, RL, Transformer.
    - Style: Professional English.
    # Example:
    Title: "Graph-based Anomaly Detection in SDN" -> Tags: ["Software-Defined Networking", "Network Anomaly Detection"]
    
    # Input:
    {papers_text}
    # Response: Strict JSON array of strings.
    """

    response = client.chat.completions.create(
        model=LLM_MODEL, messages=[{"role": "user", "content": prompt}], temperature=0.1
    )
    content = response.choices[0].message.content.strip()
    usage = response.usage
    usage_stats = {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
    }

    try:
        json_str = re.search(r"\[.*\]", content, re.DOTALL).group()
        tags = json.loads(json_str)
    except:
        tags = re.findall(r'"([^"]+)"', content)

    return [str(t).strip() for t in tags], usage_stats


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def llm_stage2_summarize(tag_counts, conference_name, year, total_papers):
    stats_text = json.dumps(tag_counts, indent=2)

    # Framework: CO-STAR
    prompt = f"""
    # Context: TPC Chair of {conference_name} ({year}).
    # Objective: Cluster tags into 5-10 high-level "Research Themes".
    # Guidelines:
    1. Taxonomy: Use broad categories (e.g., "Network Infrastructure & Protocol Security" instead of "NIDS").
    2. Format: Return a JSON list of objects: {{"name": "Chinese(English)", "ratio": "X%", "description": "..."}}.
    3. Mandatory Single Field: The "description" MUST include both the intro and sub-tags in this format: 
       "本主题研究[简短介绍]。涵盖：[细分方向1]、[细分方向2]等。"
    # Example:
    {{
      "name": "可信计算与系统安全 (Trustworthy Computing & System Security)",
      "ratio": "15%",
      "description": "探讨构建软硬件一体化的安全运行环境。涵盖：机密计算、侧信道分析、固件安全等。"
    }}

    # Data: {stats_text}
    # Total Sample Size: {total_papers}
    # Response: JSON only.
    """

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    content = response.choices[0].message.content.strip()
    usage = response.usage
    usage_stats = {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
    }

    try:
        json_str = re.search(r"\[.*\]", content, re.DOTALL).group()
        return json.loads(json_str), usage_stats
    except:
        return [], usage_stats


def analyze_year_data(
    dblp_name, year, conf_display_name, max_papers=100, verbose=False
):
    papers = fetch_dblp_papers(dblp_name, year, limit=max_papers)
    if not papers:
        print(f"   [Analysis] No papers found for {year}.")
        return None

    # 全局计数器：记录每个 Tag 在多少篇论文中出现过
    global_tag_counter = Counter()
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    batch_size = 10

    print(f"   [Analysis] Processing {len(papers)} papers via LLM ({LLM_MODEL})...")

    # --- Stage 1: Batch Processing ---
    for i in range(0, len(papers), batch_size):
        batch = papers[i : i + batch_size]

        if verbose:
            print(f"\n   [Debug] Batch {i // batch_size + 1} Inputs:")
            for p in batch:
                print(f"      - {p['title']}")

        try:
            # 获取本批次的所有 Tags
            batch_tags_flat, usage = llm_stage1_extract_tags(batch)

            # 累加用量
            for k in total_usage:
                total_usage[k] += usage.get(k, 0)

            for tag in batch_tags_flat:
                # 简单清洗：去除首尾空格，转 Title Case 方便统计
                clean_tag = tag.strip()
                if clean_tag:
                    global_tag_counter[clean_tag] += 1

            if verbose:
                print(f"   [Debug] Batch Tags: {batch_tags_flat}")
                print(f"   [Debug] Batch Usage: {usage['total_tokens']}")

        except Exception as e:
            print(f"     Batch {i // batch_size + 1} failed: {e}")

    if not global_tag_counter:
        return None

    # --- Stage 2: Summarization ---
    top_tags_map = dict(global_tag_counter)

    print(f"   [Analysis] Summarizing from {len(top_tags_map)} distinct tags...")

    # 传入 total_papers (len(papers)) 以便计算正确比例
    final_summary, usage_s2 = llm_stage2_summarize(
        tag_counts=top_tags_map,
        conference_name=conf_display_name,
        year=year,
        total_papers=len(papers),
    )

    for k in total_usage:
        total_usage[k] += usage_s2.get(k, 0)

    if verbose:
        print(
            f"\n   [Debug] Final Summary:\n{json.dumps(final_summary, indent=2, ensure_ascii=False)}"
        )
        print(f"   [Debug] Total Cost: {total_usage}")

    return {
        "titles_count": len(papers),
        "summary": final_summary,
        "token_usage": total_usage,
        "updated_at": datetime.now().strftime("%Y-%m-%d"),
    }


# --- 模块 4: 数据存储与通知 ---
def get_notification_body(info, kb_record):
    """
    组装 Markdown 通知内容，按年份倒序排列，Tag 按比例排序。
    """
    rank = info["rank"]
    rank_color_map = {"A": "#FF0000", "B": "#FFA500", "C": "#008000", "N": "#808080"}
    color = rank_color_map.get(rank, "#000000")
    rank_html = f'<font color="{color}">CCF-{rank}</font>'

    # 1. 获取近 3 年数据并按年份倒序
    years = sorted(kb_record.keys(), reverse=True)[:3] if kb_record else []

    analysis_section = ""
    total_tokens_consumed = 0

    if not years:
        analysis_section = "⚠️ **暂无历史论文趋势分析**"
    else:
        analysis_section = "🧠 **近 3 年学术趋势分析**\n"
        for y in years:
            data = kb_record[y]
            summary = data.get("summary", [])
            total_tokens_consumed += data.get("token_usage", {}).get("total_tokens", 0)

            if not summary:
                continue

            # 2. 按比例(ratio)对当前年份的 Tag 进行降序排列
            sorted_summary = sorted(
                summary,
                key=lambda x: float(x.get("ratio", "0%").strip("%")),
                reverse=True,
            )

            analysis_section += (
                f"\n#### 📅 {y} 年 (样本量: {data.get('titles_count', '?')} 篇)\n"
            )
            for tag in sorted_summary:
                name = tag.get("name", "Unknown")
                desc = tag.get("description", "")
                ratio = tag.get("ratio", "")
                analysis_section += f"- **{name}** `({ratio})`\n  - {desc}\n"

    token_footer = (
        f"\n---\n###### 💎 LLM Token Cost: {total_tokens_consumed} (Analysis Session)"
        if total_tokens_consumed > 0
        else ""
    )

    msg = f"""
## 📢 {info["title"]} {info["year"]} 更新提醒
> {info["description"]}

- **领域**: {info["sub"]} | **等级**: {rank_html}
- **时间**: {info["date"]} | **地点**: {info["place"]}
- **官网**: [点击跳转]({info["link"]})

---
### ⏰ 关键截稿 (北京时间)
- **摘要截止**: {info["abs_deadline"]}
- **全文截止**: {info["main_deadline"]}

---
{analysis_section}
{token_footer}
    """
    return msg


def send_pushplus(title, content):
    if not PUSHPLUS_TOKEN:
        print("   [Notify] Skip: No PUSHPLUS_TOKEN.")
        return

    url = "http://www.pushplus.plus/send"
    data = {
        "token": PUSHPLUS_TOKEN,
        "title": title,
        "content": content,
        "template": "markdown",
    }
    try:
        requests.post(url, json=data, timeout=5)
        print("   [Notify] PushPlus sent successfully.")
    except Exception as e:
        print(f"   [Notify] Failed: {e}")


def get_email_body(info, kb_record):
    """
    组装纯文本邮件内容（无 Markdown 符号）
    """
    years = sorted(kb_record.keys(), reverse=True)[:3] if kb_record else []

    analysis_text = ""
    if not years:
        analysis_text = "暂无历史论文趋势分析数据。"
    else:
        for y in years:
            data = kb_record[y]
            analysis_text += (
                f"\n【{y} 年趋势 (样本量: {data.get('titles_count', '?')} 篇)】\n"
            )
            summary = data.get("summary", [])
            # 按比例排序
            sorted_summary = sorted(
                summary,
                key=lambda x: float(x.get("ratio", "0%").strip("%")),
                reverse=True,
            )
            for tag in sorted_summary:
                analysis_text += f"- {tag.get('name')} (比例: {tag.get('ratio')})\n"
                analysis_text += f"  详情: {tag.get('description')}\n"

    body = f"""
会议更新提醒：{info["title"]} {info["year"]}

--------------------------------------------------

会议描述：{info["description"]}

[基本信息]
- 领域：{info["sub"]}
- 等级：CCF-{info["rank"]}
- 时间：{info["date"]}
- 地点：{info["place"]}
- 官网：{info["link"]}

[重要截稿时间 (北京时间)]
- 摘要截止：{info["abs_deadline"]}
- 全文截止：{info["main_deadline"]}

[近3年学术趋势深度分析]
{analysis_text}
--------------------------------------------------
提示：本邮件由 AI 自动生成，历史分析基于 DBLP 数据。
"""
    return body


def send_email(title, content):
    """
    通过 SMTP 发送邮件通知
    """
    # 环境变量读取
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    receiver = os.environ.get("RECEIVER_EMAIL")

    # 只有配置了完整信息才会发送
    if not all([smtp_host, smtp_user, smtp_pass, receiver]):
        print("   [Notify] Email skip: Configuration incomplete.")
        return

    message = MIMEText(content, "plain", "utf-8")
    message["From"] = smtp_user
    message["To"] = receiver
    message["Subject"] = Header(title, "utf-8")

    try:
        smtp_obj = smtplib.SMTP_SSL(smtp_host, smtp_port)
        smtp_obj.login(smtp_user, smtp_pass)
        smtp_obj.sendmail(smtp_user, [receiver], message.as_string())
        smtp_obj.quit()
        print("   [Notify] Email sent successfully.")
    except Exception as e:
        print(f"   [Notify] Email failed: {e}")


# --- 模块 5: 核心流程控制 ---


def get_timeline_status(timeline_list, timezone_str):
    """
    从 timeline 列表中找到第一个还没过期的 deadline。
    如果都过期了，返回最后一个。
    返回: (selected_timeline_item, status_text)
    """
    if not timeline_list:
        return {}, "未定"

    now_utc = datetime.now(timezone.utc)
    tz_offset = get_timezone_offset(timezone_str)

    # 寻找第一个还没过的时间
    for item in timeline_list:
        deadline_str = item.get("deadline", "TBD")
        if deadline_str == "TBD":
            continue

        try:
            # 解析 deadline
            dl_dt = date_parser.parse(deadline_str)
            # 转换为 UTC 时间以便比较: (Local Time - Offset = UTC)
            dl_utc = dl_dt - timedelta(hours=tz_offset)
            # 将其转换为时区感知的 UTC 对象，以便与 now_utc 比较
            dl_utc = dl_utc.replace(tzinfo=timezone.utc)

            if dl_utc > now_utc:
                # 找到未来的时间
                return item, "进行中"
        except Exception as e:
            print(
                f"   [Error] Timeline date parse error: {e} for deadline_str: {deadline_str}"
            )
            continue

    # 如果都过期了，返回最后一个
    return timeline_list[-1], "已截止"


def process_updates(local_test_file=None):
    """
    核心处理逻辑：支持初始化部署、领域过滤、基于最新年份的历史分析。
    """
    # 1. 加载持久化数据
    state, kb = {}, {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
    if os.path.exists(KB_FILE):
        with open(KB_FILE, "r") as f:
            kb = json.load(f)

    is_initial_run = not bool(state)
    changes_detected = False
    files_to_process = [local_test_file] if local_test_file else []

    if not local_test_file:
        for root, _, files in os.walk(CCF_PATH):
            for f in files:
                if f.endswith(".yml"):
                    files_to_process.append(os.path.join(root, f))

    for file_path in files_to_process:
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                raw_data = yaml.safe_load(f)
                data_list = raw_data if isinstance(raw_data, list) else [raw_data]
            except Exception as e:
                print(f"   [Error] Load failed {file_path}: {e}")
                continue

            for data in data_list:
                if not data:
                    continue

                # 领域过滤
                sub_code = data.get("sub", "")
                if "ALL" not in INTERESTED_AREAS and sub_code not in INTERESTED_AREAS:
                    continue

                dblp_name = data.get("dblp") or data.get("title", "").lower()

                # 核心修改：找出该会议记录中的最新年份
                all_confs = data.get("confs", [])
                if not all_confs:
                    continue
                max_year_in_data = max(c.get("year", 0) for c in all_confs)

                for conf in all_confs:
                    conf_id = str(conf.get("id"))
                    current_conf_year = conf.get("year")
                    tl_data = conf.get("timeline", [{}])[0]
                    fingerprint = {"year": current_conf_year, "timeline": tl_data}

                    # 判断更新：新会议、指纹变动、或测试模式
                    old_fp = state.get(conf_id)
                    is_new_update = old_fp != fingerprint

                    # 只有发生更新或者是初始化/测试模式时，才执行推送流程
                    if is_new_update or local_test_file or is_initial_run:
                        state[conf_id] = fingerprint
                        changes_detected = True

                        # 只针对“最新年份”的条目执行历史深度分析，避免旧条目触发重复分析
                        if current_conf_year == max_year_in_data:
                            print(
                                f"🚀 Processing Latest: {conf_id} ({current_conf_year})"
                            )

                            # 获取并转换截稿日期
                            target_tl, status = get_timeline_status(
                                conf.get("timeline", []), conf.get("timezone")
                            )
                            info = {
                                "title": data.get("title"),
                                "description": data.get("description"),
                                "sub": CCF_SUB_MAP.get(sub_code, sub_code),
                                "rank": data.get("rank", {}).get("ccf"),
                                "year": current_conf_year,
                                "date": conf.get("date"),
                                "place": conf.get("place"),
                                "link": conf.get("link"),
                                "abs_deadline": convert_to_cst(
                                    target_tl.get("abstract_deadline"),
                                    conf.get("timezone"),
                                ),
                                "main_deadline": convert_to_cst(
                                    target_tl.get("deadline"), conf.get("timezone")
                                )
                                + (" (已过)" if status == "已截止" else ""),
                            }

                            # 历史数据获取：从当前最新年份往前推 3 年 (e.g. 2025 -> 2024, 2023, 2022)
                            if dblp_name not in kb:
                                kb[dblp_name] = {}
                            target_years = [current_conf_year - i for i in range(1, 4)]

                            for y in target_years:
                                str_y = str(y)
                                if str_y not in kb[dblp_name]:
                                    print(
                                        f"   [DBLP Analysis] Fetching {dblp_name} for year {y}..."
                                    )
                                    res = analyze_year_data(
                                        dblp_name,
                                        y,
                                        info["title"],
                                        max_papers=MAX_PAPERS_PER_YEAR,
                                    )
                                    if res:
                                        kb[dblp_name][str_y] = res

                            # 推送通知 (初始化模式不推送，防止爆表)
                            if not is_initial_run:
                                msg_body = get_notification_body(
                                    info, kb.get(dblp_name)
                                )
                                send_pushplus(f"{info['title']} 更新提醒", msg_body)
                                mail_body = get_email_body(info, kb.get(dblp_name))
                                send_email(f"{info['title']} 更新提醒", mail_body)
                        else:
                            # 如果不是最新年份，仅更新状态指纹，不触发深度分析和推送
                            continue

    # 无论是否为测试模式，只要有变动就保存，确保知识库不断累积
    if changes_detected:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
        with open(KB_FILE, "w") as f:
            json.dump(kb, f, indent=2)
        print(f"✅ Data saved to {STATE_FILE} and {KB_FILE}")


# --- 本地测试入口 ---
def run_local_test(yml_path):
    print(f"🔧 Starting LOCAL TEST with file: {yml_path}")
    print("Ensure environment variables LLM_API_KEY and PUSHPLUS_TOKEN are set.")

    if not os.path.exists(yml_path):
        print("File not found!")
        return

    process_updates(local_test_file=yml_path)


if __name__ == "__main__":
    args_parser = argparse.ArgumentParser()
    args_parser.add_argument("--test", help="Path to a single yml file to test")
    args = args_parser.parse_args()

    if args.test:
        # run_local_test 函数逻辑不变，只需确保它调用 process_updates
        print(f"🔧 Starting LOCAL TEST with file: {args.test}")
        if not os.path.exists(args.test):
            print(f"❌ File not found: {args.test}")
        else:
            process_updates(local_test_file=args.test)
    else:
        process_updates()
