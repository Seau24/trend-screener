import tushare as ts
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime
import os

TS_TOKEN = os.environ.get('TUSHARE_TOKEN')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL')
SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD')
RECEIVER_EMAIL = os.environ.get('RECEIVER_EMAIL')

# 筛选参数
MAX_RETRACE = 20           # 最大回撤 < 20%
MIN_GAIN_10D = 10          # 10日涨幅 ≥ 10%

ts.set_token(TS_TOKEN)
pro = ts.pro_api()

def is_main_board(code):
    return code.startswith('60') or code.startswith('00')

def get_all_stocks():
    try:
        today = datetime.now().strftime('%Y%m%d')
        df = pro.daily(trade_date=today, fields='ts_code')
        if df is not None and len(df) > 0:
            df['code'] = df['ts_code'].str.split('.').str[0]
            df = df[df['code'].apply(is_main_board)]
            return df['ts_code'].tolist()
    except:
        pass
    return []

def get_stock_name(code):
    try:
        basic = pro.stock_basic(ts_code=code, fields='name')
        if basic is not None and len(basic) > 0:
            name = basic['name'].iloc[0]
            if 'ST' in name.upper() or '*ST' in name.upper():
                return None
            return name
    except:
        pass
    return code.split('.')[0]

def get_macd(df):
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    dif = exp1 - exp2
    dea = dif.ewm(span=9, adjust=False).mean()
    return dif, dea

def get_stock_data(code, trade_date):
    try:
        df = pro.daily(ts_code=code, start_date='', end_date=trade_date, limit=80,
                       fields='trade_date,close,low,high,vol,pct_chg')
        if df is None or len(df) < 60:
            return None
        df = df.sort_values('trade_date')
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma10'] = df['close'].rolling(10).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        
        dif, dea = get_macd(df)
        df['dif'] = dif
        df['dea'] = dea
        
        latest = df.iloc[-1]
        last_10 = df.iloc[-10:]
        last_2 = df.iloc[-2:]
        
        # 1. 均线多头
        if not (latest['ma5'] > latest['ma10'] > latest['ma20']):
            return None
        
        # 2. 收盘 > MA10
        if latest['close'] <= latest['ma10']:
            return None
        
        # 3. 10日涨幅 ≥ 10%
        gain_10d = (last_10['close'].iloc[-1] - last_10['close'].iloc[0]) / last_10['close'].iloc[0] * 100
        if gain_10d < MIN_GAIN_10D:
            return None
        
        # 4. 10日内不破10日线
        for i in range(len(last_10)):
            if last_10['low'].iloc[i] < last_10['ma10'].iloc[i]:
                return None
        
        # 5. 10日最大回撤 < 20%
        recent_high = last_10['close'].max()
        recent_low = last_10['close'].min()
        max_retrace = (recent_high - recent_low) / recent_high * 100
        if max_retrace >= MAX_RETRACE:
            return None
        
        # 6. 排除涨停/跌停
        if latest['pct_chg'] >= 9.5 or latest['pct_chg'] <= -9.5:
            return None
        
        # 7. MACD逐渐上涨
        if len(last_2) >= 2:
            curr_dif = last_2['dif'].iloc[-1]
            prev_dif = last_2['dif'].iloc[-2]
            curr_dea = last_2['dea'].iloc[-1]
            if curr_dif <= curr_dea or curr_dif <= prev_dif:
                return None
        else:
            return None
        
        name = get_stock_name(code)
        if name is None:
            return None
        
        return {
            'code': code.split('.')[0],
            'name': name,
            'close': latest['close'],
            'ma10': latest['ma10'],
            'gain_10d': gain_10d,
            'max_retrace': max_retrace,
            'dif': curr_dif,
            'dea': curr_dea
        }
    except:
        return None

def send_email(results, date_str):
    if not results:
        subject = f"趋势票筛选 - {date_str} - 无符合"
        body = f"日期：{date_str}\n\n今日无股票符合条件。"
    else:
        subject = f"趋势票筛选 - {date_str} - 发现{len(results)}只"
        body = f"日期：{date_str}\n\n发现 {len(results)} 只股票：\n\n"
        for r in results:
            body += f"【{r['code']}】{r['name']}\n"
            body += f"  收盘：{r['close']:.2f} | MA10：{r['ma10']:.2f}\n"
            body += f"  10日涨幅：{r['gain_10d']:.1f}% | 回撤：{r['max_retrace']:.1f}%\n"
            body += f"  MACD：DIF={r['dif']:.2f} DEA={r['dea']:.2f}\n\n"
    
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
    print("趋势票筛选器启动")
    date_str = datetime.now().strftime('%Y-%m-%d')
    print(f"筛选日期：{date_str}")
    
    stocks = get_all_stocks()
    print(f"共 {len(stocks)} 只沪深主板股票待筛选")
    
    results = []
    for i, code in enumerate(stocks):
        if i % 100 == 0:
            print(f"已筛选 {i} 只...")
        data = get_stock_data(code, date_str.replace('-', ''))
        if data:
            results.append(data)
    
    print(f"筛选完成！共 {len(results)} 只")
    send_email(results, date_str)

if __name__ == "__main__":
    main()
