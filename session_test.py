"""使用 Session 復用連接的測試"""
import time
import requests

def test_with_session():
    """使用 Session 測試"""
    # 創建 session 以復用連接
    session = requests.Session()
    
    print("測試 LyraLLM (使用 Session)...")
    
    results = []
    for i in range(5):
        start = time.perf_counter()
        
        resp = session.post(
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
        
        end = time.perf_counter()
        latency = (end - start) * 1000
        
        results.append(latency)
        print(f"  請求 {i+1}: {latency:.1f}ms (status: {resp.status_code})")
        
        time.sleep(0.3)
    
    session.close()
    
    avg = sum(results) / len(results)
    print(f"\n平均延遲: {avg:.1f}ms")
    print(f"範圍: {min(results):.1f} - {max(results):.1f}ms")
    return results


def test_without_session():
    """不使用 Session 測試"""
    print("\n測試 LyraLLM (不使用 Session)...")
    
    results = []
    for i in range(5):
        start = time.perf_counter()
        
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
        
        end = time.perf_counter()
        latency = (end - start) * 1000
        
        results.append(latency)
        print(f"  請求 {i+1}: {latency:.1f}ms (status: {resp.status_code})")
        
        time.sleep(0.3)
    
    avg = sum(results) / len(results)
    print(f"\n平均延遲: {avg:.1f}ms")
    print(f"範圍: {min(results):.1f} - {max(results):.1f}ms")
    return results


if __name__ == "__main__":
    print("=" * 60)
    print("Session vs 非 Session 對比測試")
    print("=" * 60)
    
    # 測試 with session
    with_session = test_with_session()
    
    time.sleep(1)
    
    # 測試 without session
    without_session = test_without_session()
    
    # 對比
    print("\n" + "=" * 60)
    print("對比結果")
    print("=" * 60)
    
    avg_with = sum(with_session) / len(with_session)
    avg_without = sum(without_session) / len(without_session)
    
    print(f"使用 Session: {avg_with:.1f}ms")
    print(f"不使用 Session: {avg_without:.1f}ms")
    print(f"差異: {avg_without - avg_with:.1f}ms ({((avg_without - avg_with)/avg_without)*100:.1f}%)")
