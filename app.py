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
    # "TASK_2": "每日 10:10, 14:10, 18:10, 22:10, 02:10 (次日), 06:10 (次日) 更新",
    "TASK_2": "每日 02:10, 06:10, 10:10, 14:10, 18:10, 22:10 更新",
    # "TASK_3": "每日 08:00-23:59 (当日), 06:00-07:59 (次日) 整点 15 分, 45 分更新",
    "TASK_3": "每日 06:00-23:59 整点 15 分, 45 分更新",
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

    # st.markdown("---")
    # st.header(f"{data_name}")

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
        fig_heatmap = px.density_heatmap(time_df_heatmap, x="PublishHour", y="PublishDayOfWeek", z="UpdateCount", title='更新活跃热力图', labels={"PublishHour": "时刻", "PublishDayOfWeek": "", "UpdateCount": "更新频次"}, category_orders={"PublishDayOfWeek": day_order, "PublishHour": hour_order}, nbinsx=24, color_continuous_scale=px.colors.sequential.Viridis, height=400)
        fig_heatmap.update_xaxes(range=[-0.5, 23.5], tickmode='linear', dtick=1)
        fig_heatmap.update_layout(
            # 将颜色条放置在图表顶部
            coloraxis_colorbar=dict(
                orientation="h",  # H: Horizontal (水平) 或 V: Vertical (垂直)
                x=1,              # X轴位置，0 是最左，1 是最右
                y=1.35,            # Y轴位置，0 是底部，1 是顶部 (负值表示在图表区域外部)
                yanchor="top",    # 确保定位是基于颜色条的顶部
                xanchor="right",  # 确保颜色条居右对齐
            ),
            coloraxis_colorbar_title_text='更新频次'  # 去掉 "sum of"
        )
        st.plotly_chart(fig_heatmap, use_container_width=True)


    # --- 3. 原始数据表格 (仅限北京) ---
    if data_name == "所有招采_正在招标_北京":
        # st.subheader("3. 原始数据表")

        # 1. 定义 BASE_URL 
        BASE_URL = 'https://b2b.10086.cn'
        
        # 2. 【精确复制 crawler.py 逻辑】构造 URL 字段，并确保 None/NaN 转换为空字符串
        def build_link_safely(row):
            # 这是一个强健的函数，用于处理 Series 中的 None/NaN，确保 URL 参数中不会出现 'None' 字符串
            def safe_param(key):
                value = row.get(key)
                # 使用 pd.notna 检查非空值，并转换为字符串
                if pd.notna(value) and value is not None:
                    return str(value)
                # 否则返回空字符串，与 crawler.py 中的 .get(key, '') 效果一致
                return ''

            # 精确使用 crawler.py 中的字段名
            link_id = safe_param('id')
            link_uuid = safe_param('uuid')
            link_publish_type = safe_param('publishType')
            link_publish_one_type = safe_param('publishOneType')
            
            # 构造 URL (与 crawler.py 模板完全一致)
            return (
                f'{BASE_URL}/#/noticeDetail?'
                f'publishId={link_id}&'
                f'publishUuid={link_uuid}&'
                f'publishType={link_publish_type}&'
                f'publishOneType={link_publish_one_type}'
            )

        # 应用新的构建函数
        df['LINK'] = df.apply(build_link_safely, axis=1)

        required_cols_map = {
            'companyTypeName': '单位',
            'name': '标题',
            'LINK': '链接',
            'publishDate': '发布时间',
            'tenderSaleDeadline': '文件售卖截止时间',
            'publicityEndTime': '公示截止时间',
            'backDate': '截标时间'
        }

        # 合并所有必要的列
        all_required_keys = list(required_cols_map.keys())
        # 由于 df 已经有 URL_LINK，我们需要确保它也被检查
        available_cols = [col for col in all_required_keys if col in df.columns]

        if not available_cols:
            st.warning("无法显示数据表：抓取的数据中缺少必要的字段。")
            return

        rename_map = {col: required_cols_map[col] for col in available_cols}
        display_df = df[available_cols].rename(columns=rename_map)

        if '发布时间' in display_df.columns:
            display_df = display_df.sort_values(by='发布时间', ascending=False)

        # 3. 【渲染逻辑】使用 st.dataframe，并应用最简 LinkColumn 配置
        st.dataframe(
            display_df, 
            use_container_width=True, 
            height=600,
            column_config={
                # 保持最简 LinkColumn 配置，避免 v1.50.0 的 TypeError Bug
                "链接": st.column_config.LinkColumn(
                    # 设定列宽
                    width="small", 
                    # 显式添加一个 help 文本，以确保 LinkColumn 实例被创建和应用
                    help="点击查看项目详情链接"
                )
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
    # st.info("通过 Cloudflare Worker 定时触发 GitHub Actions 自动更新")

    metadata = load_metadata()

    # # 遍历所有任务配置
    # for task_key in TASK_CONFIG.keys():
    #     config = TASK_CONFIG[task_key]
    #     task_name = config["name"]

    #     crawl_time = metadata.get(task_name)
    #     raw_data = load_data(task_name)

    #     show_statistics(raw_data, task_name, crawl_time, task_key)

    # 按照 TASK_CONFIG 的顺序创建 Tabs 列表
    task_keys = list(TASK_CONFIG.keys())
    tab_names = [TASK_CONFIG[key]["name"] for key in task_keys]

    # 获取第三个 Tab 的名称
    default_tab_name = tab_names[2] # 索引 2 对应第三个 Tab
    
    # 创建 Streamlit Tabs
    tabs = st.tabs(tab_names, default=default_tab_name)

    # 遍历所有任务配置，并在各自的 Tab 内调用 show_statistics
    for i, task_key in enumerate(task_keys):
        with tabs[i]:
            config = TASK_CONFIG[task_key]
            task_name = config["name"]

            crawl_time = metadata.get(task_name)
            raw_data = load_data(task_name)

            # 在 Tab 内部调用 show_statistics，它将渲染所有内容
            show_statistics(raw_data, task_name, crawl_time, task_key)


if __name__ == "__main__":
    main()