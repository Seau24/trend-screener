name: Daily Trend Screener

on:
  schedule:
    - cron: '0 8 * * 1-5'
  workflow_dispatch:

jobs:
  run-screener:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: pip install tushare pandas
      - name: Run screener
        env:
          TUSHARE_TOKEN: ${{ secrets.TUSHARE_TOKEN }}
          SENDER_EMAIL: ${{ secrets.SENDER_EMAIL }}
          SENDER_PASSWORD: ${{ secrets.SENDER_PASSWORD }}
          RECEIVER_EMAIL: ${{ secrets.RECEIVER_EMAIL }}
        run: python trend_screener.py
