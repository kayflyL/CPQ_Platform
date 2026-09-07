import json
with open('office_teamconfig.json', encoding='utf-8') as f:
    data = json.load(f)
office = data.get('layout', {}).get('office', {})
out = {
  'floor': office.get('floor'),
  'workspace': office.get('workspace'),
  'zones': office.get('zones'),
  'furniture': office.get('furniture'),
  'environment_theme': office.get('environment_theme'),
  'status_zone_map': office.get('status_zone_map'),
}
print(json.dumps(out, ensure_ascii=False, indent=2))
