#!/usr/bin/env python3
"""Fix all corrupted Chinese strings in pricing_engine.py"""

with open('app/engine/pricing_engine.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Comprehensive replacement map
replacements = [
    # Font names
    ('绛夌嚎', '等线'),
    ('闅朵功', '隶书'),
    
    # Status messages
    ('鈿狅笍 寰呭～鍏?', '⏳ 待填充'),
    ('鉁?涓€鑷?', '✅ 一致'),
    ('鉂?缂哄け (璇峰～鍏?', '❌ 缺失 (请填写)'),
    ('馃啎 鏂伴儴浠?', '🆕 新部件'),
    
    # Match types
    ('绮剧'鍖归厤', '精确匹配'),
    ('閮ㄥ垎鍖归厤', '部分匹配'),
    ('鏈尮閰?', '未匹配'),
    ('鏃犲尮閰?', '无匹配'),
    ('鏃犳潯浠?', '无条件'),
    
    # Match descriptions
    ('闄嶇骇鑷?', '降级至'),
    ('涓绘澘闄嶇骇', '主板降级'),
    ('鏈虹妯＄硦鍖归厤', '机箱型号模糊匹配'),
    ('鎶ラ敊锛氭壘涓嶅埌鍖归厤鐨凩6浠锋牸', '报错：找不到匹配的L6价格'),
    
    # Field names
    ('瑙勬牸描述', '规格描述'),
    ('鎶ヤ环绯荤粺鏇存柊', '报价系统更新'),
    
    # Template names
    ('鏍囧噯报价鍗?', '标准报价单'),
    ('鍚◣', '含税'),
    
    # Tax note
    ('浠ヤ笂浠锋牸涓哄惈绋庝环锛屽惈13%澧炲€肩◣銆傛姤浠锋湁鏁堟湡30澶┿€?', 
     '以上价格为含税价，含13%增值税。报价有效期30天。'),
    
    # Sheet names
    ('报价鍗?', '报价单'),
    
    # Error messages
    ('椤圭洰涓嶅瓨鍦?', '项目不存在'),
    ('鎶ヤ环浜?', '报价人'),
    ('涓嶅瓨鍦?', '不存在'),
    
    # Notes
    ('澶囨敞锛?', '备注：'),
    
    # Comments
    ('鏈尮閰嶏細杩斿洖鏈€浣抽儴鍒嗗尮閰嶈褰曪紙鐢ㄤ簬鍓嶇灞曠ず锛?',
     '未匹配：返回最佳部分匹配记录（用于前端展示）'),
    
    # 5维精确匹配
    ('5缁寸簿纭尮閰?', '5维精确匹配'),
]

for old, new in replacements:
    content = content.replace(old, new)

with open('app/engine/pricing_engine.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('✅ Fixed all corrupted strings')
