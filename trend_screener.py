import tushare as ts
import pandas as pd
import os
from datetime import datetime

TS_TOKEN = os.environ.get('TUSHARE_TOKEN')
ts.set_token(TS_TOKEN)
pro = ts.pro_api()

def main():
    print("=" * 50)
    print("测试模式：风华高科数据检查")
    
    code = '000636.SZ'
    trade_date = datetime.now().strftime('%Y%m%d')
    
    print(f"查询股票：{code}")
    print(f"查询日期：{trade_date}")
    print("=" * 50)
    
    # 获取日线数据
    df = pro.daily(ts_code=code, start_date='', end_date=trade_date, limit=80,
                   fields='trade_date,close,low,high,vol,pct_chg')
    
    if df is None or len(df) == 0:
        print("❌ 无法获取数据")
        return
    
    print(f"✅ 获取到 {len(df)} 条数据")
    
    # 按日期排序
    df = df.sort_values('trade_date')
    df = df.reset_index(drop=True)
    
    # 打印列名，确认数据格式
    print(f"\n列名：{df.columns.tolist()}")
    
    # 计算均线（使用 .loc 避免警告）
    df.loc[:, 'ma5'] = df['close'].rolling(5).mean()
    df.loc[:, 'ma10'] = df['close'].rolling(10).mean()
    df.loc[:, 'ma20'] = df['close'].rolling(20).mean()
    
    # 获取最新一行
    latest = df.iloc[-1]
    
    print(f"\n最新数据日期：{latest['trade_date']}")
    print(f"收盘价：{latest['close']:.2f}")
    print(f"涨跌幅：{latest['pct_chg']:.2f}%")
    print(f"MA5：{latest['ma5']:.2f}")
    print(f"MA10：{latest['ma10']:.2f}")
    print(f"MA20：{latest['ma20']:.2f}")
    
    # 均线多头判断
    if latest['ma5'] > latest['ma10'] > latest['ma20']:
        print("\n✅ 均线多头排列 (MA5 > MA10 > MA20)")
    else:
        print("\n❌ 均线不是多头排列")
    
    # 收盘价 > MA10
    if latest['close'] > latest['ma10']:
        print("✅ 收盘价 > MA10")
    else:
        print("❌ 收盘价 <= MA10")
    
    # 10日涨幅
    if len(df) >= 10:
        last_10 = df.iloc[-10:]
        gain_10d = (last_10['close'].iloc[-1] - last_10['close'].iloc[0]) / last_10['close'].iloc[0] * 100
        print(f"\n10日涨幅：{gain_10d:.2f}%")
        if gain_10d >= 10:
            print("✅ 10日涨幅 >= 10%")
        else:
            print("❌ 10日涨幅 < 10%")
    
    # 10日是否破MA10
    if len(df) >= 10:
        last_10 = df.iloc[-10:].copy()
        broke = False
        for i in range(len(last_10)):
            if last_10['low'].iloc[i] < last_10['ma10'].iloc[i]:
                broke = True
                print(f"  第{i+1}天：最低{last_10['low'].iloc[i]:.2f} < MA10{last_10['ma10'].iloc[i]:.2f} → 跌破")
        if not broke:
            print("\n✅ 10日内未跌破MA10")
        else:
            print("\n❌ 10日内有跌破MA10")
    
    # 10日最大回撤
    if len(df) >= 10:
        last_10 = df.iloc[-10:]
        recent_high = last_10['close'].max()
        recent_low = last_10['close'].min()
        max_retrace = (recent_high - recent_low) / recent_high * 100
        print(f"\n10日最大回撤：{max_retrace:.2f}%")
        if max_retrace < 20:
            print("✅ 回撤 < 20%")
        else:
            print("❌ 回撤 >= 20%")
    
    # MACD
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    dif = exp1 - exp2
    dea = dif.ewm(span=9, adjust=False).mean()
    
    print(f"\nMACD最新值：")
    print(f"  DIF：{dif.iloc[-1]:.4f}")
    print(f"  DEA：{dea.iloc[-1]:.4f}")
    
    if dif.iloc[-1] > dea.iloc[-1]:
        print("✅ DIF > DEA")
    else:
        print("❌ DIF <= DEA")
    
    if len(dif) >= 2:
        if dif.iloc[-1] > dif.iloc[-2]:
            print("✅ DIF 较昨日上升")
        else:
            print("❌ DIF 较昨日下降")
    
    print("\n" + "=" * 50)
    print("测试完成")

if __name__ == "__main__":
    main()
