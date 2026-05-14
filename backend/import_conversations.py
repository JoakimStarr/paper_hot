#!/usr/bin/env python3
"""
导入选题分析对话记录到数据库
"""

import asyncio
import re
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal, engine
from app.models import AIAnalysisReport, TrendChat
from sqlalchemy import select


async def parse_markdown_file(filepath: str):
    """解析 Markdown 对话文件"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 提取导出时间和分析报告
    export_time_match = re.search(r'导出时间：(\d{4}/\d{1,2}/\d{1,2} \d{2}:\d{2}:\d{2})', content)
    export_time = None
    if export_time_match:
        time_str = export_time_match.group(1)
        export_time = datetime.strptime(time_str, '%Y/%m/%d %H:%M:%S').replace(tzinfo=timezone.utc)
    
    # 提取分析报告
    analysis_match = re.search(r'分析报告：(.+?)(?=\n\n---|\Z)', content, re.DOTALL)
    analysis_summary = analysis_match.group(1).strip() if analysis_match else None
    
    # 解析对话
    conversations = []
    
    # 分割对话块
    pattern = r'###\s*([👤🤖])\s*(用户|选题分析师)\s*\n\n(.+?)(?=###\s*[👤🤖]|\Z)'
    matches = re.findall(pattern, content, re.DOTALL)
    
    for emoji, role_type, content_text in matches:
        role = "user" if "用户" in role_type else "assistant"
        content_clean = content_text.strip()
        conversations.append({
            "role": role,
            "content": content_clean
        })
    
    return {
        "export_time": export_time,
        "analysis_summary": analysis_summary,
        "conversations": conversations
    }


async def import_conversations():
    """导入对话到数据库"""
    filepath = "/home/joakim/Project/paper_hot/选题分析对话_2026-05-13.md"
    
    # 解析文件
    data = await parse_markdown_file(filepath)
    
    if not data["conversations"]:
        print("未找到对话数据")
        return
    
    async with AsyncSessionLocal() as session:
        # 创建分析报告记录
        report = AIAnalysisReport(
            summary=data["analysis_summary"] or "选题分析对话记录",
            model="imported",
            total_papers=0,
            status="success",
            created_at=data["export_time"] or datetime.now(timezone.utc)
        )
        session.add(report)
        await session.flush()  # 获取 report.id
        
        # 导入对话
        for conv in data["conversations"]:
            chat = TrendChat(
                report_id=report.id,
                role=conv["role"],
                content=conv["content"],
                created_at=data["export_time"] or datetime.now(timezone.utc)
            )
            session.add(chat)
        
        await session.commit()
        print(f"✅ 成功导入 {len(data['conversations'])} 条对话记录")
        print(f"📊 报告 ID: {report.id}")


if __name__ == "__main__":
    asyncio.run(import_conversations())
