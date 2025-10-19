# crawler.py

import random, requests, ssl, time, json, os, sys
from requests.adapters import HTTPAdapter
from datetime import datetime
import pytz
from github import Github, InputGitAuthor, UnknownObjectException

# --- CONFIGURATION ---
BASE_URL = 'https://b2b.10086.cn'
POST_URL = f'{BASE_URL}/api-b2b/api-sync-es/white_list_api/b2b/publish/queryList'
OUTPUT_DIR = "./zgyd"
METADATA_PATH = os.path.join(OUTPUT_DIR, "metadata.json")
TASK_3_STATE_PATH = os.path.join(OUTPUT_DIR, "task_3_state.json")  # 状态文件路径：用于 TASK 3 的差异对比

# 定义所有需要采集的任务配置
TASK_CONFIG = {
    "TASK_1": {"payload": {}, "name": "所有招采"},
    "TASK_2": {"payload": {"homePageQueryType": "Bidding"}, "name": "所有招采_正在招标"},
    "TASK_3": {"payload": {"homePageQueryType": "Bidding", "companyType": "BJ"}, "name": "所有招采_正在招标_北京"},
}

# --- UTILITIES (Headers, Adapter, Metadata) ---

USER_AGENTS = [
    # 截断列表以保持简洁
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36 OPR/26.0.1656.60",
    "Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko",
    "Mozilla/5.0 (compatible; MSIE 9.0; Windows Phone OS 7.5; Trident/5.0; IEMobile/9.0; HTC; Titan)",
    "MQQBrowser/26 Mozilla/5.0 (Linux; U; Android 2.3.7; zh-cn; MB200 Build/GRJ22; CyanogenMod-7) AppleWebKit/533.1 (KHTML, like Gecko) Version/4.0 Mobile Safari/533.1",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/38.0.2125.122 UBrowser/4.0.3214.0 Safari/537.36",
    "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; WOW64; Trident/5.0; SLCC2; .NET CLR 2.0.50727; .NET CLR 3.5.30729; .NET CLR 3.0.30729; Media Center PC 6.0; .NET4.0C; .NET4.0E; LBBROWSER)",
] * 10

def get_random_headers():
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json',
        'Origin': f'{BASE_URL}',
        'Referer': f'{BASE_URL}/',
    }

class CustomHttpAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context()
        context.options |= 0x4
        context.check_hostname = False
        kwargs['ssl_context'] = context
        return super(CustomHttpAdapter, self).init_poolmanager(*args, **kwargs)

def load_metadata():
    if os.path.exists(METADATA_PATH):
        try:
            with open(METADATA_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_metadata(metadata):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(METADATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=4, ensure_ascii=False)

# --- Server Chan Push and GitHub State Management ---

def send_server_chan_notification(server_chan_url, content_md):
    """发送 Markdown 格式的 Server 酱通知到个人微信。"""
    if not server_chan_url:
        print("[-] Server Chan URL 未配置 (WECHAT_WEBHOOK_URL)，跳过推送。")
        return

    payload = {
        "title": "北京开标数据更新",
        # Server 酱的内容字段是 'desp'
        "desp": content_md 
    }
    
    try:
        response = requests.post(server_chan_url, data=payload, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        if result.get("code") == 0:
            print("[+] Server 酱推送成功。")
        else:
            print(f"[-] Server 酱推送失败，错误信息: {result.get('message')}")
            
    except requests.exceptions.RequestException as e:
        print(f"[-] Server 酱网络请求失败: {e}")

def setup_github(repo_full_name, github_pat):
    """
    初始化 GitHub 客户端并获取仓库实例。
    
    Args:
        repo_full_name (str): 仓库的全名 (owner/repo)。
        github_pat (str): GitHub 个人访问令牌 (PAT)。

    Returns:
        github.Repository.Repository: GitHub 仓库实例。
    """
    
    # 核心修改：直接使用传入的参数
    pat_token = github_pat
    
    if not pat_token:
        print("[-] FATAL ERROR: CLOUDFLARE_WORKER / GITHUB_PAT 变量为空，PyGithub 初始化失败！")
        return None
    
    # 打印长度以确认是否读取到 Secret
    stripped_token = pat_token.strip()
    print(f"[+] CLOUDFLARE_WORKER Token 已读取，长度为: {len(stripped_token)}")
    
    try:
        # 1. 认证客户端
        g = Github(stripped_token) 
        
        # 验证认证是否成功（通过获取用户）
        user = g.get_user()
        print(f"[+] PyGithub 客户端初始化成功并验证通过。当前用户: {user.login}")

        # 2. 获取仓库实例 (这是之前缺失的关键步骤)
        # 这一步使用传入的 repo_full_name
        repo = g.get_repo(repo_full_name) 
        print(f"[+] 成功获取仓库实例: {repo_full_name}")
        
        # 3. 返回仓库实例
        return repo
        
    except Exception as e:
        print(f"[-] FATAL ERROR: PyGithub 认证或获取仓库失败，请检查 Token/Repo名称。错误信息: {e}")
        return None

def get_old_data_from_repo(repo, file_path):
    """从 GitHub 仓库获取上一次保存的状态数据"""
    try:
        contents = repo.get_contents(file_path)
        content = contents.decoded_content.decode('utf-8')
        return json.loads(content)
    except Exception:
        # 如果文件不存在，返回空列表作为初始状态
        print(f"[*] 状态文件 {file_path} 不存在或读取失败，视为初始运行。")
        return []

def commit_new_state(repo, new_data_list, file_path):
    """
    将新数据写入本地状态文件，供 git-auto-commit-action 统一提交。
    (注意：此函数仅写入本地文件，不再通过 PyGithub API 远程提交，以避免与 Actions 冲突)
    """
    new_data_content = json.dumps(new_data_list, ensure_ascii=False, indent=4)
    
    # 1. 确保目录存在 (os.makedirs 是幂等的)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    # 2. 将新状态数据写入本地文件
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_data_content)
        # 打印信息用于日志确认
        print(f"[+] 新状态数据已写入本地文件: {file_path}")
        print(f"[*] 注意：文件 {file_path} 将由后续的 git-auto-commit-action 统一提交和推送。")
    except Exception as e:
        print(f"[-] FATAL ERROR: 写入本地状态文件 {file_path} 失败！错误信息: {e}")
        # 如果本地写入失败，则后续的 git-auto-commit-action 将无法提交此文件

def compare_data_and_generate_report(new_data, old_data):
    """对比新旧数据，返回新增和删除的列表"""
    old_ids = {item['publishId'] for item in old_data if 'publishId' in item}
    new_ids = {item['publishId'] for item in new_data if 'publishId' in item}
    
    added_ids = new_ids - old_ids
    removed_ids = old_ids - new_ids
    
    new_data_map = {item['publishId']: item for item in new_data if 'publishId' in item}
    old_data_map = {item['publishId']: item for item in old_data if 'publishId' in item}
    
    added_items = [new_data_map[id] for id in added_ids]
    removed_items = [old_data_map[id] for id in removed_ids]
    
    return added_items, removed_items

def format_markdown_report(added_items, removed_items):
    """格式化 Server 酱的 Markdown 内容，包含项目名称、日期和新格式链接"""
    # 确保 BASE_URL 在此作用域内可用，因为它在文件顶部是全局定义的
    global BASE_URL
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    report_content = f"## 所有招采_正在招标_北京 数据变动报告\n"
    report_content += f"**时间：** {now_str}\n"
    report_content += f"**总计记录：** {len(added_items) + len(removed_items)} 条变动\n\n"
    
    # 辅助函数：生成单个条目的 Markdown 内容
    def format_item_details(item):
        # 从字典中安全获取所需字段
        link_id = item.get('publishId', '')
        link_uuid = item.get('uuid', '')
        link_publish_type = item.get('publishType', '')
        link_publish_one_type = item.get('publishOneType', '')
        
        # 构造用户指定的新格式 URL
        link = f'{BASE_URL}/#/noticeDetail?publishId={link_id}&publishUuid={link_uuid}&publishType={link_publish_type}&publishOneType={link_publish_one_type}'
        
        # 格式化输出内容
        item_md = ""
        item_md += f"> - **标题:** {item.get('name', 'N/A')}\n"
        item_md += f"> - **发布时间:** {item.get('publishDate', 'N/A')}\n"
        item_md += f"> - **文件售卖截止时间:** {item.get('tenderSaleDeadline', 'N/A')}\n"
        item_md += f"> - **截标时间:** {item.get('publicityEndTime', 'N/A')}\n"
        item_md += f"> - **回退时间:** {item.get('backDate', 'N/A')}\n"
        # 链接文本统一为“点击查看”
        item_md += f"> - **详情链接:** [点击查看]({link})\n\n"
        return item_md

    if added_items:
        report_content += f"### [+] 新增条目 ({len(added_items)}): \n"
        for item in added_items:
            report_content += format_item_details(item)

    if removed_items:
        report_content += f"### [-] 删除/失效条目 ({len(removed_items)}): \n"
        for item in removed_items:
            report_content += format_item_details(item) # 仍使用相同格式展示历史数据

    # 添加 Actions 日志链接 (保持不变)
    run_url = f"{os.environ.get('GITHUB_SERVER_URL', '')}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
    report_content += f"\n---\n[查看完整运行日志]({run_url})"
    
    return report_content

# --- MAIN CRAWLER LOGIC ---

def scrape_content(payload_override, output_name):
    """执行抓取操作，返回抓取到的所有数据和成功状态。"""
    base_payload = {
        "size": 100, "current": 1, "companyType": "", "name": "",
        "publishType": "PROCUREMENT", "publishOneType": "PROCUREMENT",
        "homePageQueryType": "", "sfactApplColumn5": "PC"
    }

    payload = base_payload.copy()
    payload.update(payload_override)
    page_size = payload['size']
    current_page = payload['current']
    all_content = []

    session = requests.Session()
    session.mount('https://', CustomHttpAdapter())

    print(f"[{output_name}] 开始抓取数据...")

    success = True
    while True:
        payload['current'] = current_page
        headers = get_random_headers()

        try:
            print(f"[{output_name}] 正在抓取第 {current_page} 页...")
            response = session.post(POST_URL, headers=headers, json=payload, timeout=15)
            response.raise_for_status()
            response_json = response.json()

            page_content = response_json.get('data', {}).get('content', [])
            content_count = len(page_content)

            if not page_content:
                print(f"[{output_name}] 第 {current_page} 页无内容。抓取停止。")
                break

            all_content.extend(page_content)

            if content_count < page_size:
                print(f"[{output_name}] 已达到最后一页。总计 {len(all_content)} 条记录。")
                break

            current_page += 1
            time.sleep(random.uniform(2, 5))

        except requests.exceptions.RequestException as e:
            print(f"[{output_name}] 请求第 {current_page} 页时发生错误: {e}")
            success = False
            break
        except json.JSONDecodeError:
            print(f"[{output_name}] 无法解析 JSON 响应。")
            success = False
            break

    final_count = len(all_content)

    if success and final_count > 0:
        print(f"[{output_name}] 抓取完成。总计记录: {final_count} 条。")
        return all_content, True
    else:
        print(f"[{output_name}] 抓取失败或无记录。")
        return all_content, False

# 定义时区常量
CST_TZ = pytz.timezone('Asia/Shanghai')

def run_crawler_job(task_key):
    if task_key not in TASK_CONFIG:
        print(f"错误：无效的任务键 '{task_key}'。")
        return

    config = TASK_CONFIG[task_key]
    task_name = config["name"]
    output_path = os.path.join(OUTPUT_DIR, f"{task_name}.json")

    print(f"==================================================")
    print(f"任务键: {task_key}，目标数据集: {task_name}")
    print(f"==================================================")

    new_data, success = scrape_content(config["payload"], task_name)

    if not success:
        print("抓取失败，跳过文件保存和元数据更新。")
        return

    # --- 核心逻辑分支：TASK_3 的差异化推送与状态管理 ---
    if task_key == "TASK_3":
        
        GITHUB_PAT = os.environ.get("CLOUDFLARE_WORKER")
        SERVER_CHAN_URL = os.environ.get("WECHAT_WEBHOOK_URL")
        
        # 从 wrangler.toml 注入的 Env Vars (通过 scheduler.yml)
        REPO_OWNER = os.environ.get("GITHUB_OWNER")
        REPO_NAME = os.environ.get("GITHUB_REPO")
        
        if not GITHUB_PAT or not SERVER_CHAN_URL:
            print("TASK_3 缺少推送所需的 Secrets。")
            # 即使缺少 Secrets，仍允许保存本地文件供 Streamlit 使用
            pass
        else:
            repo_full_name = f"{REPO_OWNER}/{REPO_NAME}"
            repo = setup_github(repo_full_name, GITHUB_PAT)
            if not repo:
                print("GitHub 仓库连接失败，跳过差异推送。")
            else:
                # 1. 获取旧数据 (从仓库)
                old_data = get_old_data_from_repo(repo, TASK_3_STATE_PATH)
                
                # 2. 对比数据
                added_items, removed_items = compare_data_and_generate_report(new_data, old_data)
                
                # 3. 报告并推送 (仅在有变动时)
                if added_items or removed_items:
                    print(f"发现变动：新增 {len(added_items)} 条, 删除 {len(removed_items)} 条。")
                    
                    # 生成 Markdown 报告
                    report_content = format_markdown_report(added_items, removed_items)

                    # 发送 Server 酱推送
                    send_server_chan_notification(SERVER_CHAN_URL, report_content)

                    # 4. 提交新状态数据 (覆盖旧状态文件) - 使用 PyGithub
                    commit_new_state(repo, new_data, TASK_3_STATE_PATH)
                    
                else:
                    print("数据无变化，跳过推送和状态更新。")


    # --- 通用逻辑：写入本地 JSON 文件 (供 Streamlit 读取) ---
    # TASK_3 的数据写入本地文件，Task 1/2/3 都需要写入，由 git-auto-commit-action 统一提交
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        # TASK_3 写入 zgyd/所有招采_正在招标_北京.json
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(new_data, f, indent=4, ensure_ascii=False)
        print(f"已将新数据写入本地文件: {output_path}")
    except Exception as e:
        print(f"写入本地 JSON 文件失败: {e}")
        
    # --- 通用逻辑：更新元数据 (用于 Streamlit 显示更新时间) ---
    metadata = load_metadata()
    now_cst = datetime.now(CST_TZ)
    metadata[task_name] = now_cst.strftime("%Y-%m-%d %H:%M:%S")
    save_metadata(metadata)
    print(f"元数据已更新。")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        task_key_to_run = sys.argv[1]
        run_crawler_job(task_key_to_run)
    else:
        print("错误：请提供任务键作为命令行参数 (例如: python crawler.py TASK_1)")