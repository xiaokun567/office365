import json
import uuid
import re
from datetime import datetime
from typing import Dict, List, Optional


class ConfigManager:
    """配置文件管理器"""
    
    def __init__(self, config_path='config.json'):
        self.config_path = config_path
        self.config = self.load_config()
    
    def load_config(self) -> Dict:
        """加载配置文件"""
        default_config = {
            "subscriptions": [],
            "notification": {
                "webhook_url": "",
                "webhook_json": "",
                "expiration_warning_days": 30
            },
            "login_password": "xiaokun567",
            "check_interval_hours": 12
        }
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                
                # 检查文件是否为空
                if not content:
                    print(f"⚠️  配置文件为空，创建默认配置")
                    self.save_config(default_config)
                    return default_config
                
                # 尝试解析 JSON
                config = json.loads(content)
                
                # 验证配置结构，确保必要的字段存在
                if 'subscriptions' not in config:
                    config['subscriptions'] = []
                
                if 'notification' not in config:
                    config['notification'] = default_config['notification']
                else:
                    # 确保 notification 中有所有必要字段
                    if 'webhook_url' not in config['notification']:
                        config['notification']['webhook_url'] = ""
                    if 'webhook_json' not in config['notification']:
                        config['notification']['webhook_json'] = ""
                    if 'expiration_warning_days' not in config['notification']:
                        config['notification']['expiration_warning_days'] = 30
                
                if 'login_password' not in config:
                    config['login_password'] = "xiaokun567"
                
                if 'check_interval_hours' not in config:
                    config['check_interval_hours'] = 12
                
                # 保存修复后的配置
                self.save_config(config)
                return config
                
        except FileNotFoundError:
            # 如果文件不存在，创建默认配置
            print(f"📝 配置文件不存在，创建默认配置: {self.config_path}")
            self.save_config(default_config)
            return default_config
            
        except json.JSONDecodeError as e:
            # 如果 JSON 格式错误，备份旧文件并创建新配置
            print(f"❌ 配置文件 JSON 格式错误: {e}")
            
            # 备份损坏的配置文件
            import shutil
            from datetime import datetime
            backup_path = f"{self.config_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            try:
                shutil.copy(self.config_path, backup_path)
                print(f"📦 已备份损坏的配置到: {backup_path}")
            except Exception as backup_error:
                print(f"⚠️  备份失败: {backup_error}")
            
            # 创建新的默认配置
            print(f"📝 创建新的默认配置")
            self.save_config(default_config)
            return default_config
            
        except Exception as e:
            # 其他错误
            print(f"❌ 加载配置文件时出错: {e}")
            print(f"📝 使用默认配置")
            return default_config
    
    def save_config(self, config: Optional[Dict] = None) -> None:
        """保存配置文件"""
        if config is None:
            config = self.config
        
        try:
            # 先写入临时文件
            temp_path = f"{self.config_path}.tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            # 验证写入的文件是否有效
            with open(temp_path, 'r', encoding='utf-8') as f:
                json.load(f)  # 尝试读取验证
            
            # 如果验证成功，替换原文件
            import os
            if os.path.exists(self.config_path):
                # 备份当前配置
                backup_path = f"{self.config_path}.bak"
                import shutil
                shutil.copy(self.config_path, backup_path)
            
            # 替换为新配置
            os.replace(temp_path, self.config_path)
            
        except Exception as e:
            print(f"❌ 保存配置文件失败: {e}")
            # 清理临时文件
            try:
                import os
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except:
                pass
            raise
    
    def parse_curl_command(self, curl_command: str) -> Dict:
        """解析 curl 命令，提取 URL、headers 和 cookies"""
        result = {
            'url': '',
            'headers': {},
            'cookies': ''
        }
        
        # 提取 URL
        url_match = re.search(r"curl\s+'([^']+)'", curl_command)
        if url_match:
            result['url'] = url_match.group(1)
        
        # 提取所有 -H 参数（headers）
        header_pattern = r"-H\s+'([^:]+):\s*([^']+)'"
        headers = re.findall(header_pattern, curl_command)
        for key, value in headers:
            result['headers'][key] = value
        
        # 提取 -b 参数（cookies）
        cookie_match = re.search(r"-b\s+'([^']+)'", curl_command)
        if cookie_match:
            result['cookies'] = cookie_match.group(1)
        
        return result
    
    def generate_user_create_config(self, cookies: str) -> Dict:
        """从许可证查询的 Cookie 自动生成用户创建配置"""
        # 从 Cookie 中提取 ajaxsessionkey
        ajaxsessionkey = ''
        ajax_match = re.search(r's\.AjaxSessionKey=([^;]+)', cookies)
        if ajax_match:
            # URL 解码
            import urllib.parse
            ajaxsessionkey = urllib.parse.unquote(ajax_match.group(1))
        
        # 构建用户创建配置
        user_create_config = {
            'api_url': 'https://admin.cloud.microsoft/admin/api/users',
            'headers': {
                'accept': 'application/json, text/plain, */*',
                'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'ajaxsessionkey': ajaxsessionkey,
                'content-type': 'application/json',
                'origin': 'https://admin.cloud.microsoft',
                'priority': 'u=1, i',
                'referer': 'https://admin.cloud.microsoft/?',
                'sec-ch-ua': '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"macOS"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin',
                'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36',
                'x-adminapp-request': '/users/:/adduser',
                'x-ms-mac-appid': '1f5f6b98-4e5f-486f-a0af-099e5eeb474f',
                'x-ms-mac-hostingapp': 'M365AdminPortal',
                'x-ms-mac-target-app': 'MAC',
                'x-ms-mac-version': 'host-mac_2025.11.6.2'
            },
            'cookies': cookies
        }
        
        return user_create_config
    
    def add_subscription(self, name: str, curl_command: str, order: Optional[int] = None, 
                        user_create_curl: Optional[str] = None, auto_generate_user_config: bool = True) -> Dict:
        """添加新订阅
        
        Args:
            name: 订阅名称
            curl_command: 许可证查询的 curl 命令
            order: 编号（可选）
            user_create_curl: 用户创建的 curl 命令（可选）
            auto_generate_user_config: 是否自动生成用户创建配置（默认 True）
        """
        parsed = self.parse_curl_command(curl_command)
        
        # 从 URL 中提取 subscription_id
        subscription_id = ''
        id_match = re.search(r'id=([a-f0-9\-]+)', parsed['url'])
        if id_match:
            subscription_id = id_match.group(1)
        
        # 如果没有指定编号，自动分配
        if order is None:
            existing_orders = [sub.get('order', 0) for sub in self.config['subscriptions']]
            order = max(existing_orders) + 1 if existing_orders else 1
        
        subscription = {
            'id': str(uuid.uuid4()),
            'order': order,
            'name': name,
            'subscription_id': subscription_id,
            'api_url': parsed['url'],
            'headers': parsed['headers'],
            'cookies': parsed['cookies'],
            'status': 'unknown',
            'last_check_time': None,
            'subscription_data': None
        }
        
        # 如果提供了用户创建配置，解析并保存
        if user_create_curl:
            user_create_parsed = self.parse_curl_command(user_create_curl)
            subscription['user_create_config'] = {
                'api_url': user_create_parsed['url'],
                'headers': user_create_parsed['headers'],
                'cookies': user_create_parsed['cookies']
            }
            subscription['user_create_curl'] = user_create_curl
        elif auto_generate_user_config and parsed['cookies']:
            # 自动生成用户创建配置
            subscription['user_create_config'] = self.generate_user_create_config(parsed['cookies'])
            print(f"✅ 已自动生成用户创建配置（订阅：{name}）")
        
        self.config['subscriptions'].append(subscription)
        # 按编号排序
        self.config['subscriptions'].sort(key=lambda x: x.get('order', 999))
        self.save_config()
        return subscription
    
    def update_subscription(self, sub_id: str, data: Dict) -> Optional[Dict]:
        """更新订阅"""
        for i, sub in enumerate(self.config['subscriptions']):
            if sub['id'] == sub_id:
                # 如果提供了 curl_command，重新解析
                if 'curl_command' in data:
                    parsed = self.parse_curl_command(data['curl_command'])
                    sub['api_url'] = parsed['url']
                    sub['headers'] = parsed['headers']
                    sub['cookies'] = parsed['cookies']
                    
                    # 更新 subscription_id
                    id_match = re.search(r'id=([a-f0-9\-]+)', parsed['url'])
                    if id_match:
                        sub['subscription_id'] = id_match.group(1)
                    
                    # 自动生成或更新用户创建配置（迁移旧格式）
                    if parsed['cookies']:
                        had_old_curl = 'user_create_curl' in sub
                        had_config = 'user_create_config' in sub
                        
                        # 删除旧的手动配置标记，统一使用自动生成
                        if had_old_curl:
                            sub.pop('user_create_curl', None)
                            print(f"🔄 已将订阅 {sub['name']} 迁移到自动生成模式")
                        
                        # 自动生成/更新用户创建配置
                        sub['user_create_config'] = self.generate_user_create_config(parsed['cookies'])
                        
                        if not had_config and not had_old_curl:
                            print(f"✅ 已自动生成用户创建配置（订阅：{sub['name']}）")
                        elif had_config or had_old_curl:
                            print(f"✅ 已自动更新用户创建配置的 Cookie（订阅：{sub['name']}）")
                
                # 更新名称
                if 'name' in data:
                    sub['name'] = data['name']
                
                # 更新编号
                if 'order' in data:
                    sub['order'] = int(data['order'])
                
                # 更新用户创建配置
                if 'user_create_curl' in data:
                    user_create_curl = data['user_create_curl']
                    if user_create_curl:
                        user_create_parsed = self.parse_curl_command(user_create_curl)
                        sub['user_create_config'] = {
                            'api_url': user_create_parsed['url'],
                            'headers': user_create_parsed['headers'],
                            'cookies': user_create_parsed['cookies']
                        }
                        sub['user_create_curl'] = user_create_curl
                    else:
                        # 如果为空，删除配置
                        sub.pop('user_create_config', None)
                        sub.pop('user_create_curl', None)
                
                self.config['subscriptions'][i] = sub
                # 按编号排序
                self.config['subscriptions'].sort(key=lambda x: x.get('order', 999))
                self.save_config()
                return sub
        return None
    
    def delete_subscription(self, sub_id: str) -> bool:
        """删除订阅"""
        original_length = len(self.config['subscriptions'])
        self.config['subscriptions'] = [
            sub for sub in self.config['subscriptions'] 
            if sub['id'] != sub_id
        ]
        if len(self.config['subscriptions']) < original_length:
            self.save_config()
            return True
        return False
    
    def get_subscription(self, sub_id: str) -> Optional[Dict]:
        """获取单个订阅"""
        for sub in self.config['subscriptions']:
            if sub['id'] == sub_id:
                return sub
        return None
    
    def get_all_subscriptions(self) -> List[Dict]:
        """获取所有订阅（按编号排序）"""
        subscriptions = self.config['subscriptions']
        # 确保按编号排序
        subscriptions.sort(key=lambda x: x.get('order', 999))
        return subscriptions
    
    def get_subscription_by_order(self, order: int) -> Optional[Dict]:
        """根据编号获取订阅"""
        for sub in self.config['subscriptions']:
            if sub.get('order') == order:
                return sub
        return None
    
    def update_subscription_status(self, sub_id: str, status: str, data: Optional[Dict] = None, error_type: Optional[str] = None) -> None:
        """更新订阅状态"""
        for sub in self.config['subscriptions']:
            if sub['id'] == sub_id:
                sub['status'] = status
                sub['last_check_time'] = datetime.now().isoformat()
                if data:
                    sub['subscription_data'] = data
                # 保存错误类型（如果有）
                if error_type:
                    sub['error_type'] = error_type
                elif 'error_type' in sub:
                    # 如果检测成功，清除之前的错误类型
                    del sub['error_type']
                self.save_config()
                break
    
    def get_notification_config(self) -> Dict:
        """获取通知配置"""
        notification = self.config.get('notification', {
            'webhook_url': '',
            'webhook_json': '',
            'expiration_warning_days': 30
        })
        # 确保有默认值
        if 'expiration_warning_days' not in notification:
            notification['expiration_warning_days'] = 30
        return notification
    
    def update_notification_config(self, webhook_url: str, webhook_json: str, expiration_warning_days: int = 30) -> None:
        """更新通知配置"""
        self.config['notification'] = {
            'webhook_url': webhook_url,
            'webhook_json': webhook_json,
            'expiration_warning_days': expiration_warning_days
        }
        self.save_config()
    
    def get_login_password(self) -> str:
        """获取登录密码"""
        return self.config.get('login_password', 'xiaokun567')
    
    def update_login_password(self, new_password: str) -> None:
        """更新登录密码"""
        self.config['login_password'] = new_password
        self.save_config()
    
    def get_check_interval_hours(self) -> int:
        """获取检测间隔（小时）"""
        return self.config.get('check_interval_hours', 12)
    
    def update_check_interval_hours(self, hours: int) -> None:
        """更新检测间隔（小时）"""
        self.config['check_interval_hours'] = hours
        self.save_config()
