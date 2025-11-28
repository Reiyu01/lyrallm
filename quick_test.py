"""快速性能測試 - 單次請求對比"""
import time
import requests

def test_lyrallm():
    """測試 LyraLLM"""
    print("測試 LyraLLM...")
    start = time.time()
    
    resp = requests.post(
        "http://localhost:8081/api/chat/completions",
        json={
            "model": "gpt-oss:20b",
            "messages": [
                {"role": "system", "content": "你是一位LyraLLM系統的助手，請用繁體中文回答所有問題。"},
                {"role": "user", "content": "你好，請簡短回答"}
            ],
            "stream": False,
            "temperature": 0.7,
            "features": {
                "web_search": False,
                "rag_search": False,
                "image_generation": False,
                "code_interpreter": False
            }
        },
        timeout=60
    )
    
    end = time.time()
    print(f"LyraLLM 延遲: {(end - start)*1000:.1f}ms")
    print(f"HTTP 狀態: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"響應內容: {data.get('choices', [{}])[0].get('message', {}).get('content', '')[:50]}")
    return end - start


def test_ollama():
    """測試直接調用 Ollama"""
    print("\n測試直接調用 Ollama...")
    start = time.time()
    
    resp = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": "gpt-oss:20b",
            "messages": [
                {"role": "system", "content": "你是一位LyraLLM系統的助手，請用繁體中文回答所有問題。"},
                {"role": "user", "content": "你好，請簡短回答"}
            ],
            "stream": False
        },
        timeout=60
    )
    
    end = time.time()
    print(f"Ollama 延遲: {(end - start)*1000:.1f}ms")
    print(f"HTTP 狀態: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"響應內容: {data.get('message', {}).get('content', '')[:50]}")
    return end - start


if __name__ == "__main__":
    print("=" * 60)
    print("快速性能對比測試")
    print("=" * 60)
    
    # 預熱（建立連接池和 kernel 緩存）
    print("\n🔥 預熱階段...")
    try:
        test_lyrallm()
        test_ollama()
    except Exception as e:
        print(f"預熱失敗: {e}")
    
    time.sleep(1)
    
    # 正式測試
    print("\n" + "=" * 60)
    print("📊 正式測試（已預熱）")
    print("=" * 60)
    
    lyrallm_times = []
    ollama_times = []
    
    for i in range(3):
        print(f"\n--- 第 {i+1} 輪 ---")
        try:
            t1 = test_lyrallm()
            lyrallm_times.append(t1)
        except Exception as e:
            print(f"LyraLLM 失敗: {e}")
        
        time.sleep(0.5)
        
        try:
            t2 = test_ollama()
            ollama_times.append(t2)
        except Exception as e:
            print(f"Ollama 失敗: {e}")
        
        time.sleep(0.5)
    
    # 統計
    print("\n" + "=" * 60)
    print("📈 統計結果")
    print("=" * 60)
    
    if lyrallm_times:
        avg_lyrallm = sum(lyrallm_times) / len(lyrallm_times)
        print(f"LyraLLM 平均: {avg_lyrallm*1000:.1f}ms (範圍: {min(lyrallm_times)*1000:.1f}-{max(lyrallm_times)*1000:.1f}ms)")
    
    if ollama_times:
        avg_ollama = sum(ollama_times) / len(ollama_times)
        print(f"Ollama 平均: {avg_ollama*1000:.1f}ms (範圍: {min(ollama_times)*1000:.1f}-{max(ollama_times)*1000:.1f}ms)")
    
    if lyrallm_times and ollama_times:
        overhead = avg_lyrallm - avg_ollama
        overhead_pct = (overhead / avg_ollama) * 100
        print(f"\n額外開銷: {overhead*1000:.1f}ms ({overhead_pct:.1f}%)")
