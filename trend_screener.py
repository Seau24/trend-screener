# -*- coding: utf-8 -*-
import tushare as ts
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime
import os
import time

# ========== 配置（从 GitHub Secrets 读取）==========
TS_TOKEN = os.environ.get('TUSHARE_TOKEN')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL')
SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD')
RECEIVER_EMAIL = os.environ.get('RECEIVER_EMAIL')

# ========== 筛选参数（可在此调整）==========
MAX_PRICE = 80                 # 股价 ≤ 80 元
MIN_GAIN_10D = 10              # 10日涨幅 ≥ 10%
CONSECUTIVE_DAYS_MA5 = 5       # 连续5日收盘 > MA5
CONSECUTIVE_DAYS_MA10 = 5      # 连续5日最低价 ≥ MA10（盘中不破）
CONSECUTIVE_DAYS_MA20 = 8      # 新增：连续8个交易日最低价不跌破MA20

# ========== 手动指定交易日（必填）==========
MANUAL_DATE = '20260713'

if not MANUAL_DATE:
    raise ValueError("错误：请在代码中设置 MANUAL_DATE 为要筛选的日期（例如 '20260605'）")

ts.set_token(TS_TOKEN)
pro = ts.pro_api()

def get_batch_daily_data(trade_date):
    """一次请求获取当日所有股票的日线数据"""
    try:
        df = pro.daily(trade_date=trade_date, fields='ts_code,close,vol,pct_chg')
        if df is None or len(df) == 0:
            return pd.DataFrame()
        return df
    except Exception as e:
        print(f"批量获取日线数据失败: {e}")
        return pd.DataFrame()

def get_stock_history(ts_code, end_date):
    """获取单只股票的历史数据（仅对初步筛选后的股票调用）"""
    try:
        df = pro.daily(ts_code=ts_code, start_date='', end_date=end_date, limit=120,
                       fields='trade_date,close,low,vol,pct_chg')
        if df is None or len(df) < 20:
            return None
        df = df.sort_values('trade_date').reset_index(drop=True)
        return df
    except Exception as e:
        print(f"获取历史数据失败 {ts_code}: {e}")
        return None

def check_stock(df_history, ts_code, name, trade_date):
    if df_history is None or len(df_history) < 20:
        return None

    # 计算均线
    df_history['ma5'] = df_history['close'].rolling(5).mean()
    df_history['ma10'] = df_history['close'].rolling(10).mean()
    df_history['ma20'] = df_history['close'].rolling(20).mean()

    # 计算 MACD
    exp1 = df_history['close'].ewm(span=12, adjust=False).mean()
    exp2 = df_history['close'].ewm(span=26, adjust=False).mean()
    df_history['dif'] = exp1 - exp2
    df_history['dea'] = df_history['dif'].ewm(span=9, adjust=False).mean()

    latest = df_history.iloc[-1]

    # 1. 股价限制（≤ 80元）
    if latest['close'] > MAX_PRICE:
        return None

    # 2. 均线多头排列
    if latest['ma5'] <= latest['ma10'] or latest['ma10'] <= latest['ma20']:
        return None

    # 3. 连续5日收盘 > MA5 且 最低价 ≥ MA10
    if len(df_history) < CONSECUTIVE_DAYS_MA5:
        return None
    last_n = df_history.iloc[-CONSECUTIVE_DAYS_MA5:]
    for i in range(len(last_n)):
        if last_n.iloc[i]['close'] <= last_n.iloc[i]['ma5']:
            return None
        if last_n.iloc[i]['low'] < last_n.iloc[i]['ma10']:
            return None

    # 4. 10日涨幅 ≥ 10%
    if len(df_history) < 11:
        return None
    close_10d_ago = df_history.iloc[-11]['close']
    gain_10d = (latest['close'] - close_10d_ago) / close_10d_ago * 100
    if gain_10d < MIN_GAIN_10D:
        return None

    # 5. 连续8个交易日最低价不跌破MA20（新条件）
    if len(df_history) < CONSECUTIVE_DAYS_MA20:
        return None
    last_8 = df_history.iloc[-CONSECUTIVE_DAYS_MA20:]
    for i in range(len(last_8)):
        if last_8.iloc[i]['low'] < last_8.iloc[i]['ma20']:
            return None

    # 6. MACD 上升（DIF > DEA 且 DIF 较前一日上升）
    if len(df_history) >= 2:
        if latest['dif'] <= latest['dea'] or latest['dif'] <= df_history.iloc[-2]['dif']:
            return None
    else:
        return None

    return {
        'code': ts_code.split('.')[0],
        'name': name,
        'close': latest['close'],
        'ma5': latest['ma5'],
        'ma10': latest['ma10'],
        'ma20': latest['ma20'],
        'gain_10d': gain_10d,
        'dif': latest['dif'],
        'dea': latest['dea']
    }

def get_stock_name(ts_code):
    try:
        basic = pro.stock_basic(ts_code=ts_code, fields='name')
        if basic is not None and len(basic) > 0:
            name = basic['name'].iloc[0]
            if 'ST' in name.upper() or '*ST' in name.upper():
                return None
            return name
    except:
        pass
    return ts_code.split('.')[0]

def send_email(results, date_str):
    if not results:
        subject = f"趋势票筛选 - {date_str} - 无符合"
        body = f"日期：{date_str}\n\n今日无股票符合条件。\n\n当前条件：\n- 沪深主板，非ST\n- 股价 ≤ {MAX_PRICE}元\n- MA5 > MA10 > MA20\n- 连续{CONSECUTIVE_DAYS_MA5}日收盘 > MA5 且 最低价 ≥ MA10\n- 10日涨幅 ≥ {MIN_GAIN_10D}%\n- 连续{CONSECUTIVE_DAYS_MA20}个交易日最低价不跌破MA20\n- MACD上升（DIF > DEA 且 DIF 上升）"
    else:
        subject = f"趋势票筛选 - {date_str} - 发现{len(results)}只"
        body = f"日期：{date_str}\n\n发现 {len(results)} 只股票符合条件：\n\n"
        for r in results:
            body += f"【{r['code']}】{r['name']}\n"
            body += f"  收盘：{r['close']:.2f}\n"
            body += f"  均线：MA5={r['ma5']:.2f}  MA10={r['ma10']:.2f}  MA20={r['ma20']:.2f}\n"
            body += f"  10日涨幅：{r['gain_10d']:.1f}%\n"
            body += f"  MACD：DIF={r['dif']:.4f}  DEA={r['dea']:.4f}\n\n"
        body += f"条件：股价≤{MAX_PRICE}元，连续{CONSECUTIVE_DAYS_MA5}日收盘>MA5且最低≥MA10，10日涨幅≥{MIN_GAIN_10D}%，连续{CONSECUTIVE_DAYS_MA20}个交易日最低价不跌破MA20，MACD上升。"
    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECEIVER_EMAIL
        server = smtplib.SMTP('smtp.qq.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, [RECEIVER_EMAIL], msg.as_string())
        server.quit()
        print(f"邮件发送成功！共{len(results)}只")
    except Exception as e:
        print(f"邮件发送失败：{e}")

def main():
    print("=" * 60)
    print("趋势票筛选器启动")
    trade_date = MANUAL_DATE
    print(f"手动指定交易日：{trade_date}")

    daily_df = get_batch_daily_data(trade_date)
    if daily_df.empty:
        print(f"错误：无法获取 {trade_date} 的日线数据，请确认该日期是交易日且 Tushare 有数据")
        return

    daily_df['code'] = daily_df['ts_code'].str.split('.').str[0]
    daily_df = daily_df[daily_df['code'].str.startswith(('60', '00'))]
    daily_df = daily_df[daily_df['close'] <= MAX_PRICE]
    stock_list = daily_df['ts_code'].tolist()
    print(f"初步筛选后剩余 {len(stock_list)} 只股票（主板 + 股价≤{MAX_PRICE}元）")

    results = []
    total = len(stock_list)
    for i, ts_code in enumerate(stock_list):
        if (i+1) % 20 == 0:
            print(f"已处理 {i+1}/{total} 只")
        name = get_stock_name(ts_code)
        if name is None:
            continue
        hist = get_stock_history(ts_code, trade_date)
        if hist is None:
            continue
        res = check_stock(hist, ts_code, name, trade_date)
        if res:
            results.append(res)
            print(f"  ✅ {res['code']} {res['name']}")
        time.sleep(0.2)

    print(f"\n筛选完成！共 {len(results)} 只股票符合条件")
    send_email(results, trade_date)

if __name__ == "__main__":
    main()
