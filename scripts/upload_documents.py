#!/usr/bin/env python3
"""
文檔上傳執行腳本
用於批量上傳 RAG_docs 中的文檔到 Elasticsearch
"""

import asyncio
import logging
import sys
from pathlib import Path

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tools.document_uploader import DocumentUploader

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('document_upload.log')
    ]
)

logger = logging.getLogger(__name__)


async def main():
    """主要執行函數"""
    print("🚀 開始文檔上傳程序")
    print("=" * 50)
    
    # 設定路徑
    rag_docs_path = project_root / "RAG_docs"
    
    # 檢查路徑是否存在
    if not rag_docs_path.exists():
        print(f"❌ RAG_docs 目錄不存在: {rag_docs_path}")
        return
    
    print(f"📁 準備上傳目錄: {rag_docs_path}")
    
    try:
        # 檢查目錄內容
        files = list(rag_docs_path.glob("*"))
        print(f"📄 發現 {len(files)} 個檔案:")
        for file in files:
            if file.is_file():
                print(f"   - {file.name} ({file.stat().st_size} bytes)")
        
        print("\n🔄 開始上傳處理...")
        print("-" * 30)
        
        # 初始化上傳器
        uploader = DocumentUploader()
        
        # 執行上傳
        results = await uploader.upload_directory(
            directory_path=str(rag_docs_path),
            intent="nkust_im_docs"  # 高科大資管系文檔
        )
        
        # 顯示結果
        print("\n📊 上傳完成！統計結果:")
        print("=" * 50)
        print(f"📁 總檔案數:     {results['total_files']}")
        print(f"✅ 成功上傳:     {results['successful_uploads']}")
        print(f"❌ 失敗上傳:     {results['failed_uploads']}")
        print(f"⏭️ 跳過檔案:     {results['skipped_files']}")
        
        if results['processed_files']:
            print(f"\n📄 成功處理的檔案:")
            for file_info in results['processed_files']:
                print(f"   ✅ {Path(file_info['file']).name}")
                print(f"      ID: {file_info['doc_id']}")
                print(f"      分塊數: {file_info['chunks']}")
        
        if results['failed_files']:
            print(f"\n❌ 失敗的檔案:")
            for file_info in results['failed_files']:
                print(f"   ❌ {Path(file_info['file']).name}")
                print(f"      錯誤: {file_info['error']}")
        
        print(f"\n⏰ 開始時間: {results['start_time']}")
        print(f"⏰ 結束時間: {results['end_time']}")
        
        # 成功率計算
        if results['total_files'] > 0:
            success_rate = (results['successful_uploads'] / results['total_files']) * 100
            print(f"📈 成功率: {success_rate:.1f}%")
        
        print("\n🎉 文檔上傳程序執行完成！")
        
        # 如果有失敗的檔案，返回非零退出碼
        if results['failed_uploads'] > 0:
            print("⚠️ 部分檔案上傳失敗，請檢查錯誤訊息")
            sys.exit(1)
        
    except Exception as e:
        logger.error(f"上傳過程中發生錯誤: {e}")
        print(f"❌ 上傳失敗: {e}")
        sys.exit(1)


def check_elasticsearch_connection():
    """檢查 Elasticsearch 連線"""
    print("🔍 檢查 Elasticsearch 連線...")
    
    try:
        from adapters.es_client import get_es_client
        
        # 這裡可以添加實際的連線測試
        print("✅ Elasticsearch 設定已載入")
        return True
        
    except Exception as e:
        print(f"❌ Elasticsearch 連線檢查失敗: {e}")
        return False


def check_embedding_provider():
    """檢查 embedding provider"""
    print("🔍 檢查 Embedding Provider...")
    
    try:
        from embedding_provider import get_default_provider
        
        provider = get_default_provider()
        print(f"✅ Embedding Provider 已載入: {type(provider).__name__}")
        return True
        
    except Exception as e:
        print(f"❌ Embedding Provider 檢查失敗: {e}")
        return False


async def run_upload_with_checks():
    """帶預檢查的上傳程序"""
    print("🧪 執行前置檢查...")
    print("-" * 30)
    
    # 檢查 Elasticsearch
    if not check_elasticsearch_connection():
        print("❌ Elasticsearch 檢查失敗，請檢查設定")
        return
    
    # 檢查 Embedding Provider
    if not check_embedding_provider():
        print("❌ Embedding Provider 檢查失敗，請檢查設定")
        return
    
    print("✅ 所有檢查通過！")
    print()
    
    # 執行上傳
    await main()


if __name__ == "__main__":
    try:
        asyncio.run(run_upload_with_checks())
    except KeyboardInterrupt:
        print("\n⚠️ 用戶中斷上傳程序")
        sys.exit(1)
    except Exception as e:
        logger.error(f"程序執行失敗: {e}")
        print(f"❌ 程序執行失敗: {e}")
        sys.exit(1)