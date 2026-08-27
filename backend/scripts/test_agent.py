#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 Agent 工具调用：直接跑 run_agent_chat，看模型是否自主调用检索工具。

用法:
    cd backend
    ../venv/bin/python scripts/test_agent.py "库里关于研发费用加计扣除的论文有哪些？主要结论？"
    ../venv/bin/python scripts/test_agent.py --surface paper_chat "这篇论文的方法被哪些后续工作采用？"
"""
import asyncio
import sys
import os
import argparse

# 保证从 backend/scripts/ 运行时能 import 到 backend 下的 app 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ai_service import ai_trend_service
from app.agent import run_agent_chat


async def main(question: str, surface: str):
    status = ai_trend_service.get_model_status()
    if not status:
        print("未配置任何 AI 模型")
        return
    m = status[0]
    bare = m['name'].split('/')[-1]
    client, provider = ai_trend_service.get_client(m['provider'])
    print(f"模型: {provider}/{bare}  surface: {surface}\n")

    messages = [
        {"role": "system", "content": "你是一位论文选题分析师，可以检索论文库。涉及库内论文时必须先调用工具再回答，引用用 [编号]。"},
        {"role": "user", "content": question},
    ]
    msgs, trace = await run_agent_chat(messages, client, bare, surface=surface)

    print("=" * 60)
    print("工具调用轨迹:")
    if not trace:
        print("  （模型未调用任何工具，直接回答了）")
    for t in trace:
        print(f"  [{t['tool']}] args={t.get('args')}")
        result = t.get('result') or {}
        if result.get('papers'):
            for p in result['papers'][:5]:
                print(f"      [{p.get('n')}] {p.get('title','')[:50]} | sim={p.get('similarity')}")

    print("=" * 60)
    print("最终回答（前 400 字）:")
    for msg in reversed(msgs):
        if msg.get('role') == 'assistant' and (msg.get('content') or '').strip():
            print((msg.get('content') or '').replace('\n', ' ')[:400])
            break
    else:
        print("  （未取到最终回答正文）")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='测试 Agent 工具调用')
    parser.add_argument('question', nargs='?', default='库里关于「研发费用加计扣除对企业创新影响」的论文有哪些？主要结论？')
    parser.add_argument('--surface', default='trend_chat', choices=['trend_chat', 'paper_chat'])
    args = parser.parse_args()
    asyncio.run(main(args.question, args.surface))
