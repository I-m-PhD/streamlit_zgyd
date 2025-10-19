# app.py

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.io as pio
import json
import os

# --- CONFIGURATION ---
OUTPUT_DIR = "./zgyd"
METADATA_PATH = os.path.join(OUTPUT_DIR, "metadata.json")

# 定义所有需要采集的任务配置 (用于识别文件名)
TASK_CONFIG = {
    "TASK_1": {"payload": {}, "name": "所有招采"},
    "TASK_2": {"payload": {"homePageQueryType": "Bidding"}, "name": "所有招采_正在招标"},
    "TASK_3": {"payload": {"homePageQueryType": "Bidding", "companyType": "BJ"}, "name": "所有招采_正在招标_北京"},
}

# 任务对应的动态更新计划描述
TASK_UPDATE_SCHEDULES = {
    "TASK_1": "每日 06:00 更新",
    "TASK_2": "每日 10:10, 14:10, 18:10, 22:10, 02:10 (次日), 06:10 (次日) 更新",
    "TASK_3": "每日 08:00-23:59 (当日), 06:00-07:59 (次日) 整点 15 分, 45 分更新",
}

# --- METADATA AND DATA LOADING ---

def load_metadata():
    """Loads the last successful crawl time for all tasks."""
    if os.path.exists(METADATA_PATH):
        try:
            with open(METADATA_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

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

def show_statistics(all_content, data_name, crawl_time, task_key):

    st.markdown("---")
    st.header(f"{data_name}")

    # 获取记录总数
    record_count = len(all_content) if all_content is not None else 0

    # ---------------------------------------------------------
    # 显示采集状态和数据条数
    # ---------------------------------------------------------
    
    # 动态获取更新计划描述
    schedule_text = TASK_UPDATE_SCHEDULES.get(task_key, "由 GitHub Action 定时更新")

    col_time, col_info, col_count = st.columns([1, 2, 1])

    with col_time:
        # st.subheader("采集状态")
        if crawl_time:
            st.caption(f"上次采集时间: {crawl_time}")
        else:
            st.caption(f"上次采集时间: 无记录")

    with col_info:
        st.caption(f"{schedule_text}")

    with col_count:
        # st.subheader("数据量")
        if record_count > 0:
            st.caption(f"当前总记录数: {record_count} 条")
        else:
            st.caption("当前总记录数: 0 条 (等待首次采集)")

    # st.markdown("---")
    # ---------------------------------------------------------

    if not all_content:
        st.warning("无数据可供分析。")
        return

    df = pd.DataFrame(all_content)

    # 修复了 locale.Error 的代码
    if df.empty or 'publishDate' not in df.columns:
        st.warning("DataFrame 为空或缺少 'publishDate' 字段。无法生成图表。")
        return

    try:
        df['PublishDateTime'] = pd.to_datetime(df['publishDate'])
    except Exception as e:
        st.error(f"日期格式转换错误: {e}")
        return

    cutoff_date = pd.to_datetime('2024-01-01')
    initial_count = len(df)
    df = df[df['PublishDateTime'] >= cutoff_date].copy()
    filtered_count = len(df)

    if initial_count != filtered_count:
        st.info(f"已过滤 {initial_count - filtered_count} 条早于 {cutoff_date.date()} 的历史噪音记录。")

    df['PublishDateOnly'] = df['PublishDateTime'].dt.date
    df['PublishHour'] = df['PublishDateTime'].dt.hour

    # 使用不带 locale 参数的方法获取英文名称
    df['PublishDayOfWeek'] = df['PublishDateTime'].dt.day_name()

    # 中文映射逻辑
    day_map = {'Monday': '周一', 'Tuesday': '周二', 'Wednesday': '周三', 'Thursday': '周四', 'Friday': '周五', 'Saturday': '周六', 'Sunday': '周日'}
    df['PublishDayOfWeek'] = df['PublishDayOfWeek'].map(day_map)
    day_order = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    df['PublishDayOfWeek'] = pd.Categorical(df['PublishDayOfWeek'], categories=day_order, ordered=True)

    # --- Plotting Logic (保持不变) ---
    # st.subheader("1. 每日更新频次")
    frequency_df = df.groupby(['PublishDateOnly', 'PublishDayOfWeek'], observed=True)['PublishDateTime'].count().reset_index()
    frequency_df.columns = ['PublishDate', 'PublishDayOfWeek', 'UpdateCount']
    frequency_df = frequency_df.sort_values('PublishDate')
    fig_freq = px.bar(frequency_df, x='PublishDate', y='UpdateCount', title='每日更新频次', labels={'UpdateCount': '更新频次', 'PublishDate': '日期', 'PublishDayOfWeek': '周几'}, hover_data=['PublishDayOfWeek'], height=500)
    fig_freq.update_xaxes(tickangle=-45, rangeslider_visible=True, rangeselector=dict(bgcolor="#333333", activecolor="#555555", font=dict(color="white"), buttons=[dict(count=7, label="1周", step="day", stepmode="backward"), dict(count=1, label="1月", step="month", stepmode="backward"), dict(count=3, label="1季", step="month", stepmode="backward"), dict(count=1, label="1年", step="year", stepmode="backward"), dict(step="all", label="全部")]), tickformat="%Y-%m-%d")
    st.plotly_chart(fig_freq, use_container_width=True)

    # st.subheader("2. 更新活跃度分析")
    col1, col2 = st.columns(2)
    with col1:
        time_df_hour = df.groupby('PublishHour', observed=True)['PublishDateTime'].count().reset_index(name='UpdateCount')
        fig_hour = px.bar(time_df_hour, x='PublishHour', y='UpdateCount', title='更新活跃时段', labels={'PublishHour': '时刻 (0-23)', 'UpdateCount': '更新频次'}, height=400)
        fig_hour.update_layout(xaxis={'tickmode': 'linear', 'dtick': 1, 'range': [-0.5, 23.5]})
        st.plotly_chart(fig_hour, use_container_width=True)
    with col2:
        hour_order = list(range(24))
        time_df_heatmap = df.groupby(['PublishHour', 'PublishDayOfWeek'], observed=True).size().reset_index(name='UpdateCount')
        index = pd.MultiIndex.from_product([hour_order, day_order], names=['PublishHour', 'PublishDayOfWeek'])
        time_df_heatmap = time_df_heatmap.set_index(['PublishHour', 'PublishDayOfWeek']).reindex(index, fill_value=0).reset_index()
        time_df_heatmap['PublishDayOfWeek'] = pd.Categorical(time_df_heatmap['PublishDayOfWeek'], categories=day_order, ordered=True)
        fig_heatmap = px.density_heatmap(time_df_heatmap, x="PublishHour", y="PublishDayOfWeek", z="UpdateCount", title='更新活跃时段 vs. 周几', labels={"PublishHour": "时刻", "PublishDayOfWeek": "周几", "UpdateCount": "更新频次"}, category_orders={"PublishDayOfWeek": day_order, "PublishHour": hour_order}, nbinsx=24, color_continuous_scale=px.colors.sequential.Viridis, height=400)
        fig_heatmap.update_xaxes(range=[-0.5, 23.5], tickmode='linear', dtick=1)
        st.plotly_chart(fig_heatmap, use_container_width=True)


    # --- 3. 原始数据表格 (仅限北京) ---
    if data_name == "所有招采_正在招标_北京":
        # st.subheader("3. 原始数据表")

        # 1. 定义 BASE_URL，用于构造链接 (与 crawler.py 保持一致)
        BASE_URL = 'https://b2b.10086.cn'
        
        # 2. 构造完整的 URL 字段
        # 注意：使用 .apply(lambda row: ...) 构造链接
        # 确保所有用于构造链接的字段都在 df 中，如果字段缺失，链接会包含 None 或空字符串。
        try:
            df['link'] = df.apply(
                lambda row: f'{BASE_URL}/#/noticeDetail?'
                            f'publishId={row.get("publishId", "")}&'
                            f'publishUuid={row.get("uuid", "")}&'
                            f'publishType={row.get("publishType", "")}&'
                            f'publishOneType={row.get("publishOneType", "")}',
                axis=1
            )
        except Exception as e:
            st.error(f"无法构造链接字段，请检查原始数据结构: {e}")
            return

        required_cols_map = {
            # 将 'link' 字段添加到映射中，并命名为 '详情链接' (LinkColumn将隐藏此列名)
            'link': '详情链接',
            'companyTypeName': '单位',
            'name': '标题',
            'publishDate': '发布时间',
            'tenderSaleDeadline': '文件售卖截止时间',
            'publicityEndTime': '公示截止时间',
            'backDate': '截标时间'
        }

        # 确保 'link' 字段已添加到可用列
        available_cols = [col for col in required_cols_map.keys() if col in df.columns]

        if not available_cols:
            st.warning("无法显示数据表：抓取的数据中缺少必要的字段。")
            return

        rename_map = {col: required_cols_map[col] for col in available_cols}

        # 3. 构造用于展示的 DataFrame (包含 link 字段)
        display_df = df[available_cols].rename(columns=rename_map)

        if '发布时间' in display_df.columns:
            display_df = display_df.sort_values(by='发布时间', ascending=False)

        # 4. 使用 st.dataframe 和 column_config 设置超链接
        st.dataframe(
            display_df, 
            use_container_width=True, 
            height=600,
            column_config={
                "标题": st.column_config.LinkColumn(
                    help="点击查看项目详情",
                    # 关键：指定 URL 来源列
                    link_column='详情链接'
                ),
                # 隐藏用于提供 URL 的 '详情链接' 列
                "详情链接": None 
            }
        )


# --- MAIN APPLICATION ENTRY POINT ---

def main():
    st.set_page_config(
        page_title="招采数据监控",
        layout="wide",
        initial_sidebar_state="collapsed"
    )

    st.title("招采数据监控")
    st.info("所有数据集均通过 GitHub Actions 定时更新。")

    metadata = load_metadata()

    # 遍历所有任务配置
    for task_key in TASK_CONFIG.keys():
        config = TASK_CONFIG[task_key]
        task_name = config["name"]

        crawl_time = metadata.get(task_name)
        raw_data = load_data(task_name)

        show_statistics(raw_data, task_name, crawl_time, task_key)


if __name__ == "__main__":
    main()