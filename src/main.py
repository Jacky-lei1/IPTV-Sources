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
from merger import IPTVSourceMerger

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
    # 向上一级目录查找配置文件
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
    
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
    logger.info(f"解析M3U文件: {filepath}")
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        logger.error(f"读取文件失败: {filepath}, 错误: {str(e)}")
        return {}
    
    channels = {}
    
    lines = content.strip().split('\n')
    if not lines or not lines[0].startswith('#EXTM3U'):
        logger.warning(f"不是有效的M3U文件: {filepath}")
        return channels
    
    i = 1
    while i < len(lines):
        line = lines[i].strip()
        
        # 处理EXTINF行
        if line.startswith('#EXTINF'):
            extinf_line = line
            info = parse_extinf(extinf_line)
            
            # 获取频道ID
            channel_id = info.get('tvg-id') or info.get('tvg-name') or info.get('title')
            
            if not channel_id:
                i += 1
                continue
            
            # 查找URL行
            url = None
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if next_line and not next_line.startswith('#'):
                    url = next_line
                    break
                j += 1
            
            if url:
                # 将频道添加到集合中
                if channel_id in channels:
                    channels[channel_id][1].append(url)
                else:
                    channels[channel_id] = [info, [url]]
                
                i = j + 1
            else:
                i += 1
        else:
            i += 1
    
    logger.info(f"从文件 {filepath} 解析出 {len(channels)} 个频道")
    return channels

def parse_extinf(extinf_line):
    """解析EXTINF行，提取频道信息"""
    info = {}
    
    try:
        # 提取时长和标题
        parts = extinf_line.split(',', 1)
        if len(parts) > 1:
            info['title'] = parts[1].strip()
        
        # 提取属性
        attrs_part = parts[0]
        import re
        pattern = r'(\w+[-\w]*)\s*=\s*"([^"]*)"'
        matches = re.findall(pattern, attrs_part)
        
        for key, value in matches:
            info[key] = value
            
    except Exception as e:
        logger.error(f"解析EXTINF失败: {str(e)}")
        
    return info

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='IPTV直播源收集、检测与合并工具')
    parser.add_argument('--no-check', action='store_true', help='跳过直播源检测步骤')
    parser.add_argument('--max-channels', type=int, default=0, help='最大处理频道数量(用于测试)')
    args = parser.parse_args()
    
    start_time = time.time()
    logger.info("开始IPTV直播源更新流程")
    
    try:
        # 加载配置
        config = load_config()
        logger.info(f"配置加载完成，共 {len(config['sources'])} 个直播源")
        
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
                    all_channels[channel_id] = [info, urls]
                    
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
        else:
            # 跳过检查，构造检查结果
            logger.info("跳过直播源检测步骤")
            check_results = {}
            for channel_id, (info, urls) in all_channels.items():
                check_results[channel_id] = {
                    "info": info,
                    "sources": [(url, True, 0) for url in urls]
                }
        
        # 合并直播源
        merger = IPTVSourceMerger(config)
        output_path = merger.merge(check_results)
        
        end_time = time.time()
        logger.info(f"IPTV直播源更新完成，总耗时: {end_time - start_time:.2f}秒")
        logger.info(f"输出文件: {output_path}")
        
    except Exception as e:
        logger.error(f"程序运行出错: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
