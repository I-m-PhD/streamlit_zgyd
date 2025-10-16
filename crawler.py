# crawler.py
# 此文件仅负责定时采集第三个数据集

import random, requests, ssl, time, json, os
from requests.adapters import HTTPAdapter
from datetime import datetime

# --- CONFIGURATION ---
BASE_URL = 'https://b2b.10086.cn'
POST_URL = f'{BASE_URL}/api-b2b/api-sync-es/white_list_api/b2b/publish/queryList'
OUTPUT_DIR = "./zgyd"
METADATA_PATH = os.path.join(OUTPUT_DIR, "metadata.json")

TASK_CONFIG = {
    "所有招采": {"payload": {}, "name": "所有招采"},
    "正在招标": {"payload": {"homePageQueryType": "Bidding"}, "name": "所有招采_正在招标"},
    "正在招标 (北京)": {"payload": {"homePageQueryType": "Bidding", "companyType": "BJ"}, "name": "所有招采_正在招标_北京"},
}
# 仅执行第三个任务
TARGET_TASK_KEY = "正在招标 (北京)"


# --- UTILITIES (必须包含在爬虫脚本内) ---

USER_AGENTS = [
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

def scrape_content(payload_override, output_name):

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

    print(f"[{output_name}] 🚀 开始抓取数据...")

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
            print(f"[{output_name}] ⚠️ 请求第 {current_page} 页时发生错误: {e}")
            success = False
            break
        except json.JSONDecodeError:
            print(f"[{output_name}] ⚠️ 无法解析 JSON 响应。")
            success = False
            break

    final_count = len(all_content)

    if success and final_count > 0:
        output_path = os.path.join(OUTPUT_DIR, f"{output_name}.json")
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(all_content, f, indent=4, ensure_ascii=False)
            print(f"[{output_name}] ✅ 抓取完成。总计记录: {final_count} 条。")
            return True
        except Exception as e:
            print(f"[{output_name}] ❌ 写入 JSON 文件失败: {e}")
            return False
    elif final_count == 0:
        print(f"[{output_name}] ❌ 未获取到任何记录。")
        return False
    else:
        return False


# --- MAIN CRAWLER LOGIC ---

def run_crawler_job():
    # 仅执行第三个任务
    config = TASK_CONFIG[TARGET_TASK_KEY]
    task_name = config["name"]

    success = scrape_content(config["payload"], task_name)

    if success:
        metadata = load_metadata()
        metadata[task_name] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_metadata(metadata)

if __name__ == "__main__":
    run_crawler_job()