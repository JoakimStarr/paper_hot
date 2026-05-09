#!/usr/bin/env python3
"""
CNKI DrissionPage 爬虫测试脚本
测试模块导入、期刊配置和基本功能
"""

import asyncio
import sys
from datetime import datetime

# 添加项目路径
sys.path.insert(0, '/home/joakim/Project/paper_hot/backend')


def test_import():
    """测试模块导入"""
    print("=" * 60)
    print("测试模块导入...")
    
    try:
        from app.fetchers_cnki import (
            CNKIDrissionFetcher,
            CNKITop50BatchFetcher,
            CNKI_TOP50_JOURNALS,
            DrissionPageBase,
            fetch_cnki_journal,
            fetch_cnki_top50,
        )
        print("✓ 所有模块导入成功")
        return True
    except Exception as e:
        print(f"✗ 模块导入失败: {e}")
        return False


def test_journal_config():
    """测试期刊配置"""
    print("=" * 60)
    print("测试期刊配置...")
    
    try:
        from app.fetchers_cnki import CNKI_TOP50_JOURNALS
        
        print(f"期刊总数: {len(CNKI_TOP50_JOURNALS)}")
        
        # 检查顶级期刊
        top_journals = ["经济研究", "管理世界", "经济学（季刊）", "世界经济", "中国工业经济"]
        for journal in top_journals:
            if journal in CNKI_TOP50_JOURNALS:
                config = CNKI_TOP50_JOURNALS[journal]
                print(f"✓ {journal}: code={config.get('code')}, priority={config.get('priority')}")
            else:
                print(f"✗ {journal}: 未找到")
        
        return True
    except Exception as e:
        print(f"✗ 期刊配置测试失败: {e}")
        return False


def test_scheduler_import():
    """测试 scheduler 导入"""
    print("=" * 60)
    print("测试 Scheduler 导入...")
    
    try:
        from app.scheduler import PaperScheduler
        print("✓ PaperScheduler 导入成功")
        
        # 检查是否有 CNKI 相关方法
        scheduler = PaperScheduler()
        if hasattr(scheduler, 'fetch_and_process_cnki_top50'):
            print("✓ fetch_and_process_cnki_top50 方法存在")
        else:
            print("✗ fetch_and_process_cnki_top50 方法不存在")
            
        if hasattr(scheduler, 'trigger_manual_cnki_crawl'):
            print("✓ trigger_manual_cnki_crawl 方法存在")
        else:
            print("✗ trigger_manual_cnki_crawl 方法不存在")
        
        if hasattr(scheduler, 'cnki_batch_fetcher'):
            print("✓ cnki_batch_fetcher 属性存在")
        else:
            print("✗ cnki_batch_fetcher 属性不存在")
        
        return True
    except Exception as e:
        print(f"✗ Scheduler 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_drissionpage_base():
    """测试 DrissionPageBase 基础功能"""
    print("=" * 60)
    print("测试 DrissionPageBase...")
    
    try:
        from app.fetchers_cnki import DrissionPageBase
        
        # 测试初始化（不实际启动浏览器）
        print("✓ DrissionPageBase 类可导入")
        
        # 检查方法
        methods = ['check_captcha', 'handle_captcha', 'wait_for_page_load', 
                   'random_delay', 'close']
        for method in methods:
            if hasattr(DrissionPageBase, method):
                print(f"✓ 方法 {method} 存在")
            else:
                print(f"✗ 方法 {method} 不存在")
        
        return True
    except Exception as e:
        print(f"✗ DrissionPageBase 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cnkifetcher():
    """测试 CNKIDrissionFetcher"""
    print("=" * 60)
    print("测试 CNKIDrissionFetcher...")
    
    try:
        from app.fetchers_cnki import CNKIDrissionFetcher
        
        # 创建 fetcher 实例（不启动浏览器）
        fetcher = CNKIDrissionFetcher("经济研究", headless=True)
        print(f"✓ CNKIDrissionFetcher 实例创建成功")
        print(f"  - 期刊名称: {fetcher.journal_name}")
        print(f"  - 期刊代码: {fetcher.journal_code}")
        print(f"  - 优先级: {fetcher.priority}")
        
        # 检查方法
        methods = ['fetch_papers', '_build_search_url', '_extract_papers_from_search_page',
                   '_extract_paper_detail', '_parse_date']
        for method in methods:
            if hasattr(fetcher, method):
                print(f"✓ 方法 {method} 存在")
            else:
                print(f"✗ 方法 {method} 不存在")
        
        return True
    except Exception as e:
        print(f"✗ CNKIDrissionFetcher 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_batch_fetcher():
    """测试 CNKITop50BatchFetcher"""
    print("=" * 60)
    print("测试 CNKITop50BatchFetcher...")
    
    try:
        from app.fetchers_cnki import CNKITop50BatchFetcher
        
        batch_fetcher = CNKITop50BatchFetcher(headless=True)
        print("✓ CNKITop50BatchFetcher 实例创建成功")
        
        # 获取期刊列表
        journals = batch_fetcher.get_journal_list()
        print(f"✓ 获取期刊列表: {len(journals)} 个期刊")
        
        # 获取期刊信息
        info = batch_fetcher.get_journal_info("经济研究")
        if info:
            print(f"✓ 获取期刊信息: {info}")
        else:
            print("✗ 获取期刊信息失败")
        
        # 检查方法
        if hasattr(batch_fetcher, 'fetch_all_journals'):
            print("✓ 方法 fetch_all_journals 存在")
        else:
            print("✗ 方法 fetch_all_journals 不存在")
        
        return True
    except Exception as e:
        print(f"✗ CNKITop50BatchFetcher 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_async_functions():
    """测试异步函数"""
    print("=" * 60)
    print("测试异步函数...")
    
    try:
        from app.fetchers_cnki import fetch_cnki_journal, fetch_cnki_top50
        
        print("✓ 异步函数可导入")
        print("  - fetch_cnki_journal")
        print("  - fetch_cnki_top50")
        
        # 注意：这里不实际执行爬取，只是验证函数签名
        import inspect
        
        sig1 = inspect.signature(fetch_cnki_journal)
        print(f"✓ fetch_cnki_journal 签名: {sig1}")
        
        sig2 = inspect.signature(fetch_cnki_top50)
        print(f"✓ fetch_cnki_top50 签名: {sig2}")
        
        return True
    except Exception as e:
        print(f"✗ 异步函数测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("CNKI DrissionPage 爬虫测试")
    print("=" * 60 + "\n")
    
    results = []
    
    # 运行所有测试
    results.append(("模块导入", test_import()))
    results.append(("期刊配置", test_journal_config()))
    results.append(("Scheduler导入", test_scheduler_import()))
    results.append(("DrissionPageBase", test_drissionpage_base()))
    results.append(("CNKIDrissionFetcher", test_cnkifetcher()))
    results.append(("CNKITop50BatchFetcher", test_batch_fetcher()))
    
    # 异步测试
    results.append(("异步函数", asyncio.run(test_async_functions())))
    
    # 打印结果汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{status}: {name}")
    
    print("-" * 60)
    print(f"总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️ {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
