import json
with open('office_teamconfig.json', encoding='utf-8') as f:
    data = json.load(f)
office = data.get('layout', {}).get('office', {})
plan = office.get('plan', {})
if not isinstance(plan, dict):
    print('no plan dict')
else:
    floors = plan.get('floors', [])
    print('floors:', len(floors), 'activeFloorId:', plan.get('activeFloorId'))
    for fl in floors:
        print('--- floor', fl.get('id'), fl.get('name'), 'walls', len(fl.get('walls', [])), 'rooms', len(fl.get('rooms', [])), 'furniture', len(fl.get('furniture', [])))
        print('rooms:', json.dumps(fl.get('rooms', []), ensure_ascii=False))
        furn = fl.get('furniture', [])
        from collections import Counter
        print('furniture counts:', json.dumps(Counter(f.get('catalogId') for f in furn), ensure_ascii=False))
        print('furniture positions:', json.dumps([{ 'id': f.get('id'), 'cat': f.get('catalogId'), 'x': f.get('position',{}).get('x'), 'y': f.get('position',{}).get('y'), 'rot': f.get('rotation'), 'w': f.get('width'), 'd': f.get('depth')} for f in furn], ensure_ascii=False))
