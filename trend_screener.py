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

MAX_RETRACE = 18
MIN_VOL_RATIO = 0.8
MAX_VOL_RATIO = 3.5
MIN_GAIN_20D = 5
MAX_GAIN_20D = 80
MIN_GAIN_10D = 5

ts.set_token(TS_TOKEN)
pro = ts.pro_api()

def get_all_stocks():
    try:
        today = datetime.now().strftime('%Y%m%d')
        df = pro.daily(trade_date=today, fields='ts_code')
        if df is not None and len(df) > 0:
            df = df[~df['ts_code'].str.endswith('BJ')]
            return df['ts_code'].tolist()
    except:
        pass
    return []

def check_stock(code, trade_date):
    try:
        df = pro.daily(ts_code=code, start_date='', end_date=trade_date, limit=80,
                       fields='trade_date,close,low,high,vol,pct_chg')
        if df is None or len(df) < 60:
            return None
        df = df.sort_values('trade_date')
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma10'] = df['close'].rolling(10).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        df['vol_ma5'] = df['vol'].rolling(5).mean()
        latest = df.iloc[-1]
        if not (latest['ma5'] > latest['ma10'] > latest['ma20']):
            return None
        if latest['close'] <= latest['ma20']:
            return None
        last_10 = df.iloc[-10:]
        gain_10d = (last_10['close'].iloc[-1] - last_10['close'].iloc[0]) / last_10['close'].iloc[0] * 100
        if gain_10d < MIN_GAIN_10D:
            return None
        for i in range(len(last_10)):
            if last_10['low'].iloc[i] < last_10['ma10'].iloc[i]:
                return None
        if len(df) >= 20:
            gain_20d = (latest['close'] - df['close'].iloc[-21]) / df['close'].iloc[-21] * 100
            if gain_20d < MIN_GAIN_20D or gain_20d > MAX_GAIN_20D:
                return None
        else:
            return None
        recent_high = last_10['close'].max()
        recent_low = last_10['close'].min()
        max_retrace = (recent_high - recent_low) / recent_high * 100
        if max_retrace >= MAX_RETRACE:
            return None
        vol_ratio = latest['vol'] / latest['vol_ma5'] if latest['vol_ma5'] > 0 else 0
        if vol_ratio < MIN_VOL_RATIO or vol_ratio > MAX_VOL_RATIO:
            return None
        if latest['pct_chg'] >= 9.5 or latest['pct_chg'] <= -9.5:
            return None
        name = code.split('.')[0]
        try:
            basic = pro.stock_basic(ts_code=code, fields='name')
            if basic is not None and len(basic) > 0:
                name = basic['name'].iloc[0]
        except:
            pass
        return {
            'code': code.split('.')[0],
            'name': name,
            'close': latest['close'],
            'ma5': latest['ma5'],
            'ma10': latest['ma10'],
            'ma20': latest['ma20'],
            'vol_ratio': vol_ratio,
            'gain_10d': gain_10d,
            'gain_20d': gain_20d,
            'max_retrace': max_retrace
        }
    except:
        return None

def send_email(results, date_str):
    if not results:
        subject = f"趋势票筛选 - {date_str} - 无符合"
        body = f"日期：{date_str}\n\n今日无股票符合趋势票条件。"
    else:
        subject = f"趋势票筛选 - {date_str} - 发现{len(results)}只"
        body = f"日期：{date_str}\n\n发现 {len(results)} 只股票：\n\n"
        for r in results:
            body += f"【{r['code']}】{r['name']}\n"
            body += f"  收盘：{r['close']:.2f} | 量比：{r['vol_ratio']:.2f}\n"
            body += f"  10日涨幅：{r['gain_10d']:.1f}% | 20日涨幅：{r['gain_20d']:.1f}% | 回撤：{r['max_retrace']:.1f}%\n\n"
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
    print(f"共 {len(stocks)} 只股票待筛选")
    results = []
    for i, code in enumerate(stocks):
        if i % 100 == 0:
            print(f"已筛选 {i} 只...")
        data = check_stock(code, date_str.replace('-', ''))
        if data:
            results.append(data)
    print(f"筛选完成！共 {len(results)} 只")
    send_email(results, date_str)

if __name__ == "__main__":
    main()
