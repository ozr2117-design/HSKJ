import streamlit as st
import akshare as ak
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import time

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
    """获取 800806.HK 实时点位"""
    try:
        df = ak.stock_hk_index_spot_em()
        # 港股通代码可能会带有不同的后缀，精确匹配代码
        hk_index = df[df['代码'] == '800806']
        if not hk_index.empty:
            return float(hk_index.iloc[0]['最新价'])
        return None
    except Exception as e:
        st.sidebar.error(f"⚠️ 恒生互联网指数请求失败: {e}")
        return None

@st.cache_data(ttl=60, show_spinner=False)
def fetch_etf_spot():
    """获取 513330.SH 实时盘口现价"""
    try:
        df = ak.fund_etf_spot_em()
        etf = df[df['代码'] == FUND_CODE]
        if not etf.empty:
            return float(etf.iloc[0]['最新价'])
        return None
    except Exception as e:
        st.sidebar.error(f"⚠️ ETF 实时数据请求失败: {e}")
        return None

@st.cache_data(ttl=60*60, show_spinner=False)  # K线数据缓存久一点
def fetch_etf_hist():
    """获取 513330.SH 近期日线数据用于绘图"""
    try:
        df = ak.fund_etf_hist_em(symbol=FUND_CODE, period="daily", start_date="20230101", adjust="qfq")
        # 保留最近100个交易日
        df = df.tail(100)
        df['日期'] = pd.to_datetime(df['日期'])
        return df
    except Exception as e:
        st.sidebar.error(f"⚠️ ETF K线数据请求失败: {e}")
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
    
    # 状态判断逻辑
    state_b_triggered = False
    
    if idx_val is None or etf_val is None:
        st.warning("📡 无法获取到实时数据，请检查网络或稍后重试。")
        # 兜底：如果无法获取，中止后续敏感逻辑
        return
        
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
