#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import logging

logger = logging.getLogger("IPTV-Merger")

class IPTVSourceMerger:
    def __init__(self, config):
        self.config = config
        self.output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), self.config["output_dir"])
        os.makedirs(self.output_dir, exist_ok=True)
        
    def merge(self, check_results):
        """合并有效源并生成最终M3U文件"""
        logger.info("开始合并直播源...")
        
        # 按频道分组整理源
        channels = {}
        for channel_id, result in check_results.items():
            info = result["info"]
            valid_sources = [(url, latency) for url, is_valid, latency in result["sources"] if is_valid]
            
            # 如果没有有效源，跳过此频道
            if not valid_sources:
                continue
                
            # 按延迟排序
            valid_sources.sort(key=lambda x: x[1])
            
            # 只保留前5个源(避免列表过长)
            valid_sources = valid_sources[:5]
            
            channels[channel_id] = {
                "info": info,
                "sources": [url for url, _ in valid_sources]
            }
        
        # 生成M3U文件
        output_path = os.path.join(self.output_dir, self.config["output_file"])
        with open(output_path, 'w', encoding='utf-8') as f:
            # 写入头部
            f.write("#EXTM3U\n")
            
            # 按分类排序频道
            sorted_channels = self._sort_channels_by_category(channels)
            
            # 写入频道信息
            for channel_id, data in sorted_channels:
                info = data["info"]
                sources = data["sources"]
                
                # 构建EXTINF行
                extinf = self._build_extinf(info)
                f.write(f"{extinf}\n")
                
                # 写入所有源 - APTV支持的多源格式
                for i, url in enumerate(sources):
                    if i == 0:
                        # 主源
                        f.write(f"{url}\n")
                    else:
                        # 备用源 - APTV格式
                        f.write(f"#EXTBURL:{url}\n")
        
        logger.info(f"合并完成, 生成文件: {output_path}, 共 {len(channels)} 个频道")
        return output_path
    
    def _sort_channels_by_category(self, channels):
        """按分类对频道进行排序"""
        # 定义分类顺序
        category_order = {cat: idx for idx, cat in enumerate(self.config["categories"])}
        default_order = len(category_order)
        
        def get_category_order(channel_data):
            info = channel_data[1]["info"]
            group = info.get("group-title", "其他")
            return category_order.get(group, default_order)
        
        return sorted(channels.items(), key=get_category_order)
    
    def _build_extinf(self, info):
        """构建EXTINF行"""
        attrs = []
        
        for key, value in info.items():
            if key != 'title':
                attrs.append(f'{key}="{value}"')
        
        attrs_str = ' '.join(attrs)
        title = info.get('title', '')
        
        return f"#EXTINF:-1 {attrs_str},{title}"
