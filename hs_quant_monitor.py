import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import time
import requests

# ==========================================
# 0. Page Config & Constants
# ==========================================
st.set_page_config(page_title="恒生互联网量化监控 | 2518 极限恐慌模型", layout="wide", page_icon="📈")

INDEX_TRIGGER_POINT = 2518.0
FUND_CODE = "513330"
INDEX_CODE = "800806"

# UI 样式
st.markdown("""
<style>
    .metric-container {
        background-color: #1e1e1e;
        border-radius: 10px;
        padding: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .status-alert {
        padding: 15px;
        border-radius: 8px;
        font-weight: bold;
        text-align: center;
        margin-bottom: 20px;
    }
    .status-a { background-color: #2e3b4e; color: #a0aec0; border: 1px solid #4a5568; }
    .status-b { background-color: #742a2a; color: #feb2b2; border: 1px solid #e53e3e; animation: pulse 2s infinite; }
    @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(229, 62, 62, 0.7); }
        70% { box-shadow: 0 0 0 10px rgba(229, 62, 62, 0); }
        100% { box-shadow: 0 0 0 0 rgba(229, 62, 62, 0); }
    }
</style>
""", unsafe_allow_html=True)


# ==========================================
# 1. Data Layer (数据获取与异常兜底)
# ==========================================

@st.cache_data(ttl=60, show_spinner=False)
def fetch_hk_index():
    """获取 800806.HK 实时点位 (使用新浪 Sina API)"""
    try:
        url = "https://hq.sinajs.cn/list=rt_hk800806"
        headers = {"Referer": "https://finance.sina.com.cn"}
        res = requests.get(url, headers=headers, timeout=5)
        # 返回格式: var hq_str_rt_hk800806="恒生互联网科技业,2518.00,...";
        data_str = res.text.split('"')[1]
        if data_str:
            fields = data_str.split(',')
            return float(fields[6]) # 新浪HK实时接口的第6个字段通常为最新价
    except Exception as e:
        pass
        
    # 尝试腾讯备用接口
    try:
        url = "https://qt.gtimg.cn/q=hk800806"
        res = requests.get(url, timeout=5)
        # 返回格式: v_hk800806="1~恒生互联网科技业~800806~2518.00~...
        data_str = res.text.split('"')[1]
        if data_str:
            fields = data_str.split('~')
            return float(fields[3]) # 腾讯接口第3个字段为最新价
    except:
        pass
        
    return None

@st.cache_data(ttl=60, show_spinner=False)
def fetch_etf_spot():
    """获取 513330.SH 实时盘口现价 (使用腾讯 Tencent API 或新浪 API)"""
    # 优先腾讯接口
    try:
        url = "https://qt.gtimg.cn/q=sh513330"
        res = requests.get(url, timeout=5)
        # v_sh513330="1~华夏恒生互联网ETF~513330~0.446~...
        data_str = res.text.split('"')[1]
        if data_str:
            fields = data_str.split('~')
            return float(fields[3])
    except:
        pass
        
    # 尝试新浪备用接口
    try:
        url = "https://hq.sinajs.cn/list=sh513330"
        headers = {"Referer": "https://finance.sina.com.cn"}
        res = requests.get(url, headers=headers, timeout=5)
        # var hq_str_sh513330="华夏...',0.446,...
        data_str = res.text.split('"')[1]
        if data_str:
            fields = data_str.split(',')
            return float(fields[3]) # 新浪A股接口第3字段为现价
    except:
        pass
        
    return None

@st.cache_data(ttl=60*60, show_spinner=False)
def fetch_etf_hist():
    """获取 513330.SH 近期日线数据用于绘图 (使用腾讯日线API)"""
    try:
        # 腾讯日线接口
        url = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newiqkline/get?param=sh513330,day,,,100,qfq"
        res = requests.get(url, timeout=5)
        data = res.json()
        
        # 提取日线数据 (qfqday 表示前复权)
        kline_list = data['data']['sh513330']['qfqday']
        
        # 腾讯接口格式: [date, open, close, high, low, volume]
        df = pd.DataFrame(kline_list, columns=['日期', '开盘', '收盘', '最高', '最低', '成交量'])
        df['日期'] = pd.to_datetime(df['日期'])
        df['开盘'] = df['开盘'].astype(float)
        df['收盘'] = df['收盘'].astype(float)
        df['最高'] = df['最高'].astype(float)
        df['最低'] = df['最低'].astype(float)
        
        return df
    except Exception:
        return None


# ==========================================
# 2. Core Logic (网格计算逻辑)
# ==========================================

def calculate_grid(anchor_price):
    """
    基于 ANCHOR_PRICE 计算底仓及深度防守网格
    """
    # 1. 底仓吃单区 (30,000 元)
    base_orders = [
        {"node": "底仓 第1笔", "target_price": round(anchor_price * 1.000, 3), "amount": 10000, "drop": "0.0%"},
        {"node": "底仓 第2笔", "target_price": round(anchor_price * 0.985, 3), "amount": 10000, "drop": "-1.5%"},
        {"node": "底仓 第3笔", "target_price": round(anchor_price * 0.970, 3), "amount": 10000, "drop": "-3.0%"},
    ]
    
    # 计算底仓加权平均成本
    total_base_amount = sum([order['amount'] for order in base_orders])
    total_base_shares = sum([order['amount'] / order['target_price'] for order in base_orders])
    avg_base_price = total_base_amount / total_base_shares
    
    # 2. 深度防守区 (70,000 元)
    defense_orders = [
        {"node": "防守 档位1", "target_price": round(avg_base_price * 0.95, 3), "amount": 10000, "drop": "-5.0% (相对底仓均价)"},
        {"node": "防守 档位2", "target_price": round(avg_base_price * 0.90, 3), "amount": 15000, "drop": "-10.0% (相对底仓均价)"},
        {"node": "防守 档位3", "target_price": round(avg_base_price * 0.85, 3), "amount": 20000, "drop": "-15.0% (相对底仓均价)"},
        {"node": "防守 档位4", "target_price": round(avg_base_price * 0.80, 3), "amount": 25000, "drop": "-20.0% (相对底仓均价)"},
    ]
    
    return base_orders, defense_orders, avg_base_price


# ==========================================
# 3. UI & Visualization (UI 渲染层)
# ==========================================

def render_ui():
    st.title("🛡️ 恒生互联网专属量化监控中心")
    st.markdown("### 2518 极限恐慌双锚定网格模型")
    
    st.sidebar.header("⚙️ 监控配置")
    st.sidebar.markdown(f"**目标指数**:恒生互联网科技业指数 (800806.HK)")
    st.sidebar.markdown(f"**交易标的**:华夏恒生互联网ETF (513330.SH)")
    st.sidebar.markdown(f"**触发锚点**: <= {INDEX_TRIGGER_POINT} 点")
    
    if st.sidebar.button("🔄 手动刷新数据"):
        fetch_hk_index.clear()
        fetch_etf_spot.clear()
        st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.caption(f"上次更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 获取数据
    with st.spinner("正在获取实盘数据，请稍候..."):
        idx_val = fetch_hk_index()
        etf_val = fetch_etf_spot()
        kline_df = fetch_etf_hist()
        
    # 网络失败导致的数据兜底保护层（Manual Override机制）
    is_manual_override = False
    if idx_val is None or etf_val is None:
        st.sidebar.markdown("---")
        st.sidebar.error("🔌 **网络或反爬虫拦截**\n部署云端的IP通常会被东方财富(EastMoney)等数据源安全拦截以致无法获取实时数据。")
        st.sidebar.warning("已进入 **应急手动接入模式**")
        idx_val = st.sidebar.number_input("手动输入恒指互联 (800806.HK) 当下点位:", min_value=1000.0, max_value=5000.0, value=2500.0, step=10.0)
        etf_val = st.sidebar.number_input("手动输入 ETF (513330.SH) 当下现价:", min_value=0.1, max_value=2.0, value=0.45, step=0.001, format="%.3f")
        is_manual_override = True
        
        st.warning(f"📡 自动获取实盘数据失败（遭遇强力反爬拦截）。系统已自动切换至**应急手动接入模式**，当前使用的是您在侧边栏输入的值。")
    
    # 状态判断逻辑
    state_b_triggered = False
    
    diff_points = round(idx_val - INDEX_TRIGGER_POINT, 2)
    
    if idx_val > INDEX_TRIGGER_POINT:
        # 状态 A
        st.markdown('<div class="status-alert status-a">🟢 状态 A (静默期)：未到击球区，严禁主观建仓！严禁主观建仓！严禁主观建仓！</div>', unsafe_allow_html=True)
    else:
        # 状态 B
        state_b_triggered = True
        st.markdown('<div class="status-alert status-b">🚨 状态 B (已触发)：指数进入极限恐慌区！系统已锁定锚点，按下方计划无情执行！</div>', unsafe_allow_html=True)

    # 1. 双屏仪表盘
    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="metric-container">', unsafe_allow_html=True)
        st.metric(label="📊 恒指互联指数 (800806.HK)", 
                  value=f"{idx_val:.2f}",
                  delta=f"距离触发点 {diff_points:+.2f} 点",
                  delta_color="inverse")
        st.markdown('</div>', unsafe_allow_html=True)
        
    with col2:
        st.markdown('<div class="metric-container">', unsafe_allow_html=True)
        st.metric(label="💰 交易标的现价 (513330.SH)", 
                  value=f"¥ {etf_val:.3f}", 
                  help="如果系统触发，此价格将作为基准锚定价格 (ANCHOR_PRICE)")
        st.markdown('</div>', unsafe_allow_html=True)
        
    st.markdown("---")
    
    # 预准备图表
    fig = go.Figure()
    if kline_df is not None and not kline_df.empty:
        fig.add_trace(go.Candlestick(x=kline_df['日期'],
                        open=kline_df['开盘'],
                        high=kline_df['最高'],
                        low=kline_df['最低'],
                        close=kline_df['收盘'],
                        name='513330.SH'))
    else:
        fig.add_annotation(text="暂无K线数据", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)

    # 2 & 3. 触发后的网格计算与展示
    table_data = []
    
    if state_b_triggered:
        anchor_price = etf_val
        st.subheader("🎯 行动指令表")
        st.info(f"📍 **基准锚点价 (ANCHOR_PRICE)**: 已锁定当前盘口现价 **{anchor_price:.3f}** 元")
        
        base_orders, defense_orders, avg_base_price = calculate_grid(anchor_price)
        
        # 拼装数据
        for order in base_orders:
            order['状态'] = "✅ 立即铺单" if order['target_price'] >= anchor_price else "⏳ 等待挂单成交"
            table_data.append(order)
            
        for order in defense_orders:
            order['状态'] = "🛡️ 防守网格带"
            table_data.append(order)
            
        df_orders = pd.DataFrame(table_data)
        # 调整列顺序和名称
        df_orders = df_orders[['node', 'target_price', 'drop', 'amount', '状态']]
        df_orders.columns = ['节点', '目标买入价 (¥)', '下跌幅度', '买入金额 (¥)', '执行状态']
        
        # 显示指令表
        st.dataframe(df_orders, use_container_width=True, hide_index=True)
        
        # 在K线图上标绘网格线
        colors_base = ["#ecc94b", "#d69e2e", "#b7791f"]
        colors_def = ["#fc8181", "#f56565", "#e53e3e", "#c53030"]
        
        # 绘制基线
        fig.add_hline(y=anchor_price, line_dash="dash", line_color="#cbd5e0", 
                      annotation_text=f"ANCHOR ({anchor_price:.3f})", 
                      annotation_position="right", opacity=0.8)
                      
        # 绘制底仓线
        for idx, order in enumerate(base_orders):
            p = order['target_price']
            fig.add_hline(y=p, line_dash="dash", line_color=colors_base[idx % len(colors_base)], 
                          annotation_text=f"底仓 {p:.3f} ({order['amount']}元)", 
                          annotation_position="left")
                          
        # 绘制防守线
        # 为了美观，标注底仓均价
        fig.add_hline(y=avg_base_price, line_dash="solid", line_color="#3182ce", 
                      annotation_text=f"底仓均价基准 ({avg_base_price:.3f})", 
                      annotation_position="right", opacity=0.5)
                      
        for idx, order in enumerate(defense_orders):
            p = order['target_price']
            fig.add_hline(y=p, line_dash="dot", line_color=colors_def[idx % len(colors_def)], 
                          annotation_text=f"防守 {p:.3f} ({order['amount']}元)", 
                          annotation_position="left")

    style_layout = dict(
        title="📈 华夏恒生互联网ETF (513330.SH) 可视化击球区",
        xaxis_title="Date",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        template="plotly_dark",
        height=600,
        margin=dict(l=20, r=20, t=50, b=20)
    )
    fig.update_layout(**style_layout)
    
    st.plotly_chart(fig, use_container_width=True)

if __name__ == "__main__":
    render_ui()
