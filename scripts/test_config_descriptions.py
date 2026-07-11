"""验证配置描述的保存和读取"""
import sys
import os
import pandas as pd

# 添加 backend 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.engine.pricing_engine import PricingEngine
from app.repository.quotation_repo import QuotationRepository
from app.repository.project_repo import ProjectRepository
from app.repository.kp_repo import KPRepository
from app.repository.l6_repo import L6Repository

def test_config_descriptions():
    """测试配置描述的保存和读取"""
    
    # 初始化
    kp_repo = KPRepository()
    l6_repo = L6Repository()
    project_repo = ProjectRepository()
    quotation_repo = QuotationRepository()
    engine = PricingEngine(kp_repo, l6_repo, project_repo)
    
    # 准备测试数据
    project_id = "TEST_PROJECT_001"
    project_info = {
        "project_id": project_id,
        "project_name": "测试项目",
        "customer_name": "测试客户"
    }
    
    # 创建配置数据
    configs_data = {
        "CFG1": pd.DataFrame([
            {"category": "L6", "part_name": "CPU", "spec": "Intel Xeon", "qty": 2, "final_price": 1000}
        ]),
        "CFG2": pd.DataFrame([
            {"category": "L6", "part_name": "Memory", "spec": "32GB DDR4", "qty": 4, "final_price": 500}
        ])
    }
    
    # 配置描述
    config_descriptions = {
        "CFG1": "这是配置1的描述",
        "CFG2": "这是配置2的描述"
    }
    
    # 1. 测试保存
    print("1. 测试保存配置描述...")
    result = engine.save_project(project_info, configs_data, config_descriptions)
    print(f"   保存结果: {result}")
    
    if result.get('status') != 'success':
        print("   ❌ 保存失败")
        return False
    
    quotation_id = result.get('quotation_id')
    print(f"   ✓ 保存成功，报价单ID: {quotation_id}")
    
    # 2. 验证数据库中的值
    print("\n2. 验证数据库中的值...")
    quotation = quotation_repo.get_by_id(quotation_id)
    if quotation and quotation.config_descriptions:
        print(f"   数据库中的 config_descriptions: {quotation.config_descriptions}")
        if quotation.config_descriptions == config_descriptions:
            print("   ✓ 数据库中的值正确")
        else:
            print("   ❌ 数据库中的值不匹配")
            return False
    else:
        print("   ❌ 数据库中未找到 config_descriptions")
        return False
    
    # 3. 测试读取
    print("\n3. 测试读取配置描述...")
    details = engine.get_project_details(project_id)
    if details and 'meta' in details:
        meta = details['meta']
        if 'config_descriptions' in meta:
            print(f"   meta 中的 config_descriptions: {meta['config_descriptions']}")
            if meta['config_descriptions'] == config_descriptions:
                print("   ✓ 读取的值正确")
            else:
                print("   ❌ 读取的值不匹配")
                return False
        else:
            print("   ❌ meta 中未找到 config_descriptions")
            return False
    else:
        print("   ❌ 读取项目详情失败")
        return False
    
    # 清理测试数据
    print("\n4. 清理测试数据...")
    quotation_repo.delete(quotation_id)
    project_repo.delete(project_id)
    print("   ✓ 清理完成")
    
    return True

if __name__ == "__main__":
    success = test_config_descriptions()
    if success:
        print("\n✅ 所有测试通过！")
    else:
        print("\n❌ 测试失败！")
        sys.exit(1)
