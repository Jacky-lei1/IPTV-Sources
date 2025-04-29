#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import logging
import time
import argparse
from collector import IPTVSourceCollector
from checker import IPTVSourceChecker

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("iptv_update.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("IPTV-Main")

def load_config():
    """加载配置文件"""
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        logger.info(f"成功从 {config_path} 加载配置")
        return config
    except Exception as e:
        logger.error(f"加载配置文件失败: {str(e)}")
        sys.exit(1)

def parse_m3u_file(filepath):
    """解析M3U文件，提取频道信息和URL"""
    # [保持原代码不变]...

def parse_extinf(extinf_line):
    """解析EXTINF行，提取频道信息"""
    # [保持原代码不变]...

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='IPTV直播源收集与检测工具')
    parser.add_argument('--no-check', action='store_true', help='跳过直播源检测步骤')
    parser.add_argument('--max-channels', type=int, default=0, help='最大处理频道数量(用于测试)')
    args = parser.parse_args()
    
    start_time = time.time()
    logger.info("开始IPTV直播源收集和检测流程")
    
    try:
        # 加载配置
        config = load_config()
        logger.info(f"配置加载完成，共 {len(config['sources'])} 个直播源")
        
        # 创建输出目录
        output_dir = os.path.join(os.path.dirname(__file__), config["output_dir"])
        os.makedirs(output_dir, exist_ok=True)
        
        # 收集直播源
        collector = IPTVSourceCollector(config)
        source_files = collector.collect()
        logger.info(f"直播源收集完成，共 {len(source_files)} 个文件")
        
        # 解析所有源文件
        all_channels = {}
        for filepath in source_files:
            channels = parse_m3u_file(filepath)
            
            # 合并到全局频道集合
            for channel_id, (info, urls) in channels.items():
                if channel_id in all_channels:
                    all_channels[channel_id][1].extend(urls)
                else:
                    all_channels[channel_id] = [info, [url]]
                    
            # 如果设置了最大频道数限制，用于测试
            if args.max_channels > 0 and len(all_channels) >= args.max_channels:
                logger.info(f"达到最大频道数限制 ({args.max_channels})，停止收集")
                break
        
        # 去重URL
        for channel_id, (info, urls) in all_channels.items():
            all_channels[channel_id][1] = list(set(urls))
        
        logger.info(f"共解析出 {len(all_channels)} 个频道, {sum(len(urls) for _, urls in all_channels.values())} 个直播源")
        
        # 检查直播源
        if not args.no_check:
            checker = IPTVSourceChecker(config)
            check_results = checker.check(all_channels)
            
            # 保存结果为JSON文件
            json_output_path = os.path.join(output_dir, "collected_sources.json")
            
            # 转换结果为可序列化的格式
            serializable_results = {}
            for channel_id, result in check_results.items():
                serializable_results[channel_id] = {
                    "info": result["info"],
                    "sources": [
                        {"url": url, "valid": valid, "latency": latency if latency != float('inf') else -1}
                        for url, valid, latency in result["sources"]
                    ]
                }
            
            with open(json_output_path, 'w', encoding='utf-8') as f:
                json.dump(serializable_results, f, ensure_ascii=False, indent=2)
                
            logger.info(f"JSON格式检测结果已保存到: {json_output_path}")
        else:
            logger.info("跳过直播源检测步骤")
        
        end_time = time.time()
        logger.info(f"IPTV直播源收集和检测完成，总耗时: {end_time - start_time:.2f}秒")
        
    except Exception as e:
        logger.error(f"程序运行出错: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
