import tushare as ts
import os
from datetime import datetime

TS_TOKEN = os.environ.get('TUSHARE_TOKEN')
ts.set_token(TS_TOKEN)
pro = ts.pro_api()

def main():
    print("=" * 50)
    print("测试模式：只打印风华高科数据")
    
    code = '000636.SZ'
    trade_date = datetime.now().strftime('%Y%m%d')
    
    print(f"查询股票：{code}")
    print(f"查询日期：{trade_date}")
    print("=" * 50)
    
    # 1. 获取日线数据
    df = pro.daily(ts_code=code, start_date='', end_date=trade_date, limit=80,
                   fields='trade_date,close,low,high,vol,pct_chg')
    
    if df is None or len(df) == 0:
        print("❌ 无法获取数据")
        return
    
    print(f"✅ 获取到 {len(df)} 条数据")
    
    df = df.sort_values('trade_date')
    latest = df.iloc[-1]
    last_10 = df.iloc[-10:]
    
    print(f"\n最新数据（{latest['trade_date']}）：")
    print(f"  收盘价：{latest['close']:.2f}")
    print(f"  涨跌幅：{latest['pct_chg']:.2f}%")
    print(f"  成交量：{latest['vol']:.0f}")
    
    # 2. 计算均线
    df['ma5'] = df['close'].rolling(5).mean()
    df['ma10'] = df['close'].rolling(10).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    
    print(f"\n均线（最新）：")
    print(f"  MA5：{latest['ma5']:.2f}")
    print(f"  MA10：{latest['ma10']:.2f}")
    print(f"  MA20：{latest['ma20']:.2f}")
    
    # 3. 10日涨幅
    if len(last_10) >= 10:
        gain_10d = (last_10['close'].iloc[-1] - last_10['close'].iloc[0]) / last_10['close'].iloc[0] * 100
        print(f"\n10日涨幅：{gain_10d:.1f}%")
    
    # 4. 10日是否破MA10
    broke = False
    for i in range(len(last_10)):
        if last_10['low'].iloc[i] < last_10['ma10'].iloc[i]:
            broke = True
            print(f"  第{i+1}天：最低{last_10['low'].iloc[i]:.2f} < MA10{last_10['ma10'].iloc[i]:.2f} → 跌破")
    if not broke:
        print(f"\n10日内未跌破MA10 ✅")
    
    # 5. 10日最大回撤
    recent_high = last_10['close'].max()
    recent_low = last_10['close'].min()
    max_retrace = (recent_high - recent_low) / recent_high * 100
    print(f"\n10日最大回撤：{max_retrace:.1f}%")
    
    # 6. MACD
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    dif = exp1 - exp2
    dea = dif.ewm(span=9, adjust=False).mean()
    
    print(f"\nMACD（最新）：")
    print(f"  DIF：{dif.iloc[-1]:.2f}")
    print(f"  DEA：{dea.iloc[-1]:.2f}")
    
    if len(dif) >= 2:
        if dif.iloc[-1] > dif.iloc[-2]:
            print(f"  DIF趋势：上升 ✅")
        else:
            print(f"  DIF趋势：下降 ❌")
    
    print("\n" + "=" * 50)

if __name__ == "__main__":
    main()
