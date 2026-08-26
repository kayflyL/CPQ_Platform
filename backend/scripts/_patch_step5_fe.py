from pathlib import Path
p = Path(r"D:\CPQ_Platform_V1\frontend\src\views\admin\reasoning\SlotListEditor.vue")
s = p.read_text(encoding="utf-8")

# 1) KpRow drop label
old = '''interface KpRow {
  category: string
  key: string
  label: string
  candidate_source: string
}
'''
new = '''interface KpRow {
  category: string
  key: string
  candidate_source: string
}
'''
assert old in s
s = s.replace(old, new, 1)

# 2) drop PART_OPTION_LABELS
old = '''const PART_OPTION_LABELS: Record<string, string> = {
  cpu: 'CPU', memory: '内存', storage: '存储', gpu: 'GPU', nic: '网卡', raid: '阵列卡', psu: '电源', free: '',
}
'''
assert old in s
s = s.replace(old, "", 1)

# 3) loadKpMap drop label
old = '''      return {
        category: name,
        key,
        label: String(rule.label || PART_OPTION_LABELS[key] || name),
        candidate_source: String(rule.candidate_source || 'catalog'),
      }
'''
new = '''      return {
        category: name,
        key,
        candidate_source: String(rule.candidate_source || 'catalog'),
      }
'''
assert old in s
s = s.replace(old, new, 1)

# 4) saveKpMap drop label
old = '''      map[r.category] = {
        key: r.key,
        label: r.label || PART_OPTION_LABELS[r.key] || r.category,
        candidate_source: r.candidate_source || 'catalog',
        group: '部件',
      }
'''
new = '''      map[r.category] = {
        key: r.key,
        candidate_source: r.candidate_source || 'catalog',
        group: '部件',
      }
'''
assert old in s
s = s.replace(old, new, 1)

# 5) template: drop 中文名 header + input column
old = '''            <span class="slot-key">KP 大类</span>
            <span class="slot-kp-map">映射字段</span>
            <span class="slot-label">中文名</span>
            <span class="slot-src">候选来源</span>
'''
new = '''            <span class="slot-key">KP 大类</span>
            <span class="slot-kp-map">映射字段</span>
            <span class="slot-src">候选来源</span>
'''
assert old in s
s = s.replace(old, new, 1)

old = '''            <a-select v-model:value="r.key" size="small" class="slot-kp-map" :options="PART_OPTIONS" :disabled="props.readonly || r.key === 'free'" />
            <a-input v-model:value="r.label" size="small" class="slot-label" :disabled="props.readonly || r.key === 'free'" :placeholder="r.category" />
            <a-select v-model:value="r.candidate_source" size="small" class="slot-src" :options="CANDIDATE_SOURCES" :disabled="props.readonly || r.key === 'free'" />
'''
new = '''            <a-select v-model:value="r.key" size="small" class="slot-kp-map" :options="PART_OPTIONS" :disabled="props.readonly || r.key === 'free'" />
            <a-select v-model:value="r.candidate_source" size="small" class="slot-src" :options="CANDIDATE_SOURCES" :disabled="props.readonly || r.key === 'free'" />
'''
assert old in s
s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
print("ok SlotListEditor.vue")
