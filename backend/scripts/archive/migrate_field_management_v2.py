"""
迁移脚本：为 business_fields 表新增字段管理优化所需的 5 列
- description: 字段描述
- display_type: 展示类型 (text/money/percent/date/enum)
- group_name: 分组名
- scope: 使用范围 (all/cover/config/rules)
- permission: 字段权限 (editable/readonly/hidden)
"""
import sqlite3
import os

DB_PATH = 'D:\\Quotation_Automation\\Reference\\kp_data.db'

# 默认分组和描述映射
FIELD_DEFAULTS = {
    # 商机 - 基本信息
    'customer_name':    {'group_name': '基本信息', 'description': '商机对应的客户名称', 'permission': 'editable', 'display_type': 'text'},
    'sales_person':     {'group_name': '基本信息', 'description': '负责的销售人员', 'permission': 'editable', 'display_type': 'text'},
    'fae':              {'group_name': '基本信息', 'description': '技术支持工程师', 'permission': 'editable', 'display_type': 'text'},
    'platform_type':    {'group_name': '基本信息', 'description': '产品平台类型分类', 'permission': 'readonly', 'display_type': 'enum'},
    'chassis_form':     {'group_name': '基本信息', 'description': '底盘形式', 'permission': 'readonly', 'display_type': 'enum'},
    # 商机 - 报价汇总
    'project_name':     {'group_name': '报价汇总', 'description': '商机/项目名称', 'permission': 'editable', 'display_type': 'text'},
    'version':          {'group_name': '报价汇总', 'description': '报价版本号', 'permission': 'readonly', 'display_type': 'text'},
    'quotation_date':   {'group_name': '报价汇总', 'description': '报价创建日期', 'permission': 'readonly', 'display_type': 'date'},
    'total_price':      {'group_name': '报价汇总', 'description': '报价总金额（自动计算）', 'permission': 'readonly', 'display_type': 'money'},
    'profit_margin':    {'group_name': '报价汇总', 'description': '整体毛利率', 'permission': 'readonly', 'display_type': 'percent'},
    # 配置 - 配置明细
    'config_name':      {'group_name': '配置明细', 'description': '配置项名称', 'permission': 'editable', 'display_type': 'text'},
    'category':         {'group_name': '配置明细', 'description': '配置项分类', 'permission': 'readonly', 'display_type': 'enum'},
    'part_name':        {'group_name': '配置明细', 'description': '零部件名称', 'permission': 'readonly', 'display_type': 'text'},
    'spec':             {'group_name': '配置明细', 'description': '规格型号', 'permission': 'readonly', 'display_type': 'text'},
    'qty':              {'group_name': '配置明细', 'description': '数量', 'permission': 'editable', 'display_type': 'number'},
    'final_price':      {'group_name': '配置明细', 'description': '最终单价', 'permission': 'readonly', 'display_type': 'money'},
    'item_profit_margin': {'group_name': '配置明细', 'description': '单项毛利率', 'permission': 'readonly', 'display_type': 'percent'},
    # L6 价格库
    'l6_chassis':       {'group_name': 'L6 参数', 'description': 'L6 底盘类型', 'permission': 'readonly', 'display_type': 'text'},
    'l6_chassis_type':  {'group_name': 'L6 参数', 'description': 'L6 底盘子类型', 'permission': 'readonly', 'display_type': 'text'},
    'l6_cabinet':       {'group_name': 'L6 参数', 'description': 'L6 机柜规格', 'permission': 'readonly', 'display_type': 'text'},
    'l6_cabinet_type':  {'group_name': 'L6 参数', 'description': 'L6 机柜子类型', 'permission': 'readonly', 'display_type': 'text'},
    'l6_power':         {'group_name': 'L6 参数', 'description': 'L6 电源规格', 'permission': 'readonly', 'display_type': 'text'},
    'l6_power_type':    {'group_name': 'L6 参数', 'description': 'L6 电源子类型', 'permission': 'readonly', 'display_type': 'text'},
    'l6_price':         {'group_name': 'L6 参数', 'description': 'L6 价格', 'permission': 'readonly', 'display_type': 'money'},
    'l6_currency':      {'group_name': 'L6 参数', 'description': 'L6 币种', 'permission': 'readonly', 'display_type': 'enum'},
    # KP 价格库
    'kp_category':      {'group_name': 'KP 参数', 'description': 'KP 分类', 'permission': 'readonly', 'display_type': 'text'},
    'kp_part_name':     {'group_name': 'KP 参数', 'description': 'KP 零部件名称', 'permission': 'readonly', 'display_type': 'text'},
    'kp_price':         {'group_name': 'KP 参数', 'description': 'KP 价格', 'permission': 'readonly', 'display_type': 'money'},
    'kp_currency':      {'group_name': 'KP 参数', 'description': 'KP 币种', 'permission': 'readonly', 'display_type': 'enum'},
    # 系统
    'export_date':      {'group_name': '导出信息', 'description': '导出日期', 'permission': 'readonly', 'display_type': 'date'},
    'export_user':      {'group_name': '导出信息', 'description': '导出操作人', 'permission': 'readonly', 'display_type': 'text'},
    'export_timestamp': {'group_name': '导出信息', 'description': '导出时间戳', 'permission': 'hidden', 'display_type': 'text'},
}

NEW_COLUMNS = [
    ('description', 'TEXT DEFAULT NULL'),
    ('display_type', 'TEXT DEFAULT "text"'),
    ('group_name', 'TEXT DEFAULT NULL'),
    ('scope', 'TEXT DEFAULT "all"'),
    ('permission', 'TEXT DEFAULT "editable"'),
]


def migrate():
    print(f"数据库路径: {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print(f"✗ 数据库不存在: {DB_PATH}")
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 检查表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='business_fields'")
    if not cursor.fetchone():
        print("✗ business_fields 表不存在")
        conn.close()
        return False

    # 获取现有列
    cursor.execute("PRAGMA table_info(business_fields)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    print(f"现有列: {existing_cols}")

    # 添加新列
    added = 0
    for col_name, col_def in NEW_COLUMNS:
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE business_fields ADD COLUMN {col_name} {col_def}")
            print(f"  ✓ 新增列: {col_name}")
            added += 1
        else:
            print(f"  - 列已存在: {col_name}")

    if added == 0:
        print("所有列已存在，跳过新增")

    # 填充默认值
    cursor.execute("SELECT key FROM business_fields")
    keys = [row[0] for row in cursor.fetchall()]

    updated = 0
    for key in keys:
        defaults = FIELD_DEFAULTS.get(key)
        if defaults:
            sets = []
            for field, value in defaults.items():
                sets.append(f"{field} = '{value}'")
            # scope 默认 all
            sets.append("scope = 'all'")
            sql = f"UPDATE business_fields SET {', '.join(sets)} WHERE key = '{key}'"
            cursor.execute(sql)
            updated += 1
        else:
            print(f"  ⚠ 未找到默认配置: {key}，使用通用默认值")
            cursor.execute(f"UPDATE business_fields SET group_name = '其他', scope = 'all', permission = 'editable' WHERE key = '{key}'")
            updated += 1

    conn.commit()
    conn.close()

    print(f"\n✓ 迁移完成: 新增 {added} 列, 更新 {updated} 条记录")
    return True


if __name__ == '__main__':
    migrate()
