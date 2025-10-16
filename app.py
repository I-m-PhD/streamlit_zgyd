# app.py
# 此文件用于手动采集前两个数据集

import streamlit as st
import random, requests, ssl, time, json, os
from requests.adapters import HTTPAdapter
import pandas as pd
import plotly.express as px
import plotly.io as pio
from datetime import datetime

# --- GLOBAL SETTINGS AND UTILITIES ---

# --- API Endpoints ---
BASE_URL = 'https://b2b.10086.cn'
POST_URL = f'{BASE_URL}/api-b2b/api-sync-es/white_list_api/b2b/publish/queryList'
# 使用固定的本地文件夹来存储数据
OUTPUT_DIR = "./zgyd"

# 定义所有需要采集的任务配置
TASK_CONFIG = {
    "所有招采": {"payload": {}, "name": "所有招采"},
    "正在招标": {"payload": {"homePageQueryType": "Bidding"}, "name": "所有招采_正在招标"},
    "正在招标 (北京)": {"payload": {"homePageQueryType": "Bidding", "companyType": "BJ"}, "name": "所有招采_正在招标_北京"},
}

# 用于记录数据采集时间的文件
METADATA_PATH = os.path.join(OUTPUT_DIR, "metadata.json")

# --- User Agents (Keeping the mechanism but truncating list display) ---
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
    """Generates standard headers with a random User-Agent."""
    return {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json',
        'Origin': f'{BASE_URL}',
        'Referer': f'{BASE_URL}/',
    }

class CustomHttpAdapter(HTTPAdapter):
    """HTTPAdapter that handles the required SSL context fix."""
    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context()
        context.options |= 0x4
        context.check_hostname = False
        kwargs['ssl_context'] = context
        return super(CustomHttpAdapter, self).init_poolmanager(*args, **kwargs)

# --- METADATA HANDLER ---

def load_metadata():
    """Loads the last successful crawl time for all tasks."""
    if os.path.exists(METADATA_PATH):
        try:
            with open(METADATA_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            # 文件损坏或为空，返回空字典
            return {}
    return {}

def save_metadata(metadata):
    """Saves the last successful crawl time."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(METADATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=4, ensure_ascii=False)

# --- DATA SCRAPING FUNCTION (Writing to Disk) ---

def scrape_content(payload_override, output_name, status_placeholder):
    """
    Scrapes data and saves it to a local JSON file. (和 crawler.py 中保持一致)
    """

    # Base Payload structure (defaults)
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

    status_placeholder.info(f"[{output_name}] 🚀 开始抓取数据...")

    success = True
    while True:
        payload['current'] = current_page
        headers = get_random_headers()

        try:
            status_placeholder.text(f"[{output_name}] 正在抓取第 {current_page} 页，当前总计 {len(all_content)} 条记录...")
            response = session.post(POST_URL, headers=headers, json=payload, timeout=15)
            response.raise_for_status()
            response_json = response.json()

            page_content = response_json.get('data', {}).get('content', [])
            content_count = len(page_content)

            if not page_content:
                status_placeholder.text(f"[{output_name}] 第 {current_page} 页无内容。抓取停止。")
                break

            all_content.extend(page_content)

            if content_count < page_size:
                status_placeholder.text(f"[{output_name}] 已达到最后一页。总计 {len(all_content)} 条记录。")
                break

            current_page += 1
            time.sleep(random.uniform(2, 5))

        except requests.exceptions.RequestException as e:
            status_placeholder.error(f"[{output_name}] ⚠️ 请求第 {current_page} 页时发生错误: {e}")
            success = False
            time.sleep(10)
            break
        except json.JSONDecodeError:
            status_placeholder.error(f"[{output_name}] ⚠️ 无法解析第 {current_page} 页的 JSON 响应。")
            success = False
            time.sleep(10)
            break

    final_count = len(all_content)

    # --- Saving Data ---
    if success and final_count > 0:
        output_path = os.path.join(OUTPUT_DIR, f"{output_name}.json")
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(all_content, f, indent=4, ensure_ascii=False)
            status_placeholder.success(f"[{output_name}] ✅ 抓取完成。总计记录: **{final_count}** 条。")
            return True
        except Exception as e:
            status_placeholder.error(f"[{output_name}] ❌ 写入 JSON 文件失败: {e}")
            return False
    elif final_count == 0:
        status_placeholder.warning(f"[{output_name}] 未获取到任何记录。")
        return False
    else:
        return False


# --- DATA LOADING (Reading from Disk) ---

def load_data(task_name):
    """Loads data from a local JSON file."""
    output_path = os.path.join(OUTPUT_DIR, f"{task_name}.json")
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    return None

# --- DATA ANALYSIS AND PLOTTING FUNCTION ---

# Setting plotly template
pio.templates.default = "plotly_dark"

def show_statistics(all_content, data_name, crawl_time, is_manual_task=True): # 增加 is_manual_task 参数

    st.markdown("---")
    st.header(f"数据分析: {data_name}")

    # --- 新增/修改：手动采集按钮和状态显示 ---
    if is_manual_task:
        st.subheader("手动采集控制")
        task_config = next(v for k, v in TASK_CONFIG.items() if v["name"] == data_name)

        # 按钮容器
        col_btn, col_status = st.columns([1, 4])

        if col_btn.button(f"现在采集: {data_name}", key=f"btn_{data_name}", type="primary"):
            start_time = datetime.now()

            # 使用状态占位符
            status_placeholder = col_status.empty()

            success = scrape_content(task_config["payload"], data_name, status_placeholder)

            if success:
                metadata = load_metadata()
                metadata[data_name] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                save_metadata(metadata)

            status_placeholder.empty()
            col_status.success(f"采集完成！耗时: {datetime.now() - start_time}。请刷新页面查看新数据。")
            st.rerun() # 触发页面重新加载以显示新数据

        else:
            col_status.caption(f"上次采集时间：**{crawl_time if crawl_time else '无记录'}**")

    else:
        # 自动采集任务的显示逻辑
        st.subheader("自动采集状态")
        if crawl_time:
            st.caption(f"数据采集时间：**{crawl_time}** (由 GitHub Action 定时更新)")
        else:
            st.caption("尚未成功采集该任务数据。数据由 GitHub Action 定时更新。")

    st.markdown("---") # 确保图表和按钮/状态分离

    if not all_content:
        st.warning("无数据可供分析。")
        return

    df = pd.DataFrame(all_content)

    # ... (保持原有的日期转换、过滤、特征工程逻辑) ...
    if df.empty or 'publishDate' not in df.columns:
        st.warning("DataFrame 为空或缺少 'publishDate' 字段。无法生成图表。")
        return

    try:
        # 使用 .copy() 避免 SettingWithCopyWarning
        df['PublishDateTime'] = pd.to_datetime(df['publishDate'])
    except Exception as e:
        st.error(f"日期格式转换错误: {e}")
        return

    cutoff_date = pd.to_datetime('2024-01-01')
    initial_count = len(df)
    df = df[df['PublishDateTime'] >= cutoff_date].copy() # 再次使用 copy() 确保链式操作安全
    filtered_count = len(df)

    if initial_count != filtered_count:
        st.info(f"已过滤 {initial_count - filtered_count} 条早于 {cutoff_date.date()} 的历史噪音记录。")

    df['PublishDateOnly'] = df['PublishDateTime'].dt.date
    df['PublishHour'] = df['PublishDateTime'].dt.hour
    df['PublishDayOfWeek'] = df['PublishDateTime'].dt.day_name(locale='en_GB')
    day_map = {'Monday': '周一', 'Tuesday': '周二', 'Wednesday': '周三', 'Thursday': '周四', 'Friday': '周五', 'Saturday': '周六', 'Sunday': '周日'}
    df['PublishDayOfWeek'] = df['PublishDayOfWeek'].map(day_map)
    day_order = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    df['PublishDayOfWeek'] = pd.Categorical(df['PublishDayOfWeek'], categories=day_order, ordered=True)

    # --- Plotting Logic (保持不变) ---
    st.subheader("1. 每日更新频次")
    # ... (Plotting code for PLOT 1) ...
    frequency_df = df.groupby(['PublishDateOnly', 'PublishDayOfWeek'], observed=True)['PublishDateTime'].count().reset_index()
    frequency_df.columns = ['PublishDate', 'PublishDayOfWeek', 'UpdateCount']
    frequency_df = frequency_df.sort_values('PublishDate')

    fig_freq = px.bar(
        frequency_df, x='PublishDate', y='UpdateCount', title='每日更新频次 (可缩放)',
        labels={'UpdateCount': '更新频次', 'PublishDate': '日期', 'PublishDayOfWeek': '周几'},
        hover_data=['PublishDayOfWeek'], height=500
    )
    fig_freq.update_xaxes(
        tickangle=-45, rangeslider_visible=True,
        rangeselector=dict(
            bgcolor="#333333", activecolor="#555555", font=dict(color="white"),
            buttons=[
                dict(count=7, label="1周", step="day", stepmode="backward"),
                dict(count=1, label="1月", step="month", stepmode="backward"),
                dict(count=3, label="1季", step="month", stepmode="backward"),
                dict(count=1, label="1年", step="year", stepmode="backward"),
                dict(step="all", label="全部")
            ]),
        tickformat="%Y-%m-%d"
    )
    st.plotly_chart(fig_freq, use_container_width=True)

    st.subheader("2. 更新活跃度分析")
    col1, col2 = st.columns(2)
    with col1:
        time_df_hour = df.groupby('PublishHour', observed=True)['PublishDateTime'].count().reset_index(name='UpdateCount')
        fig_hour = px.bar(time_df_hour, x='PublishHour', y='UpdateCount', title='全时段更新活跃度', labels={'PublishHour': '时刻 (0-23)', 'UpdateCount': '更新频次'}, height=400)
        fig_hour.update_layout(xaxis={'tickmode': 'linear', 'dtick': 1})
        st.plotly_chart(fig_hour, use_container_width=True)
    with col2:
        hour_order = list(range(24))
        time_df_heatmap = df.groupby(['PublishHour', 'PublishDayOfWeek'], observed=True).size().reset_index(name='UpdateCount')
        index = pd.MultiIndex.from_product([hour_order, day_order], names=['PublishHour', 'PublishDayOfWeek'])
        time_df_heatmap = time_df_heatmap.set_index(['PublishHour', 'PublishDayOfWeek']).reindex(index, fill_value=0).reset_index()
        time_df_heatmap['PublishDayOfWeek'] = pd.Categorical(time_df_heatmap['PublishDayOfWeek'], categories=day_order, ordered=True)
        fig_heatmap = px.density_heatmap(time_df_heatmap, x="PublishHour", y="PublishDayOfWeek", z="UpdateCount", title='更新活跃度: 时刻 vs. 周几', labels={"PublishHour": "时刻", "PublishDayOfWeek": "周几", "UpdateCount": "更新频次"}, category_orders={"PublishDayOfWeek": day_order, "PublishHour": hour_order}, nbinsx=24, color_continuous_scale=px.colors.sequential.Viridis, height=400)
        fig_heatmap.update_xaxes(range=[-0.5, 23.5], tickmode='linear', dtick=1)
        st.plotly_chart(fig_heatmap, use_container_width=True)


    # --- 3. 原始数据表格 (仅限北京) ---
    if data_name == "所有招采_正在招标_北京":
        st.subheader("3. 原始数据表")

        required_cols_map = {
            'publishDate': '发布时间',
            'companyTypeName': '公司区域',
            'name': '标题',
            'tenderSaleDeadline': '截标时间',
            'backDate': '退回时间'
        }

        available_cols = [col for col in required_cols_map.keys() if col in df.columns]

        if not available_cols:
            st.warning("无法显示数据表：抓取的数据中缺少必要的字段。")
            return

        rename_map = {col: required_cols_map[col] for col in available_cols}
        display_df = df[available_cols].rename(columns=rename_map)

        if '发布时间' in display_df.columns:
            display_df = display_df.sort_values(by='发布时间', ascending=False)

        st.dataframe(display_df, use_container_width=True, height=600)


# --- MAIN APPLICATION ENTRY POINT ---

def main():
    st.set_page_config(
        page_title="招采数据监控",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    st.title("📡 中国移动招采平台数据监控")
    st.info("数据集 1 和 2 可手动触发采集；数据集 3 由 GitHub Actions 定时更新。")

    # 4. 优先读取本地 json 文件并显示图表
    metadata = load_metadata()

    # 遍历所有任务配置
    for i, task_key in enumerate(TASK_CONFIG.keys()):
        config = TASK_CONFIG[task_key]
        task_name = config["name"]

        crawl_time = metadata.get(task_name)
        raw_data = load_data(task_name)

        # 判断是否为手动任务
        is_manual = (i < 2) # 前两个任务 (索引 0 和 1) 是手动的

        # 传入 is_manual 参数来控制按钮和状态的显示
        show_statistics(raw_data, task_name, crawl_time, is_manual_task=is_manual)


if __name__ == "__main__":
    main()