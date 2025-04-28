#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
import requests
from urllib.parse import urlparse

logger = logging.getLogger("IPTV-Collector")

class IPTVSourceCollector:
    def __init__(self, config):
        self.config = config
        self.sources_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "sources")
        os.makedirs(self.sources_dir, exist_ok=True)
        
    def collect(self):
        """收集所有配置的直播源"""
        logger.info("开始收集直播源...")
        
        collected_files = []
        for source_url in self.config["sources"]:
            try:
                # 获取源文件名
                filename = self._get_filename_from_url(source_url)
                local_path = os.path.join(self.sources_dir, filename)
                
                # 下载源文件
                logger.info(f"下载源: {source_url}")
                response = requests.get(
                    source_url, 
                    headers={"User-Agent": self.config["user_agent"]},
                    timeout=30
                )
                
                if response.status_code == 200:
                    with open(local_path, 'w', encoding='utf-8') as f:
                        f.write(response.text)
                    collected_files.append(local_path)
                    logger.info(f"成功下载源到: {local_path}")
                else:
                    logger.error(f"下载源失败: {source_url}, 状态码: {response.status_code}")
            except Exception as e:
                logger.error(f"处理源失败: {source_url}, 错误: {str(e)}")
        
        logger.info(f"收集完成, 共下载 {len(collected_files)} 个源文件")
        return collected_files
    
    def _get_filename_from_url(self, url):
        """从URL中获取文件名"""
        parsed = urlparse(url)
        path = parsed.path.strip('/')
        
        # 提取文件名
        filename = os.path.basename(path)
        
        # 如果没有扩展名，添加.m3u
        if not filename.endswith(('.m3u', '.m3u8')):
            filename = filename + '.m3u'
            
        # 添加域名前缀以避免冲突
        domain = parsed.netloc.split('.')[-2] if len(parsed.netloc.split('.')) > 1 else parsed.netloc
        filename = f"{domain}_{filename}"
        
        return filename
