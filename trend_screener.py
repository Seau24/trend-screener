# -*- coding: utf-8 -*-
import tushare as ts
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime, timedelta
import os
import time

# ========== 配置（从 GitHub Secrets 读取）==========
TS_TOKEN = os.environ.get('TUSHARE_TOKEN')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL')
SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD')
RECEIVER_EMAIL = os.environ.get('RECEIVER_EMAIL')

# ========== 筛选参数（可在此调整）==========
MAX_PRICE = 75                 # 股价 < 75元
MIN_GAIN_10D = 10              # 10日涨幅 ≥ 10%
CONSECUTIVE_DAYS = 6           # 连续6日收盘 > MA10
MA5_MA10_MA20 = True           # 要求均线多头排列
MACD_RISING = True             # 要求 MACD 上升

ts.set_token(TS_TOKEN)
pro = ts.pro_api()

def get_all_a_stocks():
    """获取所有沪深主板股票代码（剔除ST、创业板、科创板、北交所）"""
    try:
        # 使用 stock_basic 获取全部股票列表（需要积分，但一般默认有200积分可用）
        df = pro.stock_basic(exchange='', list_status='L', fields='ts_code,name')
        if df is None or len(df) == 0:
            # 备用方案：通过交易日获取当日有交易的股票
            today = datetime.now().strftime('%Y%m%d')
            daily = pro.daily(trade_date=today, fields='ts_code')
            if daily is not None and len(daily) > 0:
                df = daily
            else:
                return []
        # 提取代码数字部分
        df['code'] = df['ts_code'].str.split('.').str[0]
        # 只保留主板（60、00开头）
        df = df[df['code'].str.startswith(('60', '00'))]
        # 剔除 ST（名称中含 ST 或 *ST）
        if 'name' in df.columns:
            df = df[~df['name'].str.contains('ST|\\*ST', case=False, na=False)]
        return df['ts_code'].tolist()
    except Exception as e:
        print(f"获取股票列表失败: {e}")
        return []

def get_stock_data(ts_code, end_date):
    """获取单只股票的日线数据及计算指标"""
    try:
        # 获取最近 100 个交易日数据
        df = pro.daily(ts_code=ts_code, start_date='', end_date=end_date, limit=100,
                       fields='trade_date,open,high,low,close,vol,pct_chg')
        if df is None or len(df) < 20:
            return None
        df = df.sort_values('trade_date').reset_index(drop=True)
        
        # 计算均线
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma10'] = df['close'].rolling(10).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        
        # 计算 MACD
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        df['dif'] = exp1 - exp2
        df['dea'] = df['dif'].ewm(span=9, adjust=False).mean()
        df['macd'] = (df['dif'] - df['dea']) * 2
        
        latest = df.iloc[-1]
        # 检查股价
        if latest['close'] >= MAX_PRICE:
            return None
        
        # 均线多头排列
        if latest['ma5'] <= latest['ma10'] or latest['ma10'] <= latest['ma20']:
            return None
        
        # 连续 N 日收盘 > MA10
        if len(df) < CONSECUTIVE_DAYS:
            return None
        last_n = df.iloc[-CONSECUTIVE_DAYS:]
        for i in range(len(last_n)):
            if last_n.iloc[i]['close'] <= last_n.iloc[i]['ma10']:
                return None
        
        # 10日涨幅
        if len(df) < 11:
            return None
        close_10d_ago = df.iloc[-11]['close']
        gain_10d = (latest['close'] - close_10d_ago) / close_10d_ago * 100
        if gain_10d < MIN_GAIN_10D:
            return None
        
        # 10日内最低价不低于 MA20
        last_10 = df.iloc[-10:]
        for i in range(len(last_10)):
            if last_10.iloc[i]['low'] < last_10.iloc[i]['ma20']:
                return None
        
        # MACD 上升：当前 DIF > DEA 且 DIF > 前一日 DIF
        if len(df) >= 2:
            if latest['dif'] <= latest['dea'] or latest['dif'] <= df.iloc[-2]['dif']:
                return None
        else:
            return None
        
        # 获取股票名称
        name = ts_code.split('.')[0]
        try:
            basic = pro.stock_basic(ts_code=ts_code, fields='name')
            if basic is not None and len(basic) > 0:
                name = basic['name'].iloc[0]
        except:
            pass
        
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
    except Exception as e:
        print(f"处理 {ts_code} 时出错: {e}")
        return None

def send_email(results, date_str):
    """发送邮件"""
    if not results:
        subject = f"趋势票筛选 - {date_str} - 无符合"
        body = f"日期：{date_str}\n\n今日无股票符合条件。\n\n当前条件：\n- 沪深主板，非ST\n- 股价 < 75元\n- MA5 > MA10 > MA20\n- 连续6日收盘 > MA10\n- 10日涨幅 ≥ 10%\n- 10日内最低价 ≥ MA20\n- MACD上升（DIF > DEA 且 DIF 上升）"
    else:
        subject = f"趋势票筛选 - {date_str} - 发现{len(results)}只"
        body = f"日期：{date_str}\n\n发现 {len(results)} 只股票符合条件：\n\n"
        for r in results:
            body += f"【{r['code']}】{r['name']}\n"
            body += f"  收盘：{r['close']:.2f}\n"
            body += f"  均线：MA5={r['ma5']:.2f} MA10={r['ma10']:.2f} MA20={r['ma20']:.2f}\n"
            body += f"  10日涨幅：{r['gain_10d']:.1f}%\n"
            body += f"  MACD：DIF={r['dif']:.4f} DEA={r['dea']:.4f}\n\n"
    
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
    print("=" * 50)
    print("趋势票筛选器启动")
    trade_date = datetime.now().strftime('%Y-%m-%d')
    print(f"筛选日期：{trade_date}")
    print(f"条件：股价<{MAX_PRICE}元 | 连续{CONSECUTIVE_DAYS}日收盘>MA10 | 10日涨幅≥{MIN_GAIN_10D}% | MACD上升")
    print("=" * 50)
    
    # 获取所有股票列表
    stocks = get_all_a_stocks()
    print(f"共获取 {len(stocks)} 只沪深主板股票")
    
    results = []
    total = len(stocks)
    for i, ts_code in enumerate(stocks):
        if (i+1) % 50 == 0:
            print(f"已处理 {i+1}/{total} 只")
        # 避免请求过快
        time.sleep(0.1)
        data = get_stock_data(ts_code, trade_date)
        if data:
            results.append(data)
            print(f"  ✅ {data['code']} {data['name']}")
    
    print(f"\n筛选完成！共 {len(results)} 只股票符合条件")
    send_email(results, trade_date)

if __name__ == "__main__":
    main()
