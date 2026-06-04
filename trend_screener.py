import tushare as ts
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime
import os

# ========== 配置区（GitHub Secrets 会自动填充）==========
TS_TOKEN = os.environ.get('TUSHARE_TOKEN')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL')
SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD')
RECEIVER_EMAIL = os.environ.get('RECEIVER_EMAIL')
# ========== 配置结束 ==========

# 筛选参数
MAX_RETRACE = 8
MIN_VOL_RATIO = 1.2
MAX_VOL_RATIO = 2.5
MIN_TURNOVER = 3
MAX_TURNOVER = 15
MIN_GAIN_20D = 15
MAX_GAIN_20D = 50

ts.set_token(TS_TOKEN)
pro = ts.pro_api()

def get_all_stocks():
    df = pro.stock_basic(exchange='', list_status='L', fields='ts_code,name')
    df = df[~df['ts_code'].str.endswith('.BJ')]
    return df

def get_ma_data(code, end_date):
    df = pro.daily(ts_code=code, start_date='', end_date=end_date, limit=80,
                   fields='trade_date,close,vol,turnover_rate')
    if df is None or len(df) < 60:
        return None
    df = df.sort_values('trade_date')
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma10'] = df['close'].rolling(10).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()
    df['vol_ma5'] = df['vol'].rolling(5).mean()
    recent_high = df['close'].iloc[-10:].max()
    recent_low = df['close'].iloc[-10:].min()
    max_retrace = (recent_high - recent_low) / recent_high * 100
    if len(df) >= 20:
        gain_20d = (df['close'].iloc[-1] - df['close'].iloc[-21]) / df['close'].iloc[-21] * 100
    else:
        gain_20d = 0
    latest = df.iloc[-1]
    return {
        'code': code, 'name': '', 'close': latest['close'], 'ma5': latest['ma5'],
        'ma10': latest['ma10'], 'ma20': latest['ma20'], 'ma60': latest['ma60'],
        'volume': latest['vol'], 'vol_ma5': latest['vol_ma5'],
        'turnover': latest['turnover_rate'] if pd.notna(latest['turnover_rate']) else 0,
        'max_retrace': max_retrace, 'gain_20d': gain_20d
    }

def check_trend(data):
    if data is None:
        return False
    if pd.isna(data['ma5']) or pd.isna(data['ma10']) or pd.isna(data['ma20']) or pd.isna(data['ma60']):
        return False
    if not (data['ma5'] > data['ma10'] > data['ma20'] > data['ma60']):
        return False
    if data['close'] <= data['ma5']:
        return False
    if data['max_retrace'] >= MAX_RETRACE:
        return False
    vol_ratio = data['volume'] / data['vol_ma5']
    if vol_ratio < MIN_VOL_RATIO or vol_ratio > MAX_VOL_RATIO:
        return False
    if data['turnover'] < MIN_TURNOVER or data['turnover'] > MAX_TURNOVER:
        return False
    if data['gain_20d'] < MIN_GAIN_20D or data['gain_20d'] > MAX_GAIN_20D:
        return False
    return True

def send_email(results, date_str):
    if not results:
        subject = f"趋势票筛选 - {date_str} - 今日无符合"
        body = f"日期：{date_str}\n\n今日无股票符合趋势票条件。"
    else:
        subject = f"趋势票筛选 - {date_str} - 发现{len(results)}只"
        body = f"日期：{date_str}\n\n发现 {len(results)} 只股票符合趋势票条件：\n\n"
        for r in results:
            body += f"【{r['code']}】{r['name']}\n"
            body += f"  收盘价：{r['close']:.2f}\n"
            body += f"  均线：MA5>{r['ma5']:.2f} MA10>{r['ma10']:.2f} MA20>{r['ma20']:.2f}\n"
            body += f"  换手率：{r['turnover']:.1f}% | 量比：{r['vol_ratio']:.2f}\n"
            body += f"  近20日涨幅：{r['gain_20d']:.1f}% | 近10日最大回撤：{r['max_retrace']:.1f}%\n\n"
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
    print(f"共 {len(stocks)} 只股票")
    results = []
    for _, row in stocks.iterrows():
        code = row['ts_code']
        name = row['name']
        data = get_ma_data(code, date_str)
        if data:
            data['name'] = name
            data['vol_ratio'] = data['volume'] / data['vol_ma5'] if data['vol_ma5'] > 0 else 0
            if check_trend(data):
                results.append({
                    'code': code.split('.')[0],
                    'name': name,
                    'close': data['close'],
                    'ma5': data['ma5'],
                    'ma10': data['ma10'],
                    'ma20': data['ma20'],
                    'turnover': data['turnover'],
                    'vol_ratio': data['vol_ratio'],
                    'gain_20d': data['gain_20d'],
                    'max_retrace': data['max_retrace']
                })
    print(f"筛选完成！共 {len(results)} 只")
    send_email(results, date_str)

if __name__ == "__main__":
    main()
