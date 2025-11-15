from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime


class TaskScheduler:
    """定时任务调度器"""
    
    def __init__(self, checker, config_manager, notifier):
        self.checker = checker
        self.config_manager = config_manager
        self.notifier = notifier
        self.scheduler = BackgroundScheduler()
    
    def start(self):
        """启动定时任务"""
        # 获取检测间隔
        check_interval = self.config_manager.get_check_interval_hours()
        
        # 按配置的间隔执行检测
        self.scheduler.add_job(
            self.run_daily_check,
            'interval',
            hours=check_interval,
            id='subscription_check',
            name=f'订阅检测（每{check_interval}小时）'
        )
        self.scheduler.start()
        print(f"定时任务已启动，将每{check_interval}小时执行一次检测")
    
    def stop(self):
        """停止定时任务"""
        self.scheduler.shutdown()
        print("定时任务已停止")
    
    def run_daily_check(self):
        """执行每日检测"""
        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始执行定时检测...")
        
        subscriptions = self.config_manager.get_all_subscriptions()
        
        if not subscriptions:
            print("没有配置的订阅项")
            return
        
        for sub in subscriptions:
            print(f"检测订阅: {sub['name']}")
            result = self.checker.check_subscription(sub['id'])
            
            if not result['success']:
                # 检测失败，发送通知
                error_type = result.get('error', '')
                error_message = result.get('message', '未知错误')
                
                if error_type == 'auth_failure':
                    print(f"  ❌ 认证失败")
                    self.notifier.notify_auth_failure(sub['name'])
                elif error_type == 'network_error':
                    print(f"  ❌ 网络错误: {error_message}")
                    # 网络错误通常是 Cookie 过期导致的 JSON 解析失败
                    self.notifier.notify_auth_failure(sub['name'])
                elif error_type == 'timeout':
                    print(f"  ❌ 请求超时")
                    # 超时也可能是认证问题
                    self.notifier.notify_auth_failure(sub['name'])
                else:
                    print(f"  ❌ 检测失败: {error_message}")
                    # 其他错误也发送通知
                    self.notifier.notify_auth_failure(sub['name'])
            else:
                # 检测成功
                status = result.get('status', '')
                data = result.get('data', {})
                
                if status == 'expired':
                    print(f"  ❌ 订阅已失效")
                    self.notifier.notify_subscription_expired(sub['name'])
                else:
                    # 检查是否即将到期
                    expiration_date = data.get('expirationDate', '')
                    if expiration_date:
                        days_remaining = self.checker.calculate_days_remaining(expiration_date)
                        
                        # 获取自定义的到期提醒天数
                        notification_config = self.config_manager.get_notification_config()
                        warning_days = notification_config.get('expiration_warning_days', 30)
                        
                        if 0 < days_remaining <= warning_days:
                            print(f"  ⏰ 即将到期，剩余 {days_remaining} 天")
                            self.notifier.notify_expiration_warning(sub['name'], days_remaining)
                        else:
                            print(f"  ✅ 状态正常，剩余 {days_remaining} 天")
                    else:
                        print(f"  ✅ 状态正常")
        
        print("定时检测完成\n")
