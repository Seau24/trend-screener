import tushare as ts
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime
import os

# ========== 配置区 ==========
TS_TOKEN = os.environ.get('TUSHARE_TOKEN')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL')
SENDER_PASSWORD = os.environ.get('SENDER_PASSWORD')
RECEIVER_EMAIL = os.environ.get('RECEIVER_EMAIL')
BACKTEST_DATE = '20250112'
TEST_STOCKS = ['000510.SZ']
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
    """获取所有A股列表 - 使用 trade_cal 接口替代"""
    # 先获取交易日历，拿到最新交易日
    try:
        cal = pro.trade_cal(exchange='SSE', start_date='20200101', end_date=datetime.now().strftime('%Y%m%d'))
        trade_dates = cal[cal['is_open'] == 1]['cal_date'].tolist()
        latest_date = trade_dates[-1]
    except:
        latest_date = datetime.now().strftime('%Y%m%d')
    
    # 通过日线数据获取所有有交易的股票
    try:
        # 获取当天有交易的股票代码
        daily = pro.daily(trade_date=latest_date, fields='ts_code')
        if daily is not None and len(daily) > 0:
            # 获取股票名称
            codes = daily['ts_code'].tolist()
            names = []
            for code in codes:
                # 从代码中提取简单名称
                if code.startswith('6'):
                    name = code.split('.')[0]
                else:
                    name = code.split('.')[0]
                names.append(name)
            
            df = pd.DataFrame({'ts_code': codes, 'name': names})
            # 剔除北交所
            df = df[~df['ts_code'].str.endswith('BJ')]
            return df
    except:
        pass
    
    # 备选方案：使用固定的大盘股列表（确保有数据）
    default_stocks = [
        '000001.SZ', '000002.SZ', '000858.SZ', '002415.SZ', '300750.SZ',
        '600519.SH', '600036.SH', '601318.SH', '601166.SH', '600900.SH',
        '601398.SH', '600276.SH', '601288.SH', '600030.SH', '601328.SH'
    ]
    default_names = ['平安银行', '万科A', '五粮液', '海康威视', '宁德时代',
                     '贵州茅台', '招商银行', '中国平安', '兴业银行', '长江电力',
                     '工商银行', '恒瑞医药', '农业银行', '中信证券', '交通银行']
    return pd.DataFrame({'ts_code': default_stocks, 'name': default_names})

def get_ma_data(code, end_date):
    """获取均线数据"""
    try:
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
        max_retrace = (recent_high - recent_low) / recent_high * 100 if recent_high > 0 else 0
        
        if len(df) >= 20:
            gain_20d = (df['close'].iloc[-1] - df['close'].iloc[-21]) / df['close'].iloc[-21] * 100
        else:
            gain_20d = 0
        
        latest = df.iloc[-1]
        return {
            'code': code, 'close': latest['close'],
            'ma5': latest['ma5'], 'ma10': latest['ma10'],
            'ma20': latest['ma20'], 'ma60': latest['ma60'],
            'volume': latest['vol'], 'vol_ma5': latest['vol_ma5'],
            'turnover': latest['turnover_rate'] if pd.notna(latest['turnover_rate']) else 0,
            'max_retrace': max_retrace, 'gain_20d': gain_20d
        }
    except Exception as e:
        return None

def check_trend(data):
    """检查是否符合趋势票条件"""
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
    vol_ratio = data['volume'] / data['vol_ma5'] if data['vol_ma5'] > 0 else 0
    if vol_ratio < MIN_VOL_RATIO or vol_ratio > MAX_VOL_RATIO:
        return False
    if data['turnover'] < MIN_TURNOVER or data['turnover'] > MAX_TURNOVER:
        return False
    if data['gain_20d'] < MIN_GAIN_20D or data['gain_20d'] > MAX_GAIN_20D:
        return False
    return True

def send_email(results, date_str):
    """发送邮件"""
    if not results:
        subject = f"趋势票筛选 - {date_str} - 今日无符合"
        body = f"日期：{date_str}\n\n今日无股票符合趋势票条件。\n\n条件：均线多头排列 | 近10日回撤<{MAX_RETRACE}% | 量比{MIN_VOL_RATIO}-{MAX_VOL_RATIO} | 换手率{MIN_TURNOVER}-{MAX_TURNOVER}% | 近20日涨幅{MIN_GAIN_20D}-{MAX_GAIN_20D}%"
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
        print(f"邮件发送成功！共{len(results)}只股票")
    except Exception as e:
        print(f"邮件发送失败：{e}")

def main():
    print("=" * 50)
    print("趋势票筛选器启动")
    date_str = datetime.now().strftime('%Y-%m-%d')
    print(f"筛选日期：{date_str}")
    print("=" * 50)
    
    stocks = get_all_stocks()
    print(f"共 {len(stocks)} 只股票待筛选")
    
    results = []
    count = 0
    
    for _, row in stocks.iterrows():
        code = row['ts_code']
        name = row['name']
        count += 1
        
        if count % 50 == 0:
            print(f"已筛选 {count} 只...")
        
        data = get_ma_data(code, date_str)
        if data:
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
    
    print("\n" + "=" * 50)
    print(f"筛选完成！共 {len(results)} 只股票符合趋势票条件：")
    for r in results:
        print(f"{r['code']} {r['name']} | 换手{r['turnover']:.1f}% | 量比{r['vol_ratio']:.2f} | 20日涨幅{r['gain_20d']:.1f}% | 回撤{r['max_retrace']:.1f}%")
    
    send_email(results, date_str)
    print("=" * 50)

if __name__ == "__main__":
    main()
