# REITs 项目公示对比看板

自动更新公募REITs项目公示信息与沪深交易所审核进度对比。

## 数据源

- [投资在线平台](https://www.tzxm.gov.cn:8081/aweb-ui/reits/) — 发改委项目公示（133条）
- [上交所 REITs](https://www.sse.com.cn/reits/info/) — 交易所受理/注册进度（~93条）
- [深交所 REITs](https://reits.szse.cn/projectdynamic/index.html) — 交易所受理/注册进度（首发44+新购入5条）

## 自动更新

- GitHub Actions 每天北京时间 10:00 自动运行
- 可手动触发: Actions → Update REITs Data → Run workflow

## 技术

Python + Playwright（上交所爬虫）+ 人工校准匹配（118/133映射）
