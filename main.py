#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import logging
import time
import argparse
import requests
import gzip
import xml.etree.ElementTree as ET
import re
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
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

def download_and_parse_epg(config):
    """下载并解析EPG数据"""
    if "epg_urls" not in config or not config["epg_urls"]:
        logger.info("未配置EPG URL，跳过EPG处理")
        return {}
        
    logger.info("开始下载和解析EPG数据")
    
    epg_data = {}  # 格式: {频道ID: {"id": id, "name": name, "icon": icon_url}}
    
    for epg_url in config["epg_urls"]:
        logger.info(f"下载EPG: {epg_url}")
        try:
            response = requests.get(epg_url, timeout=120)
            if response.status_code != 200:
                logger.error(f"下载EPG失败，状态码: {response.status_code}")
                continue
                
            # 检查是否为gzip格式
            if epg_url.endswith('.gz'):
                try:
                    content = gzip.decompress(response.content)
                except Exception as e:
                    logger.error(f"解压EPG数据失败: {str(e)}")
                    continue
            else:
                content = response.content
                
            # 解析XML
            try:
                root = ET.fromstring(content)
                
                # 查找频道信息
                for channel in root.findall(".//channel"):
                    channel_id = channel.get('id')
                    if not channel_id:
                        continue
                        
                    # 获取频道名称
                    display_name = channel.find('.//display-name')
                    name = display_name.text if display_name is not None else ""
                    
                    # 获取频道图标
                    icon = channel.find('.//icon')
                    icon_url = icon.get('src') if icon is not None else ""
                    
                    # 存储频道信息
                    if channel_id not in epg_data:
                        epg_data[channel_id] = {
                            "id": channel_id,
                            "name": name,
                            "icon": icon_url
                        }
                    elif not epg_data[channel_id]["icon"] and icon_url:
                        # 如果当前EPG数据没有图标但新数据有，则更新
                        epg_data[channel_id]["icon"] = icon_url
                        
                logger.info(f"从 {epg_url} 解析出 {len(root.findall('.//channel'))} 个频道信息")
                    
            except ET.ParseError as e:
                logger.error(f"解析EPG XML数据失败: {str(e)}")
                continue
                
        except Exception as e:
            logger.error(f"处理EPG出错: {str(e)}")
            continue
    
    logger.info(f"EPG数据解析完成，共收集 {len(epg_data)} 个频道信息")
    return epg_data

def match_channels_with_epg(sources_data, epg_data, config):
    """将频道与EPG数据匹配"""
    if not epg_data:
        return sources_data
        
    logger.info("开始匹配频道与EPG数据")
    
    # 简化频道名称的函数，用于匹配
    def simplify_name(name):
        if not name:
            return ""
        # 移除空格和特殊字符
        simplified = re.sub(r'[^\w\u4e00-\u9fff]', '', name.lower())
        # 常见频道名称替换
        replacements = {
            'cctv': 'cctv',
            'central': 'cctv',
            'china': 'cctv',
            'hong': 'hk',
            'tai': 'tw',
            'television': 'tv',
            'channel': ''
        }
        for old, new in replacements.items():
            simplified = simplified.replace(old, new)
        return simplified
    
    # 创建EPG索引，用于快速查找
    epg_index = {}
    for epg_id, data in epg_data.items():
        simple_name = simplify_name(data["name"])
        if simple_name:
            epg_index[simple_name] = epg_id
    
    # 匹配频道
    matched_count = 0
    for channel_id, data in sources_data.items():
        info = data["info"]
        title = info.get('title', '')
        
        # 规范化频道名称
        normalized_title = normalize_channel_name(title, config)
        if normalized_title != title:
            info['title'] = normalized_title
            
        # 尝试直接匹配EPG ID
        if channel_id in epg_data:
            # 更新tvg-id和tvg-logo
            info['tvg-id'] = epg_data[channel_id]["id"]
            if not info.get('tvg-logo') and epg_data[channel_id]["icon"]:
                info['tvg-logo'] = epg_data[channel_id]["icon"]
            matched_count += 1
            continue
            
        # 尝试通过简化名称匹配
        simple_title = simplify_name(normalized_title)
        if simple_title in epg_index:
            epg_id = epg_index[simple_title]
            # 更新tvg-id和tvg-logo
            info['tvg-id'] = epg_data[epg_id]["id"]
            if not info.get('tvg-logo') and epg_data[epg_id]["icon"]:
                info['tvg-logo'] = epg_data[epg_id]["icon"]
            matched_count += 1
            continue
            
        # 尝试模糊匹配
        for epg_name, epg_id in epg_index.items():
            if (epg_name in simple_title) or (simple_title in epg_name and len(simple_title) > 3):
                # 更新tvg-id和tvg-logo
                info['tvg-id'] = epg_data[epg_id]["id"]
                if not info.get('tvg-logo') and epg_data[epg_id]["icon"]:
                    info['tvg-logo'] = epg_data[epg_id]["icon"]
                matched_count += 1
                break
    
    logger.info(f"频道与EPG匹配完成，成功匹配 {matched_count} 个频道")
    return sources_data

def normalize_channel_name(name, config):
    """规范化频道名称"""
    if not name:
        return name
        
    name_lower = name.lower()
    
    # 尝试匹配映射表
    if "channel_name_map" in config:
        for pattern, normalized_name in config["channel_name_map"].items():
            if re.search(pattern, name_lower):
                return normalized_name
                
    return name

def organize_channels(sources_data, config):
    """整理频道，去除重复，选择最佳源"""
    logger.info("开始整理频道...")
    
    # 按频道名称分组
    channels_by_name = {}
    
    # 整理频道
    for channel_id, data in sources_data.items():
        info = data["info"]
        title = info.get('title', '')
        
        # 跳过没有标题的频道
        if not title:
            continue
            
        # 收集有效源
        valid_sources = []
        for source in data["sources"]:
            if source["valid"]:
                valid_sources.append((source["url"], source["latency"]))
        
        # 如果没有有效源，跳过此频道
        if not valid_sources:
            continue
            
        # 按延迟排序
        valid_sources.sort(key=lambda x: x[1])
        
        # 只保留最佳源
        best_source = valid_sources[0][0]
        best_latency = valid_sources[0][1]
        
        # 将频道添加到按名称分组的集合中
        if title in channels_by_name:
            # 如果已存在相同名称的频道，比较延迟选择最佳的
            if best_latency < channels_by_name[title]["latency"]:
                channels_by_name[title] = {
                    "info": info,
                    "source": best_source,
                    "latency": best_latency
                }
        else:
            channels_by_name[title] = {
                "info": info,
                "source": best_source,
                "latency": best_latency
            }
    
    logger.info(f"频道整理完成，共 {len(channels_by_name)} 个唯一频道")
    return channels_by_name

def sort_channels_by_category(channels, config):
    """按分类对频道进行排序"""
    # 定义分类顺序
    category_order = {cat: idx for idx, cat in enumerate(config.get("categories", []))}
    default_order = len(category_order)
    
    def get_category_order(channel_data):
        channel_name, data = channel_data
        info = data["info"]
        group = info.get("group-title", "其他")
        return category_order.get(group, default_order)
    
    return sorted(channels.items(), key=get_category_order)

def generate_m3u(sorted_channels, output_path):
    """生成M3U文件"""
    logger.info(f"开始生成M3U文件: {output_path}")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        # 写入头部
        f.write("#EXTM3U\n")
        
        # 写入频道信息
        for channel_name, data in sorted_channels:
            info = data["info"]
            source = data["source"]
            
            # 构建EXTINF行
            extinf = build_extinf(info)
            f.write(f"{extinf}\n")
            f.write(f"{source}\n")
    
    logger.info(f"M3U文件生成完成: {output_path}, 共 {len(sorted_channels)} 个频道")
    return output_path

def build_extinf(info):
    """构建EXTINF行"""
    attrs = []
    
    for key, value in info.items():
        if key != 'title':
            attrs.append(f'{key}="{value}"')
    
    attrs_str = ' '.join(attrs)
    title = info.get('title', '')
    
    return f"#EXTINF:-1 {attrs_str},{title}"

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='IPTV直播源收集、检测与整理工具')
    parser.add_argument('--no-check', action='store_true', help='跳过直播源检测步骤')
    parser.add_argument('--no-epg', action='store_true', help='跳过EPG处理')
    parser.add_argument('--max-channels', type=int, default=0, help='最大处理频道数量(用于测试)')
    args = parser.parse_args()
    
    start_time = time.time()
    logger.info("开始IPTV直播源处理流程")
    
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
            
            # 保存结果为JSON文件（仅用于调试或API访问）
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
            
            # 下载和解析EPG数据
            epg_data = {}
            if not args.no_epg:
                epg_data = download_and_parse_epg(config)
                
                # 匹配频道与EPG
                serializable_results = match_channels_with_epg(serializable_results, epg_data, config)
            
            # 整理频道
            channels_by_name = organize_channels(serializable_results, config)
            
            # 按分类排序频道
            sorted_channels = sort_channels_by_category(channels_by_name, config)
            
            # 生成最终M3U文件
            output_file = config.get("output_file", "iptv_collection.m3u")
            output_path = os.path.join(output_dir, output_file)
            generate_m3u(sorted_channels, output_path)
        else:
            logger.info("跳过直播源检测步骤")
        
        end_time = time.time()
        logger.info(f"IPTV直播源处理完成，总耗时: {end_time - start_time:.2f}秒")
        
    except Exception as e:
        logger.error(f"程序运行出错: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
