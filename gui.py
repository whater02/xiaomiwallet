import flet as ft
import json
import os
import requests
import time
from datetime import datetime
from typing import List, Dict, Optional, Union, Any
import threading
import random
from pathlib import Path

CONFIG_PATH = "xiaomiconfig.json"
API_HOST = "m.jr.airstarfinance.net"
LOG_PATH = "task_logs"
USER_AGENT_MOBILE = (
    'Mozilla/5.0 (Linux; U; Android 14; zh-CN; M2012K11AC Build/UKQ1.230804.001; '
    'AppBundle/com.mipay.wallet; AppVersionName/6.89.1.5275.2323; AppVersionCode/20577595; '
    'MiuiVersion/stable-V816.0.13.0.UMNCNXM; DeviceId/alioth; NetworkType/WIFI; '
    'mix_version; WebViewVersion/118.0.0.0) AppleWebKit/537.36 (KHTML, like Gecko) '
    'Version/4.0 Mobile Safari/537.36 XiaoMi/MiuiBrowser/4.3'
)

class XiaomiAccount:
    def __init__(self, us, user_id=None, pass_token=None, security_token=None):
        self.us = us.strip()
        self.user_id = user_id
        self.pass_token = pass_token
        self.security_token = security_token

    @staticmethod
    def load_accounts() -> List[Dict]:
        """加载账号配置"""
        if not os.path.isfile(CONFIG_PATH):
            return []
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                content = f.read()
                if not content:
                    return []
                return json.loads(content)
        except json.JSONDecodeError as e:
            print(f"❌ JSON格式错误: {e.msg}")
            return []
        except Exception as e:
            print(f"❌ 读取配置文件时发生未知错误: {str(e)}")
            return []

    @classmethod
    def from_json(cls, us):
        accounts = cls.load_accounts()
        for acc in accounts:
            if acc.get("data", {}).get("us") == us.strip():
                data = acc.get("data", {})
                return cls(
                    us=data.get("us"),
                    user_id=data.get("userId"),
                    pass_token=data.get("passToken"),
                    security_token=data.get("securityToken")
                )
        return None

    def save_to_json(self):
        """更新或添加账号数据到 xiaomiconfig.json"""
        accounts = self.load_accounts()
        updated = False
        for acc in accounts:
            if acc.get("data", {}).get("us") == self.us:
                acc["data"].update({
                    "us": self.us,
                    "userId": str(self.user_id) if self.user_id else None,
                    "passToken": self.pass_token,
                    "securityToken": self.security_token
                })
                updated = True
                break
        
        if not updated:
            new_account = {
                "data": {
                    "us": self.us,
                    "userId": str(self.user_id) if self.user_id else None,
                    "passToken": self.pass_token,
                    "securityToken": self.security_token
                }
            }
            accounts.append(new_account)
            
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(accounts, f, indent=4, ensure_ascii=False)
            print(f"✅ 账号 '{self.us}' 数据已成功保存！")
            return True
        except Exception as e:
            print(f"❌ 保存文件失败: {e}")
            return False

    def get_login_qr(self):
        """获取登录二维码信息"""
        url = "https://account.xiaomi.com/longPolling/loginUrl"
        querystring = {
            "_group": "DEFAULT", "_qrsize": "240", "qs": "?callback=https%3A%2F%2Faccount.xiaomi.com%2Fsts%3Fsign%3DZvAtJIzsDsFe60LdaPa76nNNP58%253D%26followup%3Dhttps%253A%252F%252Faccount.xiaomi.com%252Fpass%252Fauth%252Fsecurity%252Fhome%26sid%3Dpassport&sid=passport&_group=DEFAULT",
            "bizDeviceType": "", "callback": "https://account.xiaomi.com/sts?sign=ZvAtJIzsDsFe60LdaPa76nNNP58=&followup=https://account.xiaomi.com/pass/auth/security/home&sid=passport",
            "_hasLogo": "false", "theme": "", "sid": "passport", "needTheme": "false", "showActiveX": "false", "serviceParam": "{\"checkSafePhone\":false,\"checkSafeAddress\":false,\"lsrp_score\":0.0}",
            "_locale": "zh_CN", "_sign": "2&V1_passport&BUcblfwZ4tX84axhVUaw8t6yi2E=", "_dc": str(int(time.time() * 1000))
        }
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"}
        
        try:
            response = requests.get(url, headers=headers, params=querystring, timeout=10)
            response.raise_for_status()
            response_text = response.text
            if "&&&START&&&" in response_text:
                return json.loads(response_text.split("&&&START&&&", 1)[-1].strip())
            return response.json()
        except requests.RequestException as e:
            print(f"❌ 网络请求失败: {e}")
            return None
        except json.JSONDecodeError:
            print("❌ 解析服务器响应失败。")
            return None

class ApiRequest:
    """封装 API 请求，统一管理会话、Cookie 和请求头。"""
    def __init__(self, cookies: Union[str, Dict[str, str]]):
        self.session = requests.Session()
        self.base_headers = {'Host': API_HOST, 'User-Agent': USER_AGENT_MOBILE}
        self.update_cookies(cookies)

    @staticmethod
    def _parse_cookies(cookies_str: str) -> Dict[str, str]:
        """将 Cookie 字符串解析为字典。"""
        return {
            k.strip(): v for k, v in
            (item.split('=', 1) for item in cookies_str.split(';') if '=' in item)
        }

    def update_cookies(self, cookies: Union[str, Dict[str, str]]) -> None:
        """更新会话中的 Cookie。"""
        if not cookies:
            return
        dict_cookies = self._parse_cookies(cookies) if isinstance(cookies, str) else cookies
        self.session.cookies.update(dict_cookies)
        self.base_headers['Cookie'] = '; '.join([f"{k}={v}" for k, v in dict_cookies.items()])

    def request(self, method: str, url: str, **kwargs) -> Optional[Dict[str, Any]]:
        """发送一个 HTTP 请求。"""
        headers = {**self.base_headers, **kwargs.pop('headers', {})}
        try:
            resp = self.session.request(method.upper(), url, verify=False, headers=headers, timeout=15, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            print(f"  [Request Error] {e}")
            return None
        except (json.JSONDecodeError, AttributeError):
            print(f"  [JSON Parse Error] 无法解析服务器响应: {getattr(resp, 'text', 'No Response Text')[:100]}")
            return None

    def get(self, url: str, **kwargs) -> Optional[Dict[str, Any]]:
        """发送 GET 请求。"""
        return self.request('GET', url, **kwargs)

    def post(self, url: str, **kwargs) -> Optional[Dict[str, Any]]:
        """发送 POST 请求。"""
        return self.request('POST', url, **kwargs)

class RNL:
    """封装小米钱包任务的具体业务逻辑。"""
    def __init__(self, api_request: ApiRequest):
        self.api = api_request
        self.activity_code = '2211-videoWelfare'
        self.t_id: Optional[str] = None
        self.total_days: str = "未知"
        self.today_records: List[Dict[str, Any]] = []
        self.error_info: str = ""

    def get_task_list(self) -> Optional[List[Dict[str, Any]]]:
        """获取任务列表。"""
        url = f"https://{API_HOST}/mp/api/generalActivity/getTaskList"
        try:
            response = self.api.post(url, data={'activityCode': self.activity_code})
            if response and response.get('code') == 0:
                target_tasks = [
                    task for task in response['value']['taskInfoList']
                    if '浏览组浏览任务' in task.get('taskName', '')
                ]
                return target_tasks
            self.error_info = f"获取任务列表失败：{response}"
            return None
        except Exception as e:
            self.error_info = f'获取任务列表时发生异常：{e}'
            return None

    def get_task(self, task_code: str) -> Optional[str]:
        """通过 taskCode 获取 userTaskId。"""
        url = f"https://{API_HOST}/mp/api/generalActivity/getTask"
        data = {
            'activityCode': self.activity_code,
            'taskCode': task_code,
            'jrairstar_ph': '98lj8puDf9Tu/WwcyMpVyQ=='
        }
        try:
            response = self.api.post(url, data=data)
            if response and response.get('code') == 0:
                return response['value']['taskInfo']['userTaskId']
            self.error_info = f'获取任务信息失败：{response}'
            return None
        except Exception as e:
            self.error_info = f'获取任务信息时发生异常：{e}'
            return None

    def complete_task(self, task_id: str, t_id: str, brows_click_url_id: str) -> Optional[str]:
        """完成浏览任务。"""
        url = f"https://{API_HOST}/mp/api/generalActivity/completeTask"
        params = {
            'activityCode': self.activity_code,
            'app': 'com.mipay.wallet',
            'isNfcPhone': 'true',
            'channel': 'mipay_indexicon_TVcard',
            'deviceType': '2',
            'system': '1',
            'visitEnvironment': '2',
            'userExtra': '{"platformType":1,"com.miui.player":"4.27.0.4","com.miui.video":"v2024090290(MiVideo-UN)","com.mipay.wallet":"6.83.0.5175.2256"}',
            'taskId': task_id,
            'browsTaskId': t_id,
            'browsClickUrlId': brows_click_url_id,
            'clickEntryType': 'undefined',
            'festivalStatus': '0'
        }
        try:
            response = self.api.get(url, params=params)
            if response and response.get('code') == 0:
                return response.get('value')
            self.error_info = f'完成任务失败：{response}'
            return None
        except Exception as e:
            self.error_info = f'完成任务时发生异常：{e}'
            return None

    def receive_award(self, user_task_id: str) -> bool:
        """领取奖励。"""
        url = f"https://{API_HOST}/mp/api/generalActivity/luckDraw"
        params = {
            'activityCode': self.activity_code,
            'userTaskId': user_task_id,
            'app': 'com.mipay.wallet',
            'isNfcPhone': 'true',
            'channel': 'mipay_indexicon_TVcard',
            'deviceType': '2',
            'system': '1',
            'visitEnvironment': '2',
            'userExtra': '{"platformType":1,"com.miui.player":"4.27.0.4","com.miui.video":"v2024090290(MiVideo-UN)","com.mipay.wallet":"6.83.0.5175.2256"}',
        }
        try:
            response = self.api.get(url, params=params)
            if response and response.get('code') == 0:
                self.error_info = ""
                return True
            self.error_info = f'领取奖励失败：{response}'
            return False
        except Exception as e:
            self.error_info = f'领取奖励时发生异常：{e}'
            return False

    def query_user_info_and_records(self) -> bool:
        """查询用户总奖励和今日记录。"""
        base_url = f"https://{API_HOST}/mp/api/generalActivity/"
        params = {
            'activityCode': self.activity_code,
            'app': 'com.mipay.wallet',
            'deviceType': '2',
            'system': '1',
            'visitEnvironment': '2',
            'userExtra': '{"platformType":1,"com.miui.player":"4.27.0.4","com.miui.video":"v2024090290(MiVideo-UN)","com.mipay.wallet":"6.83.0.5175.2256"}'
        }
        try:
            total_res = self.api.get(f"{base_url}queryUserGoldRichSum", params=params)
            if not total_res or total_res.get('code') != 0:
                self.error_info = f'获取兑换视频天数失败：{total_res}'
                return False
            self.total_days = f"{int(total_res.get('value', 0)) / 100:.2f}天"

            record_params = {**params, 'pageNum': 1, 'pageSize': 20}
            record_res = self.api.get(f"{base_url}queryUserJoinList", params=record_params)
            if not record_res or record_res.get('code') != 0:
                self.error_info = f'查询任务完成记录失败：{record_res}'
                return False

            self.today_records = []
            current_date = datetime.now().strftime("%Y-%m-%d")
            for item in record_res.get('value', {}).get('data', []):
                if item.get('createTime', '').startswith(current_date):
                    self.today_records.append(item)
            return True
        except Exception as e:
            self.error_info = f'获取任务记录时发生异常：{e}'
            return False

class XiaomiWalletGUI:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "小米钱包每日任务"
        self.page.window_width = 800
        self.page.window_height = 600
        self.page.theme_mode = ft.ThemeMode.LIGHT

        # 配置Tab页
        self.tabs = ft.Tabs(
            selected_index=0,
            on_change=self.on_tab_change,
            tabs=[
                ft.Tab(text="主页面", icon=ft.Icons.HOME),
                ft.Tab(text="账号管理", icon=ft.Icons.ACCOUNT_CIRCLE),
                ft.Tab(text="扫码登录", icon=ft.Icons.QR_CODE),
                ft.Tab(text="运行结果", icon=ft.Icons.LIST_ALT),
            ]
        )
        
        # 主页面
        self.main_page = self.create_main_page()
        
        # 账号管理页面
        self.account_page = self.create_account_page()
        
        # 扫码登录页面
        self.login_page = self.create_login_page()
        
        # 运行结果页面
        self.result_page = self.create_result_page()
        
        # 详情页面（初始化为空）
        self.details_page = ft.Container(
            content=ft.Text("任务详情将显示在这里"),
            expand=True
        )
        
        # 页面容器
        self.page_content = ft.Container(
            content=self.main_page,
            expand=True
        )
        
        # 主布局
        self.page.add(
            ft.Column(
                [
                    self.tabs,
                    self.page_content
                ],
                expand=True,
                alignment=ft.MainAxisAlignment.START
            )
        )
        
        # 更新账号列表
        self.update_account_list()
    
    def on_tab_change(self, e):
        """Tab切换事件"""
        if self.tabs.selected_index == 0:
            self.page_content.content = self.main_page
        elif self.tabs.selected_index == 1:
            self.page_content.content = self.account_page
            self.update_account_list()
        elif self.tabs.selected_index == 2:
            self.page_content.content = self.login_page
        elif self.tabs.selected_index == 3:
            self.page_content.content = self.result_page
            # 加载本地保存的任务日志
            self.load_local_task_logs()
        self.page.update()
        
    def load_local_task_logs(self):
        """加载本地保存的任务日志文件"""
        try:
            # 清空结果列表
            self.result_list_view.controls.clear()
            
            # 检查日志目录是否存在
            if not os.path.exists(LOG_PATH):
                self.result_list_view.controls.append(ft.Text("暂无本地执行记录"))
                self.page.update()
                return
            
            # 获取日期目录列表（按日期倒序）
            date_dirs = []
            for item in os.listdir(LOG_PATH):
                item_path = os.path.join(LOG_PATH, item)
                if os.path.isdir(item_path):
                    try:
                        # 验证是有效日期格式
                        datetime.strptime(item, '%Y-%m-%d')
                        date_dirs.append(item)
                    except ValueError:
                        continue
            
            # 按日期倒序排序
            date_dirs.sort(reverse=True)
            
            # 存储加载的任务结果
            self.task_results = []
            
            # 遍历日期目录
            for date_dir in date_dirs:
                date_path = os.path.join(LOG_PATH, date_dir)
                # 获取日志文件列表（按时间倒序）
                log_files = []
                for item in os.listdir(date_path):
                    if item.endswith('.json'):
                        log_files.append(os.path.join(date_path, item))
                
                # 按文件名中的时间倒序排序
                log_files.sort(reverse=True)
                
                # 收集当前日期的所有记录，然后倒序插入
                date_records = []
                
                # 遍历日志文件
                for log_file in log_files:
                    try:
                        with open(log_file, 'r', encoding='utf-8') as f:
                            result_obj = json.load(f)
                            
                        # 添加到任务结果列表
                        result_index = len(self.task_results)
                        self.task_results.append(result_obj)
                        
                        # 使用统一的add_result方法创建结果卡片
                        is_success = result_obj.get('success', True)
                        summary_text = f"✅ 账号 '{result_obj['us']}' 任务执行成功" if is_success else f"❌ 账号 '{result_obj['us']}' 任务执行失败"
                        
                        # 创建结果卡片但不直接添加到界面
                        bg_color = ft.Colors.GREEN_50 if is_success else ft.Colors.RED_50
                        content_items = [ft.Text(summary_text, selectable=True, size=14)]
                        content_items.append(ft.Text("点击查看详情...", size=12, color=ft.Colors.GREY_500))
                        
                        result_card = ft.Card(
                            content=ft.Container(
                                content=ft.Column(content_items),
                                padding=15,
                                bgcolor=bg_color,
                                border_radius=5,
                                on_click=lambda e, idx=result_index: self.show_task_details(idx) if hasattr(self, 'task_results') else None
                            )
                        )
                        date_records.append(result_card)
                        
                    except Exception as e:
                        error_card = ft.Card(
                            content=ft.Container(
                                content=ft.Text(f"⚠️ 加载日志文件失败: {os.path.basename(log_file)} - {str(e)}", color=ft.Colors.RED),
                                padding=15,
                                bgcolor=ft.Colors.RED_50,
                                border_radius=5
                            )
                        )
                        date_records.append(error_card)
                
                # 如果有记录，先插入日期标题，然后插入记录（倒序）
                if date_records:
                    # 倒序插入记录
                    for record in date_records:
                        self.result_list_view.controls.insert(0, record)
                    # 最后插入日期标题（这样标题会在最前面）
                    date_title = ft.Text(f"📅 {date_dir}", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE)
                    self.result_list_view.controls.insert(0, date_title)
            
            # 如果没有日志文件
            if len(self.result_list_view.controls) == 0:
                self.result_list_view.controls.append(ft.Text("暂无本地执行记录"))
                
        except Exception as e:
            error_text = ft.Text(f"加载日志时发生错误: {str(e)}", color=ft.Colors.RED)
            self.result_list_view.controls.append(error_text)
        
        self.page.update()
    
    def create_main_page(self):
        """创建主页面"""
        self.run_all_button = ft.ElevatedButton(
            text="一键运行所有任务",
            icon=ft.Icons.PLAY_CIRCLE,
            on_click=self.run_all_tasks,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.GREEN,
                color=ft.Colors.WHITE
            )
        )
        
        self.status_text = ft.Text(
            value="欢迎使用小米钱包每日任务工具",
            size=16,
            weight=ft.FontWeight.BOLD
        )
        
        # 账号统计信息
        self.account_count_text = ft.Text(value="账号数量: 0")
        self.logged_in_count_text = ft.Text(value="已登录: 0")

        return ft.Column(
            [
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text("小米钱包每日任务工具", size=24, weight=ft.FontWeight.BOLD)
                        ],
                        alignment=ft.MainAxisAlignment.CENTER
                    ),
                    padding=20,
                    bgcolor=ft.Colors.BLUE_50
                ),
                
                ft.Container(
                    content=ft.Row(
                        [
                            self.account_count_text,
                            ft.VerticalDivider(width=20),
                            self.logged_in_count_text
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=20
                    ),
                    padding=20
                ),
                
                ft.Container(
                    content=ft.Row(
                        [self.run_all_button],
                        alignment=ft.MainAxisAlignment.CENTER
                    ),
                    padding=20
                ),
                
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("功能说明:", weight=ft.FontWeight.BOLD),
                            ft.Text("1. 支持扫码登录小米账号"),
                            ft.Text("2. 支持批量账号管理"),
                            ft.Text("3. 一键启动所有任务"),
                            ft.Text("4. 任务结果展示")
                        ],
                        spacing=5
                    ),
                    padding=20,
                    expand=True
                ),
                
                ft.Container(
                    content=self.status_text,
                    padding=20,
                    expand=True
                )
            ],
            expand=True
        )
    
    def create_account_page(self):
        """创建账号管理页面"""
        # 账号列表视图
        self.account_list_view = ft.ListView(
            expand=True,
            spacing=10
        )

        return ft.Column(
            [
                ft.Container(
                    content=ft.Text("账号管理", size=24, weight=ft.FontWeight.BOLD),
                    padding=20
                ),
                
                ft.Container(
                    content=self.account_list_view,
                    expand=True,
                    padding=20
                ),
                
                ft.Container(
                    content=ft.Row(
                        [
                            ft.ElevatedButton(
                                text="添加账号",
                                on_click=lambda _: self.switch_to_login_tab()
                            ),
                            ft.ElevatedButton(
                                text="刷新列表",
                                on_click=self.update_account_list
                            )
                        ],
                        alignment=ft.MainAxisAlignment.END,
                        spacing=10
                    ),
                    padding=20
                )
            ],
            expand=True
        )
    
    def switch_to_login_tab(self):
        """切换到扫码登录标签页并更新页面内容"""
        self.tabs.selected_index = 2
        self.page_content.content = self.login_page
        self.page.update()
    
    def create_login_page(self):
        """创建扫码登录页面"""
        self.account_alias_input = ft.TextField(
            label="账号别名",
            hint_text="请输入账号别名，例如：账号1",
            width=300,
            on_change=self.on_account_alias_change
        )
        
        # 二维码图片组件，初始状态不可见
        self.qr_image = ft.Image(
            width=240,
            height=240,
            fit=ft.ImageFit.CONTAIN,
            visible=False  # 初始状态不可见
        )
        
        self.login_status_text = ft.Text(
            value="请输入账号别名，然后点击'生成二维码'按钮",
            color=ft.Colors.BLACK
        )
        
        self.countdown_text = ft.Text(value="")
        
        # 添加二维码链接显示组件
        self.qr_url_text = ft.Text(value="", selectable=True)
        
        # 单独创建生成二维码按钮，便于在on_change事件中更新其状态
        self.generate_qr_button = ft.ElevatedButton(
            text="生成二维码",
            on_click=self.generate_qr_code,
            disabled=True  # 初始状态为禁用
        )
        
        return ft.Column(
            [
                ft.Container(
                    content=ft.Text("扫码登录", size=24, weight=ft.FontWeight.BOLD),
                    padding=20
                ),
                
                ft.Container(
                    content=ft.Row(
                        [
                            self.account_alias_input,
                            self.generate_qr_button
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        spacing=10
                    ),
                    padding=20
                ),
                
                ft.Container(
                    content=ft.Row(
                        [self.qr_image],
                        alignment=ft.MainAxisAlignment.CENTER
                    ),
                    padding=20,
                    bgcolor=ft.Colors.WHITE,
                    border=ft.Border(
                        left=ft.BorderSide(1, ft.Colors.GREY_300),
                        right=ft.BorderSide(1, ft.Colors.GREY_300),
                        top=ft.BorderSide(1, ft.Colors.GREY_300),
                        bottom=ft.BorderSide(1, ft.Colors.GREY_300)
                    ),
                    border_radius=5
                ),
                
                # 显示登录状态和倒计时
                ft.Container(
                    content=ft.Column(
                        [
                            self.login_status_text,
                            self.countdown_text,
                            self.qr_url_text  # 添加二维码链接显示组件
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER
                    ),
                    padding=20
                )
            ],
            expand=True,
            scroll=ft.ScrollMode.AUTO
        )
    
    def create_result_page(self):
        """创建运行结果页面"""
        self.result_text = ft.Text(value="运行结果将显示在这里")
        
        self.result_list_view = ft.ListView(
            expand=True,
            spacing=10
        )
        
        return ft.Column(
            [
                ft.Container(
                    content=ft.Text("运行结果", size=24, weight=ft.FontWeight.BOLD),
                    padding=20
                ),
                
                ft.Container(
                    content=self.result_list_view,
                    expand=True,
                    padding=20
                )
            ],
            expand=True
        )
    
    def update_account_list(self, *args, **kwargs):
        """更新账号列表"""
        self.account_list_view.controls.clear()
        
        accounts = XiaomiAccount.load_accounts()
        total_accounts = len(accounts)
        logged_in_count = sum(1 for acc in accounts if acc.get("data", {}).get("userId"))
        
        self.account_count_text.value = f"账号数量: {total_accounts}"
        self.logged_in_count_text.value = f"已登录: {logged_in_count}"
        
        if not accounts:
            self.account_list_view.controls.append(ft.Text("暂无账号，请先添加账号"))
        else:
            for i, acc in enumerate(accounts):
                data = acc.get("data", {})
                us = data.get("us", "N/A")
                user_id = data.get("userId", "未登录")
                
                # 账号卡片
                # 使用函数包装确保正确捕获每个账号的别名
                def create_account_card(us_value, user_id_value):
                    def handle_delete(e):
                        self.delete_account(us_value)
                    
                    return ft.Card(
                        content=ft.Container(
                            content=ft.Row(
                                [
                                    ft.Column(
                                        [
                                            ft.Text(f"别名: {us_value}", weight=ft.FontWeight.BOLD),
                                            ft.Text(f"小米ID: {user_id_value}")
                                        ],
                                        expand=True
                                    ),
                                    ft.ElevatedButton(
                                        text="删除",
                                        on_click=handle_delete
                                    )
                                ],
                                spacing=10
                            ),
                            padding=10
                        )
                    )
                
                account_card = create_account_card(us, user_id)
                
                self.account_list_view.controls.append(account_card)
        
        self.page.update()
    
    def delete_account(self, us_to_delete):
        """删除账号（直接删除，无确认弹窗）"""
        print(f"🔍 删除账号函数被调用，要删除的账号: {us_to_delete}")
        
        accounts = XiaomiAccount.load_accounts()
        print(f"🔍 加载的账号数量: {len(accounts)}")
        
        original_count = len(accounts)
        new_accounts = [acc for acc in accounts if acc.get("data", {}).get("us") != us_to_delete]
        print(f"🔍 过滤后的账号数量: {len(new_accounts)}")
        
        if len(new_accounts) == original_count:
            print(f"⚠️ 警告：没有找到要删除的账号 '{us_to_delete}'")
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ 未找到要删除的账号 '{us_to_delete}'"),
                bgcolor=ft.Colors.RED
            )
            self.page.snack_bar.open = True
            self.page.update()
            return
        
        try:
            # 1. 删除配置文件中的账号信息
            print(f"🔍 正在写入配置文件: {CONFIG_PATH}")
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(new_accounts, f, indent=4, ensure_ascii=False)
            print(f"✅ 配置文件写入成功")
            
            # 2. 删除相关的任务日志文件
            deleted_log_count = 0
            if os.path.exists(LOG_PATH):
                for date_dir in os.listdir(LOG_PATH):
                    date_path = os.path.join(LOG_PATH, date_dir)
                    if os.path.isdir(date_path):
                        for log_file in os.listdir(date_path):
                            # 检查日志文件是否属于要删除的账号（格式：{us}_{timestamp}.json）
                            if log_file.startswith(f"{us_to_delete}_") and log_file.endswith(".json"):
                                log_file_path = os.path.join(date_path, log_file)
                                try:
                                    os.remove(log_file_path)
                                    deleted_log_count += 1
                                except Exception as log_e:
                                    print(f"删除日志文件失败: {log_file_path}, 错误: {log_e}")
                        
                        # 如果日期目录为空，删除该目录
                        try:
                            if not os.listdir(date_path):
                                os.rmdir(date_path)
                        except Exception:
                            pass  # 忽略删除空目录的错误
            
            # 显示删除成功消息
            success_msg = f"✅ 已成功删除账号 '{us_to_delete}'"
            if deleted_log_count > 0:
                success_msg += f"\n同时清理了 {deleted_log_count} 个相关日志文件"
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(success_msg),
                bgcolor=ft.Colors.GREEN
            )
            self.page.snack_bar.open = True
            self.update_account_list()
            self.page.update()
            print(f"✅ 账号 '{us_to_delete}' 删除完成")
            
        except Exception as e:
            print(f"❌ 删除账号失败: {e}")
            # 显示删除失败消息
            self.page.snack_bar = ft.SnackBar(
                content=ft.Text(f"❌ 删除账号失败: {e}"),
                bgcolor=ft.Colors.RED
            )
            self.page.snack_bar.open = True
            self.page.update()
    
    def on_account_alias_change(self, e):
        """账号别名输入变化时更新生成二维码按钮状态"""
        self.generate_qr_button.disabled = self.account_alias_input.value.strip() == ""
        self.page.update()
    
    def generate_qr_code(self, e):
        """生成登录二维码"""
        us = self.account_alias_input.value.strip()
        
        if not us:
            self.login_status_text.value = "❌ 请输入账号别名"
            self.login_status_text.color = ft.Colors.RED
            self.page.update()
            return
        
        account = XiaomiAccount(us)
        
        # 在新线程中处理登录，避免阻塞UI
        def login_thread():
            login_data = account.get_login_qr()
            
            if not login_data or login_data.get("code") != 0:
                def update_status_error():
                    self.update_login_status("❌ 获取二维码失败，请检查网络或稍后再试", ft.Colors.RED)
                self.page.run_task(update_status_error)
                return
            
            qr_url = login_data.get("qr")
            if not qr_url:
                def update_status_no_qr():
                    self.update_login_status("❌ 未能从响应中获取二维码URL", ft.Colors.RED)
                self.page.run_task(update_status_no_qr)
                return
            
            # 解决Image组件显示问题
            async def update_qr_image():
                # 先清除之前的src_base64属性，确保src属性生效
                self.qr_image.src_base64 = None
                # 设置图片的src属性为API返回的二维码URL
                self.qr_image.src = qr_url
                # 显示二维码图片
                self.qr_image.visible = True
                # 显示二维码链接
                self.qr_url_text.value = f"二维码链接: {qr_url}"
                self.page.update()

            # 修复run_task需要协程函数
            self.page.run_task(update_qr_image)
            async def update_status_scan():
                self.update_login_status("📱 请使用小米手机APP扫描上方二维码登录", ft.Colors.BLACK)
            self.page.run_task(update_status_scan)
            
            # 检查登录状态
            lp_url = login_data.get("lp")
            timeout = login_data.get("timeout", 300)
            self.check_login_status(lp_url, timeout, account)
        
        # 启动登录线程
        threading.Thread(target=login_thread, daemon=True).start()
    
    def update_login_status(self, text, color=ft.Colors.BLACK):
        """更新登录状态文本"""
        self.login_status_text.value = text
        self.login_status_text.color = color
        self.page.update()
    
    def check_login_status(self, lp_url, timeout, account):
        """检查登录状态"""
        start_time = time.time()
        end_time = start_time + timeout
        
        status_messages = {700: "等待扫码", 701: "已扫码, 请在手机上确认", 702: "二维码已过期", 0: "登录成功"}
        last_status_code = -1
        
        # 优化倒计时更新逻辑
        self.countdown_timer = None
        
        def update_countdown():
            remaining = int(end_time - time.time())
            if remaining > 0:
                async def update_ui():
                    self.countdown_text.value = f"⏳ 二维码有效时间剩余 {remaining} 秒"
                    self.page.update()
                
                self.page.run_task(update_ui)
                # 每秒更新一次倒计时
                self.countdown_timer = threading.Timer(1.0, update_countdown)
                self.countdown_timer.start()
            else:
                async def update_expired():
                    self.countdown_text.value = "❌ 二维码已过期"
                    self.page.update()
                
                self.page.run_task(update_expired)
        
        # 启动倒计时更新
        update_countdown()
        
        # 继续轮询登录状态
        while time.time() < end_time:
            try:
                response = requests.get(lp_url, timeout=60)
                response_text = response.text
                if "&&&START&&&" in response_text:
                    response_text = response_text.split("&&&START&&&", 1)[-1].strip()
                result = json.loads(response_text)
                
                status_code = result.get("code", -1)
                
                if status_code != last_status_code:
                    status_msg = status_messages.get(status_code, f"未知状态: {status_code}")
                    self.update_login_status(f"ℹ️  状态更新: {status_msg}")
                    last_status_code = status_code
                
                if status_code == 0:
                    # 停止倒计时定时器
                    if hasattr(self, 'countdown_timer') and self.countdown_timer:
                        self.countdown_timer.cancel()
                    
                    user_id = result.get("userId")
                    security_token = result.get("ssecurity")
                    pass_token = result.get("passToken")
                    
                    account.user_id = user_id
                    account.security_token = security_token
                    account.pass_token = pass_token
                    
                    if account.save_to_json():
                        self.update_login_status("🎉 登录成功! 账号已保存，正在跳转到首页...", ft.Colors.GREEN)
                        self.countdown_text.value = ""
                        self.update_account_list()
                        # 延迟1秒后自动跳转到首页
                        def auto_redirect():
                            time.sleep(1)
                            async def switch_to_home():
                                self.tabs.selected_index = 0
                                self.page_content.content = self.main_page
                                self.page.update()
                            self.page.run_task(switch_to_home)
                        threading.Thread(target=auto_redirect, daemon=True).start()
                    else:
                        self.update_login_status("❌ 登录成功，但保存账号失败", ft.Colors.RED)
                    self.page.update()
                    return
                
                if status_code == 702:
                    # 停止倒计时定时器
                    if hasattr(self, 'countdown_timer') and self.countdown_timer:
                        self.countdown_timer.cancel()
                    
                    self.update_login_status("❌ 二维码已过期，请重新生成", ft.Colors.RED)
                    self.countdown_text.value = ""
                    self.page.update()
                    return
                
            except requests.exceptions.Timeout:
                # 这个超时是客户端设置的60秒超时，说明服务器一直没响应，是正常的，继续轮询
                continue
            except requests.exceptions.RequestException as e:
                self.update_login_status(f"❌ 网络连接错误: {e}", ft.Colors.RED)
                time.sleep(3)
                continue
            except Exception as e:
                self.update_login_status(f"❌ 发生未知错误: {e}", ft.Colors.RED)
                time.sleep(3)
                continue
        
        # 超时处理
        # 停止倒计时定时器
        if hasattr(self, 'countdown_timer') and self.countdown_timer:
            self.countdown_timer.cancel()
        
        self.update_login_status("❌ 登录超时", ft.Colors.RED)
        self.countdown_text.value = ""
        self.page.update()
    
    def save_task_log(self, result_obj):
        """缓存任务执行记录到本地文件"""
        try:
            # 创建日期目录
            today = datetime.now().strftime('%Y-%m-%d')
            date_dir = os.path.join(LOG_PATH, today)
            Path(date_dir).mkdir(exist_ok=True)
            
            # 生成日志文件名
            timestamp = datetime.now().strftime('%H-%M-%S')
            log_filename = f"{result_obj['us']}_{timestamp}.json"
            log_path = os.path.join(date_dir, log_filename)
            
            # 保存日志到文件
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(result_obj, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"保存任务日志失败: {e}")
    
    def add_result(self, text, is_success=True, is_summary=False, result_index=None):
        """添加运行结果，支持点击查看详情"""
        bg_color = ft.Colors.GREEN_50 if is_success else ft.Colors.RED_50
        if is_summary:
            bg_color = ft.Colors.BLUE_50
        
        # 创建结果卡片内容
        content_items = [ft.Text(text, selectable=True, size=14)]
        
        # 如果存在result_index，添加点击提示
        if result_index is not None:
            content_items.append(ft.Text("点击查看详情...", size=12, color=ft.Colors.GREY_500))
        
        # 创建结果卡片
        result_card = ft.Card(
            content=ft.Container(
                content=ft.Column(content_items),
                padding=15,
                bgcolor=bg_color,
                border_radius=5,
                # 明确设置Container为可点击
                on_click=lambda e, idx=result_index: self.show_task_details(idx) if result_index is not None and hasattr(self, 'task_results') else None
            )
        )
        
        # 将新记录插入到列表开头，实现倒序显示
        self.result_list_view.controls.insert(0, result_card)
        self.page.update()
    
    def show_task_details(self, result_index):
        """显示任务执行详情弹窗"""
        if not hasattr(self, 'task_results') or result_index >= len(self.task_results):
            return
        
        result_obj = self.task_results[result_index]
        
        # 创建详情内容
        details_content = ft.Column(
            controls=[
                ft.Text(f"账号: {result_obj['us']}", size=18, weight=ft.FontWeight.BOLD),
                ft.Text(f"用户ID: {result_obj['user_id']}", size=16),
                ft.Text(f"执行时间: {result_obj['start_time']}", size=16),
                ft.Text(f"结束时间: {result_obj.get('end_time', '未知')}", size=16),
                ft.Text(f"状态: {'成功' if result_obj['success'] else '失败'}", size=16),
                ft.Divider(),
                ft.Text("执行日志:", size=16, weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=ft.Text("\n".join(result_obj['logs']), size=14, selectable=True),
                    padding=10,
                    bgcolor=ft.Colors.GREY_50,
                    border_radius=5,
                    expand=True
                )
            ],
            spacing=10,
            expand=True,
            scroll=ft.ScrollMode.AUTO
        )
        
        # 创建弹窗
        self.details_dialog = ft.AlertDialog(
            title=ft.Text("任务执行详情"),
            content=ft.Container(
                content=details_content,
                width=600,
                height=400,
                padding=10
            ),
            actions=[
                ft.TextButton("关闭", on_click=lambda e: self.page.close(self.details_dialog))
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        # 显示弹窗
        self.page.open(self.details_dialog)
    
    def back_to_results_list(self):
        """返回到结果列表"""
        if hasattr(self, 'details_dialog') and self.details_dialog.open:
            self.page.close(self.details_dialog)
        self.page_content.content = self.result_page
        self.page.update()

    def run_all_tasks(self, e):
        """一键运行所有任务"""
        def run_task_thread():
            # 确保日志目录存在
            Path(LOG_PATH).mkdir(exist_ok=True)
            
            # 更新状态
            async def update_status_running():
                self.status_text.value = "正在执行任务，请稍候..."
                self.run_all_button.disabled = True
                self.page.update()

            self.page.run_task(update_status_running)
            
            # 清空结果列表
            async def clear_results():
                self.result_list_view.controls.clear()
                self.page.update()

            self.page.run_task(clear_results)
            
            # 获取所有账号
            accounts = XiaomiAccount.load_accounts()
            
            if not accounts:
                async def update_status_no_accounts():
                    self.status_text.value = "❌ 没有找到账号，请先添加账号"
                    self.run_all_button.disabled = False
                    self.page.update()

                self.page.run_task(update_status_no_accounts)
                return
            
            total_accounts = len(accounts)
            successful_accounts = 0
            failed_accounts = 0
            
            # 存储执行结果的详细信息
            self.task_results = []
            
            for i, acc in enumerate(accounts):
                data = acc.get("data", {})
                us = data.get("us", "未知账号")
                user_id = data.get("userId")
                pass_token = data.get("passToken")
                
                # 更新进度状态
                async def update_progress():
                    self.status_text.value = f"正在执行任务: {i+1}/{total_accounts} - 账号 '{us}'"
                    self.page.update()
                self.page.run_task(update_progress)
                
                # 创建任务执行结果对象
                result_obj = {
                    "us": us,
                    "user_id": user_id,
                    "start_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    "logs": [],
                    "success": False,
                    "error": None
                }
                
                if not user_id or not pass_token:
                    error_msg = f"⚠️ 账号 '{us}' 未登录或配置不完整，跳过执行"
                    result_obj["error"] = error_msg
                    result_obj["logs"].append(error_msg)
                    
                    # 添加到结果列表
                    self.task_results.append(result_obj)
                    
                    # 显示在结果页面
                    async def add_no_login_result():
                        self.add_result(f"⚠️ 账号 '{us}' 任务执行情况", is_summary=True)
                    
                    self.page.run_task(add_no_login_result)
                    failed_accounts += 1
                    continue
                
                try:
                    # 从main.py集成的真实任务执行逻辑
                    # 1. 记录开始执行
                    result_obj["logs"].append(f"✅ 账号 '{us}' 任务执行开始")
                    result_obj["logs"].append(f"用户ID: {user_id}")
                    result_obj["logs"].append(f"执行时间: {result_obj['start_time']}")
                    result_obj["logs"].append("开始执行任务...")
                    
                    # 2. 获取会话Cookie
                    result_obj["logs"].append("1. 获取会话Cookie...")
                    session_cookies = self.get_session_cookies(pass_token, user_id)
                    
                    if not session_cookies:
                        error_msg = "获取会话Cookie失败，请重新登录"
                        result_obj["error"] = error_msg
                        result_obj["logs"].append(f"❌ {error_msg}")
                        failed_accounts += 1
                    else:
                        result_obj["logs"].append("✅ 会话Cookie获取成功")
                        
                        # 3. 创建API请求实例
                        api_request = ApiRequest(session_cookies)
                        rnl = RNL(api_request)
                        
                        # 4. 查询用户信息和记录
                        result_obj["logs"].append("2. 查询用户信息和奖励记录...")
                        if not rnl.query_user_info_and_records():
                            error_msg = f"获取用户信息失败: {rnl.error_info}"
                            result_obj["error"] = error_msg
                            result_obj["logs"].append(f"❌ {error_msg}")
                            failed_accounts += 1
                        else:
                            result_obj["logs"].append(f"✅ 当前可兑换视频天数: {rnl.total_days}")
                            
                            # 5. 执行两轮任务，与main.py保持一致的逻辑
                            success = True
                            for round_num in range(2):
                                result_obj["logs"].append(f"\n--- 开始第 {round_num + 1} 轮任务 ---")
                                tasks = rnl.get_task_list()
                                
                                if not tasks:
                                    result_obj["logs"].append("⚠️ 未找到可执行的任务列表，可能今日任务已完成")
                                    break
                                
                                task = tasks[0]
                                try:
                                    rnl.t_id = task['generalActivityUrlInfo']['id']
                                except (KeyError, TypeError):
                                    pass
                                
                                if not rnl.t_id:
                                    result_obj["logs"].append("❌ 无法获取任务t_id，中断执行")
                                    success = False
                                    break
                                
                                task_id = task['taskId']
                                task_code = task['taskCode']
                                brows_click_url_id = task['generalActivityUrlInfo']['browsClickUrlId']
                                
                                result_obj["logs"].append("3. 执行浏览任务...")
                                result_obj["logs"].append(f"等待随机延迟...")
                                delay = random.randint(10, 15)
                                result_obj["logs"].append(f"等待 {delay} 秒...")
                                time.sleep(delay)
                                
                                user_task_id = rnl.complete_task(
                                    task_id=task_id,
                                    t_id=rnl.t_id,
                                    brows_click_url_id=brows_click_url_id
                                )
                                
                                time.sleep(random.randint(2, 4))
                                
                                if not user_task_id:
                                    result_obj["logs"].append("⚠️ 任务完成接口返回为空，尝试从获取任务接口重试...")
                                    time.sleep(random.randint(2, 4))
                                    user_task_id = rnl.get_task(task_code=task_code)
                                
                                if user_task_id:
                                    result_obj["logs"].append("4. 领取奖励...")
                                    time.sleep(random.randint(2, 4))
                                    rnl.receive_award(user_task_id=user_task_id)
                                    if rnl.error_info:
                                        result_obj["logs"].append(f"⚠️ 领取奖励时可能出现问题: {rnl.error_info}")
                                    else:
                                        result_obj["logs"].append("✅ 奖励领取成功")
                                else:
                                    result_obj["logs"].append("❌ 未能获取user_task_id，无法领取本轮奖励")
                                
                                time.sleep(random.randint(2, 4))
                            
                            if success:
                                result_obj["logs"].append("\n5. 刷新最终数据...")
                                rnl.query_user_info_and_records()
                                result_obj["logs"].append(f"✅ 任务执行完成！最终可兑换视频天数: {rnl.total_days}")
                                
                                # 添加今日记录到日志
                                if rnl.today_records:
                                    result_obj["logs"].append("\n📅 今日新增奖励记录:")
                                    for record in rnl.today_records:
                                        record_time = record.get("createTime", "未知时间")
                                        value = record.get("value", 0)
                                        days = int(value) / 100
                                        result_obj["logs"].append(f"| ⏰ {record_time}")
                                        result_obj["logs"].append(f"| 🎁 领到视频会员，+{days:.2f}天")
                                else:
                                    result_obj["logs"].append("\n📅 今日暂无新增奖励记录")
                                
                                result_obj["success"] = True
                                successful_accounts += 1
                            else:
                                result_obj["error"] = "任务执行失败"
                                failed_accounts += 1
                    
                except Exception as ex:
                    error_msg = f"执行任务时发生异常: {str(ex)}"
                    result_obj["error"] = error_msg
                    result_obj["logs"].append(f"❌ {error_msg}")
                    failed_accounts += 1
                    
                finally:
                    # 记录结束时间
                    result_obj["end_time"] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    result_obj["logs"].append(f"\n任务执行结束时间: {result_obj['end_time']}")
                    
                    # 缓存执行记录到本地
                    self.save_task_log(result_obj)
                    
                    # 添加到结果列表
                    self.task_results.append(result_obj)
                    
                    # 显示在结果页面（只显示摘要，点击查看详情）
                    summary_text = f"✅ 账号 '{us}' 任务执行成功" if result_obj["success"] else f"❌ 账号 '{us}' 任务执行失败"
                    async def add_result_summary():
                        self.add_result(summary_text, is_success=result_obj["success"], result_index=len(self.task_results)-1)
                    
                    self.page.run_task(add_result_summary)
                    
                    # 模拟网络延迟，与main.py保持一致
                    time.sleep(random.randint(0, 5))
            
            # 完成任务后的更新
            final_status = f"所有任务执行完成 - 成功: {successful_accounts}, 失败: {failed_accounts}"
            
            async def update_status_completed():
                self.status_text.value = final_status
                self.run_all_button.disabled = False
                # 添加总结果摘要
                self.add_result(final_status, is_summary=True)
                # 自动切换到运行结果标签页
                self.tabs.selected_index = 3
                self.page_content.content = self.result_page
                self.page.update()

            self.page.run_task(update_status_completed)
        
        # 启动任务线程
        threading.Thread(target=run_task_thread, daemon=True).start()
        
    def get_session_cookies(self, pass_token: str, user_id: str) -> Optional[str]:
        """使用长效凭证获取用于访问任务API的临时会话Cookie"""
        login_url = (
            'https://account.xiaomi.com/pass/serviceLogin?callback=https%3A%2F%2Fapi.jr.airstarfinance.net%2Fsts'
            '%3Fsign%3D1dbHuyAmee0NAZ2xsRw5vhdVQQ8%253D%26followup%3Dhttps%253A%252F%252Fm.jr.airstarfinance.net'
            '%252Fmp%252Fapi%252Flogin%253Ffrom%253Dmipay_indexicon_TVcard%2526deepLinkEnable%253Dfalse'
            '%2526requestUrl%253Dhttps%25253A%25252F%25252Fm.jr.airstarfinance.net%25252Fmp%25252Factivity'
            '%25252FvideoActivity%25253Ffrom%25253Dmipay_indexicon_TVcard%252526_noDarkMode%25253Dtrue'
            '%252526_transparentNaviBar%25253Dtrue%252526cUserId%25253Dusyxgr5xjumiQLUoAKTOgvi858Q'
            '%252526_statusBarHeight%25253D137&sid=jrairstar&_group=DEFAULT&_snsNone=true&_loginType=ticket'
        )
        
        headers = {
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0',
            'cookie': f'passToken={pass_token}; userId={user_id};'
        }
        
        session = requests.Session()
        try:
            session.get(url=login_url, headers=headers, verify=False, timeout=10)
            cookies = session.cookies.get_dict()
            
            c_user_id = cookies.get('cUserId')
            service_token = cookies.get('serviceToken')
            
            if c_user_id and service_token:
                return f"cUserId={c_user_id}; jrairstar_serviceToken={service_token}"
            
            return None
        except requests.RequestException:
            return None

def main(page: ft.Page):
    XiaomiWalletGUI(page)

if __name__ == "__main__":
    ft.app(target=main)