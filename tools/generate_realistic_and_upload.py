"""Generate more realistic simulated documents (financial reports, meeting minutes, etc.)
and upload them to Elasticsearch with embeddings.

Usage:
  python lyrallm\tools\generate_realistic_and_upload.py --count 20 --chunk-size 800 --types financial,meeting
python lyrallm\tools\generate_realistic_and_upload.py --from-folder data_update --chunk-size 800 --batch-size 12
This reuses the project's embedding provider and ES client.
"""
import argparse
import asyncio
import json
import logging
import random
import sys
from datetime import date, timedelta
from pathlib import Path
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from lyrallm.config.config_manager import config_manager
    from lyrallm.adapters.es_client import get_es_client, get_es_index
    from lyrallm.embedding_provider import get_default_provider
except Exception:
    repo_root = Path(__file__).resolve().parents[2]
    lyrallm_pkg = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    if str(lyrallm_pkg) not in sys.path:
        sys.path.insert(0, str(lyrallm_pkg))
    from lyrallm.config.config_manager import config_manager
    from lyrallm.adapters.es_client import get_es_client, get_es_index
    from lyrallm.embedding_provider import get_default_provider


DATA_DIR = Path('data') / 'generated_realistic_docs'
DATA_DIR.mkdir(parents=True, exist_ok=True)


def fake_money(amount_min=10000, amount_max=500000) -> str:
    return f"${random.randint(amount_min, amount_max):,}"


def gen_financial_report(idx: int) -> str:
    today = date.today()
    start = today.replace(day=1) - timedelta(days=30)
    title = f"財務報表 Q{random.randint(1,4)} {start.year} - 模擬公司 {idx}"
    lines = [f"# {title}\n\n", f"報表期間: {start.isoformat()} - {today.isoformat()}\n\n"]
    # Executive summary
    lines.append("## 執行摘要\n\n")
    lines.append("本報表彙整本期主要財務指標，包含營收、毛利、淨利與資產負債狀況。重點如下：\n\n")
    # Key numbers
    revenue = fake_money(200000, 2000000)
    cogs = fake_money(50000, 800000)
    net_income = fake_money(10000, 300000)
    lines.append(f"- 營收: {revenue}\n")
    lines.append(f"- 銷貨成本 (COGS): {cogs}\n")
    lines.append(f"- 淨利: {net_income}\n\n")

    # Income statement (simple table-like markdown)
    lines.append("## 損益表\n\n")
    lines.append("項目 | 本期 | 同期比較\n---|---:|---:\n")
    lines.append(f"營收 | {revenue} | {random.choice(['+5%','-3%','+12%'])}\n")
    lines.append(f"毛利 | {fake_money(10000, 500000)} | {random.choice(['+2%','-1%','+8%'])}\n")
    lines.append(f"營業費用 | {fake_money(5000, 200000)} | {random.choice(['+1%','-4%','+10%'])}\n")
    lines.append(f"稅後淨利 | {net_income} | {random.choice(['+7%','-6%','+3%'])}\n\n")

    # Notes and commentary
    lines.append("## 備註與說明\n\n")
    lines.append("本期營收成長主要受新產品線上線與國外市場擴張所推動；需注意供應鏈成本上升對毛利率之影響。\n\n")

    # Append some tabular balance sheet skeleton
    lines.append("## 資產負債表 (摘要)\n\n")
    lines.append("項目 | 金額\n---|---:\n")
    lines.append(f"流動資產 | {fake_money(50000, 2000000)}\n")
    lines.append(f"固定資產 | {fake_money(20000, 1000000)}\n")
    lines.append(f"負債合計 | {fake_money(10000, 800000)}\n\n")

    return ''.join(lines)


def gen_meeting_minutes(idx: int) -> str:
    today = date.today()
    title = f"會議記錄 - 第 {idx} 次 專案會議 ({today.isoformat()})"
    attendees = ["Alice", "Bob", "Carol", "David"]
    random.shuffle(attendees)
    lines = [f"# {title}\n\n", f"出席者: {', '.join(attendees[:random.randint(2,4)])}\n\n"]
    lines.append("## 議程\n\n")
    agenda = ["專案進度報告", "風險與問題討論", "下階段工作項目與負責人", "里程碑檢視"]
    for a in agenda:
        lines.append(f"- {a}\n")
    lines.append("\n## 討論內容\n\n")
    # Add several discussion bullets
    for i in range(4):
        lines.append(f"- {random.choice(['進度符合預期','需加強測試','發現第三方服務延遲','預算略為吃緊'])}，建議: {random.choice(['增加資源','調整時程','召開專案小組'] )}。\n")
    lines.append("\n## 決議與待辦\n\n")
    for i in range(3):
        assignee = random.choice(attendees)
        lines.append(f"- [ ] {random.choice(['完成測試用例','修正登入錯誤','確認 API 規格'])}  — 負責: {assignee} — 期限: {(date.today()+timedelta(days=random.randint(3,14))).isoformat()}\n")
    lines.append("\n")
    return ''.join(lines)


def gen_generic(idx: int) -> str:
    # fallback to previous fake style but slightly longer
    title = f"模擬文件 {idx} - GENERIC"
    parts = [f"# {title}\n\n"]
    for sec in range(4):
        parts.append(f"## 節 {sec+1}\n\n")
        # longer paragraphs
        parts.append(' '.join(['本系統'] * random.randint(60, 120)) + '\n\n')
    return ''.join(parts)


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100):
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    L = len(text)
    while start < L:
        end = min(start + chunk_size, L)
        chunks.append(text[start:end])
        if end == L:
            break
        start = end - overlap
    return chunks



async def main(count: int = 20, chunk_size: int = 800, types: list[str] = None, batch_size: int = 16, sleep_sec: float = 0.15, from_folder: str = None):
    emb = get_default_provider()
    es = get_es_client()
    cfg = config_manager.config.get('vectordb') or {}
    index = cfg.get('index') or get_es_index()
    total_indexed = 0
    actions = []

    if from_folder:
        folder = Path(from_folder)
        if not folder.exists() or not folder.is_dir():
            logger.error(f"指定的資料夾不存在: {from_folder}")
            return
        files = list(folder.glob('*.md')) + list(folder.glob('*.txt'))
        if not files:
            logger.warning(f"{from_folder} 沒有找到任何 .md 或 .txt 檔案")
            return
        logger.info(f"將處理 {len(files)} 個檔案於 {from_folder}")
        for file in files:
            title = file.stem
            content = file.read_text(encoding='utf-8')
            doc_type = 'uploaded'
            chunks = chunk_text(content, chunk_size=chunk_size)
            for idx, chunk in enumerate(chunks, start=1):
                doc_id = f"{title}-p{idx}"
                vec = await emb.embed(chunk)
                action = {"index": {"_index": index, "_id": doc_id}}
                source = {
                    "title": title,
                    "text": chunk,
                    "document_id": doc_id,
                    "document_type": doc_type,
                    "visibility": "public",
                    "effective_allowed_roles": ["standard_user"],
                    "restricted_roles": [],
                    "source_path": str(file),
                    "embedding": vec
                }
                actions.append(json.dumps(action))
                actions.append(json.dumps(source, ensure_ascii=False))
                if len(actions) >= batch_size * 2:
                    body = '\n'.join(actions) + '\n'
                    try:
                        res = await es.bulk(body=body, request_timeout=60)
                        logger.info('Bulk indexed batch: items=%d took=%s', len(actions)//2, res.get('took'))
                        total_indexed += len(actions)//2
                    except Exception as e:
                        logger.exception('Bulk upload failed: %s', e)
                    actions = []
                    await asyncio.sleep(sleep_sec)
        if actions:
            body = '\n'.join(actions) + '\n'
            try:
                res = await es.bulk(body=body, request_timeout=60)
                logger.info('Bulk indexed final batch: items=%d took=%s', len(actions)//2, res.get('took'))
                total_indexed += len(actions)//2
            except Exception as e:
                logger.exception('Bulk upload failed: %s', e)
        logger.info('Total indexed documents (passages): %d', total_indexed)
        try:
            await es.close()
        except Exception:
            pass
        return

    # 原本隨機產生文件的模式
    if types is None:
        types = ['financial', 'meeting']
    for i in range(1, count + 1):
        doc_type = random.choice(types)
        if doc_type == 'financial':
            content = gen_financial_report(i)
            title = f'financial_report_{i:04d}'
        elif doc_type == 'meeting':
            content = gen_meeting_minutes(i)
            title = f'meeting_minutes_{i:04d}'
        else:
            content = gen_generic(i)
            title = f'generic_{i:04d}'
        src = DATA_DIR / f'{title}.md'
        src.write_text(content, encoding='utf-8')
        chunks = chunk_text(content, chunk_size=chunk_size)
        for idx, chunk in enumerate(chunks, start=1):
            doc_id = f"{title}-p{idx}"
            vec = await emb.embed(chunk)
            action = {"index": {"_index": index, "_id": doc_id}}
            source = {
                "title": title,
                "text": chunk,
                "document_id": doc_id,
                "document_type": doc_type,
                "visibility": "public",
                "effective_allowed_roles": ["standard_user"],
                "restricted_roles": [],
                "source_path": str(src),
                "embedding": vec
            }
            actions.append(json.dumps(action))
            actions.append(json.dumps(source, ensure_ascii=False))
            if len(actions) >= batch_size * 2:
                body = '\n'.join(actions) + '\n'
                try:
                    res = await es.bulk(body=body, request_timeout=60)
                    logger.info('Bulk indexed batch: items=%d took=%s', len(actions)//2, res.get('took'))
                    total_indexed += len(actions)//2
                except Exception as e:
                    logger.exception('Bulk upload failed: %s', e)
                actions = []
                await asyncio.sleep(sleep_sec)
    if actions:
        body = '\n'.join(actions) + '\n'
        try:
            res = await es.bulk(body=body, request_timeout=60)
            logger.info('Bulk indexed final batch: items=%d took=%s', len(actions)//2, res.get('took'))
            total_indexed += len(actions)//2
        except Exception as e:
            logger.exception('Bulk upload failed: %s', e)
    logger.info('Total indexed documents (passages): %d', total_indexed)
    try:
        await es.close()
    except Exception:
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, default=20, help='(隨機產生模式) 產生幾份文件')
    parser.add_argument('--chunk-size', type=int, default=800)
    parser.add_argument('--types', type=str, default='financial,meeting', help='comma-separated list: financial,meeting,generic')
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--from-folder', type=str, default=None, help='指定要自動上傳的資料夾 (例如 data_update)')
    args = parser.parse_args()
    types = [t.strip() for t in args.types.split(',') if t.strip()]
    asyncio.run(main(count=args.count, chunk_size=args.chunk_size, types=types, batch_size=args.batch_size, from_folder=args.from_folder))
