"""
Semantic Kernel Chat Terminal with Azure OpenAI
支援 Web Search 功能的對話終端
"""
import asyncio
import os
import sys
from typing import Optional
import logging
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 添加專案路徑
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import lyrallm as sk
from lyrallm.connectors.ai.open_ai import AzureChatCompletion
from lyrallm.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from lyrallm.contents.chat_history import ChatHistory
from lyrallm.functions.kernel_arguments import KernelArguments
from lyrallm.kernel import Kernel
from lyrallm.connectors.ai import FunctionChoiceBehavior



# 設定 logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatTerminal:
    def __init__(self):
        self.kernel: Optional[Kernel] = None
        self.chat_history = ChatHistory()
        self.available_models = {
            "gpt-4o": os.getenv("AZURE_OPENAI_GPT4O_DEPLOYMENT_NAME", "gpt-4o"),
            "o3-mini": os.getenv("AZURE_OPENAI_O3MINI_DEPLOYMENT_NAME", "o3-mini")
        }
        self.current_model = "gpt-4o"  # 預設使用 GPT-4o
        
        self.system_message = """你是一個智能助理，可以幫助用戶回答各種問題。

請回答用戶的問題，盡力提供準確和有幫助的資訊。

請用繁體中文回答。"""

    def validate_environment(self):
        """驗證環境變數"""
        required_vars = {
            "AZURE_OPENAI_ENDPOINT": "Azure OpenAI Endpoint",
            "AZURE_OPENAI_API_KEY": "Azure OpenAI API Key", 
            "AZURE_OPENAI_API_VERSION": "Azure OpenAI API Version",
            "FIRECRAWL_API_KEY": "Firecrawl API Key"
        }
        
        missing_vars = []
        for var_name, display_name in required_vars.items():
            if not os.getenv(var_name):
                missing_vars.append(f"{display_name} ({var_name})")
        
        if missing_vars:
            print("❌ 缺少必要的環境變數:")
            for var in missing_vars:
                print(f"   - {var}")
            print("\n請在 .env 檔案中設定這些變數")
            return False
        
        return True

    async def initialize_kernel(self, model_name: str = "gpt-4o"):
        """初始化 Semantic Kernel with Azure OpenAI"""
        try:
            if not self.validate_environment():
                return False
            
            # 創建 kernel
            self.kernel = Kernel()
            self.current_model = model_name
            
            # 取得環境變數
            endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
            api_key = os.getenv("AZURE_OPENAI_API_KEY")
            api_version = os.getenv("AZURE_OPENAI_API_VERSION")
            deployment_name = self.available_models.get(model_name, model_name)
            
            print(f"🔧 使用模型: {model_name}")
            print(f"📍 Azure Endpoint: {endpoint}")
            print(f"🚀 Deployment: {deployment_name}")
            print(f"📅 API Version: {api_version}")
            
            # 添加 Azure OpenAI 聊天完成服務
            service_id = f"azure-{model_name}"
            azure_chat_completion = AzureChatCompletion(
                service_id=service_id,
                deployment_name=deployment_name,
                endpoint=endpoint,
                api_key=api_key,
                api_version=api_version
            )
            
            self.kernel.add_service(azure_chat_completion)
            
            # 設定系統訊息
            self.chat_history.clear()
            self.chat_history.add_system_message(self.system_message)
            
            print("✅ Semantic Kernel 初始化成功!")
            print(f"📦 Semantic Kernel 版本: {sk.__version__}")
            return True
            
        except Exception as e:
            print(f"❌ 初始化失敗: {e}")
            logger.error(f"Initialization error: {e}", exc_info=True)
            return False

    async def switch_model(self, model_name: str):
        """切換模型"""
        if model_name not in self.available_models:
            print(f"❌ 不支援的模型: {model_name}")
            print(f"🎯 可用模型: {', '.join(self.available_models.keys())}")
            return False
        
        print(f"🔄 正在切換到模型: {model_name}")
        success = await self.initialize_kernel(model_name)
        if success:
            print(f"✅ 已切換到模型: {model_name}")
        return success

    async def chat_loop(self):
        """主要聊天循環"""
        if not await self.initialize_kernel():
            return
            
        print("\n" + "="*70)
        print("🤖 Semantic Kernel Chat Terminal with Azure OpenAI & Web Search")
        print("="*70)
        print("🔧 指令:")
        print("  quit/exit/q - 退出程式")
        print("  clear - 清除對話歷史")
        print("  help - 查看幫助")
        print("  model <模型名> - 切換模型 (gpt-4o, o3-mini)")
        print("  status - 查看當前狀態")
        print("-"*70)
        
        while True:
            try:
                # 獲取用戶輸入
                user_input = input(f"\n🧑 您 [{self.current_model}]: ").strip()
                
                # 處理特殊命令
                if user_input.lower() in ['quit', 'exit', 'q']:
                    print("👋 再見!")
                    break
                elif user_input.lower() == 'clear':
                    self.chat_history.clear()
                    self.chat_history.add_system_message(self.system_message)
                    print("🧹 對話歷史已清除")
                    continue
                elif user_input.lower() == 'help':
                    self.show_help()
                    continue
                elif user_input.lower() == 'status':
                    self.show_status()
                    continue
                elif user_input.lower().startswith('model '):
                    model_name = user_input[6:].strip()
                    await self.switch_model(model_name)
                    continue
                elif not user_input:
                    continue
                
                # 添加用戶訊息到歷史
                self.chat_history.add_user_message(user_input)
                
                print(f"\n🤖 助理 [{self.current_model}]: ", end="", flush=True)
                
                # 使用 Semantic Kernel 處理對話
                chat_completion: ChatCompletionClientBase = self.kernel.get_service(
                    type=ChatCompletionClientBase
                )
                
                # 建立執行設定
                execution_settings = self.kernel.get_prompt_execution_settings_from_service_id(
                    service_id=chat_completion.service_id
                )
                
                # 設定參數
                execution_settings.temperature = 0.7
                execution_settings.max_tokens = 2000
                execution_settings.top_p = 1.0
                
                # 啟用函數呼叫 (工具使用)
                try:
                    execution_settings.function_choice_behavior = FunctionChoiceBehavior.Auto()
                    logger.info("✅ Function choice behavior enabled")
                except Exception as e:
                    logger.warning(f"⚠️ Cannot set function_choice_behavior: {e}")
                    # 嘗試其他可能的屬性名稱
                    for attr_name in ['function_call', 'tool_choice', 'functions']:
                        if hasattr(execution_settings, attr_name):
                            try:
                                setattr(execution_settings, attr_name, "auto")
                                logger.info(f"✅ Set {attr_name} to auto")
                                break
                            except Exception as inner_e:
                                logger.warning(f"⚠️ Cannot set {attr_name}: {inner_e}")
                
                # 獲取回應
                start_time = asyncio.get_event_loop().time()
                response = await chat_completion.get_chat_message_contents(
                    chat_history=self.chat_history,
                    settings=execution_settings,
                    kernel=self.kernel
                )
                end_time = asyncio.get_event_loop().time()
                
                if response:
                    assistant_message = str(response[0].content)
                    print(assistant_message)
                    
                    # 顯示處理時間
                    processing_time = end_time - start_time
                    print(f"\n⏱️ 處理時間: {processing_time:.2f} 秒")
                    
                    # 添加助理回應到歷史
                    self.chat_history.add_assistant_message(assistant_message)
                else:
                    print("抱歉，我無法處理您的請求。")
                    
            except KeyboardInterrupt:
                print("\n\n👋 再見!")
                break
            except Exception as e:
                print(f"\n❌ 錯誤: {e}")
                logger.error(f"Chat error: {e}", exc_info=True)

    def show_help(self):
        """顯示幫助資訊"""
        print("\n" + "="*50)
        print("📖 幫助資訊")
        print("="*50)
        
        print("\n🎮 指令:")
        print("  quit/exit/q - 退出程式")
        print("  clear - 清除對話歷史")
        print("  help - 顯示此幫助")
        print("  model <名稱> - 切換模型")
        print("  status - 查看當前狀態")
        
        print(f"\n🤖 可用模型:")
        for model_key, deployment_name in self.available_models.items():
            current = " (目前)" if model_key == self.current_model else ""
            print(f"  {model_key} - {deployment_name}{current}")
        
        print("\n🔍 Web Search 功能:")
        print("  自動觸發: 詢問新聞、價格、天氣等即時資訊")
        print("  範例: '今天有什麼重要新聞?'")
        print("       'OpenAI 最新模型有什麼功能?'")
        print("       '比特幣目前價格是多少?'")
        print("       '台灣今天天氣如何?'")
        
        print("\n🛠️ 可用工具:")
        print("  web_search - 搜尋網路資訊")
        print("  web_extract - 抽取網頁詳細內容")
        
        print("\n💡 提示:")
        print("  如果自動工具呼叫不工作，可以手動要求:")
        print("  '請使用 web_search 搜尋最新的...'")
        print("  '請使用 web_extract 抽取這個網頁的內容: <URL>'")
        print("-"*50)

    def show_status(self):
        """顯示當前狀態"""
        print("\n" + "="*40)
        print("📊 系統狀態")
        print("="*40)
        print(f"🤖 當前模型: {self.current_model}")
        print(f"🚀 部署名稱: {self.available_models[self.current_model]}")
        print(f"💬 對話輪數: {len([msg for msg in self.chat_history.messages if msg.role == 'user'])}")
        print(f"📦 SK 版本: {sk.__version__}")
        
        # 檢查 plugins
        if self.kernel and self.kernel.plugins:
            print(f"🔌 已載入插件: {', '.join(self.kernel.plugins.keys())}")
        else:
            print("🔌 已載入插件: 無")
        
        # 檢查環境變數狀態
        env_status = []
        required_vars = ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", 
                        "AZURE_OPENAI_API_VERSION", "FIRECRAWL_API_KEY"]
        
        for var in required_vars:
            if os.getenv(var):
                env_status.append(f"✅ {var}")
            else:
                env_status.append(f"❌ {var}")
        
        print("\n🔐 環境變數:")
        for status in env_status:
            print(f"  {status}")
        
        print("-"*40)

async def main():
    """主函數"""
    terminal = ChatTerminal()
    await terminal.chat_loop()

if __name__ == "__main__":
    # 顯示歡迎資訊
    print("🚀 啟動 Semantic Kernel Chat Terminal with Azure OpenAI")
    print("=" * 60)
    
    # 顯示版本資訊
    print(f"🐍 Python: {sys.version}")
    try:
        print(f"📦 Semantic Kernel: {sk.__version__}")
    except:
        print("📦 Semantic Kernel: 版本未知")
    
    print("\n🔧 Azure OpenAI 配置:")
    print(f"📍 Endpoint: {os.getenv('AZURE_OPENAI_ENDPOINT', '未設定')}")
    print(f"📅 API Version: {os.getenv('AZURE_OPENAI_API_VERSION', '未設定')}")
    print(f"🎯 GPT-4o Deployment: {os.getenv('AZURE_OPENAI_GPT4O_DEPLOYMENT_NAME', '未設定')}")
    print(f"🎯 O3-Mini Deployment: {os.getenv('AZURE_OPENAI_O3MINI_DEPLOYMENT_NAME', '未設定')}")
    
    print("\n🛠️ 配置狀態:")
    print("💬 基本聊天功能: 已啟用")
    
    print("=" * 60)
    
    # 啟動聊天終端
    asyncio.run(main())