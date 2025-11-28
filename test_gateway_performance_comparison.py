"""
Gateway 性能對比測試：Portkey vs LyraLLM vs 直接調用
比較三種不同 Gateway 方案的延遲差異
測試目標模型：gpt-oss:20b (Ollama)
"""

import time
import statistics
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

# Portkey 支援
try:
    from portkey_ai import Portkey
    PORTKEY_AVAILABLE = True
except ImportError:
    PORTKEY_AVAILABLE = False
    print("⚠️  portkey_ai 未安裝，Portkey 測試將跳過")

# HTTP 請求支援
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("⚠️  requests 未安裝，直接調用測試將跳過")


class GatewayComparisonTest:
    """三方 Gateway 對比測試類"""
    
    def __init__(self):
        self.portkey_results: List[Dict[str, Any]] = []
        self.lyrallm_results: List[Dict[str, Any]] = []
        self.direct_results: List[Dict[str, Any]] = []
        
        # 配置
        self.portkey_config = {
            "provider": "ollama",
            "base_url": "http://localhost:8787/v1",
            "custom_host": "http://localhost:11434"
        }
        
        self.lyrallm_config = {
            "base_url": "http://localhost:8081/api/chat/completions",
            "timeout": 60
        }
        
        self.ollama_config = {
            "base_url": "http://localhost:11434/api/chat",
            "timeout": 60
        }
        
        self.model = "gpt-oss:20b"
    
    def test_portkey_gateway(self, prompt: str = "你好", num_tests: int = 5) -> List[Dict[str, Any]]:
        """通過 Portkey Gateway 測試"""
        if not PORTKEY_AVAILABLE:
            print("❌ 跳過 Portkey 測試（未安裝 portkey_ai）")
            return []
        
        print(f"\n🔵 測試 Portkey Gateway ({num_tests} 次)...")
        
        try:
            client = Portkey(
                provider=self.portkey_config["provider"],
                base_url=self.portkey_config["base_url"],
                custom_host=self.portkey_config["custom_host"]
            )
        except Exception as e:
            print(f"❌ Portkey 客戶端初始化失敗: {e}")
            return []
        
        results = []
        for i in range(num_tests):
            start = time.time()
            try:
                response = client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "你是一位LyraLLM系統的助手，請用繁體中文回答所有問題。"},
                        {"role": "user", "content": prompt}
                    ],
                    model=self.model
                )
                end = time.time()
                latency = end - start
                
                results.append({
                    "success": True,
                    "latency": latency,
                    "method": "portkey",
                    "timestamp": datetime.now().isoformat(),
                    "model": self.model
                })
                print(f"  請求 {i+1}: {latency:.3f}s ✓")
                
            except Exception as e:
                end = time.time()
                results.append({
                    "success": False,
                    "latency": end - start,
                    "error": str(e),
                    "method": "portkey",
                    "model": self.model
                })
                print(f"  請求 {i+1}: 失敗 ✗ ({str(e)[:50]})")
            
            time.sleep(0.5)
        
        self.portkey_results = results
        return results
    
    def test_lyrallm_gateway(self, prompt: str = "你好", num_tests: int = 5) -> List[Dict[str, Any]]:
        """通過 LyraLLM Gateway 測試"""
        if not REQUESTS_AVAILABLE:
            print("❌ 跳過 LyraLLM 測試（未安裝 requests）")
            return []
        
        print(f"\n🟣 測試 LyraLLM Gateway ({num_tests} 次)...")
        
        url = self.lyrallm_config["base_url"]
        timeout = self.lyrallm_config["timeout"]
        
        # 使用 Session 復用 HTTP 連接以獲得準確的性能測量
        session = requests.Session()
        
        results = []
        for i in range(num_tests):
            start = time.time()
            try:
                # LyraLLM 使用 OpenAI 兼容格式
                # 明確禁用所有 features 以避免觸發 Agent 模式，確保公平比較
                response = session.post(
                    url,
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": "你是一位LyraLLM系統的助手，請用繁體中文回答所有問題。"},
                            {"role": "user", "content": prompt}
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
                    headers={"Content-Type": "application/json"},
                    timeout=timeout
                )
                end = time.time()
                latency = end - start
                
                if response.status_code == 200:
                    results.append({
                        "success": True,
                        "latency": latency,
                        "method": "lyrallm",
                        "timestamp": datetime.now().isoformat(),
                        "model": self.model,
                        "status_code": response.status_code
                    })
                    print(f"  請求 {i+1}: {latency:.3f}s ✓")
                else:
                    results.append({
                        "success": False,
                        "latency": latency,
                        "error": f"HTTP {response.status_code}: {response.text[:100]}",
                        "method": "lyrallm",
                        "model": self.model,
                        "status_code": response.status_code
                    })
                    print(f"  請求 {i+1}: HTTP {response.status_code} ✗")
                    
            except requests.exceptions.Timeout:
                end = time.time()
                results.append({
                    "success": False,
                    "latency": end - start,
                    "error": "請求超時",
                    "method": "lyrallm",
                    "model": self.model
                })
                print(f"  請求 {i+1}: 超時 ✗")
                
            except Exception as e:
                end = time.time()
                results.append({
                    "success": False,
                    "latency": end - start,
                    "error": str(e),
                    "method": "lyrallm",
                    "model": self.model
                })
                print(f"  請求 {i+1}: 失敗 ✗ ({str(e)[:50]})")
            
            time.sleep(0.5)
        
        session.close()
        self.lyrallm_results = results
        return results
    
    def test_direct_ollama(self, prompt: str = "你好", num_tests: int = 5) -> List[Dict[str, Any]]:
        """直接調用 Ollama API 測試"""
        if not REQUESTS_AVAILABLE:
            print("❌ 跳過直接調用測試（未安裝 requests）")
            return []
        
        print(f"\n🟢 測試直接調用 Ollama ({num_tests} 次)...")
        
        url = self.ollama_config["base_url"]
        timeout = self.ollama_config["timeout"]
        
        # 使用 Session 復用 HTTP 連接
        session = requests.Session()
        
        results = []
        for i in range(num_tests):
            start = time.time()
            try:
                response = session.post(
                    url,
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": "你是一位LyraLLM系統的助手，請用繁體中文回答所有問題。"},
                            {"role": "user", "content": prompt}
                        ],
                        "stream": False
                    },
                    timeout=timeout
                )
                end = time.time()
                latency = end - start
                
                if response.status_code == 200:
                    results.append({
                        "success": True,
                        "latency": latency,
                        "method": "direct",
                        "timestamp": datetime.now().isoformat(),
                        "model": self.model
                    })
                    print(f"  請求 {i+1}: {latency:.3f}s ✓")
                else:
                    results.append({
                        "success": False,
                        "latency": latency,
                        "error": f"HTTP {response.status_code}",
                        "method": "direct",
                        "model": self.model
                    })
                    print(f"  請求 {i+1}: HTTP {response.status_code} ✗")
                    
            except Exception as e:
                end = time.time()
                results.append({
                    "success": False,
                    "latency": end - start,
                    "error": str(e),
                    "method": "direct",
                    "model": self.model
                })
                print(f"  請求 {i+1}: 失敗 ✗ ({str(e)[:50]})")
            
            time.sleep(0.5)
        
        session.close()
        self.direct_results = results
        return results
    
    def _calculate_stats(self, results: List[Dict[str, Any]], method_name: str) -> Optional[Dict[str, Any]]:
        """計算統計數據"""
        success_results = [r for r in results if r.get("success")]
        
        if not success_results:
            return None
        
        latencies = [r["latency"] for r in success_results]
        
        stats = {
            "method": method_name,
            "total_tests": len(results),
            "success_count": len(success_results),
            "success_rate": len(success_results) / len(results) * 100,
            "avg_latency": statistics.mean(latencies),
            "min_latency": min(latencies),
            "max_latency": max(latencies),
            "median_latency": statistics.median(latencies)
        }
        
        if len(latencies) > 1:
            stats["stdev"] = statistics.stdev(latencies)
        else:
            stats["stdev"] = 0.0
        
        return stats
    
    def compare_results(self):
        """對比分析結果"""
        print("\n" + "="*80)
        print("📊 Gateway 性能對比分析")
        print("="*80)
        
        all_stats = []
        
        # Portkey 結果
        if self.portkey_results:
            portkey_stats = self._calculate_stats(self.portkey_results, "Portkey Gateway")
            if portkey_stats:
                all_stats.append(portkey_stats)
                print("\n🔵 Portkey Gateway:")
                print(f"  成功率: {portkey_stats['success_count']}/{portkey_stats['total_tests']} ({portkey_stats['success_rate']:.1f}%)")
                print(f"  平均延遲: {portkey_stats['avg_latency']:.3f}s")
                print(f"  最小延遲: {portkey_stats['min_latency']:.3f}s")
                print(f"  最大延遲: {portkey_stats['max_latency']:.3f}s")
                print(f"  中位數延遲: {portkey_stats['median_latency']:.3f}s")
                if portkey_stats['stdev'] > 0:
                    print(f"  標準差: {portkey_stats['stdev']:.3f}s")
        
        # LyraLLM 結果
        if self.lyrallm_results:
            lyrallm_stats = self._calculate_stats(self.lyrallm_results, "LyraLLM Gateway")
            if lyrallm_stats:
                all_stats.append(lyrallm_stats)
                print("\n🟣 LyraLLM Gateway:")
                print(f"  成功率: {lyrallm_stats['success_count']}/{lyrallm_stats['total_tests']} ({lyrallm_stats['success_rate']:.1f}%)")
                print(f"  平均延遲: {lyrallm_stats['avg_latency']:.3f}s")
                print(f"  最小延遲: {lyrallm_stats['min_latency']:.3f}s")
                print(f"  最大延遲: {lyrallm_stats['max_latency']:.3f}s")
                print(f"  中位數延遲: {lyrallm_stats['median_latency']:.3f}s")
                if lyrallm_stats['stdev'] > 0:
                    print(f"  標準差: {lyrallm_stats['stdev']:.3f}s")
        
        # 直接調用結果
        if self.direct_results:
            direct_stats = self._calculate_stats(self.direct_results, "直接調用 Ollama")
            if direct_stats:
                all_stats.append(direct_stats)
                print("\n🟢 直接調用 Ollama:")
                print(f"  成功率: {direct_stats['success_count']}/{direct_stats['total_tests']} ({direct_stats['success_rate']:.1f}%)")
                print(f"  平均延遲: {direct_stats['avg_latency']:.3f}s")
                print(f"  最小延遲: {direct_stats['min_latency']:.3f}s")
                print(f"  最大延遲: {direct_stats['max_latency']:.3f}s")
                print(f"  中位數延遲: {direct_stats['median_latency']:.3f}s")
                if direct_stats['stdev'] > 0:
                    print(f"  標準差: {direct_stats['stdev']:.3f}s")
        
        # Gateway 開銷對比分析
        if len(all_stats) >= 2:
            print("\n" + "="*80)
            print("⚡ Gateway 開銷對比分析")
            print("="*80)
            
            # 找出直接調用作為基準
            direct_baseline = next((s for s in all_stats if s["method"] == "直接調用 Ollama"), None)
            
            if direct_baseline:
                baseline_latency = direct_baseline["avg_latency"]
                
                for stats in all_stats:
                    if stats["method"] == "直接調用 Ollama":
                        continue
                    
                    overhead = stats["avg_latency"] - baseline_latency
                    overhead_percent = (overhead / baseline_latency) * 100
                    
                    print(f"\n📊 {stats['method']} vs 直接調用:")
                    print(f"  平均額外延遲: {overhead:.3f}s")
                    print(f"  開銷百分比: {overhead_percent:.1f}%")
                    
                    if overhead_percent < 5:
                        print("  ✅ 開銷很小，Gateway 性能優秀")
                    elif overhead_percent < 15:
                        print("  ⚠️  開銷適中，可接受範圍")
                    else:
                        print("  ⚠️  開銷較大，可能需要優化")
            
            # 排名
            print("\n🏆 性能排名（按平均延遲）:")
            sorted_stats = sorted(all_stats, key=lambda x: x["avg_latency"])
            for idx, stats in enumerate(sorted_stats, 1):
                print(f"  {idx}. {stats['method']}: {stats['avg_latency']:.3f}s")
    
    def save_comparison(self, filename: str = "gateway_comparison_results.json"):
        """保存對比結果"""
        data = {
            "test_info": {
                "test_time": datetime.now().isoformat(),
                "model": self.model,
                "configurations": {
                    "portkey": self.portkey_config,
                    "lyrallm": self.lyrallm_config,
                    "ollama": self.ollama_config
                }
            },
            "results": {
                "portkey": self.portkey_results,
                "lyrallm": self.lyrallm_results,
                "direct": self.direct_results
            }
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 對比結果已保存到: {filename}")


def main():
    """主函數"""
    print("🎯 Gateway 性能對比測試：Portkey vs LyraLLM vs 直接調用")
    print("="*80)
    
    tester = GatewayComparisonTest()
    
    # 測試配置
    num_tests = 5
    prompt = "你好，請簡短回答"
    
    print(f"\n⚙️  測試配置:")
    print(f"  測試次數: {num_tests}")
    print(f"  測試提示: {prompt}")
    print(f"  模型: {tester.model}")
    print(f"  Portkey Gateway: {tester.portkey_config['base_url']}")
    print(f"  LyraLLM Gateway: {tester.lyrallm_config['base_url']}")
    print(f"  Ollama 直接調用: {tester.ollama_config['base_url']}")
    
    # 執行測試
    input("\n按 Enter 開始測試...")
    
    tester.test_portkey_gateway(prompt, num_tests)
    tester.test_lyrallm_gateway(prompt, num_tests)
    tester.test_direct_ollama(prompt, num_tests)
    
    # 對比結果
    tester.compare_results()
    
    # 保存結果
    tester.save_comparison()
    
    print("\n✅ 測試完成!")
    print("\n💡 提示:")
    print("  - 如果 LyraLLM 測試失敗，請確認後端服務正在運行（python main.py）")
    print("  - 如果 Portkey 測試失敗，請確認 Portkey Gateway 正在運行")
    print("  - 如果直接調用失敗，請確認 Ollama 服務正在運行")


if __name__ == "__main__":
    main()
