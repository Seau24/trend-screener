import tushare as ts
import pandas as pd
import os
from datetime import datetime

# ========== 配置区 ==========
TS_TOKEN = os.environ.get('TUSHARE_TOKEN')

# ========== 回测设置 ==========
BACKTEST_DATE = '20260112'  # 改成你想回测的日期
TEST_STOCKS = ['000510.SZ', '002859.SZ']
# ========== 配置结束 ==========

# 调整后的筛选参数
MAX_RETRACE = 18          # 最大回撤18%
MIN_VOL_RATIO = 0.8
MAX_VOL_RATIO = 3.5
MIN_GAIN_20D = 5          # 最小涨幅5%
MAX_GAIN_20D = 80         # 最大涨幅80%

ts.set_token(TS_TOKEN)
pro = ts.pro_api()

def get_all_stocks():
    if TEST_STOCKS:
        stocks = []
        for code in TEST_STOCKS:
            stocks.append({'ts_code': code, 'name': code.split('.')[0]})
        return pd.DataFrame(stocks)
    return pd.DataFrame()

def get_ma_data(code, end_date):
    try:
        df = pro.daily(ts_code=code, start_date='', end_date=end_date, limit=80,
                       fields='trade_date,close,vol')
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
            'max_retrace': max_retrace, 'gain_20d': gain_20d
        }
    except Exception as e:
        print(f"获取{code}数据出错: {e}")
        return None

def check_trend(data):
    if data is None:
        return False
    if pd.isna(data['ma5']) or pd.isna(data['ma10']) or pd.isna(data['ma20']):
        return False
    if not (data['ma5'] > data['ma10'] > data['ma20']):
        return False
    if data['close'] <= data['ma20']:
        return False
    if data['max_retrace'] >= MAX_RETRACE:
        return False
    vol_ratio = data['volume'] / data['vol_ma5'] if data['vol_ma5'] > 0 else 0
    if vol_ratio < MIN_VOL_RATIO or vol_ratio > MAX_VOL_RATIO:
        return False
    if data['gain_20d'] < MIN_GAIN_20D or data['gain_20d'] > MAX_GAIN_20D:
        return False
    return True

def main():
    date_str = BACKTEST_DATE if BACKTEST_DATE else datetime.now().strftime('%Y%m%d')
    print(f"回测模式 - 日期：{date_str}")
    print("=" * 50)
    print(f"条件：回撤<{MAX_RETRACE}% | 量比{MIN_VOL_RATIO}-{MAX_VOL_RATIO} | 20日涨幅{MIN_GAIN_20D}-{MAX_GAIN_20D}%")
    print("=" * 50)
    
    stocks = get_all_stocks()
    print(f"共 {len(stocks)} 只股票\n")
    
    results = []
    
    for _, row in stocks.iterrows():
        code = row['ts_code']
        name = row['name']
        
        print(f"--- {code} {name} ---")
        data = get_ma_data(code, date_str)
        
        if data is None:
            print("  无法获取数据\n")
            continue
        
        vol_ratio = data['volume'] / data['vol_ma5'] if data['vol_ma5'] > 0 else 0
        
        print(f"  收盘: {data['close']:.2f}")
        print(f"  MA5: {data['ma5']:.2f}, MA10: {data['ma10']:.2f}, MA20: {data['ma20']:.2f}")
        print(f"  量比: {vol_ratio:.2f}")
        print(f"  20日涨幅: {data['gain_20d']:.1f}%")
        print(f"  10日最大回撤: {data['max_retrace']:.1f}%")
        
        ma_ok = data['ma5'] > data['ma10'] > data['ma20']
        price_ok = data['close'] > data['ma20']
        retrace_ok = data['max_retrace'] < MAX_RETRACE
        vol_ok = MIN_VOL_RATIO <= vol_ratio <= MAX_VOL_RATIO
        gain_ok = MIN_GAIN_20D <= data['gain_20d'] <= MAX_GAIN_20D
        
        print(f"  判断: 均线{'✅' if ma_ok else '❌'} | 股价>MA20{'✅' if price_ok else '❌'} | 回撤{'✅' if retrace_ok else '❌'} | 量比{'✅' if vol_ok else '❌'} | 涨幅{'✅' if gain_ok else '❌'}")
        
        if check_trend(data):
            results.append({
                'code': code.split('.')[0],
                'name': name,
                'close': data['close'],
                'ma5': data['ma5'],
                'ma10': data['ma10'],
                'ma20': data['ma20'],
                'vol_ratio': vol_ratio,
                'gain_20d': data['gain_20d'],
                'max_retrace': data['max_retrace']
            })
            print(f"  ✅ 符合条件\n")
        else:
            print(f"  ❌ 不符合条件\n")
    
    print("=" * 50)
    print(f"筛选完成！共 {len(results)} 只股票符合条件")
    
    for r in results:
        print(f"{r['code']} {r['name']} | 收盘{r['close']:.2f} | 量比{r['vol_ratio']:.2f} | 20日涨幅{r['gain_20d']:.1f}% | 回撤{r['max_retrace']:.1f}%")

if __name__ == "__main__":
    main()
