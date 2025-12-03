"""
Gateway 全面性能基準測試：Portkey vs LyraLLM vs 直接調用 Ollama
測試指標：吞吐量、延遲分布、成功率、並發性能、長文本處理、首 Token 延遲

使用方式：
  python benchmark_gateway_full.py --tests all          # 執行所有測試
  python benchmark_gateway_full.py --tests latency      # 只測延遲
  python benchmark_gateway_full.py --tests throughput   # 只測吞吐量
  python benchmark_gateway_full.py --tests concurrent   # 只測並發
"""

import time
import statistics
import json
import argparse
import asyncio
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

# HTTP 請求支援
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("⚠️  requests 未安裝")

# 異步 HTTP 支援
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    print("⚠️  aiohttp 未安裝，並發測試將使用 threading")

# Portkey 支援
try:
    from portkey_ai import Portkey
    PORTKEY_AVAILABLE = True
except ImportError:
    PORTKEY_AVAILABLE = False
    print("⚠️  portkey_ai 未安裝，Portkey 測試將跳過")


@dataclass
class RequestResult:
    """單次請求結果"""
    success: bool
    latency_ms: float  # 總延遲 (毫秒)
    ttft_ms: Optional[float] = None  # Time To First Token (毫秒)
    tokens_generated: int = 0
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class BenchmarkStats:
    """統計結果"""
    method: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    success_rate: float  # 百分比
    
    # 延遲統計 (毫秒)
    avg_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    median_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    stdev_latency_ms: float
    
    # 吞吐量
    total_time_s: float
    requests_per_second: float  # RPS
    tokens_per_second: float  # TPS (如果有 token 計數)
    
    # TTFT 統計 (如果有)
    avg_ttft_ms: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class GatewayBenchmark:
    """全面性能基準測試"""
    
    def __init__(self, model: str = "gpt-oss:20b"):
        self.model = model
        
        # 配置
        self.config = {
            "portkey": {
                "provider": "ollama",
                "base_url": "http://localhost:8787/v1",
                "custom_host": "http://localhost:11434"
            },
            "lyrallm": {
                "base_url": "http://localhost:8081/api/chat/completions",
                "timeout": 120
            },
            "ollama": {
                "base_url": "http://localhost:11434/api/chat",
                "timeout": 120
            }
        }
        
        # 測試提示詞
        self.prompts = {
            "short": "你好",
            "medium": "請用100字左右介紹台灣的歷史。",
            "long": "請詳細介紹人工智慧的發展歷程，包括：1) 早期符號主義 AI；2) 專家系統時代；3) 機器學習崛起；4) 深度學習革命；5) 大型語言模型時代。每個階段請說明主要技術突破、代表性成果和關鍵人物。"
        }
        
        # 結果存儲
        self.results: Dict[str, List[RequestResult]] = {
            "portkey": [],
            "lyrallm": [],
            "ollama": []
        }
    
    # ========== 單次請求方法 ==========
    
    def _request_portkey(self, prompt: str, stream: bool = False) -> RequestResult:
        """Portkey Gateway 請求"""
        if not PORTKEY_AVAILABLE:
            return RequestResult(success=False, latency_ms=0, error="portkey_ai 未安裝")
        
        start = time.perf_counter()
        ttft = None
        tokens = 0
        
        try:
            client = Portkey(
                provider=self.config["portkey"]["provider"],
                base_url=self.config["portkey"]["base_url"],
                custom_host=self.config["portkey"]["custom_host"]
            )
            
            if stream:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    stream=True
                )
                first_chunk = True
                for chunk in response:
                    if first_chunk:
                        ttft = (time.perf_counter() - start) * 1000
                        first_chunk = False
                    if chunk.choices and chunk.choices[0].delta.content:
                        tokens += 1  # 簡化計數
            else:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    stream=False
                )
                if hasattr(response, 'usage') and response.usage:
                    tokens = response.usage.completion_tokens or 0
            
            latency = (time.perf_counter() - start) * 1000
            return RequestResult(success=True, latency_ms=latency, ttft_ms=ttft, tokens_generated=tokens)
            
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return RequestResult(success=False, latency_ms=latency, error=str(e)[:100])
    
    def _request_lyrallm(self, prompt: str, stream: bool = False, session: Optional[requests.Session] = None) -> RequestResult:
        """LyraLLM Gateway 請求"""
        start = time.perf_counter()
        ttft = None
        tokens = 0
        
        url = self.config["lyrallm"]["base_url"]
        timeout = self.config["lyrallm"]["timeout"]
        
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
            "temperature": 0.7,
            "features": {
                "web_search": False,
                "rag_search": False,
                "image_generation": False,
                "code_interpreter": False
            }
        }
        
        try:
            requester = session if session else requests
            
            if stream:
                response = requester.post(url, json=payload, timeout=timeout, stream=True)
                if response.status_code == 200:
                    first_content_chunk = True
                    for line in response.iter_lines():
                        if line:
                            # 解析 SSE 格式，只有包含 choices[].delta.content 的才計入 TTFT
                            try:
                                line_str = line.decode('utf-8') if isinstance(line, bytes) else line
                                if line_str.startswith('data: '):
                                    json_str = line_str[6:].strip()
                                    if json_str == '[DONE]':
                                        continue
                                    data = json.loads(json_str)
                                    
                                    # LyraLLM 格式：檢查 choices[].delta.content 是否存在
                                    has_content = False
                                    if 'choices' in data and isinstance(data['choices'], list):
                                        for choice in data['choices']:
                                            if isinstance(choice, dict) and 'delta' in choice:
                                                delta = choice['delta']
                                                if isinstance(delta, dict) and 'content' in delta and delta['content']:
                                                    has_content = True
                                                    break
                                    
                                    # 只有實際內容才計入 TTFT
                                    if has_content and first_content_chunk:
                                        ttft = (time.perf_counter() - start) * 1000
                                        first_content_chunk = False
                                    
                                    # 計算 token 數（有內容或是 final）
                                    if has_content or 'usage' in data:
                                        tokens += 1
                            except (json.JSONDecodeError, UnicodeDecodeError):
                                # 非 JSON 格式，按舊邏輯處理
                                if first_content_chunk:
                                    ttft = (time.perf_counter() - start) * 1000
                                    first_content_chunk = False
                                tokens += 1
                    latency = (time.perf_counter() - start) * 1000
                    return RequestResult(success=True, latency_ms=latency, ttft_ms=ttft, tokens_generated=tokens)
                else:
                    latency = (time.perf_counter() - start) * 1000
                    return RequestResult(success=False, latency_ms=latency, error=f"HTTP {response.status_code}")
            else:
                response = requester.post(url, json=payload, timeout=timeout)
                latency = (time.perf_counter() - start) * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    if 'usage' in data and data['usage']:
                        tokens = data['usage'].get('completion_tokens', 0)
                    return RequestResult(success=True, latency_ms=latency, tokens_generated=tokens)
                else:
                    return RequestResult(success=False, latency_ms=latency, error=f"HTTP {response.status_code}")
                    
        except requests.exceptions.Timeout:
            latency = (time.perf_counter() - start) * 1000
            return RequestResult(success=False, latency_ms=latency, error="Timeout")
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return RequestResult(success=False, latency_ms=latency, error=str(e)[:100])
    
    def _request_ollama(self, prompt: str, stream: bool = False, session: Optional[requests.Session] = None) -> RequestResult:
        """直接調用 Ollama"""
        start = time.perf_counter()
        ttft = None
        tokens = 0
        
        url = self.config["ollama"]["base_url"]
        timeout = self.config["ollama"]["timeout"]
        
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream
        }
        
        try:
            requester = session if session else requests
            
            if stream:
                response = requester.post(url, json=payload, timeout=timeout, stream=True)
                if response.status_code == 200:
                    first_chunk = True
                    for line in response.iter_lines():
                        if line:
                            if first_chunk:
                                ttft = (time.perf_counter() - start) * 1000
                                first_chunk = False
                            try:
                                data = json.loads(line)
                                if 'message' in data and 'content' in data['message']:
                                    tokens += len(data['message']['content'].split())
                            except:
                                pass
                    latency = (time.perf_counter() - start) * 1000
                    return RequestResult(success=True, latency_ms=latency, ttft_ms=ttft, tokens_generated=tokens)
                else:
                    latency = (time.perf_counter() - start) * 1000
                    return RequestResult(success=False, latency_ms=latency, error=f"HTTP {response.status_code}")
            else:
                response = requester.post(url, json=payload, timeout=timeout)
                latency = (time.perf_counter() - start) * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    if 'message' in data and 'content' in data['message']:
                        tokens = len(data['message']['content'].split())
                    return RequestResult(success=True, latency_ms=latency, tokens_generated=tokens)
                else:
                    return RequestResult(success=False, latency_ms=latency, error=f"HTTP {response.status_code}")
                    
        except requests.exceptions.Timeout:
            latency = (time.perf_counter() - start) * 1000
            return RequestResult(success=False, latency_ms=latency, error="Timeout")
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return RequestResult(success=False, latency_ms=latency, error=str(e)[:100])
    
    # ========== 統計計算 ==========
    
    def _calculate_percentile(self, data: List[float], percentile: float) -> float:
        """計算百分位數"""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = (len(sorted_data) - 1) * percentile / 100
        lower = int(index)
        upper = lower + 1
        if upper >= len(sorted_data):
            return sorted_data[-1]
        weight = index - lower
        return sorted_data[lower] * (1 - weight) + sorted_data[upper] * weight
    
    def _calculate_stats(self, results: List[RequestResult], method: str, total_time_s: float) -> BenchmarkStats:
        """計算統計數據"""
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        
        latencies = [r.latency_ms for r in successful] if successful else [0]
        tokens = sum(r.tokens_generated for r in successful)
        ttfts = [r.ttft_ms for r in successful if r.ttft_ms is not None]
        
        return BenchmarkStats(
            method=method,
            total_requests=len(results),
            successful_requests=len(successful),
            failed_requests=len(failed),
            success_rate=(len(successful) / len(results) * 100) if results else 0,
            
            avg_latency_ms=statistics.mean(latencies) if latencies else 0,
            min_latency_ms=min(latencies) if latencies else 0,
            max_latency_ms=max(latencies) if latencies else 0,
            median_latency_ms=statistics.median(latencies) if latencies else 0,
            p95_latency_ms=self._calculate_percentile(latencies, 95),
            p99_latency_ms=self._calculate_percentile(latencies, 99),
            stdev_latency_ms=statistics.stdev(latencies) if len(latencies) > 1 else 0,
            
            total_time_s=total_time_s,
            requests_per_second=len(successful) / total_time_s if total_time_s > 0 else 0,
            tokens_per_second=tokens / total_time_s if total_time_s > 0 else 0,
            
            avg_ttft_ms=statistics.mean(ttfts) if ttfts else None
        )
    
    # ========== 測試方法 ==========
    
    def test_latency(self, num_requests: int = 10, prompt_type: str = "short", warmup: int = 2) -> Dict[str, BenchmarkStats]:
        """延遲測試（串行請求）"""
        print(f"\n{'='*70}")
        print(f"📊 延遲測試 (請求數: {num_requests}, 提示詞類型: {prompt_type})")
        print(f"{'='*70}")
        
        prompt = self.prompts.get(prompt_type, self.prompts["short"])
        results = {}
        
        methods = [
            ("ollama", "🟢 直接調用 Ollama", self._request_ollama),
            ("lyrallm", "🟣 LyraLLM Gateway", self._request_lyrallm),
        ]
        
        if PORTKEY_AVAILABLE:
            methods.append(("portkey", "🔵 Portkey Gateway", self._request_portkey))
        
        for method_key, method_name, request_func in methods:
            print(f"\n{method_name}:")
            
            # 預熱
            if warmup > 0:
                print(f"  預熱 {warmup} 次...")
                session = requests.Session() if method_key in ["lyrallm", "ollama"] else None
                for _ in range(warmup):
                    if method_key == "portkey":
                        request_func(prompt)
                    else:
                        request_func(prompt, session=session)
                if session:
                    session.close()
            
            # 正式測試
            method_results = []
            session = requests.Session() if method_key in ["lyrallm", "ollama"] else None
            start_total = time.perf_counter()
            
            for i in range(num_requests):
                if method_key == "portkey":
                    result = request_func(prompt)
                else:
                    result = request_func(prompt, session=session)
                method_results.append(result)
                
                status = "✓" if result.success else f"✗ ({result.error})"
                print(f"  請求 {i+1}/{num_requests}: {result.latency_ms:.0f}ms {status}")
                
                time.sleep(0.3)  # 避免過度負載
            
            total_time = time.perf_counter() - start_total
            if session:
                session.close()
            
            self.results[method_key] = method_results
            results[method_key] = self._calculate_stats(method_results, method_name, total_time)
        
        return results
    
    def test_throughput(self, duration_s: int = 30, prompt_type: str = "short") -> Dict[str, BenchmarkStats]:
        """吞吐量測試（固定時間內盡可能多請求）"""
        print(f"\n{'='*70}")
        print(f"🚀 吞吐量測試 (持續時間: {duration_s}秒)")
        print(f"{'='*70}")
        
        prompt = self.prompts.get(prompt_type, self.prompts["short"])
        results = {}
        
        methods = [
            ("ollama", "🟢 直接調用 Ollama", self._request_ollama),
            ("lyrallm", "🟣 LyraLLM Gateway", self._request_lyrallm),
        ]
        
        if PORTKEY_AVAILABLE:
            methods.append(("portkey", "🔵 Portkey Gateway", self._request_portkey))
        
        for method_key, method_name, request_func in methods:
            print(f"\n{method_name}: 測試中...")
            
            method_results = []
            session = requests.Session() if method_key in ["lyrallm", "ollama"] else None
            start_time = time.perf_counter()
            end_time = start_time + duration_s
            
            request_count = 0
            while time.perf_counter() < end_time:
                if method_key == "portkey":
                    result = request_func(prompt)
                else:
                    result = request_func(prompt, session=session)
                method_results.append(result)
                request_count += 1
                
                # 每 10 個請求輸出進度
                if request_count % 10 == 0:
                    elapsed = time.perf_counter() - start_time
                    rps = request_count / elapsed
                    print(f"  進度: {request_count} 請求, {rps:.2f} RPS")
            
            total_time = time.perf_counter() - start_time
            if session:
                session.close()
            
            self.results[method_key] = method_results
            stats = self._calculate_stats(method_results, method_name, total_time)
            results[method_key] = stats
            
            print(f"  完成: {stats.total_requests} 請求, {stats.requests_per_second:.2f} RPS")
        
        return results
    
    def test_concurrent(self, concurrency: int = 5, total_requests: int = 20, prompt_type: str = "short") -> Dict[str, BenchmarkStats]:
        """並發測試（多線程同時請求）"""
        print(f"\n{'='*70}")
        print(f"⚡ 並發測試 (並發數: {concurrency}, 總請求: {total_requests})")
        print(f"{'='*70}")
        
        prompt = self.prompts.get(prompt_type, self.prompts["short"])
        results = {}
        
        methods = [
            ("ollama", "🟢 直接調用 Ollama", self._request_ollama),
            ("lyrallm", "🟣 LyraLLM Gateway", self._request_lyrallm),
        ]
        
        if PORTKEY_AVAILABLE:
            methods.append(("portkey", "🔵 Portkey Gateway", self._request_portkey))
        
        for method_key, method_name, request_func in methods:
            print(f"\n{method_name}:")
            
            method_results = []
            start_time = time.perf_counter()
            
            # 創建共享 Session 連接池（提升並發效率）
            shared_session = None
            if method_key in ["lyrallm", "ollama"]:
                shared_session = requests.Session()
                adapter = requests.adapters.HTTPAdapter(
                    pool_connections=concurrency,
                    pool_maxsize=concurrency * 2,
                    max_retries=0
                )
                shared_session.mount('http://', adapter)
                shared_session.mount('https://', adapter)
            
            def worker(idx: int, sess: Optional[requests.Session] = None) -> RequestResult:
                # 使用共享 Session 連接池
                if method_key in ["lyrallm", "ollama"]:
                    result = request_func(prompt, session=sess)
                else:
                    result = request_func(prompt)
                return result
            
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [executor.submit(worker, i, shared_session) for i in range(total_requests)]
                
                completed = 0
                for future in as_completed(futures):
                    result = future.result()
                    method_results.append(result)
                    completed += 1
                    
                    status = "✓" if result.success else "✗"
                    if completed % 5 == 0 or completed == total_requests:
                        print(f"  完成: {completed}/{total_requests}")
            
            total_time = time.perf_counter() - start_time
            
            # 關閉共享 Session
            if shared_session:
                shared_session.close()
            
            self.results[method_key] = method_results
            stats = self._calculate_stats(method_results, method_name, total_time)
            results[method_key] = stats
            
            print(f"  結果: {stats.successful_requests}/{stats.total_requests} 成功, "
                  f"平均延遲 {stats.avg_latency_ms:.0f}ms, {stats.requests_per_second:.2f} RPS")
        
        return results
    
    def test_streaming_ttft(self, num_requests: int = 5, prompt_type: str = "medium") -> Dict[str, BenchmarkStats]:
        """串流首 Token 延遲測試 (TTFT)"""
        print(f"\n{'='*70}")
        print(f"⏱️  首 Token 延遲測試 (TTFT, 請求數: {num_requests})")
        print(f"{'='*70}")
        
        prompt = self.prompts.get(prompt_type, self.prompts["medium"])
        results = {}
        
        methods = [
            ("ollama", "🟢 直接調用 Ollama", self._request_ollama),
            ("lyrallm", "🟣 LyraLLM Gateway", self._request_lyrallm),
        ]
        
        for method_key, method_name, request_func in methods:
            print(f"\n{method_name}:")
            
            method_results = []
            session = requests.Session() if method_key in ["lyrallm", "ollama"] else None
            start_total = time.perf_counter()
            
            for i in range(num_requests):
                result = request_func(prompt, stream=True, session=session)
                method_results.append(result)
                
                ttft_str = f"TTFT={result.ttft_ms:.0f}ms" if result.ttft_ms else "N/A"
                status = "✓" if result.success else f"✗ ({result.error})"
                print(f"  請求 {i+1}/{num_requests}: {ttft_str}, 總計 {result.latency_ms:.0f}ms {status}")
                
                time.sleep(0.5)
            
            total_time = time.perf_counter() - start_total
            if session:
                session.close()
            
            self.results[method_key] = method_results
            results[method_key] = self._calculate_stats(method_results, method_name, total_time)
        
        return results
    
    def test_long_context(self, num_requests: int = 3) -> Dict[str, BenchmarkStats]:
        """長文本測試"""
        print(f"\n{'='*70}")
        print(f"📝 長文本測試 (請求數: {num_requests})")
        print(f"{'='*70}")
        
        prompt = self.prompts["long"]
        print(f"  提示詞長度: {len(prompt)} 字符")
        
        return self.test_latency(num_requests=num_requests, prompt_type="long", warmup=1)
    
    # ========== 結果報告 ==========
    
    def print_comparison_report(self, all_results: Dict[str, Dict[str, BenchmarkStats]]):
        """輸出對比報告"""
        print(f"\n{'='*80}")
        print("📊 完整性能對比報告")
        print(f"{'='*80}")
        print(f"測試時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"測試模型: {self.model}")
        
        # 彙總各測試結果
        for test_name, results in all_results.items():
            if not results:
                continue
                
            print(f"\n{'─'*60}")
            print(f"📈 {test_name}")
            print(f"{'─'*60}")
            
            # 表格標題
            print(f"\n{'方法':<25} {'成功率':>10} {'平均延遲':>12} {'P95延遲':>12} {'P99延遲':>12} {'RPS':>10}")
            print(f"{'-'*25} {'-'*10} {'-'*12} {'-'*12} {'-'*12} {'-'*10}")
            
            for method, stats in results.items():
                print(f"{stats.method:<25} "
                      f"{stats.success_rate:>9.1f}% "
                      f"{stats.avg_latency_ms:>10.0f}ms "
                      f"{stats.p95_latency_ms:>10.0f}ms "
                      f"{stats.p99_latency_ms:>10.0f}ms "
                      f"{stats.requests_per_second:>9.2f}")
        
        # Gateway 開銷分析
        print(f"\n{'='*80}")
        print("⚡ Gateway 開銷分析 (相比直接調用 Ollama)")
        print(f"{'='*80}")
        
        for test_name, results in all_results.items():
            if "ollama" not in results:
                continue
            
            baseline = results["ollama"].avg_latency_ms
            if baseline <= 0:
                continue
            
            print(f"\n{test_name}:")
            for method, stats in results.items():
                if method == "ollama":
                    continue
                
                overhead_ms = stats.avg_latency_ms - baseline
                overhead_pct = (overhead_ms / baseline) * 100
                
                indicator = "✅" if overhead_pct < 10 else "⚠️" if overhead_pct < 25 else "❌"
                print(f"  {stats.method}: +{overhead_ms:.0f}ms ({overhead_pct:+.1f}%) {indicator}")
    
    def save_results(self, all_results: Dict[str, Dict[str, BenchmarkStats]], filename: str = "benchmark_results.json"):
        """保存結果到 JSON"""
        data = {
            "test_info": {
                "timestamp": datetime.now().isoformat(),
                "model": self.model,
                "config": self.config
            },
            "results": {}
        }
        
        for test_name, results in all_results.items():
            data["results"][test_name] = {
                method: stats.to_dict() for method, stats in results.items()
            }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 結果已保存到: {filename}")


def main():
    parser = argparse.ArgumentParser(description="Gateway 全面性能基準測試")
    parser.add_argument("--tests", type=str, default="all", 
                        choices=["all", "latency", "throughput", "concurrent", "ttft", "longtext"],
                        help="要執行的測試類型")
    parser.add_argument("--model", type=str, default="gpt-oss:20b", help="測試模型")
    parser.add_argument("--requests", type=int, default=10, help="延遲測試請求數")
    parser.add_argument("--duration", type=int, default=30, help="吞吐量測試持續時間(秒)")
    parser.add_argument("--concurrency", type=int, default=5, help="並發測試並發數")
    parser.add_argument("--output", type=str, default="benchmark_results.json", help="輸出檔案名")
    
    args = parser.parse_args()
    
    print("🎯 Gateway 全面性能基準測試")
    print("="*80)
    print(f"測試模型: {args.model}")
    print(f"測試類型: {args.tests}")
    
    benchmark = GatewayBenchmark(model=args.model)
    all_results = {}
    
    if args.tests in ["all", "latency"]:
        all_results["延遲測試 (短文本)"] = benchmark.test_latency(num_requests=args.requests, prompt_type="short")
    
    if args.tests in ["all", "throughput"]:
        all_results["吞吐量測試"] = benchmark.test_throughput(duration_s=args.duration)
    
    if args.tests in ["all", "concurrent"]:
        all_results["並發測試"] = benchmark.test_concurrent(concurrency=args.concurrency, total_requests=args.requests*2)
    
    if args.tests in ["all", "ttft"]:
        all_results["首Token延遲 (TTFT)"] = benchmark.test_streaming_ttft(num_requests=5)
    
    if args.tests in ["all", "longtext"]:
        all_results["長文本測試"] = benchmark.test_long_context(num_requests=3)
    
    # 輸出報告
    benchmark.print_comparison_report(all_results)
    benchmark.save_results(all_results, args.output)
    
    print("\n✅ 測試完成!")


if __name__ == "__main__":
    main()
