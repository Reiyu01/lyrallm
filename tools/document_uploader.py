"""
文檔上傳器 - 負責將文檔處理並上傳到 Elasticsearch
支援多種文檔格式，自動生成 embedding 並建立索引
"""

import asyncio
import hashlib
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from config.config_manager import config_manager
from adapters.elasticsearch_adapter import ElasticsearchAdapter
from embedding_provider import get_default_provider

logger = logging.getLogger(__name__)


class DocumentUploader:
    """文檔上傳器，處理文檔解析、embedding 生成和 ES 上傳"""
    
    def __init__(self, index_name: Optional[str] = None):
        self.elasticsearch_adapter = None
        self.embedding_provider = None
        self.index_name = index_name or self._get_default_index()
        self._initialized = False
        
        # 支援的文件格式
        self.supported_extensions = {'.md', '.txt', '.json'}
        
        logger.info(f"📁 DocumentUploader 初始化，目標索引: {self.index_name}")
    
    def _get_default_index(self) -> str:
        """獲取預設索引名稱"""
        try:
            vectordb_config = config_manager.config.get('vectordb', {})
            return vectordb_config.get('index', 'document_index')
        except:
            return 'document_index'
    
    async def initialize(self):
        """初始化 ES 適配器和 embedding provider"""
        if self._initialized:
            return
        
        try:
            # 初始化 Elasticsearch 適配器
            self.elasticsearch_adapter = ElasticsearchAdapter(index=self.index_name)
            await self.elasticsearch_adapter.ensure_index()
            logger.info(f"✅ Elasticsearch 適配器已初始化，索引: {self.index_name}")
            
            # 初始化 embedding provider
            self.embedding_provider = get_default_provider()
            logger.info("✅ Embedding provider 已初始化")
            
            self._initialized = True
            
        except Exception as e:
            logger.error(f"❌ DocumentUploader 初始化失敗: {e}")
            raise
    
    async def upload_directory(self, directory_path: str, intent: str = "document") -> Dict[str, Any]:
        """
        上傳整個目錄的文檔
        
        Args:
            directory_path: 目錄路徑
            intent: 文檔意圖標籤
            
        Returns:
            上傳結果統計
        """
        directory_path = Path(directory_path)
        
        if not directory_path.exists() or not directory_path.is_dir():
            raise ValueError(f"目錄不存在或不是有效目錄: {directory_path}")
        
        await self.initialize()
        
        logger.info(f"📂 開始上傳目錄: {directory_path}")
        
        results = {
            'total_files': 0,
            'successful_uploads': 0,
            'failed_uploads': 0,
            'skipped_files': 0,
            'processed_files': [],
            'failed_files': [],
            'start_time': datetime.now().isoformat()
        }
        
        # 遞迴處理目錄中的所有文件
        for file_path in directory_path.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in self.supported_extensions:
                results['total_files'] += 1
                
                try:
                    logger.info(f"📄 處理文件: {file_path.name}")
                    upload_result = await self.upload_file(str(file_path), intent)
                    
                    if upload_result['success']:
                        results['successful_uploads'] += 1
                        results['processed_files'].append({
                            'file': str(file_path),
                            'doc_id': upload_result['doc_id'],
                            'chunks': upload_result.get('chunks_created', 1)
                        })
                        logger.info(f"✅ 文件上傳成功: {file_path.name}")
                    else:
                        results['failed_uploads'] += 1
                        results['failed_files'].append({
                            'file': str(file_path),
                            'error': upload_result.get('error', 'Unknown error')
                        })
                        logger.error(f"❌ 文件上傳失敗: {file_path.name}")
                        
                except Exception as e:
                    results['failed_uploads'] += 1
                    results['failed_files'].append({
                        'file': str(file_path),
                        'error': str(e)
                    })
                    logger.error(f"❌ 處理文件時發生錯誤 {file_path.name}: {e}")
            else:
                if file_path.is_file():
                    results['skipped_files'] += 1
                    logger.debug(f"⏭️ 跳過不支援的文件: {file_path.name}")
        
        results['end_time'] = datetime.now().isoformat()
        
        logger.info(f"📊 目錄上傳完成統計:")
        logger.info(f"   總檔案數: {results['total_files']}")
        logger.info(f"   成功上傳: {results['successful_uploads']}")
        logger.info(f"   失敗上傳: {results['failed_uploads']}")
        logger.info(f"   跳過檔案: {results['skipped_files']}")
        
        return results
    
    async def upload_file(self, file_path: str, intent: str = "document") -> Dict[str, Any]:
        """
        上傳單個文檔
        
        Args:
            file_path: 文件路徑
            intent: 文檔意圖標籤
            
        Returns:
            上傳結果
        """
        file_path = Path(file_path)
        
        if not file_path.exists() or not file_path.is_file():
            return {
                'success': False,
                'error': f"文件不存在: {file_path}",
                'doc_id': None
            }
        
        if file_path.suffix.lower() not in self.supported_extensions:
            return {
                'success': False,
                'error': f"不支援的文件格式: {file_path.suffix}",
                'doc_id': None
            }
        
        await self.initialize()
        
        try:
            # 讀取文件內容
            content = await self._read_file_content(file_path)
            
            # 解析文檔
            parsed_content = await self._parse_document(content, file_path)
            
            # 生成文檔 ID
            doc_id = self._generate_document_id(file_path, content)
            
            # 處理長文檔分塊
            chunks = await self._split_document(parsed_content, file_path)
            
            # 為每個塊生成 embedding 並上傳
            uploaded_chunks = 0
            for i, chunk in enumerate(chunks):
                chunk_id = f"{doc_id}_chunk_{i}"
                
                # 生成 embedding
                embedding = await self.embedding_provider.embed(chunk['text'])
                
                # 準備元數據
                metadata = {
                    'source_file': str(file_path),
                    'file_name': file_path.name,
                    'file_size': file_path.stat().st_size,
                    'file_extension': file_path.suffix,
                    'chunk_index': i,
                    'total_chunks': len(chunks),
                    'chunk_size': len(chunk['text']),
                    'upload_time': datetime.now().isoformat(),
                    **chunk.get('metadata', {})
                }
                
                # 上傳到 Elasticsearch
                await self.elasticsearch_adapter.upsert_doc(
                    doc_id=chunk_id,
                    text=chunk['text'],
                    embedding=embedding,
                    intent=intent,
                    metadata=metadata
                )
                
                uploaded_chunks += 1
            
            logger.info(f"✅ 文檔上傳成功: {file_path.name} ({uploaded_chunks} 個分塊)")
            
            return {
                'success': True,
                'doc_id': doc_id,
                'chunks_created': uploaded_chunks,
                'file_size': file_path.stat().st_size,
                'content_length': len(parsed_content['text'])
            }
            
        except Exception as e:
            logger.error(f"❌ 上傳文檔失敗 {file_path.name}: {e}")
            return {
                'success': False,
                'error': str(e),
                'doc_id': None
            }
    
    async def _read_file_content(self, file_path: Path) -> str:
        """讀取文件內容"""
        try:
            # 嘗試不同的編碼
            encodings = ['utf-8', 'utf-8-sig', 'gbk', 'big5']
            
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    logger.debug(f"成功使用 {encoding} 編碼讀取文件: {file_path.name}")
                    return content
                except UnicodeDecodeError:
                    continue
            
            # 如果所有編碼都失敗，使用二進制模式並忽略錯誤
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            logger.warning(f"使用 utf-8 編碼並忽略錯誤讀取文件: {file_path.name}")
            return content
            
        except Exception as e:
            logger.error(f"讀取文件失敗 {file_path.name}: {e}")
            raise
    
    async def _parse_document(self, content: str, file_path: Path) -> Dict[str, Any]:
        """解析文檔內容"""
        file_extension = file_path.suffix.lower()
        
        if file_extension == '.md':
            return await self._parse_markdown(content)
        elif file_extension == '.txt':
            return await self._parse_text(content)
        elif file_extension == '.json':
            return await self._parse_json(content)
        else:
            # 預設當作純文本處理
            return await self._parse_text(content)
    
    async def _parse_markdown(self, content: str) -> Dict[str, Any]:
        """解析 Markdown 文檔"""
        # 簡單的 Markdown 解析
        lines = content.split('\n')
        sections = []
        current_section = []
        current_title = ""
        
        for line in lines:
            line = line.strip()
            if line.startswith('#'):
                # 新的標題
                if current_section:
                    sections.append({
                        'title': current_title,
                        'content': '\n'.join(current_section)
                    })
                    current_section = []
                current_title = line.lstrip('#').strip()
            else:
                if line:  # 忽略空行
                    current_section.append(line)
        
        # 添加最後一個段落
        if current_section:
            sections.append({
                'title': current_title,
                'content': '\n'.join(current_section)
            })
        
        return {
            'text': content,
            'sections': sections,
            'format': 'markdown'
        }
    
    async def _parse_text(self, content: str) -> Dict[str, Any]:
        """解析純文本"""
        return {
            'text': content,
            'format': 'text'
        }
    
    async def _parse_json(self, content: str) -> Dict[str, Any]:
        """解析 JSON 文檔"""
        import json
        try:
            data = json.loads(content)
            # 將 JSON 轉換為可搜尋的文本
            text_content = json.dumps(data, ensure_ascii=False, indent=2)
            return {
                'text': text_content,
                'json_data': data,
                'format': 'json'
            }
        except json.JSONDecodeError:
            # 如果 JSON 解析失敗，當作純文本處理
            return await self._parse_text(content)
    
    async def _split_document(self, parsed_content: Dict[str, Any], file_path: Path) -> List[Dict[str, Any]]:
        """將長文檔分割為適當大小的塊"""
        max_chunk_size = 1000  # 每塊最大字符數
        overlap_size = 100     # 重疊字符數
        
        text = parsed_content['text']
        
        if len(text) <= max_chunk_size:
            # 文檔足夠小，不需要分割
            return [{
                'text': text,
                'metadata': {
                    'chunk_method': 'no_split',
                    'original_length': len(text)
                }
            }]
        
        chunks = []
        
        # 如果是 Markdown 且有段落結構，按段落分割
        if parsed_content.get('format') == 'markdown' and parsed_content.get('sections'):
            current_chunk = ""
            current_metadata = {'sections': []}
            
            for section in parsed_content['sections']:
                section_text = f"# {section['title']}\n{section['content']}\n\n"
                
                if len(current_chunk + section_text) > max_chunk_size and current_chunk:
                    # 當前塊已滿，保存並開始新塊
                    chunks.append({
                        'text': current_chunk.strip(),
                        'metadata': {
                            'chunk_method': 'section_based',
                            **current_metadata
                        }
                    })
                    current_chunk = section_text
                    current_metadata = {'sections': [section['title']]}
                else:
                    current_chunk += section_text
                    current_metadata['sections'].append(section['title'])
            
            # 添加最後一個塊
            if current_chunk:
                chunks.append({
                    'text': current_chunk.strip(),
                    'metadata': {
                        'chunk_method': 'section_based',
                        **current_metadata
                    }
                })
        else:
            # 按字符數分割
            start = 0
            chunk_index = 0
            
            while start < len(text):
                end = min(start + max_chunk_size, len(text))
                
                # 如果不是最後一塊，嘗試在句號或換行處結束
                if end < len(text):
                    # 向前查找合適的分割點
                    for break_char in ['\n\n', '。', '\n', '.']:
                        break_pos = text.rfind(break_char, start, end)
                        if break_pos > start + max_chunk_size // 2:
                            end = break_pos + len(break_char)
                            break
                
                chunk_text = text[start:end].strip()
                if chunk_text:
                    chunks.append({
                        'text': chunk_text,
                        'metadata': {
                            'chunk_method': 'character_based',
                            'chunk_index': chunk_index,
                            'start_position': start,
                            'end_position': end
                        }
                    })
                    chunk_index += 1
                
                # 計算下一個塊的起始位置（考慮重疊）
                start = max(start + 1, end - overlap_size)
        
        logger.debug(f"文檔 {file_path.name} 分割為 {len(chunks)} 個塊")
        return chunks
    
    def _generate_document_id(self, file_path: Path, content: str) -> str:
        """生成文檔 ID"""
        # 使用文件路徑和內容哈希生成穩定的 ID
        path_hash = hashlib.md5(str(file_path).encode('utf-8')).hexdigest()[:8]
        content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()[:8]
        return f"doc_{path_hash}_{content_hash}"
    
    async def check_index_status(self) -> Dict[str, Any]:
        """檢查索引狀態"""
        await self.initialize()
        
        try:
            # 這裡可以添加檢查索引狀態的邏輯
            # 目前先返回基本資訊
            return {
                'index_name': self.index_name,
                'status': 'ready',
                'embedding_provider': str(type(self.embedding_provider).__name__),
                'supported_formats': list(self.supported_extensions)
            }
        except Exception as e:
            return {
                'index_name': self.index_name,
                'status': 'error',
                'error': str(e)
            }


# 便捷函數
async def upload_documents_from_directory(directory_path: str, intent: str = "document", index_name: Optional[str] = None) -> Dict[str, Any]:
    """
    便捷函數：上傳目錄中的所有文檔
    
    Args:
        directory_path: 目錄路徑
        intent: 文檔意圖標籤
        index_name: 目標索引名稱（可選）
        
    Returns:
        上傳結果統計
    """
    uploader = DocumentUploader(index_name=index_name)
    return await uploader.upload_directory(directory_path, intent)


async def upload_single_document(file_path: str, intent: str = "document", index_name: Optional[str] = None) -> Dict[str, Any]:
    """
    便捷函數：上傳單個文檔
    
    Args:
        file_path: 文件路徑
        intent: 文檔意圖標籤
        index_name: 目標索引名稱（可選）
        
    Returns:
        上傳結果
    """
    uploader = DocumentUploader(index_name=index_name)
    return await uploader.upload_file(file_path, intent)