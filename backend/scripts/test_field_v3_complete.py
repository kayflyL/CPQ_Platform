"""完整测试字段管理 v3 所有功能"""
import requests
import json

BASE = "http://localhost:8000/api/admin"

def test(name, fn):
    try:
        result = fn()
        print(f"✓ {name}")
        return result
    except Exception as e:
        print(f"✗ {name}: {e}")
        return None

print("=" * 60)
print("字段管理 v3 完整测试")
print("=" * 60)

# 1. 创建测试字段
print("\n【1】创建字段")
def create_field():
    res = requests.post(f"{BASE}/business-fields", json={
        "key": "test_validation",
        "label": "测试校验字段",
        "category": "system",
        "source": "Custom",
        "display_type": "text",
        "validation_rules": json.dumps({"required": True, "minLength": 3, "maxLength": 20}),
        "enabled": True,
        "sort_order": 100
    })
    assert res.status_code == 200, f"Status: {res.status_code}"
    data = res.json()
    assert data["key"] == "test_validation"
    assert data["validation_rules"] is not None
    return data

test("创建字段", create_field)

# 2. 更新字段（触发审计日志）
print("\n【2】更新字段 + 审计日志")
def update_field():
    res = requests.put(f"{BASE}/business-fields/test_validation", json={
        "label": "测试校验字段-已更新",
        "description": "添加描述"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["label"] == "测试校验字段-已更新"
    assert data["updated_at"] is not None
    return data

test("更新字段", update_field)

# 3. 查看审计历史
print("\n【3】审计历史")
def check_history():
    res = requests.get(f"{BASE}/business-fields/test_validation/history")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 2, f"Expected >= 2 logs, got {data['total']}"
    print(f"  历史记录数: {data['total']}")
    for log in data["history"][:3]:
        changes = json.loads(log["changes"]) if log["changes"] else {}
        print(f"  - {log['action']} by {log['operator']}")
        if changes:
            for k, v in list(changes.items())[:2]:
                print(f"    {k}: {v['old']} → {v['new']}")
    return data

test("审计历史", check_history)

# 4. 字段校验
print("\n【4】字段校验规则")
def validate_field():
    # 空值（应该失败，required=true）
    res = requests.post(f"{BASE}/business-fields/test_validation/validate", json={"value": ""})
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] == False, "Empty value should fail"
    print(f"  空值校验: valid={data['valid']}, errors={data['errors']}")
    
    # 太短（应该失败，minLength=3）
    res = requests.post(f"{BASE}/business-fields/test_validation/validate", json={"value": "ab"})
    data = res.json()
    assert data["valid"] == False, "Too short should fail"
    print(f"  太短校验: valid={data['valid']}, errors={data['errors']}")
    
    # 正常值（应该通过）
    res = requests.post(f"{BASE}/business-fields/test_validation/validate", json={"value": "测试值"})
    data = res.json()
    assert data["valid"] == True, f"Normal value should pass: {data}"
    print(f"  正常值校验: valid={data['valid']}")
    
    return data

test("字段校验", validate_field)

# 5. 使用统计
print("\n【5】使用统计")
def usage_stats():
    # 记录使用
    res = requests.post(f"{BASE}/business-fields/test_validation/record-usage")
    assert res.status_code == 200
    
    # 查看统计
    res = requests.get(f"{BASE}/business-fields/test_validation/stats")
    assert res.status_code == 200
    data = res.json()
    assert data["usage_count"] >= 1
    print(f"  使用次数: {data['usage_count']}, 最后使用: {data['last_used_at']}")
    return data

test("使用统计", usage_stats)

# 6. 字段引用
print("\n【6】字段引用管理")
def field_references():
    # 添加引用
    res = requests.post(f"{BASE}/business-fields/test_validation/references", json={
        "ref_type": "template",
        "ref_id": 1,
        "ref_name": "测试模板"
    })
    assert res.status_code == 200
    print(f"  添加引用: {res.json()}")
    
    # 查看引用
    res = requests.get(f"{BASE}/business-fields/test_validation/references")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    print(f"  引用数量: {data['total']}")
    
    # 尝试删除（应该被阻止）
    res = requests.delete(f"{BASE}/business-fields/test_validation")
    data = res.json()
    assert data["has_references"] == True
    print(f"  删除被阻止: {data['message']}")
    
    # 删除引用
    res = requests.delete(f"{BASE}/business-fields/test_validation/references/template/1")
    assert res.status_code == 200
    print(f"  删除引用: {res.json()}")
    
    return data

test("字段引用", field_references)

# 7. 导出字段
print("\n【7】导出字段")
def export_fields():
    res = requests.get(f"{BASE}/business-fields-export")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 33
    assert "exported_at" in data
    print(f"  导出数量: {data['total']}, 时间: {data['exported_at']}")
    return data

test("导出字段", export_fields)

# 8. 导入字段
print("\n【8】导入字段")
def import_fields():
    res = requests.post(f"{BASE}/business-fields-import", json={
        "fields": [
            {"key": "import_test_1", "label": "导入测试1", "category": "system", "source": "Custom", "enabled": True, "sort_order": 101},
            {"key": "import_test_2", "label": "导入测试2", "category": "system", "source": "Custom", "enabled": True, "sort_order": 102},
        ],
        "mode": "skip"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["created"] == 2
    print(f"  导入结果: created={data['created']}, updated={data['updated']}, skipped={data['skipped']}")
    return data

test("导入字段", import_fields)

# 9. 清理测试数据
print("\n【9】清理测试数据")
def cleanup():
    for key in ["test_validation", "import_test_1", "import_test_2"]:
        res = requests.delete(f"{BASE}/business-fields/{key}/force")
        assert res.status_code == 200
    print(f"  已清理测试字段")

test("清理数据", cleanup)

# 10. 批量校验
print("\n【10】批量校验")
def batch_validate():
    res = requests.post(f"{BASE}/business-fields/validate-batch", json={
        "values": {
            "customer_name": "测试客户",
            "project_name": "测试项目"
        }
    })
    assert res.status_code == 200
    data = res.json()
    print(f"  批量校验: valid={data['valid']}, 字段数={len(data['results'])}")
    return data

test("批量校验", batch_validate)

print("\n" + "=" * 60)
print("所有测试完成！")
print("=" * 60)
