#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import logging
import requests
import argparse
import gzip
import xml.etree.ElementTree as ET
import re
from organizer import IPTVSourceOrganizer

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("iptv_organizer.log"),
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

def fetch_sources_data(config):
    """从收集器仓库获取源数据"""
    repo = config["collector_repo"]
    branch = config.get("collector_branch", "main")
    output_file = config["collector_output_file"]
    
    # 构建原始文件URL
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/{output_file}"
    
    logger.info(f"从 {url} 获取源数据")
    
    try:
        response = requests.get(url, timeout=60)
        if response.status_code == 200:
            sources_data = response.json()
            logger.info(f"成功获取源数据，包含 {len(sources_data)} 个频道")
            return sources_data
        else:
            logger.error(f"获取源数据失败，状态码: {response.status_code}")
            sys.exit(1)
    except Exception as e:
        logger.error(f"获取源数据出错: {str(e)}")
        sys.exit(1)

def download_and_parse_epg(epg_urls):
    """下载并解析EPG数据"""
    logger.info("开始下载和解析EPG数据")
    
    epg_data = {}  # 格式: {频道ID: {"id": id, "name": name, "icon": icon_url}}
    
    for epg_url in epg_urls:
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

def match_channels_with_epg(sources_data, epg_data):
    """将频道与EPG数据匹配"""
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
        
        # 尝试直接匹配EPG ID
        if channel_id in epg_data:
            # 更新tvg-id和tvg-logo
            info['tvg-id'] = epg_data[channel_id]["id"]
            if not info.get('tvg-logo') and epg_data[channel_id]["icon"]:
                info['tvg-logo'] = epg_data[channel_id]["icon"]
            matched_count += 1
            continue
            
        # 尝试通过简化名称匹配
        simple_title = simplify_name(title)
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

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='IPTV直播源整理工具')
    parser.add_argument('--local', help='使用本地JSON文件而不是从GitHub获取', default='')
    parser.add_argument('--no-epg', action='store_true', help='跳过EPG处理')
    args = parser.parse_args()
    
    logger.info("开始IPTV直播源整理流程")
    
    try:
        # 加载配置
        config = load_config()
        
        # 获取源数据
        if args.local:
            # 从本地文件加载
            logger.info(f"从本地文件 {args.local} 加载源数据")
            try:
                with open(args.local, 'r', encoding='utf-8') as f:
                    sources_data = json.load(f)
                logger.info(f"成功从本地文件加载源数据，包含 {len(sources_data)} 个频道")
            except Exception as e:
                logger.error(f"加载本地源数据失败: {str(e)}")
                sys.exit(1)
        else:
            # 从GitHub仓库获取
            sources_data = fetch_sources_data(config)
        
        # 处理EPG数据
        if not args.no_epg and "epg_urls" in config and config["epg_urls"]:
            # 下载和解析EPG
            epg_data = download_and_parse_epg(config["epg_urls"])
            
            # 匹配频道与EPG
            sources_data = match_channels_with_epg(sources_data, epg_data)
        
        # 整理源数据
        organizer = IPTVSourceOrganizer(config)
        output_path = organizer.organize(sources_data)
        
        logger.info(f"IPTV直播源整理完成，输出文件: {output_path}")
        
    except Exception as e:
        logger.error(f"程序运行出错: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
