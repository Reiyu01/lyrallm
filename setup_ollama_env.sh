#!/bin/bash

# Ollama Web Search Plugin 環境變數設定腳本
# 使用方式: source setup_ollama_env.sh

echo "=== Ollama Web Search Plugin 環境設定 ==="

# 檢查是否已有 .env 檔案
if [ -f ".env" ]; then
    echo "✅ 發現 .env 檔案，載入環境變數..."
    export $(grep -v '^#' .env | xargs)
    echo "已載入 .env 檔案中的環境變數"
else
    echo "⚠️  未找到 .env 檔案"
    echo "請先複製 .env.example 為 .env 並設定您的配置"
    echo "執行: cp .env.example .env"
fi

# 檢查必要的環境變數
echo ""
echo "=== 環境變數檢查 ==="

check_env() {
    local var_name=$1
    local var_value=$(eval echo \$$var_name)
    
    if [ -n "$var_value" ]; then
        if [ "$var_name" = "OLLAMA_API_KEY" ]; then
            echo "✅ $var_name: ***已設定***"
        else
            echo "✅ $var_name: $var_value"
        fi
    else
        echo "❌ $var_name: 未設定"
    fi
}

# 檢查主要配置
check_env "OLLAMA_API_KEY"
check_env "OLLAMA_WEB_SEARCH_BASE_URL"
check_env "OLLAMA_WEB_SEARCH_TIMEOUT"
check_env "OLLAMA_WEB_SEARCH_MAX_RESULTS"
check_env "OLLAMA_WEB_SEARCH_ENABLED"
check_env "OLLAMA_BASE_URL"

echo ""

# 檢查配置完整性
if [ -n "$OLLAMA_API_KEY" ]; then
    echo "✅ Ollama Web Search 配置完整，可以開始使用"
    echo ""
    echo "測試指令:"
    echo "  python test_ollama_plugin.py"
else
    echo "❌ OLLAMA_API_KEY 未設定，請先配置"
    echo ""
    echo "設定方式:"
    echo "1. 編輯 .env 檔案"
    echo "2. 或者執行: export OLLAMA_API_KEY='your_api_key_here'"
fi

echo ""
echo "=== 設定完成 ==="