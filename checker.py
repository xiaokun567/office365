import requests
from datetime import datetime
from typing import Dict, Optional


class SubscriptionChecker:
    """订阅检测器"""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
    
    def check_subscription(self, subscription_id: str) -> Dict:
        """检测订阅状态"""
        subscription = self.config_manager.get_subscription(subscription_id)
        if not subscription:
            return {
                'success': False,
                'error': '订阅不存在'
            }
        
        try:
            # 准备请求
            headers = subscription['headers']
            cookies_str = subscription['cookies']
            
            # 如果订阅配置的 cookie 为空，尝试使用用户创建配置的 cookie
            if not cookies_str or cookies_str.strip() == '':
                user_create_config = subscription.get('user_create_config')
                if user_create_config and user_create_config.get('cookies'):
                    cookies_str = user_create_config['cookies']
                    print(f"[检测订阅] 使用用户创建配置的 cookie")
            
            # 将 cookies 字符串转换为字典
            cookies = {}
            if cookies_str:
                for cookie in cookies_str.split('; '):
                    if '=' in cookie:
                        key, value = cookie.split('=', 1)
                        cookies[key] = value
            
            # 发送请求
            response = requests.get(
                subscription['api_url'],
                headers=headers,
                cookies=cookies,
                timeout=30
            )
            
            # 检查响应状态
            if response.status_code == 401 or response.status_code == 403:
                self.config_manager.update_subscription_status(
                    subscription_id, 
                    'error',
                    None,
                    'auth_failure'
                )
                return {
                    'success': False,
                    'error': 'auth_failure',
                    'message': '认证失败，Cookie 可能已过期'
                }
            
            if response.status_code != 200:
                self.config_manager.update_subscription_status(
                    subscription_id,
                    'error',
                    None,
                    'api_error'
                )
                return {
                    'success': False,
                    'error': 'api_error',
                    'message': f'API 返回错误状态码: {response.status_code}'
                }
            
            # 解析响应
            data = response.json()
            parsed_data = self.parse_response(data)
            
            # 判断订阅状态
            status = 'active' if parsed_data.get('state') == 'Active' else 'expired'
            
            # 更新配置
            self.config_manager.update_subscription_status(
                subscription_id,
                status,
                parsed_data
            )
            
            return {
                'success': True,
                'data': parsed_data,
                'status': status
            }
            
        except requests.exceptions.Timeout:
            self.config_manager.update_subscription_status(
                subscription_id,
                'error',
                None,
                'timeout'
            )
            return {
                'success': False,
                'error': 'timeout',
                'message': '请求超时'
            }
        except requests.exceptions.RequestException as e:
            self.config_manager.update_subscription_status(
                subscription_id,
                'error',
                None,
                'network_error'
            )
            return {
                'success': False,
                'error': 'network_error',
                'message': f'网络错误: {str(e)}'
            }
        except Exception as e:
            self.config_manager.update_subscription_status(
                subscription_id,
                'error',
                None,
                'unknown_error'
            )
            return {
                'success': False,
                'error': 'unknown_error',
                'message': f'未知错误: {str(e)}'
            }
    
    def parse_response(self, response_json: Dict) -> Dict:
        """解析 API 响应 - 兼容新旧两种接口"""
        # 检查是否是订阅列表响应（新接口 - 多许可证支持）
        if '@odata.context' in response_json and 'value' in response_json:
            return self.parse_subscriptions_list(response_json)
        
        # 单个订阅响应（旧接口）
        parsed = {
            'name': response_json.get('name', ''),
            'totalLicenses': 0,
            'consumedUnits': 0,
            'expirationDate': response_json.get('expirationDate', ''),
            'state': response_json.get('state', ''),
            'skuPartNumber': '',
            'is_multi_license': False,
            'api_type': 'single'  # 标记为旧接口
        }
        
        # 获取许可证信息
        parsed['totalLicenses'] = response_json.get('totalLicenses', 0)
        
        # 从 subscribedSku 获取已使用数量
        subscribed_sku = response_json.get('subscribedSku', {})
        if subscribed_sku:
            parsed['consumedUnits'] = subscribed_sku.get('consumedUnits', 0)
            parsed['skuPartNumber'] = subscribed_sku.get('skuPartNumber', '')
        
        return parsed
    
    def parse_subscriptions_list(self, response_json: Dict) -> Dict:
        """解析订阅列表响应 - 处理多许可证情况（新接口）"""
        subscriptions = response_json.get('value', [])
        
        if not subscriptions:
            return {
                'name': '',
                'totalLicenses': 0,
                'consumedUnits': 0,
                'expirationDate': '',
                'state': '',
                'skuPartNumber': '',
                'is_multi_license': False,
                'api_type': 'list'
            }
        
        # 按 skuId 分组订阅
        sku_groups = {}
        for sub in subscriptions:
            # 只处理活跃状态的订阅
            if sub.get('state') != 'Active':
                continue
                
            subscribed_sku = sub.get('subscribedSku')
            if not subscribed_sku:
                continue
                
            sku_id = subscribed_sku.get('skuId')
            if not sku_id:
                continue
            
            if sku_id not in sku_groups:
                sku_groups[sku_id] = []
            sku_groups[sku_id].append(sub)
        
        # 如果没有活跃订阅，检查是否有非活跃订阅
        if not sku_groups:
            # 尝试获取第一个订阅的信息
            first_sub = subscriptions[0] if subscriptions else {}
            return {
                'name': first_sub.get('name', ''),
                'totalLicenses': first_sub.get('totalLicenses', 0),
                'consumedUnits': 0,
                'expirationDate': first_sub.get('expirationDate', ''),
                'state': first_sub.get('state', 'Inactive'),
                'skuPartNumber': first_sub.get('subscribedSku', {}).get('skuPartNumber', '') if first_sub.get('subscribedSku') else '',
                'is_multi_license': False,
                'api_type': 'list'
            }
        
        # 选择许可证数量最多的 SKU 组
        main_sku_id = max(sku_groups.keys(), key=lambda k: len(sku_groups[k]))
        main_subscriptions = sku_groups[main_sku_id]
        
        # 判断是否为多许可证
        is_multi = len(main_subscriptions) > 1
        
        # 聚合数据
        first_sub = main_subscriptions[0]
        subscribed_sku = first_sub.get('subscribedSku', {})
        
        # 计算总许可证数（每个订阅的许可证数）
        total_licenses_per_sub = first_sub.get('totalLicenses', 0)
        total_subscriptions = len(main_subscriptions)
        
        # 从 subscribedSku 获取实际的总许可证数和消费数
        actual_total = subscribed_sku.get('prepaidUnits', {}).get('enabled', 0)
        consumed_units = subscribed_sku.get('consumedUnits', 0)
        
        # 找到最晚的到期日期
        expiration_dates = [sub.get('expirationDate', '') for sub in main_subscriptions if sub.get('expirationDate')]
        latest_expiration = max(expiration_dates) if expiration_dates else ''
        
        parsed = {
            'name': first_sub.get('name', ''),
            'totalLicenses': actual_total,  # 使用实际总数
            'consumedUnits': consumed_units,
            'expirationDate': latest_expiration,
            'state': 'Active',
            'skuPartNumber': subscribed_sku.get('skuPartNumber', ''),
            'is_multi_license': is_multi,
            'api_type': 'list'  # 标记为新接口
        }
        
        # 如果是多许可证，添加详细信息
        if is_multi:
            parsed['multi_license_info'] = {
                'subscription_count': total_subscriptions,
                'licenses_per_subscription': total_licenses_per_sub,
                'subscriptions': [
                    {
                        'id': sub.get('id'),
                        'order_id': sub.get('orderId'),
                        'licenses': sub.get('totalLicenses', 0),
                        'expiration_date': sub.get('expirationDate', ''),
                        'start_date': sub.get('startDate', '')
                    }
                    for sub in main_subscriptions
                ]
            }
        
        return parsed
    
    def calculate_days_remaining(self, expiration_date: str) -> int:
        """计算剩余天数"""
        if not expiration_date:
            return 0
        
        try:
            exp_date = datetime.fromisoformat(expiration_date.replace('Z', '+00:00'))
            now = datetime.now(exp_date.tzinfo)
            delta = exp_date - now
            return max(0, delta.days)
        except Exception:
            return 0
    
    def calculate_usage_percentage(self, consumed: int, total: int) -> float:
        """计算使用百分比"""
        if total == 0:
            return 0.0
        return round((consumed / total) * 100, 1)
