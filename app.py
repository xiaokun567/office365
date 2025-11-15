from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from config_manager import ConfigManager
from checker import SubscriptionChecker
from notifier import Notifier
from scheduler import TaskScheduler
from user_creator import UserCreator
from user_lister import UserLister
from user_activation import UserActivationService
import atexit
from functools import wraps
from datetime import datetime
import hashlib

app = Flask(__name__)
app.secret_key = 'office365_monitor_secret_key_2024'

# 默认登录密码
DEFAULT_PASSWORD = 'xiaokun567'

# 初始化组件
config_manager = ConfigManager('config.json')
checker = SubscriptionChecker(config_manager)
user_creator = UserCreator(config_manager)
user_lister = UserLister(config_manager)
user_activation = UserActivationService(config_manager)

# 获取通知配置
notification_config = config_manager.get_notification_config()
notifier = Notifier(notification_config)

# 初始化定时任务
scheduler = TaskScheduler(checker, config_manager, notifier)
scheduler.start()

# 确保应用退出时停止定时任务
atexit.register(lambda: scheduler.stop())


# ============ 登录验证装饰器 ============

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# ============ 登录路由 ============

@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    if request.method == 'POST':
        password = request.form.get('password')
        current_password = config_manager.get_login_password()
        
        if password == current_password:
            session['logged_in'] = True
            # 检查是否是默认密码
            if current_password == DEFAULT_PASSWORD:
                session['need_change_password'] = True
                return redirect(url_for('change_password'))
            return redirect(url_for('index'))
        else:
            # 登录失败，发送通知
            notifier.send_notification(
                f"⚠️ Office 365 监控系统登录失败\n\n"
                f"尝试密码: {password}\n"
                f"IP地址: {request.remote_addr}\n"
                f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            return render_template('login.html', error='密码错误')
    return render_template('login.html')


@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """修改密码页面"""
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not new_password or len(new_password) < 6:
            return render_template('change_password.html', error='密码长度至少6位')
        
        if new_password != confirm_password:
            return render_template('change_password.html', error='两次输入的密码不一致')
        
        # 更新密码
        config_manager.update_login_password(new_password)
        session.pop('need_change_password', None)
        
        return render_template('change_password.html', success=True)
    
    return render_template('change_password.html')


@app.route('/logout')
def logout():
    """登出"""
    session.clear()
    return redirect(url_for('login'))


# ============ 页面路由 ============

@app.route('/')
@login_required
def index():
    """仪表板页面"""
    # 如果需要修改密码，重定向
    if session.get('need_change_password'):
        return redirect(url_for('change_password'))
    return render_template('index.html')


@app.route('/settings')
@login_required
def settings():
    """设置页面"""
    if session.get('need_change_password'):
        return redirect(url_for('change_password'))
    return render_template('settings.html')


# ============ API 路由 ============

@app.route('/api/subscriptions', methods=['GET'])
@login_required
def get_subscriptions():
    """获取所有订阅"""
    subscriptions = config_manager.get_all_subscriptions()
    
    # 为每个订阅计算额外信息
    for sub in subscriptions:
        if sub.get('subscription_data'):
            data = sub['subscription_data']
            if data.get('expirationDate'):
                sub['days_remaining'] = checker.calculate_days_remaining(data['expirationDate'])
            else:
                sub['days_remaining'] = 0
            
            sub['usage_percentage'] = checker.calculate_usage_percentage(
                data.get('consumedUnits', 0),
                data.get('totalLicenses', 0)
            )
    
    return jsonify({
        'success': True,
        'data': subscriptions
    })


@app.route('/api/subscriptions', methods=['POST'])
@login_required
def create_subscription():
    """创建新订阅"""
    data = request.json
    
    if not data.get('name') or not data.get('curl_command'):
        return jsonify({
            'success': False,
            'error': '缺少必要参数'
        }), 400
    
    try:
        order = data.get('order')
        user_create_curl = data.get('user_create_curl')
        subscription = config_manager.add_subscription(
            data['name'],
            data['curl_command'],
            order,
            user_create_curl
        )
        return jsonify({
            'success': True,
            'data': subscription
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/subscriptions/<sub_id>', methods=['PUT'])
@login_required
def update_subscription(sub_id):
    """更新订阅"""
    data = request.json
    
    subscription = config_manager.update_subscription(sub_id, data)
    
    if subscription:
        return jsonify({
            'success': True,
            'data': subscription
        })
    else:
        return jsonify({
            'success': False,
            'error': '订阅不存在'
        }), 404


@app.route('/api/subscriptions/<sub_id>', methods=['DELETE'])
@login_required
def delete_subscription(sub_id):
    """删除订阅"""
    success = config_manager.delete_subscription(sub_id)
    
    if success:
        return jsonify({
            'success': True
        })
    else:
        return jsonify({
            'success': False,
            'error': '订阅不存在'
        }), 404


@app.route('/api/subscriptions/<sub_id>/check', methods=['POST'])
@login_required
def check_subscription(sub_id):
    """手动检测订阅"""
    result = checker.check_subscription(sub_id)
    
    if result['success']:
        status = result.get('status', '')
        data = result.get('data', {})
        subscription = config_manager.get_subscription(sub_id)
        
        # 获取自定义的到期提醒天数
        notification_config = config_manager.get_notification_config()
        warning_days = notification_config.get('expiration_warning_days', 30)
        
        if status == 'expired':
            notifier.notify_subscription_expired(subscription['name'])
        elif status == 'active':
            expiration_date = data.get('expirationDate', '')
            if expiration_date:
                days_remaining = checker.calculate_days_remaining(expiration_date)
                if 0 < days_remaining <= warning_days:
                    notifier.notify_expiration_warning(subscription['name'], days_remaining)
        
        if data.get('expirationDate'):
            result['days_remaining'] = checker.calculate_days_remaining(data['expirationDate'])
        result['usage_percentage'] = checker.calculate_usage_percentage(
            data.get('consumedUnits', 0),
            data.get('totalLicenses', 0)
        )
        
        return jsonify(result)
    else:
        error_type = result.get('error', '')
        subscription = config_manager.get_subscription(sub_id)
        
        if error_type == 'auth_failure' and subscription:
            notifier.notify_auth_failure(subscription['name'])
        
        return jsonify(result), 400


@app.route('/api/users/create', methods=['POST'])
@login_required
def create_user_api():
    """Web界面创建用户API"""
    try:
        data = request.get_json()
        subscription_id = data.get('subscription_id')
        username = data.get('username')
        password = data.get('password')
        
        if not subscription_id or not username:
            return jsonify({
                'success': False,
                'error': '缺少必要参数'
            }), 400
        
        if not password:
            import random
            import string
            password_chars = (
                random.choices(string.ascii_uppercase, k=3) +
                random.choices(string.ascii_lowercase, k=3) +
                random.choices(string.digits, k=3) +
                random.choices('!@#$%', k=3)
            )
            random.shuffle(password_chars)
            password = ''.join(password_chars)
        
        result = user_creator.create_user(subscription_id, username, password)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'创建用户失败: {str(e)}'
        }), 500


@app.route('/api/users/list/<sub_id>', methods=['GET'])
@login_required
def list_users_api(sub_id):
    """Web界面查询用户列表API"""
    try:
        result = user_lister.list_users(sub_id)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'查询用户失败: {str(e)}'
        }), 500


@app.route('/api/users/activation/<sub_id>/<username>', methods=['GET'])
@login_required
def query_user_activation_api(sub_id, username):
    """Web界面查询用户激活信息API"""
    try:
        result = user_activation.query_user_activation(sub_id, username)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'查询激活信息失败: {str(e)}'
        }), 500


@app.route('/api/users/activation/all/<sub_id>', methods=['GET'])
@login_required
def query_all_users_activation_api(sub_id):
    """Web界面查询所有用户激活信息API"""
    try:
        result = user_activation.query_all_users_activation(sub_id)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'批量查询激活信息失败: {str(e)}'
        }), 500


# ============ Webhook 配置 API ============

@app.route('/api/webhook-config', methods=['GET'])
@login_required
def get_webhook_config():
    """获取 Webhook 配置"""
    config = config_manager.get_notification_config()
    return jsonify({
        'success': True,
        'data': config
    })


@app.route('/api/webhook-config', methods=['POST'])
@login_required
def update_webhook_config():
    """更新 Webhook 配置"""
    data = request.json
    
    webhook_url = data.get('webhook_url', '')
    webhook_json = data.get('webhook_json', '')
    expiration_warning_days = data.get('expiration_warning_days', 30)
    
    # 验证天数
    try:
        expiration_warning_days = int(expiration_warning_days)
        if expiration_warning_days < 1 or expiration_warning_days > 365:
            return jsonify({
                'success': False,
                'error': '到期提醒天数必须在 1-365 之间'
            }), 400
    except (ValueError, TypeError):
        expiration_warning_days = 30
    
    config_manager.update_notification_config(webhook_url, webhook_json, expiration_warning_days)
    
    # 重新初始化 notifier
    global notifier
    notification_config = config_manager.get_notification_config()
    notifier = Notifier(notification_config)
    
    return jsonify({
        'success': True,
        'message': 'Webhook 配置已更新'
    })


@app.route('/api/webhook-test', methods=['POST'])
@login_required
def test_webhook():
    """测试 Webhook 通知"""
    try:
        # 发送测试消息
        test_message = "🧪 这是一条测试通知\n\nOffice 365 订阅监控系统\n测试时间: " + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        success = notifier.send_notification(test_message)
        
        if success:
            return jsonify({
                'success': True,
                'message': '测试通知已发送'
            })
        else:
            return jsonify({
                'success': False,
                'error': '通知发送失败，请检查 Webhook 配置'
            }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'发送失败: {str(e)}'
        }), 500


@app.route('/api/check-interval', methods=['GET'])
@login_required
def get_check_interval():
    """获取检测间隔"""
    interval = config_manager.get_check_interval_hours()
    return jsonify({
        'success': True,
        'data': {
            'check_interval_hours': interval
        }
    })


@app.route('/api/check-interval', methods=['POST'])
@login_required
def update_check_interval():
    """更新检测间隔"""
    data = request.json
    hours = data.get('check_interval_hours', 12)
    
    try:
        hours = int(hours)
        if hours < 1 or hours > 168:  # 1小时到7天
            return jsonify({
                'success': False,
                'error': '检测间隔必须在 1-168 小时之间'
            }), 400
    except (ValueError, TypeError):
        return jsonify({
            'success': False,
            'error': '无效的小时数'
        }), 400
    
    config_manager.update_check_interval_hours(hours)
    
    # 重启定时任务
    global scheduler
    scheduler.stop()
    scheduler = TaskScheduler(checker, config_manager, notifier)
    scheduler.start()
    
    return jsonify({
        'success': True,
        'message': f'检测间隔已更新为 {hours} 小时'
    })


if __name__ == '__main__':
    print("Office 365 订阅监控系统启动中...")
    print("访问地址: http://localhost:5000")
    app.run(host='0.0.0.0', port=5005, debug=True)
