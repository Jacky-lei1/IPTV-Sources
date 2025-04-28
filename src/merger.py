#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import logging
import json
import subprocess
from collections import defaultdict

logger = logging.getLogger("IPTV-Merger")

class IPTVSourceMerger:
    def __init__(self, config):
        self.config = config
        self.output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), self.config["output_dir"])
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 频道名称规范化映射表
        self.channel_name_map = {
            # 央视频道标准化
            r'cctv-?1(\s|-|_|.)*': 'CCTV-1 综合',
            r'cctv-?2(\s|-|_|.)*': 'CCTV-2 财经',
            r'cctv-?3(\s|-|_|.)*': 'CCTV-3 综艺',
            r'cctv-?4(\s|-|_|.)*': 'CCTV-4 中文国际',
            r'cctv-?5(\s|-|_|.)*': 'CCTV-5 体育',
            r'cctv-?5\+(\s|-|_|.)*': 'CCTV-5+ 体育赛事',
            r'cctv-?6(\s|-|_|.)*': 'CCTV-6 电影',
            r'cctv-?7(\s|-|_|.)*': 'CCTV-7 国防军事',
            r'cctv-?8(\s|-|_|.)*': 'CCTV-8 电视剧',
            r'cctv-?9(\s|-|_|.)*': 'CCTV-9 纪录',
            r'cctv-?10(\s|-|_|.)*': 'CCTV-10 科教',
            r'cctv-?11(\s|-|_|.)*': 'CCTV-11 戏曲',
            r'cctv-?12(\s|-|_|.)*': 'CCTV-12 社会与法',
            r'cctv-?13(\s|-|_|.)*': 'CCTV-13 新闻',
            r'cctv-?14(\s|-|_|.)*': 'CCTV-14 少儿',
            r'cctv-?15(\s|-|_|.)*': 'CCTV-15 音乐',
            r'cctv-?16(\s|-|_|.)*': 'CCTV-16 奥林匹克',
            r'cctv-?17(\s|-|_|.)*': 'CCTV-17 农业农村',
            
            # 卫视频道标准化
            r'(湖南|湖南卫视)(\s|-|_|.)*': '湖南卫视',
            r'(浙江|浙江卫视)(\s|-|_|.)*': '浙江卫视',
            r'(江苏|江苏卫视)(\s|-|_|.)*': '江苏卫视',
            r'(东方|东方卫视)(\s|-|_|.)*': '东方卫视',
            r'(北京|北京卫视)(\s|-|_|.)*': '北京卫视',
            r'(广东|广东卫视)(\s|-|_|.)*': '广东卫视',
            r'(深圳|深圳卫视)(\s|-|_|.)*': '深圳卫视',
            r'(山东|山东卫视)(\s|-|_|.)*': '山东卫视',
            r'(湖北|湖北卫视)(\s|-|_|.)*': '湖北卫视',
            r'(安徽|安徽卫视)(\s|-|_|.)*': '安徽卫视',
            r'(东南|福建|东南卫视|福建卫视)(\s|-|_|.)*': '东南卫视',
            r'(江西|江西卫视)(\s|-|_|.)*': '江西卫视',
            r'(河南|河南卫视)(\s|-|_|.)*': '河南卫视',
            r'(河北|河北卫视)(\s|-|_|.)*': '河北卫视',
            r'(山西|山西卫视)(\s|-|_|.)*': '山西卫视',
            r'(辽宁|辽宁卫视)(\s|-|_|.)*': '辽宁卫视',
            r'(吉林|吉林卫视)(\s|-|_|.)*': '吉林卫视',
            r'(黑龙江|黑龙江卫视)(\s|-|_|.)*': '黑龙江卫视',
            r'(广西|广西卫视)(\s|-|_|.)*': '广西卫视',
            r'(云南|云南卫视)(\s|-|_|.)*': '云南卫视',
            r'(贵州|贵州卫视)(\s|-|_|.)*': '贵州卫视',
            r'(四川|四川卫视)(\s|-|_|.)*': '四川卫视',
            r'(重庆|重庆卫视)(\s|-|_|.)*': '重庆卫视',
            r'(陕西|陕西卫视)(\s|-|_|.)*': '陕西卫视',
            r'(甘肃|甘肃卫视)(\s|-|_|.)*': '甘肃卫视',
            r'(宁夏|宁夏卫视)(\s|-|_|.)*': '宁夏卫视',
            r'(青海|青海卫视)(\s|-|_|.)*': '青海卫视',
            r'(新疆|新疆卫视)(\s|-|_|.)*': '新疆卫视',
            r'(西藏|西藏卫视)(\s|-|_|.)*': '西藏卫视',
            r'(内蒙古|内蒙古卫视)(\s|-|_|.)*': '内蒙古卫视',
            r'(海南|海南卫视)(\s|-|_|.)*': '海南卫视',
            
            # 港澳台频道标准化
            r'(翡翠台|TVB翡翠台)(\s|-|_|.)*': '翡翠台',
            r'(明珠台|TVB明珠台)(\s|-|_|.)*': '明珠台',
            r'(J2|TVB J2)(\s|-|_|.)*': 'J2',
            r'(凤凰中文|凤凰卫视中文台)(\s|-|_|.)*': '凤凰卫视中文台',
            r'(凤凰资讯|凤凰卫视资讯台)(\s|-|_|.)*': '凤凰卫视资讯台',
            r'(凤凰香港|凤凰卫视香港台)(\s|-|_|.)*': '凤凰卫视香港台',
            r'(香港台|RTHK|RTHK31|RTHK32)(\s|-|_|.)*': '香港电台',
            r'(澳门|澳视|澳亚|澳视澳门|澳门卫视)(\s|-|_|.)*': '澳门卫视',
            r'(台湾|台视|中视|华视|民视)(\s|-|_|.)*': '台湾电视台',
            r'(TVBS|TVBS新闻台)(\s|-|_|.)*': 'TVBS新闻台',
        }
        
        # 可疑频道关键词（需特别验证）
        self.suspicious_keywords = [
            'xxx', 'adult', 'porn', '成人', '福利', '深夜', '午夜', '限制', 
            'movie', 'cinema', 'film', '电影', '影院', 
            'sports', 'espn', 'sky', 'star', '体育', '赛事',
            'fox', 'hbo', 'cnn', 'bbc', 'nbc', 'abc', 'cbs',
            'discovery', 'national', 'animal', 'history',
            'disney', 'cartoon', '动画', '卡通'
        ]
        
    def normalize_channel_name(self, name):
        """规范化频道名称"""
        if not name:
            return name
            
        name_lower = name.lower()
        
        # 尝试匹配映射表
        for pattern, normalized_name in self.channel_name_map.items():
            if re.match(pattern, name_lower):
                return normalized_name
                
        return name
        
    def verify_channel(self, url, claimed_info):
        """验证频道身份是否与声明一致"""
        claimed_name = claimed_info.get('title', '').lower()
        
        # 检查是否存在可疑关键词
        need_verification = False
        for keyword in self.suspicious_keywords:
            if keyword in claimed_name:
                need_verification = True
                break
                
        # CCTV频道需要额外验证
        if 'cctv' in claimed_name or '央视' in claimed_name:
            need_verification = True
            
        # 如果不需要验证，直接返回原始信息
        if not need_verification:
            return True, claimed_info
            
        try:
            # 使用ffprobe获取流信息
            cmd = [
                'ffprobe', 
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_programs',
                '-show_streams',
                '-i', url
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=5)
            
            if result.returncode == 0:
                output = result.stdout.decode('utf-8', errors='ignore')
                data = json.loads(output)
                
                # 尝试从流信息中获取频道名称
                actual_name = None
                if 'programs' in data and data['programs']:
                    for program in data['programs']:
                        if 'tags' in program and 'service_name' in program['tags']:
                            actual_name = program['tags']['service_name']
                            break
                
                # 从流信息中尝试获取更多元数据
                if not actual_name and 'streams' in data and data['streams']:
                    for stream in data['streams']:
                        if 'tags' in stream:
                            tags = stream['tags']
                            if 'title' in tags:
                                actual_name = tags['title']
                                break
                            elif 'service_name' in tags:
                                actual_name = tags['service_name']
                                break
                
                # 如果获取到了实际名称，检查是否与声明的名称匹配
                if actual_name:
                    actual_name_lower = actual_name.lower()
                    
                    # 检查CCTV频道
                    if 'cctv' in claimed_name:
                        if 'cctv' not in actual_name_lower:
                            logger.warning(f"频道身份不匹配: 声称是 {claimed_name}，但实际为 {actual_name}")
                            return False, claimed_info
                    
                    # 其他频道简单比较关键词
                    claimed_keywords = set(re.findall(r'\w+', claimed_name))
                    actual_keywords = set(re.findall(r'\w+', actual_name_lower))
                    
                    # 如果关键词重叠不足，视为不匹配
                    overlap = claimed_keywords.intersection(actual_keywords)
                    if len(overlap) < min(1, len(claimed_keywords) // 3):
                        logger.warning(f"频道身份可能不匹配: 声称是 {claimed_name}，但实际为 {actual_name}")
                        return False, claimed_info
            
            return True, claimed_info
            
        except Exception as e:
            logger.error(f"验证频道时出错: {url}, {str(e)}")
            return True, claimed_info  # 验证失败时默认通过，避免误删有效源
        
    def merge(self, check_results):
        """合并有效源并生成最终M3U文件"""
        logger.info("开始合并直播源...")
        
        # 按频道分组整理源
        channels_by_name = defaultdict(list)
        
        # 第一步：整理和验证频道
        for channel_id, result in check_results.items():
            info = result["info"]
            title = info.get('title', '')
            
            # 规范化频道名称
            normalized_title = self.normalize_channel_name(title)
            if normalized_title != title:
                info['title'] = normalized_title
                logger.info(f"规范化频道名称: {title} -> {normalized_title}")
            
            # 收集有效源
            valid_sources = []
            for url, is_valid, latency in result["sources"]:
                if is_valid:
                    # 验证频道身份
                    is_verified, _ = self.verify_channel(url, info)
                    if is_verified:
                        valid_sources.append((url, latency))
            
            # 如果没有有效源，跳过此频道
            if not valid_sources:
                continue
                
            # 按延迟排序
            valid_sources.sort(key=lambda x: x[1])
            
            # 只保留最佳源
            best_source = valid_sources[0][0]
            
            # 将频道添加到按名称分组的集合中
            channels_by_name[normalized_title].append({
                "info": info,
                "source": best_source,
                "latency": valid_sources[0][1]
            })
        
        # 第二步：对于每个频道名称，选择最佳源
        final_channels = []
        for channel_name, sources in channels_by_name.items():
            # 按延迟排序
            sources.sort(key=lambda x: x['latency'])
            
            # 选择最佳源
            best_channel = sources[0]
            final_channels.append((channel_name, best_channel))
        
        # 生成M3U文件
        output_path = os.path.join(self.output_dir, self.config["output_file"])
        with open(output_path, 'w', encoding='utf-8') as f:
            # 写入头部
            f.write("#EXTM3U\n")
            
            # 按分类排序频道
            sorted_channels = self._sort_channels_by_category(final_channels)
            
            # 写入频道信息
            for channel_name, data in sorted_channels:
                info = data["info"]
                source = data["source"]
                
                # 构建EXTINF行
                extinf = self._build_extinf(info)
                f.write(f"{extinf}\n")
                f.write(f"{source}\n")
        
        logger.info(f"合并完成, 生成文件: {output_path}, 共 {len(final_channels)} 个频道")
        return output_path
    
    def _sort_channels_by_category(self, channels):
        """按分类对频道进行排序"""
        # 定义分类顺序
        category_order = {cat: idx for idx, cat in enumerate(self.config["categories"])}
        default_order = len(category_order)
        
        def get_category_order(channel_data):
            channel_name, data = channel_data
            info = data["info"]
            group = info.get("group-title", "其他")
            return category_order.get(group, default_order)
        
        return sorted(channels, key=get_category_order)
    
    def _build_extinf(self, info):
        """构建EXTINF行"""
        attrs = []
        
        for key, value in info.items():
            if key != 'title':
                attrs.append(f'{key}="{value}"')
        
        attrs_str = ' '.join(attrs)
        title = info.get('title', '')
        
        return f"#EXTINF:-1 {attrs_str},{title}"
