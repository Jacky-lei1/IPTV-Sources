#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm

logger = logging.getLogger("IPTV-Checker")

class IPTVSourceChecker:
    def __init__(self, config):
        self.config = config
        self.results = {}  # 格式: {频道ID: [(URL, 有效性, 延迟), ...]}
        
    def check(self, channels):
        """检查所有频道的所有源的有效性"""
        logger.info(f"开始检查 {len(channels)} 个频道的直播源...")
        
        # 准备检查任务
        check_tasks = []
        for channel_id, (info, urls) in channels.items():
            for url in urls:
                check_tasks.append((channel_id, info, url))
        
        # 使用线程池并发检查
        with ThreadPoolExecutor(max_workers=self.config["max_workers"]) as executor:
            futures = {executor.submit(self._check_source, task[2]): task for task in check_tasks}
            
            # 显示进度条
            with tqdm(total=len(futures), desc="检查直播源") as pbar:
                for future in futures:
                    channel_id, info, url = futures[future]
                    try:
                        is_valid, latency = future.result()
                        
                        # 存储结果
                        if channel_id not in self.results:
                            self.results[channel_id] = {
                                "info": info,
                                "sources": []
                            }
                        
                        self.results[channel_id]["sources"].append((url, is_valid, latency))
                    except Exception as e:
                        logger.error(f"检查任务失败: {channel_id}, {url}, 错误: {str(e)}")
                    finally:
                        pbar.update(1)
        
        logger.info("直播源检查完成")
        return self.results
    
    def _check_source(self, url):
        """检查单个源是否有效，返回(是否有效, 延迟)"""
        try:
            start_time = time.time()
            
            # 使用ffprobe检查流
            process = subprocess.run(
                [
                    "ffprobe", 
                    "-v", "quiet", 
                    "-print_format", "json", 
                    "-show_streams", 
                    "-select_streams", "v", 
                    "-i", url
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.config["check_timeout"]
            )
            
            end_time = time.time()
            latency = end_time - start_time
            
            is_valid = process.returncode == 0 and b"streams" in process.stdout
            return is_valid, latency
        except subprocess.TimeoutExpired:
            return False, float('inf')
        except Exception as e:
            logger.error(f"检查源出错: {url}, 错误: {str(e)}")
            return False, float('inf')
