#!/usr/bin/env python3
"""
REITs 数据抓取 + 匹配 + HTML 生成
用于 GitHub Actions 定时更新
"""

import json, re, os, sys
from difflib import SequenceMatcher
from datetime import datetime

# ── 数据抓取 ────────────────────────────────────────

def fetch_json(url, headers=None):
    import urllib.request
    h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    if headers: h.update(headers)
    req = urllib.request.Request(url, headers=h)
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read().decode('utf-8'))

def fetch_tzxm():
    """投资在线平台 REITs 项目公示"""
    url = 'https://www.tzxm.gov.cn:8081/aweb/api/v1/pi/getReitsPublicInfoList'
    data = json.dumps({"pageNum": 1, "pageSize": 200}).encode('utf-8')
    import urllib.request
    req = urllib.request.Request(url, data=data, headers={
        'Content-Type': 'application/json;charset=UTF-8',
        'User-Agent': 'Mozilla/5.0'
    })
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read().decode('utf-8'))

def fetch_szse(biztypsb):
    """深交所 REITs 项目动态"""
    url = f'https://reits.szse.cn/api/reits/projectrends/query?biztypsb={biztypsb}&bizType=2&pageIndex=0&pageSize=50&random=1'
    data = fetch_json(url)
    return [{'name': item['cmpnm'], 'applyType': item.get('biztypsbName',''), 
             'status': item.get('prjst',''), 'updateDate': item.get('updtdt','') or '', 
             'acceptDate': item.get('acptdt','') or ''} for item in data['data']]

def fetch_sse():
    """上交所 REITs 项目动态 - 使用 Playwright 抓取"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed, skipping SSE", file=sys.stderr)
        return []
    
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto('https://www.sse.com.cn/reits/info/', wait_until='networkidle', timeout=30000)
        
        # 提取所有4页数据
        for page_num in range(1, 5):
            data = page.evaluate(f'showData({page_num})')
            if data:
                results.extend(data)
        
        browser.close()
    
    # 去重: name + applyType 组合唯一
    seen = set()
    unique = []
    for item in results:
        key = f"{item.get('name','')}|{item.get('applyType','')}"
        if key not in seen:
            seen.add(key)
            unique.append(item)
    
    return unique

# ── 匹配 ────────────────────────────────────────

# 人工校准映射（tzxm项目名 → 交易所基金名|申请类型）
CALIBRATION = json.loads('{"龙地仓储物流项目":null,"京东仓储物流西北电子商务营业中心等新购入项目":"嘉实京东仓储物流封闭式基础设施证券投资基金|首次发售","京东集团仓储物流项目":"嘉实京东仓储物流封闭式基础设施证券投资基金|首次发售","温州公用水利项目":null,"润泽科技数据中心润泽（廊坊）国际信息港A-7等新购入项目":"南方润泽科技数据中心封闭式基础设施证券投资基金|新购入项目","江天数科数据中心项目":null,"鹏瑞利集团消费基础设施项目":null,"上实租赁住房项目":"汇添富上海地产租赁住房封闭式基础设施证券投资基金|首次发售","华润商业资产消费基础设施杭州萧山万象汇等新购入项目":"华夏华润商业资产封闭式基础设施证券投资基金|新购入项目","招商蛇口光明产业园及南油仓储新购入项目":"博时招商蛇口产业园封闭式基础设施证券投资基金|新购入项目","厦门市政集团停车场项目":null,"广州发展清洁能源项目":"中信建投广州发展清洁能源封闭式基础设施证券投资基金|首次发售","申能股份新能源项目":"东方红申能股份新能源封闭式基础设施证券投资基金|首次发售","华能燃煤发电项目":"长城华能燃煤发电封闭式基础设施证券投资基金|首次发售","华润电力燃煤发电项目":"华夏华润电力燃煤发电封闭式基础设施证券投资基金|首发","粤海水务水利项目":"银华粤海水务水利封闭式基础设施证券投资基金|首发","菜鸟物流仓储项目":"中金菜鸟仓储物流封闭式基础设施证券投资基金|首发","杭州安居保障性租赁住房项目":"中金杭州安居保障性租赁住房封闭式基础设施证券投资基金|首发","蜀道集团雅泸高速公路项目":"华夏蜀道集团高速公路封闭式基础设施证券投资基金|首发","中国建筑租赁住房项目":"国泰海通中国建筑租赁住房封闭式基础设施证券投资基金|首次发售","深圳龙岗城投产业园项目":"华夏龙岗城投产业园封闭式基础设施证券投资基金|首发","首衡农副农贸市场项目":null,"陶邑发展消费基础设施项目":null,"鲁商集团消费基础设施项目":null,"嘉泽新能新能源项目":"国金嘉泽新能源封闭式基础设施证券投资基金|首次发售","北京昌保租赁住房项目":"中航北京昌保租赁住房封闭式基础设施证券投资基金|首发","厦门安居租赁住房思明区林边公寓等新购入项目":"中金厦门安居保障性租赁住房封闭式基础设施证券投资基金|扩募发售","天津临港发展集团港口项目":"建信天津临港发展集团港口封闭式基础设施证券投资基金|首次发售","三峡清洁能源项目":"华泰三峡清洁能源封闭式基础设施证券投资基金|首次发售","金鹰商业消费基础设施项目":null,"钱江隧道项目":null,"武汉高科产业园项目":null,"山东铁投路桥项目":"博时山东铁投路桥封闭式基础设施证券投资基金|首次发售","广西北投高速公路项目":"易方达广西北投高速公路封闭式基础设施证券投资基金|首次发售","华润商业资产消费昆山万象汇新购入项目":"华夏华润商业资产封闭式基础设施证券投资基金|新购入项目","华润有巢租赁住房有巢马桥新购入项目":"华夏基金华润有巢租赁住房封闭式基础设施证券投资基金|扩募发售","西安高科产业园项目":"平安西安高科产业园封闭式基础设施证券投资基金|首发","中核汇能新能源项目":"中航中核汇能新能源封闭式基础设施证券投资基金|首次发售","厦门火炬产业园项目":"中金厦门火炬产业园封闭式基础设施证券投资基金|首发","东久新经济产业园南通智造园及重庆智造园一期新购入项目":"国泰君安东久新经济产业园封闭式基础设施证券投资基金|扩募发售","湖北交投楚天高速项目":"华夏湖北交投楚天高速公路封闭式基础设施证券投资基金|首次发售","天虹股份消费基础设施项目":"中航天虹消费封闭式基础设施证券投资基金|首发","中海消费基础设施项目":"华夏中海商业资产封闭式基础设施证券投资基金|首发","安博仓储物流项目":"华夏安博仓储物流封闭式基础设施证券投资基金|首发","京能光伏保山苏家河口水电站等新购入项目":"中航京能光伏封闭式基础设施证券投资基金|扩募发售","新华发电清洁能源项目":null,"晋中公投瑞阳供热项目":"山证晋中公投瑞阳供热封闭式基础设施证券投资基金|首次发售","唯品会杉杉奥特莱斯项目":"中金唯品会奥特莱斯封闭式基础设施证券投资基金|首次发售","北京电子城产业园项目":"创金合信电子城产业园封闭式基础设施证券投资基金|首次发售","凯德消费基础设施项目":"华夏凯德封闭式商业不动产证券投资基金|首次发售","临港创新产业园漕河泾科技绿洲康桥园区新购入项目":"国泰君安临港创新智造产业园封闭式基础设施证券投资基金|扩募发售","万国数据数据中心项目":"南方万国数据中心封闭式基础设施证券投资基金|首次发售","润泽科技数据中心项目":"南方润泽科技数据中心封闭式基础设施证券投资基金|首发","北京保障房中心租赁住房朗悦嘉园等新购入项目":"华夏北京保障房中心租赁住房封闭式基础设施证券投资基金|扩募发售","中国绿发消费基础设施项目":"中金中国绿发商业资产封闭式基础设施证券投资基金|首发","北京首农产业园项目":"中信建投首农食品集团封闭式商业不动产证券投资基金|首次发售","华电清洁能源项目":"华夏华电清洁能源封闭式基础设施证券投资基金|首次发售","苏州恒泰租赁住房项目":"华泰紫金苏州恒泰租赁住房封闭式基础设施证券投资基金|首次发售","上海地产保障性租赁住房项目":"汇添富上海地产租赁住房封闭式基础设施证券投资基金|首次发售","中国外运仓储物流项目":"中银中外运仓储物流封闭式基础设施证券投资基金|首次发售","福建华威农贸市场项目":"易方达华威农贸市场封闭式基础设施证券投资基金|首发","北京亦庄产业园项目":"中金亦庄产业园封闭式基础设施证券投资基金|首次发售","济南能源供热项目":"国泰君安济南能源供热封闭式基础设施证券投资基金|首次发售","宁波交投杭州湾跨海大桥项目":"平安宁波交投杭州湾跨海大桥封闭式基础设施证券投资基金|首次发售","顺丰仓储物流项目":"南方顺丰仓储物流封闭式基础设施证券投资基金|首发","九州通医药仓储物流项目":"汇添富九州通医药仓储物流封闭式基础设施证券投资基金|首次发售","上海外高桥仓储物流":"华安外高桥仓储物流封闭式基础设施证券投资基金|首次发售","成都高新投资集团产业园区项目":"广发成都高投产业园封闭式基础设施证券投资基金|首发","沈阳国际软件园项目":"中信建投沈阳国际软件园封闭式基础设施证券投资基金|首次发售","内蒙古能源集团清洁能源项目":"工银瑞信蒙能清洁能源封闭式基础设施证券投资基金|首发","浙江绍兴原水水利项目":"银华绍兴原水水利封闭式基础设施证券投资基金|首发","大悦城消费基础设施项目":"华夏大悦城购物中心封闭式基础设施证券投资基金|首发","招商蛇口保障房项目":"招商基金招商蛇口租赁住房封闭式基础设施证券投资基金|首发","江苏南京绕越高速公路项目":"华夏南京交通高速公路封闭式基础设施证券投资基金|首次发售","北京联东产业园项目":"中金联东科技创新产业园封闭式基础设施证券投资基金|首次发售","北京金隅产业园项目":"华夏金隅智造工场产业园封闭式基础设施证券投资基金|首次发售","深圳万纬物流项目":"华夏万纬仓储物流封闭式基础设施证券投资基金|首发","上海杨浦科创产业园项目":null,"建信保障性租赁住房项目":"建信建融家园租赁住房封闭式基础设施证券投资基金|首次发售","明阳智能新能源项目":"中信建投明阳智能新能源封闭式基础设施证券投资基金|首次发售","首创商业消费基础设施项目":"华夏首创奥特莱斯封闭式基础设施证券投资基金|首次发售","上海百联消费基础设施项目":"华安百联消费封闭式基础设施证券投资基金|首次发售","特变电工新能源项目":"华夏特变电工新能源封闭式基础设施证券投资基金|首次发售","宝湾物流项目":"华泰紫金宝湾物流仓储封闭式基础设施证券投资基金|首发","深国际仓储物流项目":"华夏深国际仓储物流封闭式基础设施证券投资基金|首发","易商仓储物流项目":"中航易商仓储物流封闭式基础设施证券投资基金|首次发售","物美消费基础设施项目":"嘉实物美消费封闭式基础设施证券投资基金|首次发售","印力消费基础设施项目":"中金印力消费基础设施封闭式基础设施证券投资基金|首发","华润消费基础设施项目":"华夏华润商业资产封闭式基础设施证券投资基金|首发","金茂消费基础设施项目":"华夏金茂购物中心封闭式基础设施证券投资基金|首次发售","深圳高速集团益常高速公路项目":"易方达深高速高速公路封闭式基础设施证券投资基金|首次发售","招商公路亳阜高速公路项目":"招商基金招商公路高速公路封闭式基础设施证券投资基金|首发","上海城投宽庭保障性租赁住房项目":"国泰君安城投宽庭保障性租赁住房封闭式基础设施证券投资基金|首次发售","重庆两江产业园项目":"中金重庆两江产业园封闭式基础设施证券投资基金|首次发售","中国电建清洁能源项目":"嘉实中国电建清洁能源封闭式基础设施证券投资基金|首次发售","天津经济技术开发区产业园项目":"博时津开科工产业园封闭式基础设施证券投资基金|首次发售","南京建邺高投国际研发总部园项目":"华泰紫金南京建邺产业园封闭式基础设施证券投资基金|首次发售","金风科技江西赣州风电场项目":"建信金风新能源封闭式基础设施证券投资基金|首发","武汉天河机场第二公路通道项目":null,"广州开发区控股集团高新产业园项目":"易方达广州开发区高新产业园封闭式基础设施证券投资基金|首发","河北高速集团荣乌高速公路项目":"工银瑞信河北高速集团高速公路封闭式基础设施证券投资基金|首次发售","普洛斯仓储物流园青岛前湾港国际物流园等新购入项目":"中金普洛斯仓储物流封闭式基础设施证券投资基金|扩募发售","招商蛇口产业园光明科技园新购入项目":"博时招商蛇口产业园封闭式基础设施证券投资基金|新购入项目","红土盐田港世纪物流园新购入项目":"红土创新盐田港仓储物流封闭式基础设施证券投资基金|新购入项目","张江光大园张润大厦新购入项目":"华安张江光大园封闭式基础设施证券投资基金|扩募发售","京能国际光伏发电项目":"中航京能光伏封闭式基础设施证券投资基金|首次发售","湖北科投光谷产业园项目":"中金湖北科投光谷产业园封闭式基础设施证券投资基金|首次发售","国家电投新能源项目":"中信建投国家电投新能源封闭式基础设施证券投资基金|首次发售","山东高速集团鄄菏高速公路项目":"中金山高集团高速公路封闭式基础设施证券投资基金|首次发售","华润有巢保障性租赁住房项目":"华夏基金华润有巢租赁住房封闭式基础设施证券投资基金|首次发售","杭州和达高科产业园项目":"华夏杭州和达高科产业园封闭式基础设施证券投资基金|首发","安徽交控集团沿江高速公路项目":"中金安徽交控高速公路封闭式基础设施证券投资基金|首次发售","北京保障房中心租赁住房项目":"华夏北京保障房中心租赁住房封闭式基础设施证券投资基金|首次发售","合肥高新创新产业园一期项目":"华夏合肥高新创新产业园封闭式基础设施证券投资基金|首发","厦门安居集团保障性租赁住房项目":"中金厦门安居保障性租赁住房封闭式基础设施证券投资基金|首次发售","深圳市人才安居集团保障性租赁住房项目":"红土创新深圳人才安居保障性租赁住房封闭式基础设施证券投资基金|首发","江苏交控沪苏浙高速公路项目":"华泰紫金江苏交控高速公路封闭式基础设施证券投资基金|首次发售","深圳能源东部电厂（一期）天然气发电项目":"鹏华深圳能源清洁能源封闭式基础设施证券投资基金|首发","中关村发展集团园区项目":"建信中关村产业园封闭式基础设施证券投资基金|首次发售","中交嘉通高速公路项目":"华夏中国交建高速公路封闭式基础设施证券投资基金|首次发售","越秀汉孝高速公路项目":"华夏越秀高速公路封闭式基础设施证券投资基金|首发","东久新经济项目":"国泰君安东久新经济产业园封闭式基础设施证券投资基金|首次发售","临港创新产业园项目":"国泰君安临港创新智造产业园封闭式基础设施证券投资基金|首次发售","普洛斯仓储物流项目":"中金普洛斯仓储物流封闭式基础设施证券投资基金|首次发售","盐田港现代物流中心项目":"红土创新盐田港仓储物流封闭式基础设施证券投资基金|首发","招商蛇口产业园项目":"博时招商蛇口产业园封闭式基础设施证券投资基金|首发","苏州工业园区产业园项目":"东吴苏州工业园区产业园封闭式基础设施证券投资基金|首次发售","张江光大园项目":"华安张江光大园封闭式基础设施证券投资基金|首次发售","北京首创污水处理厂（深圳、合肥）项目":null,"北京首钢生物质项目":"中航首钢生物质封闭式基础设施证券投资基金|首发","广州交投广河高速公路（广州段）项目":"平安广州交投广河高速公路封闭式基础设施证券投资基金|首发","浙江交投杭徽高速公路（浙江段）项目":"浙商证券沪杭甬杭徽高速封闭式基础设施证券投资基金|首次发售","中铁建渝遂高速公路（重庆段）项目":"国金铁建重庆渝遂高速公路封闭式基础设施证券投资基金|首次发售"}')

def compute_score(tzxm_name, exch_name):
    t = re.sub(r'(封闭式|基础设施|证券投资基金|商业不动产|项目|等|新购入|（[^）]*）|\([^)]*\)|\s+)', '', tzxm_name)
    e = re.sub(r'(封闭式|基础设施|证券投资基金|商业不动产|\s+)', '', exch_name)
    def grams(s):
        g = set()
        for i in range(len(s)-1):
            if re.match(r'^[\u4e00-\u9fff]{2}$', s[i:i+2]): g.add(s[i:i+2])
        for i in range(len(s)-2):
            if re.match(r'^[\u4e00-\u9fff]{3}$', s[i:i+3]): g.add(s[i:i+3])
        return g
    tg, eg = grams(t), grams(e)
    ns = len(tg & eg) / len(tg) * 100 if tg else 0
    ss = SequenceMatcher(None, t, e).ratio() * 100
    return max(min(int(max(ns*0.7+ss*0.3, ss+20)), 99), 25)

def build_exchange_pool(sse_data, szse_ipo, szse_exp):
    pool = {}
    for lst, ex in [(sse_data, '上交所'), (szse_ipo, '深交所'), (szse_exp, '深交所')]:
        for e in lst:
            key = e['name'] + '|' + e.get('applyType', '首次发售')
            pool[key] = {'st': e['status'], 'ac': e.get('acceptDate',''), 'ex': ex, 'up': e.get('updateDate',''), 'nm': e['name']}
    return pool

def match_and_build(tzxm_data, pool):
    rows = []
    mc = rc = 0
    for idx, item in enumerate(tzxm_data, 1):
        pn = item.get('reitsProName','')
        r = [idx, pn, item.get('mainDeclareUnit',''), item.get('industry',''), 
             item.get('fundMoney',''), (item.get('reportRecommendTime','') or '')[:10],
             '', '', '', '', '', 0]
        mk = CALIBRATION.get(pn)
        if mk and mk in pool:
            inf = pool[mk]
            r[6] = inf['ex']; r[7] = inf['nm']; r[8] = inf['ac']
            if inf['st'] in ('注册生效','通过'): r[9] = inf['up']
            r[10] = inf['st']; r[11] = compute_score(pn, inf['nm'])
            mc += 1; rc += (1 if inf['st'] in ('注册生效','通过') else 0)
        rows.append(r)
    return rows, mc, rc

# ── HTML 生成 ────────────────────────────────────────

def generate_html(rows, mc, rc, total, sse_n, szse_n):
    data_json = json.dumps(rows, ensure_ascii=False, separators=(',', ':'))
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    note = f'匹配 {mc}/{total}({round(mc/total*100)}%) | 注册生效{rc} | 未匹配{total-mc} | 上交所{sse_n} 深交所{szse_n} | 更新: {now}'
    
    return f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>REITs项目公示对比</title><style>*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:#f0f2f5;color:#333}}.h{{background:linear-gradient(135deg,#1a3a5c,#2d6da4);color:#fff;padding:20px 32px;text-align:center}}h1{{font-size:20px;font-weight:600}}.sub{{font-size:12px;opacity:.85;margin-top:4px}}.tb{{display:flex;gap:8px;padding:8px 20px;background:#fff;border-bottom:1px solid #e8e8e8;flex-wrap:wrap;align-items:center;position:sticky;top:0;z-index:10}}.tb input,.tb select{{padding:5px 10px;border:1px solid #d9d9d9;border-radius:6px;font-size:12px;outline:none}}.tb input{{flex:1;min-width:160px}}.st{{font-size:11px;color:#888;white-space:nowrap}}table{{width:100%;border-collapse:collapse;font-size:12px;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.06);margin-top:8px}}th{{background:#f5f7fa;padding:8px 6px;text-align:left;font-weight:600;color:#555;border-bottom:2px solid #e8e8e8;white-space:nowrap;cursor:pointer;user-select:none}}th:hover{{background:#e8ecf2}}td{{padding:6px;border-bottom:1px solid #f0f0f0}}tr:hover{{background:#f8fafe}}tr.nm{{background:#fffbe6}}td.am{{text-align:right}}td.sc{{text-align:center;font-size:11px}}.c0{{color:#237804;font-weight:600}}.c1{{color:#1890ff;font-weight:600}}.c2{{color:#d48806}}.c3{{color:#cf1322}}.c9{{color:#999}}.bd{{display:inline-block;padding:1px 7px;border-radius:10px;font-size:10px;font-weight:500;white-space:nowrap}}.bs{{background:#e6f0fa;color:#1a5fa8}}.bz{{background:#f0e6fa;color:#7a2da4}}.bn{{background:#f5f5f5;color:#999}}.bo{{background:#e6f7e6;color:#389e0d}}.bf{{background:#fff7e6;color:#d48806}}.ba{{background:#e6f7ff;color:#1890ff}}.bp{{background:#fff1f0;color:#cf1322}}.bt{{background:#f5f5f5;color:#888}}.ft{{text-align:center;padding:16px;font-size:10px;color:#999}}.nt{{background:#fffbe6;border:1px solid #ffe58f;border-radius:6px;padding:6px 12px;margin-bottom:8px;font-size:11px;color:#8c6d00}}</style></head><body><div class="h"><h1>公募REITs项目公示信息</h1><div class="sub">投资在线平台({total}条) + 上交所({sse_n}条) + 深交所(首发{szse_n-5}+新购入5={szse_n}条) | 自动更新</div></div><div class="tb"><input type="text" id="s" placeholder="搜索..." oninput="f()"><select id="x" onchange="f()"><option value="">全部</option><option value="上交所">上交所</option><option value="深交所">深交所</option><option value="未匹配">未匹配</option></select><select id="st" onchange="f()"><option value="">全部状态</option><option value="注册生效">注册生效</option><option value="已反馈">已反馈</option><option value="已受理">已受理</option><option value="已问询">已问询</option><option value="终止">终止</option><option value="终止(撤回)">终止(撤回)</option><option value="已申报">已申报</option></select><select id="ind" onchange="f()"><option value="">全部行业</option><option value="交通基础设施">交通</option><option value="仓储物流基础设施">仓储物流</option><option value="园区基础设施">园区</option><option value="市政基础设施">市政</option><option value="新型基础设施">新型</option><option value="水利设施">水利</option><option value="消费基础设施">消费</option><option value="生态环保基础设施">生态环保</option><option value="租赁住房">租赁住房</option><option value="能源基础设施">能源</option></select><span class="st" id="stt">共{total}条</span></div><div class="container"><div class="nt">{note}</div><table id="tbl"><thead><tr><th onclick="stb(0)">序号</th><th onclick="stb(1)">项目名称</th><th onclick="stb(2)">申报地方</th><th onclick="stb(3)">行业</th><th onclick="stb(4)">总额(亿)</th><th onclick="stb(5)">推荐日期</th><th onclick="stb(6)">交易所</th><th onclick="stb(7)">交易所基金名称</th><th onclick="stb(8)">受理日期</th><th onclick="stb(9)">注册生效</th><th onclick="stb(10)">状态</th><th onclick="stb(11)">匹配度</th></tr></thead><tbody id="tb"></tbody></table></div><div class="ft">数据来源: <a href="https://www.tzxm.gov.cn:8081/aweb-ui/reits/" target="_blank">投资在线平台</a> | <a href="https://www.sse.com.cn/reits/info/" target="_blank">上交所</a> | <a href="https://reits.szse.cn/projectdynamic/index.html" target="_blank">深交所</a> | 自动更新</div><script>var D={data_json};var SM={{"注册生效":'<span class="bd bo">注册生效</span>',"通过":'<span class="bd bo">注册生效</span>',"已反馈":'<span class="bd bf">已反馈</span>',"已受理":'<span class="bd ba">已受理</span>',"已问询":'<span class="bd bf">已问询</span>',"终止":'<span class="bd bp">终止</span>',"终止(撤回)":'<span class="bd bp">终止(撤回)</span>',"已申报":'<span class="bd bt">已申报</span>'}};var EM={{"上交所":'<span class="bd bs">上交所</span>',"深交所":'<span class="bd bz">深交所</span>'}};var sc=["c9","c0","c1","c2","c3"];function scs(v){{if(v>=80)return 1;if(v>=60)return 2;if(v>=40)return 3;if(v>0)return 4;return 0}}function r(){{var h="";for(var i=0;i<D.length;i++){{var o=D[i];var nm=o[7]?"":"nm";var ex=o[6]||"";var st=o[10]||"";var ind=o[3]||"";var ss=scs(o[11]);h+='<tr class="'+nm+'" data-x="'+(ex||'未匹配')+'" data-st="'+st+'" data-ind="'+ind+'"><td>'+o[0]+'</td><td>'+o[1]+'</td><td>'+o[2]+'</td><td>'+o[3]+'</td><td class="am">'+o[4]+'</td><td>'+o[5]+'</td><td>'+(EM[ex]||'<span class="bd bn">—</span>')+'</td><td>'+(o[7]||'—')+'</td><td>'+(o[8]||'—')+'</td><td>'+(o[9]||'—')+'</td><td>'+(SM[st]||'<span class="bd bt">—</span>')+'</td><td class="sc"><span class="'+sc[ss]+'">'+(o[11]?o[11]+'%':'—')+'</span></td></tr>'}}document.getElementById("tb").innerHTML=h}}function f(){{var s=document.getElementById("s").value.toLowerCase(),e=document.getElementById("x").value,st=document.getElementById("st").value,ind=document.getElementById("ind").value,c=0;document.querySelectorAll("#tb tr").forEach(function(r){{var t=r.textContent.toLowerCase(),ex=r.getAttribute("data-x"),st2=r.getAttribute("data-st"),id=r.getAttribute("data-ind");var m=(!s||t.includes(s))&&(!e||!ex||ex===e)&&(!st||st2===st)&&(!ind||id===ind);r.style.display=m?"":"none";if(m)c++}});document.getElementById("stt").textContent="显示 "+c+" / "+D.length+" 条"}}var sd={{}};function stb(col){{sd[col]=!sd[col];var tb=document.getElementById("tb");var rows=Array.from(tb.querySelectorAll("tr"));rows.sort(function(a,b){{var av=a.cells[col].textContent.trim(),bv=b.cells[col].textContent.trim();if(col===11){{var ap=av==="—"?-1:parseInt(av),bp=bv==="—"?-1:parseInt(bv);return sd[col]?ap-bp:bp-ap}}var an=parseFloat(av),bn=parseFloat(bv);if(!isNaN(an)&&!isNaN(bn))return sd[col]?an-bn:bn-an;return sd[col]?av.localeCompare(bv):bv.localeCompare(av)}});rows.forEach(function(r){{tb.appendChild(r)}})}}r();</script></body></html>'''

# ── 主流程 ────────────────────────────────────────

def main():
    print("Fetching tzxm data...")
    try:
        tzxm_resp = fetch_tzxm()
        tzxm_data = tzxm_resp['data']['list'] if isinstance(tzxm_resp.get('data'), dict) else tzxm_resp['data']
    except Exception as e:
        print(f"  tzxm FAILED: {e}, using cached")
        with open('data.json') as f: cached = json.load(f)
        tzxm_data = cached['tzxm']
    print(f"  tzxm: {len(tzxm_data)} entries")
    
    print("Fetching SZSE data...")
    try:
        szse_ipo = fetch_szse(21)
        szse_exp = fetch_szse(23)
    except Exception as e:
        print(f"  SZSE FAILED: {e}, using cached")
        with open('data.json') as f: cached = json.load(f)
        szse_ipo = cached['szse_ipo']
        szse_exp = cached['szse_exp']
    print(f"  SZSE IPO: {len(szse_ipo)}, EXP: {len(szse_exp)}")
    
    print("Fetching SSE data...")
    try:
        sse_data = fetch_sse()
    except Exception as e:
        print(f"  SSE FAILED: {e}, using cached")
        with open('data.json') as f: cached = json.load(f)
        sse_data = cached.get('sse', [])
    print(f"  SSE: {len(sse_data)} entries")
    
    # Save raw data for reference
    raw = {'tzxm': tzxm_data, 'sse': sse_data, 'szse_ipo': szse_ipo, 'szse_exp': szse_exp}
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)
    
    pool = build_exchange_pool(sse_data, szse_ipo, szse_exp)
    rows, mc, rc = match_and_build(tzxm_data, pool)
    
    sse_n = len(sse_data)
    szse_n = len(szse_ipo) + len(szse_exp)
    total = len(tzxm_data)
    
    print(f"Match: {mc}/{total} ({round(mc/total*100)}%), Reg: {rc}")
    
    html = generate_html(rows, mc, rc, total, sse_n, szse_n)
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"Generated index.html ({len(html):,} chars)")

if __name__ == '__main__':
    main()
