import argparse
import asyncio
import json
import time
import os
import sys
from typing import List

# Ensure package import works when executed via `python -m` or direct path
try:
    from lyrallm.config.config_manager import config_manager
    from lyrallm.core.model_executor import ModelExecutor
except ModuleNotFoundError:
    # Fallback: add parent directory of this file to sys.path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from lyrallm.config.config_manager import config_manager
    from lyrallm.core.model_executor import ModelExecutor


def format_capability_table(cap_details, selected: str = None):
    if not cap_details:
        return "(no capability details)"
    headers = ["model", "level", "required", "diff", "meets", "pr", "iq"]
    lines = [" | ".join(headers), "-|-|-|-|-|-|-"]
    for d in cap_details:
        name = str(d.get('model'))
        if selected and name == selected:
            name = f"*{name}*"
        lines.append(" | ".join([
            name,
            f"{d.get('level')}",
            str(d.get('required')),
            str(d.get('diff')),
            "✅" if d.get('meets') else "❌",
            f"{d.get('pr')}",
            f"{d.get('iq')}"
        ]))
    return "\n".join(lines)


async def run_single_turn(executor: ModelExecutor, user_input: str, model: str, history: List[dict]):
    start = time.time()
    messages = history + [{'role': 'user', 'content': user_input}]
    result = await executor.generate(model_name=model, messages=messages)
    latency = (time.time() - start) * 1000

    routing_info = (result.get('meta') or {}).get('routing_info') or {}
    trace = routing_info.get('trace', {}) if isinstance(routing_info, dict) else {}
    analyzer = trace.get('analyzer') or {
        'intent': routing_info.get('intent'),
        'confidence': routing_info.get('confidence'),
        'complexity': routing_info.get('complexity')
    }
    decision = trace.get('decision') or {
        'selected': routing_info.get('model'),
        'candidates': routing_info.get('candidates', [])
    }
    capability_details = decision.get('capability_details') or []

    print("\n=== Routing Result ===")
    print(f"Input: {user_input}")
    if analyzer:
        print(f"Intent: {analyzer.get('intent')}  (confidence={analyzer.get('confidence')})")
        print(f"Complexity: {analyzer.get('complexity')}")
    if decision:
        print(f"Selected Model: {result.get('model')} (decision model: {decision.get('selected')})")
        router_name = trace.get('router') or 'unknown'
        print(f"Router: {router_name}")
        analyzer_trace = trace.get('analyzer', {})
        slm_model = analyzer_trace.get('slm_model')
        eff_model = analyzer_trace.get('effective_slm_model') or slm_model
        fallback = analyzer_trace.get('fallback')
        if slm_model:
            label = "SLM Model"
            if fallback:
                label += " [FALLBACK]"
            if eff_model and eff_model != slm_model:
                print(f"{label}: {slm_model} (effective: {eff_model})")
            else:
                print(f"{label}: {slm_model}")
        print("Candidates:", decision.get('candidates'))
    print(f"Latency: {latency:.1f} ms")
    if capability_details:
        print("\nCapability Details:\n" + format_capability_table(capability_details, decision.get('selected')))
    print("\n=== Model Response (truncated 800 chars) ===\n")
    answer = (result.get('text') or '')[:800]
    print(answer)
    history.append({'role': 'user', 'content': user_input})
    history.append({'role': 'assistant', 'content': answer})
    if len(history) > 40:
        del history[: len(history) - 40]
    return answer


def list_models():
    models = [m.get('name') for m in config_manager.get_available_models()]
    print("Available models:")
    for m in models:
        print(" -", m)


def main():
    parser = argparse.ArgumentParser(description="Interactive multi-turn routing test for LyraLLM")
    parser.add_argument('-m', '--model', default='auto', help='Initial model name or auto')
    parser.add_argument('--list', action='store_true', help='List models and exit')
    args = parser.parse_args()

    if args.list:
        list_models()
        return

    executor = ModelExecutor()
    current_model = args.model
    history: List[dict] = []
    print("\n=== LyraLLM Multi-turn Console ===")
    print("指令: /exit 離開 | /model <name> 切換模型 | /auto 回自動 | /models 列出模型")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        while True:
            user_input = input(f"\n[{current_model}] >> ").strip()
            if not user_input:
                continue
            if user_input.startswith('/'):
                if user_input == '/exit':
                    print("Bye.")
                    break
                if user_input == '/models':
                    list_models()
                    continue
                if user_input == '/auto':
                    current_model = 'auto'
                    print("Switched to auto routing.")
                    continue
                if user_input.startswith('/model '):
                    _, _, newm = user_input.partition(' ')
                    if newm:
                        current_model = newm.strip()
                        print(f"Switched model -> {current_model}")
                    continue
                print("未知指令")
                continue
            loop.run_until_complete(run_single_turn(executor, user_input, current_model, history))
    finally:
        loop.close()


if __name__ == '__main__':
    main()
