import tushare as ts
import os
from datetime import datetime

TS_TOKEN = os.environ.get('TUSHARE_TOKEN')
ts.set_token(TS_TOKEN)
pro = ts.pro_api()

def main():
    print("=" * 50)
    print("测试1：检查股票池")
    
    today = datetime.now().strftime('%Y%m%d')
    print(f"查询日期：{today}")
    
    # 获取当天有交易的股票
    df = pro.daily(trade_date=today, fields='ts_code', limit=100)
    
    if df is None or len(df) == 0:
        print("❌ 无法获取股票列表")
        return
    
    print(f"✅ 获取到 {len(df)} 只股票")
    
    # 筛选沪深主板
    df['code'] = df['ts_code'].str.split('.').str[0]
    main_board = df[df['code'].str.startswith(('60', '00'))]
    print(f"✅ 沪深主板：{len(main_board)} 只")
    
    print("\n前10只股票代码：")
    for code in main_board['code'].head(10).tolist():
        print(f"  {code}")

if __name__ == "__main__":
    main()
