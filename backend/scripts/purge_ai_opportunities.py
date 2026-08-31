# -*- coding: utf-8 -*-
"""一次性清空 AI 办公室隐藏商机（ai-% 前缀）+ 级联数据。
先全量备份到 _purge_ai_opps_backup_*.json 再删。"""
import datetime
import io
import json
import psycopg2

conn = psycopg2.connect(host='localhost', dbname='cpq_platform', user='postgres', password='961216')
conn.set_client_encoding('UTF8')
cur = conn.cursor()

# 1. 收集待删 id
cur.execute("SELECT opportunity_id FROM opportunities.opportunities WHERE opportunity_id LIKE 'ai-%'")
opp_ids = [r[0] for r in cur.fetchall()]
print('待删商机:', len(opp_ids))
if not opp_ids:
    conn.close()
    raise SystemExit(0)

ph = ','.join(['%s'] * len(opp_ids))

def fetch_all(table, where, params):
    cur.execute(f"SELECT * FROM {table} WHERE {where}", params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]

backup = {
    'opportunities': fetch_all('opportunities.opportunities', f'opportunity_id = ANY(%s)', (opp_ids,)),
    'opportunity_requirements': fetch_all('opportunities.opportunity_requirements', f'opportunity_id = ANY(%s)', (opp_ids,)),
    'opportunity_bom_schemes': fetch_all('opportunities.opportunity_bom_schemes', f'opportunity_id = ANY(%s)', (opp_ids,)),
    'threads': fetch_all('opportunities.assistant_threads', f'opportunity_id = ANY(%s)', (opp_ids,)),
}
cur.execute("SELECT thread_id FROM opportunities.assistant_threads WHERE opportunity_id = ANY(%s)", (opp_ids,))
thread_ids = [r[0] for r in cur.fetchall()]
backup['messages'] = fetch_all('opportunities.assistant_messages', f'thread_id = ANY(%s)', (thread_ids,)) if thread_ids else []
# 报价单是否有关联
cur.execute("SELECT count(*) FROM opportunities.quotations WHERE opportunity_id = ANY(%s)", (opp_ids,))
backup['_quotation_refs'] = cur.fetchone()[0]

stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
path = f'_purge_ai_opps_backup_{stamp}.json'
with io.open(path, 'w', encoding='utf-8') as f:
    json.dump(backup, f, ensure_ascii=False, indent=1, default=str)
print('备份:', path, '| 商机', len(backup['opportunities']), '| 需求', len(backup['opportunity_requirements']),
      '| BOM', len(backup['opportunity_bom_schemes']), '| 会话', len(backup['threads']),
      '| 消息', len(backup['messages']), '| 报价引用', backup['_quotation_refs'])

# 2. 级联删除（子表先删）
if thread_ids:
    cur.execute("DELETE FROM opportunities.assistant_messages WHERE thread_id = ANY(%s)", (thread_ids,))
    print('删消息:', cur.rowcount)
cur.execute("DELETE FROM opportunities.assistant_threads WHERE opportunity_id = ANY(%s)", (opp_ids,))
print('删会话:', cur.rowcount)
cur.execute("DELETE FROM opportunities.opportunity_bom_schemes WHERE opportunity_id = ANY(%s)", (opp_ids,))
print('删BOM方案:', cur.rowcount)
cur.execute("DELETE FROM opportunities.opportunity_requirements WHERE opportunity_id = ANY(%s)", (opp_ids,))
print('删需求登记:', cur.rowcount)
cur.execute("DELETE FROM opportunities.opportunities WHERE opportunity_id = ANY(%s)", (opp_ids,))
print('删商机:', cur.rowcount)

conn.commit()
cur.execute("SELECT count(*) FROM opportunities.opportunities WHERE opportunity_id LIKE 'ai-%'")
print('剩余 ai- 商机:', cur.fetchone()[0])
conn.close()
