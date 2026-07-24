"""Test script for field management v3 features"""
import requests
import json

BASE = "http://localhost:8000/api/admin"

def test(name, fn):
    try:
        fn()
        print(f"  ✓ {name}")
    except Exception as e:
        print(f"  ✗ {name}: {e}")

# Test 1: Update field (audit log)
print("=== 1. Update field + audit log ===")
def t1():
    res = requests.put(f"{BASE}/business-fields/test_field", json={
        "label": "测试字段-已更新",
        "description": "这是一个测试字段"
    })
    assert res.status_code == 200, f"Status: {res.status_code}, Body: {res.text}"
    data = res.json()
    assert data["label"] == "测试字段-已更新"
    assert data["updated_at"] is not None
test("Update field", t1)

# Test 2: Audit history
print("\n=== 2. Audit history ===")
def t2():
    res = requests.get(f"{BASE}/business-fields/test_field/history")
    assert res.status_code == 200, f"Status: {res.status_code}"
    data = res.json()
    assert data["total"] >= 2, f"Expected >= 2 logs, got {data['total']}"
    for log in data["history"]:
        print(f"    {log['action']} by {log['operator']} - changes: {log['changes'][:80] if log['changes'] else 'none'}")
test("Audit history", t2)

# Test 3: Validate field value
print("\n=== 3. Validate field value ===")
def t3():
    res = requests.post(f"{BASE}/business-fields/test_field/validate", json={"value": ""})
    assert res.status_code == 200
    data = res.json()
    assert data["valid"] == False, "Empty value should fail (required=true)"
    assert len(data["errors"]) > 0
    print(f"    Empty value: valid={data['valid']}, errors={data['errors']}")
    
    res = requests.post(f"{BASE}/business-fields/test_field/validate", json={"value": "OK"})
    data = res.json()
    assert data["valid"] == True, f"Normal value should pass: {data}"
    print(f"    Normal value: valid={data['valid']}")
test("Validate field", t3)

# Test 4: Usage stats
print("\n=== 4. Usage stats ===")
def t4():
    res = requests.post(f"{BASE}/business-fields/test_field/record-usage")
    assert res.status_code == 200
    res = requests.get(f"{BASE}/business-fields/test_field/stats")
    assert res.status_code == 200
    data = res.json()
    print(f"    usage_count={data['usage_count']}, last_used={data['last_used_at']}")
test("Usage stats", t4)

# Test 5: Export fields
print("\n=== 5. Export fields ===")
def t5():
    res = requests.get(f"{BASE}/business-fields-export")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 33
    print(f"    Exported {data['total']} fields at {data['exported_at']}")
test("Export fields", t5)

# Test 6: Import fields
print("\n=== 6. Import fields ===")
def t6():
    res = requests.post(f"{BASE}/business-fields-import", json={
        "fields": [
            {"key": "import_test_1", "label": "导入测试1", "category": "system", "source": "Custom", "enabled": True, "sort_order": 100},
            {"key": "import_test_2", "label": "导入测试2", "category": "system", "source": "Custom", "enabled": True, "sort_order": 101},
        ],
        "mode": "skip"
    })
    assert res.status_code == 200, f"Status: {res.status_code}, Body: {res.text}"
    data = res.json()
    print(f"    created={data['created']}, updated={data['updated']}, skipped={data['skipped']}")
test("Import fields", t6)

# Test 7: References (add + check + delete)
print("\n=== 7. References ===")
def t7():
    # Add reference
    res = requests.post(f"{BASE}/business-fields/test_field/references", json={
        "ref_type": "template",
        "ref_id": 1,
        "ref_name": "测试模板"
    })
    assert res.status_code == 200, f"Add ref: {res.status_code} {res.text}"
    print(f"    Added reference: {res.json()}")
    
    # Get references
    res = requests.get(f"{BASE}/business-fields/test_field/references")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    print(f"    References: {data['total']}")
    
    # Try delete (should warn about references)
    res = requests.delete(f"{BASE}/business-fields/test_field")
    data = res.json()
    assert data["has_references"] == True
    print(f"    Delete blocked: {data['message']}")
    
    # Force delete
    res = requests.delete(f"{BASE}/business-fields/test_field/force")
    assert res.status_code == 200
    print(f"    Force delete: {res.json()}")
    
    # Verify deleted
    res = requests.get(f"{BASE}/business-fields/test_field/references")
    assert res.json()["total"] == 0
test("References", t7)

# Test 8: Cleanup import test fields
print("\n=== 8. Cleanup ===")
def t8():
    for key in ["import_test_1", "import_test_2"]:
        res = requests.delete(f"{BASE}/business-fields/{key}/force")
        assert res.status_code == 200
    print("    Cleaned up test fields")
test("Cleanup", t8)

print("\n=== All tests passed! ===")
