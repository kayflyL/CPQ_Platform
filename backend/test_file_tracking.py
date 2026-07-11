"""
测试文件留痕功能
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.project_file import ProjectFile
from app.utils.file_storage import FileStorage
from app.repository.project_file_repo import ProjectFileRepository
from app.models.base import Proj_SessionLocal, Base

def test_file_storage():
    """测试文件存储"""
    print("\n=== 测试文件存储 ===")
    
    storage = FileStorage()
    
    # 测试上传文件存储
    test_content = b"This is a test file content"
    result = storage.save_upload("TEST001", test_content, "test_upload.xlsx")
    print(f"上传文件存储结果: {result}")
    
    # 测试导出文件存储
    result = storage.save_export("TEST001", test_content, "test_export.xlsx")
    print(f"导出文件存储结果: {result}")
    
    # 测试文件计数
    counts = storage.get_project_file_count("TEST001")
    print(f"文件计数: {counts}")
    
    return True

def test_database():
    """测试数据库操作"""
    print("\n=== 测试数据库操作 ===")
    
    # 确保表存在
    Base.metadata.create_all(bind=Proj_SessionLocal().bind)
    
    repo = ProjectFileRepository()
    
    # 添加测试记录
    file1 = repo.add_file(
        project_id="TEST001",
        file_type="upload",
        original_name="test1.xlsx",
        stored_path="uploads/test1.xlsx",
        file_size=1024
    )
    print(f"添加文件记录: {file1.to_dict()}")
    
    file2 = repo.add_file(
        project_id="TEST001",
        file_type="export",
        original_name="export1.xlsx",
        stored_path="exports/export1.xlsx",
        file_size=2048
    )
    print(f"添加文件记录: {file2.to_dict()}")
    
    # 查询文件列表
    files = repo.get_files_by_project("TEST001")
    print(f"项目文件列表: {len(files)} 个文件")
    
    # 查询特定类型
    uploads = repo.get_files_by_project("TEST001", file_type="upload")
    print(f"上传文件: {len(uploads)} 个")
    
    exports = repo.get_files_by_project("TEST001", file_type="export")
    print(f"导出文件: {len(exports)} 个")
    
    # 获取文件计数
    counts = repo.get_file_counts_by_project("TEST001")
    print(f"文件计数: {counts}")
    
    # 清理测试数据
    repo.delete_files_by_project("TEST001")
    print("已清理测试数据")
    
    repo.close()
    return True

def test_file_download():
    """测试文件下载"""
    print("\n=== 测试文件下载 ===")
    
    storage = FileStorage()
    
    # 先保存一个测试文件
    test_content = b"Test content for download"
    result = storage.save_upload("TEST002", test_content, "download_test.xlsx")
    
    # 获取文件路径
    file_path = storage.get_file_path("TEST002", result['stored_path'])
    print(f"文件路径: {file_path}")
    print(f"文件存在: {os.path.exists(file_path)}")
    
    # 读取文件内容验证
    with open(file_path, 'rb') as f:
        content = f.read()
    print(f"文件内容匹配: {content == test_content}")
    
    # 清理
    storage.delete_project_files("TEST002")
    print("已清理测试文件")
    
    return True

def main():
    print("开始测试文件留痕功能...")
    
    try:
        test_file_storage()
        test_database()
        test_file_download()
        
        print("\n✅ 所有测试通过！")
        return 0
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
