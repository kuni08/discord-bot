import discord
from discord import app_commands
from discord.ext import commands
import os
import datetime
import json
import asyncio
from flask import Flask
from threading import Thread
from collections import defaultdict, Counter
import io
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
import matplotlib.patches as patches
import pandas as pd
import random
import numpy as np

# ---------------------------------------------------------
# 1. サーバー維持機能
# ---------------------------------------------------------
app = Flask('')

@app.route('/')
def home():
    return "I am alive!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ---------------------------------------------------------
# 2. 設定・定数
# ---------------------------------------------------------
TOKEN = os.getenv('DISCORD_TOKEN')

# チャンネル名の定義
CH_DATA = "🔒データ保存用"
CH_DASHBOARD = "🎮ダッシュボード"
CH_TIMELINE = "📜タイムライン"
CH_GOALS = "🎯目標管理"
CH_REPORT = "📊レポート"
CAT_NAME = "MY LIFE LOG"

# 日本時間（JST）の定義
JST = datetime.timezone(datetime.timedelta(hours=9))

PRAISE_MESSAGES = [
    "お疲れ様でした！素晴らしい集中力です✨",
    "ナイス！その調子でいきましょう🚀",
    "目標達成おめでとうございます！🎉",
    "よく頑張りましたね！ゆっくり休んでください🍵",
    "今日のあなたは輝いています！✨",
    "継続は力なり。さすがです！💪",
    "完璧です！次のタスクもこの調子で！🔥",
    "えらい！すごすぎる！💯",
]

BUTTON_STYLES = {
    "primary": discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "danger": discord.ButtonStyle.danger
}

FONT_PATH = "font.ttf"
try:
    if os.path.exists(FONT_PATH):
        font_prop = fm.FontProperties(fname=FONT_PATH)
        plt.rcParams['font.family'] = font_prop.get_name()
    else:
        print("【警告】font.ttfが見つかりません。")
except Exception as e:
    print(f"フォント設定エラー: {e}")

intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix='!', intents=intents)

# ---------------------------------------------------------
# 3. 共通ヘルパー関数
# ---------------------------------------------------------
async def resend_dashboard(interaction, bot):
    """ダッシュボードパネルを最下部に再設置する"""
    dm = DataManager(bot)
    tasks = await dm.load_tasks(interaction.guild)
    
    dashboard_ch = discord.utils.get(interaction.guild.text_channels, name=CH_DASHBOARD)
    target_ch = dashboard_ch if dashboard_ch else interaction.channel
    
    try:
        async for msg in target_ch.history(limit=5):
            if msg.author == bot.user and msg.content == "行動宣言パネル":
                await msg.delete()
    except:
        pass

    try:
        await target_ch.send("行動宣言パネル", view=DashboardView(bot, tasks))
    except Exception as e:
        print(f"パネル再設置エラー: {e}")

# ---------------------------------------------------------
# 4. データ管理クラス
# ---------------------------------------------------------
class DataManager:
    def __init__(self, bot):
        self.bot = bot
        self.default_tasks = [
            {"name": "勉強", "style": "primary"},
            {"name": "読書", "style": "primary"},
            {"name": "運動", "style": "success"},
            {"name": "食事", "style": "success"},
            {"name": "風呂", "style": "primary"},
            {"name": "コーヒー", "style": "secondary"},
            {"name": "移動", "style": "secondary"},
            {"name": "PC作業", "style": "primary"},
            {"name": "ゲーム", "style": "success"}
        ]

    async def get_channel_by_name(self, guild, name, category=None, hidden=False):
        channel = discord.utils.get(guild.text_channels, name=name)
        if channel: return channel
        
        overwrites = {}
        if hidden:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True),
            }
        elif name == CH_DASHBOARD or name == CH_GOALS:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(send_messages=False),
                guild.me: discord.PermissionOverwrite(send_messages=True)
            }
            
        return await guild.create_text_channel(name, category=category, overwrites=overwrites)

    async def get_data_channel(self, guild):
        return await self.get_channel_by_name(guild, CH_DATA, hidden=True)

    async def get_timeline_channel(self, guild):
        return await self.get_channel_by_name(guild, CH_TIMELINE)

    async def get_goals_channel(self, guild):
        return await self.get_channel_by_name(guild, CH_GOALS)

    async def get_report_channel(self, guild):
        return await self.get_channel_by_name(guild, CH_REPORT)

    async def load_tasks(self, guild):
        channel = await self.get_data_channel(guild)
        pins = await channel.pins()
        for msg in pins:
            if msg.content.startswith("CONFIG_TASKS:"):
                try:
                    data = json.loads(msg.content.replace("CONFIG_TASKS:", ""))
                    if data and isinstance(data[0], str): 
                        return [{"name": t, "style": "secondary"} for t in data]
                    return data
                except: pass
        
        initial_data = self.default_tasks
        msg = await channel.send(f"CONFIG_TASKS:{json.dumps(initial_data, ensure_ascii=False)}")
        await msg.pin()
        return initial_data

    async def save_tasks(self, guild, tasks):
        channel = await self.get_data_channel(guild)
        pins = await channel.pins()
        for msg in pins:
            if msg.content.startswith("CONFIG_TASKS:"):
                await msg.edit(content=f"CONFIG_TASKS:{json.dumps(tasks, ensure_ascii=False)}")
                return
        msg = await channel.send(f"CONFIG_TASKS:{json.dumps(tasks, ensure_ascii=False)}")
        await msg.pin()

    async def load_goals(self, guild):
        channel = await self.get_data_channel(guild)
        pins = await channel.pins()
        for msg in pins:
            if msg.content.startswith("CONFIG_GOALS:"):
                try:
                    data = json.loads(msg.content.replace("CONFIG_GOALS:", ""))
                    new_data = {}
                    for k, v in data.items():
                        if isinstance(v, dict): new_data[k] = [v]
                        else: new_data[k] = v
                    return new_data
                except: pass
        return {}

    async def save_goals(self, guild, goals):
        channel = await self.get_data_channel(guild)
        pins = await channel.pins()
        for msg in pins:
            if msg.content.startswith("CONFIG_GOALS:"):
                await msg.edit(content=f"CONFIG_GOALS:{json.dumps(goals, ensure_ascii=False)}")
                return
        msg = await channel.send(f"CONFIG_GOALS:{json.dumps(goals, ensure_ascii=False)}")
        await msg.pin()

    async def save_log(self, guild, log_data):
        data_ch = await self.get_data_channel(guild)
        timeline_ch = await self.get_timeline_channel(guild)

        embed = discord.Embed(title=f"✅ {log_data['task']}", color=discord.Color.green())
        embed.add_field(name="時間", value=f"{log_data['duration_str']}")
        if log_data.get('memo'):
            embed.add_field(name="📝 メモ", value=log_data['memo'], inline=False)
        embed.set_footer(text="Logged via MyLifeLog")
        embed.timestamp = datetime.datetime.now(JST)
        
        await timeline_ch.send(embed=embed)

        embed.set_footer(text=f"LOG_ID:{json.dumps(log_data, ensure_ascii=False)}")
        await data_ch.send(embed=embed)

        await self.refresh_goals_panel(guild)

    async def fetch_logs(self, guild, limit=1500):
        channel = await self.get_data_channel(guild)
        logs = []
        async for msg in channel.history(limit=limit):
            if not msg.embeds: continue
            embed = msg.embeds[0]
            if not embed.footer.text or "LOG_ID:" not in embed.footer.text: continue
            try:
                data = json.loads(embed.footer.text.replace("LOG_ID:", ""))
                logs.append(data)
            except: continue
        return logs

    async def refresh_goals_panel(self, guild):
        goals_ch = await self.get_goals_channel(guild)
        if not goals_ch: return

        logs = await self.fetch_logs(guild, limit=1000)
        goals = await self.load_goals(guild)
        
        embed = discord.Embed(title="🔥 目標進捗ダッシュボード", description="設定された目標の達成状況です。", color=discord.Color.orange())
        
        if not goals:
            embed.description = "目標が設定されていません。下のボタンから追加してください。"
        else:
            progress_data = GraphGenerator.calculate_progress(logs, goals)
            if not progress_data:
                embed.description = "データ不足のため表示できません。"
            else:
                for p in progress_data:
                    bar_len = 10
                    filled = int(bar_len * (p['percent'] / 100))
                    bar = "▓" * filled + "░" * (bar_len - filled)
                    
                    value_str = f"{p['current']}/{p['target']}分"
                    embed.add_field(
                        name=f"{p['task']} ({p['period_label']})",
                        value=f"`[{bar}]` **{p['percent']}%** ({value_str})",
                        inline=False
                    )
        
        await goals_ch.purge(limit=5)
        tasks = await self.load_tasks(guild)
        await goals_ch.send(embed=embed, view=GoalManagePanel(self.bot, tasks))

# ---------------------------------------------------------
# 5. グラフ & 進捗計算クラス
# ---------------------------------------------------------
class GraphGenerator:
    @staticmethod
    def _prepare_df(logs, start_date=None, end_date=None, tasks_filter=None):
        if not logs: return None
        df = pd.DataFrame(logs)
        if df.empty: return None
        
        df['date_obj'] = pd.to_datetime(df['date']).dt.tz_localize(None) 
        
        if 'timestamp' in df.columns:
             df['ts_obj'] = pd.to_datetime(df['timestamp']).dt.tz_convert(JST).dt.tz_localize(None)
        else:
             df['ts_obj'] = df['date_obj']

        if start_date:
            df = df[df['ts_obj'] >= start_date]
        if end_date:
            df = df[df['ts_obj'] <= end_date]
            
        if tasks_filter:
            df = df[df['task'].isin(tasks_filter)]
            
        if df.empty: return None
        return df

    @staticmethod
    def get_font_prop(size=14, weight='normal'):
        if os.path.exists(FONT_PATH):
            return fm.FontProperties(fname=FONT_PATH, size=size, weight=weight)
        return None

    @staticmethod
    def combine_images(image_buffers):
        if not image_buffers: return None
        images = [plt.imread(buf) for buf in image_buffers]
        n = len(images)
        if n == 1: return image_buffers[0]
        
        cols = 2 if n > 1 else 1
        rows = (n + 1) // 2
        fig = plt.figure(figsize=(10 * cols, 8 * rows))
        
        for i, img in enumerate(images):
            ax = fig.add_subplot(rows, cols, i+1)
            ax.imshow(img)
            ax.axis('off')
            
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        return buf

    @staticmethod
    def create_pie_chart(logs, start_date, end_date, tasks_filter):
        df = GraphGenerator._prepare_df(logs, start_date, end_date, tasks_filter)
        if df is None: return None
        
        fp = GraphGenerator.get_font_prop(size=14)
        plt.figure(figsize=(10, 6))
        task_sum = df.groupby('task')['duration_min'].sum()
        colors = plt.cm.Pastel1.colors
        wedges, texts, autotexts = plt.pie(
            task_sum, labels=None, autopct='%1.1f%%', startangle=90, colors=colors, pctdistance=0.85
        )
        centre_circle = plt.Circle((0,0),0.70,fc='white')
        fig = plt.gcf()
        fig.gca().add_artist(centre_circle)
        plt.legend(wedges, task_sum.index, title="Tasks", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1), prop=fp)
        plt.title("行動内訳", fontproperties=fp, fontsize=16)
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        return buf

    @staticmethod
    def create_bar_chart(logs, start_date, end_date, tasks_filter):
        df = GraphGenerator._prepare_df(logs, start_date, end_date, tasks_filter)
        if df is None: return None
        fp = GraphGenerator.get_font_prop(size=14)
        plt.figure(figsize=(12, 6))
        pivot_df = df.pivot_table(index='date', columns='task', values='duration_min', aggfunc='sum', fill_value=0)
        if pivot_df.empty: return None
        ax = pivot_df.plot(kind='bar', stacked=True, colormap='Pastel1', figsize=(12, 6))
        plt.title("日別積み上げグラフ", fontproperties=fp, fontsize=16)
        plt.xlabel("日付", fontproperties=fp)
        plt.ylabel("時間 (分)", fontproperties=fp)
        plt.legend(prop=fp, bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.xticks(rotation=45, fontproperties=fp)
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        return buf

    @staticmethod
    def create_heatmap(logs, start_date, end_date, tasks_filter):
        df = GraphGenerator._prepare_df(logs, start_date, end_date, tasks_filter)
        if df is None: return None
        fp = GraphGenerator.get_font_prop(size=14)
        plt.figure(figsize=(10, 5))
        df['weekday'] = df['ts_obj'].dt.weekday
        df['hour'] = df['ts_obj'].dt.hour
        heatmap_data = df.pivot_table(index='weekday', columns='hour', values='duration_min', aggfunc='count', fill_value=0)
        heatmap_data = heatmap_data.reindex(index=range(7), columns=range(24), fill_value=0)
        plt.imshow(heatmap_data, cmap='Blues', aspect='auto')
        days_label = ['月', '火', '水', '木', '金', '土', '日']
        plt.yticks(range(7), days_label, fontproperties=fp)
        plt.xticks(range(24), [str(h) for h in range(24)], fontproperties=fp)
        plt.xlabel("時間帯 (時)", fontproperties=fp)
        plt.ylabel("曜日", fontproperties=fp)
        plt.title("活動リズム ヒートマップ (濃度=回数)", fontproperties=fp, fontsize=16)
        plt.colorbar(label="回数", pad=0.02)
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        return buf

    @staticmethod
    def create_punch_card(logs, start_date, end_date, tasks_filter):
        df = GraphGenerator._prepare_df(logs, start_date, end_date, tasks_filter)
        if df is None: return None
        fp = GraphGenerator.get_font_prop(size=14)
        df['weekday'] = df['ts_obj'].dt.weekday
        df['hour'] = df['ts_obj'].dt.hour
        grouped = df.groupby(['weekday', 'hour'])['duration_min'].sum().reset_index()
        plt.figure(figsize=(12, 6))
        plt.scatter(grouped['hour'], 6 - grouped['weekday'], s=grouped['duration_min']*2, alpha=0.6, c=grouped['duration_min'], cmap='viridis')
        days_label = ['日', '土', '金', '木', '水', '火', '月']
        plt.yticks(range(7), days_label, fontproperties=fp)
        plt.xticks(range(24), [str(h) for h in range(24)], fontproperties=fp)
        plt.xlabel("時間帯 (時)", fontproperties=fp)
        plt.ylabel("曜日", fontproperties=fp)
        plt.title("パンチカード (円の大きさ=活動時間)", fontproperties=fp, fontsize=16)
        plt.grid(True, linestyle='--', alpha=0.5)
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        return buf

    @staticmethod
    def create_timeline_vertical(logs, start_date, end_date, tasks_filter):
        df = GraphGenerator._prepare_df(logs, start_date, end_date, tasks_filter)
        if df is None: return None
        fp = GraphGenerator.get_font_prop(size=12)
        
        df['date_only'] = df['ts_obj'].dt.date
        df['end_time'] = df['ts_obj']
        df['start_time'] = df['end_time'] - pd.to_timedelta(df['duration_min'], unit='m')
        
        dates = sorted(df['date_only'].unique())
        if len(dates) > 30:
             dates = dates[-30:]
             df = df[df['date_only'].isin(dates)]
             
        fig, ax = plt.subplots(figsize=(len(dates) * 1.5 + 2, 10))
        ax.set_xlim(-0.5, len(dates) - 0.5)
        ax.set_ylim(24, 0)
        
        unique_tasks = df['task'].unique()
        cmap = plt.cm.get_cmap('Pastel1', len(unique_tasks))
        task_colors = {task: cmap(i) for i, task in enumerate(unique_tasks)}
        
        legend_handles = []
        for task, color in task_colors.items():
            legend_handles.append(patches.Patch(color=color, label=task))

        for i, target_date in enumerate(dates):
            day_df = df[df['date_only'] == target_date]
            for _, row in day_df.iterrows():
                start_h = row['start_time'].hour + row['start_time'].minute / 60
                end_h = row['end_time'].hour + row['end_time'].minute / 60
                if start_h < 0: start_h = 0
                if end_h > 24: end_h = 24
                duration_h = end_h - start_h
                if duration_h <= 0: continue
                rect = patches.Rectangle((i - 0.4, start_h), 0.8, duration_h, facecolor=task_colors[row['task']], edgecolor='white')
                ax.add_patch(rect)

        ax.set_xticks(range(len(dates)))
        ax.set_xticklabels([d.strftime('%m/%d') for d in dates], fontproperties=fp, rotation=45)
        ax.set_ylabel("時刻", fontproperties=fp)
        ax.grid(axis='y', linestyle='--', alpha=0.5)
        plt.title(f"タイムライン ({len(dates)}日間)", fontproperties=fp, fontsize=16)
        plt.legend(handles=legend_handles, bbox_to_anchor=(1.05, 1), loc='upper left', prop=fp)
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        return buf

    @staticmethod
    def create_daily_timeline(logs, target_date=None):
        if not logs: return None
        df = pd.DataFrame(logs)
        if df.empty: return None
        if 'timestamp' in df.columns:
             df['end_time'] = pd.to_datetime(df['timestamp']).dt.tz_convert(JST).dt.tz_localize(None)
        else:
             df['end_time'] = pd.to_datetime(df['date'])
        
        if target_date is None:
            target_date = datetime.datetime.now(JST).date()
        
        df['date_only'] = df['end_time'].dt.date
        df = df[df['date_only'] == target_date].copy()
        if df.empty: return None
        
        df['start_time'] = df['end_time'] - pd.to_timedelta(df['duration_min'], unit='m')
        
        fp = GraphGenerator.get_font_prop(size=12)
        fp_bold = GraphGenerator.get_font_prop(size=14, weight='bold')
        
        fig, ax = plt.subplots(figsize=(8, 12))
        ax.set_xlim(0, 100)
        ax.set_ylim(24, 0)
        ax.set_facecolor('#f8f9fa')
        
        for h in range(25):
            ax.axhline(y=h, color='#dee2e6', linewidth=1) 
            if h < 24:
                for m in [0.25, 0.5, 0.75]:
                    ax.axhline(y=h+m, color='#e9ecef', linewidth=0.5, linestyle=':')

        ax.set_yticks(range(0, 25))
        ax.set_yticklabels([f"{h:02d}:00" for h in range(25)], fontsize=10, fontproperties=fp)
        
        unique_tasks = df['task'].unique()
        cmap = plt.cm.get_cmap('Pastel1', len(unique_tasks))
        task_colors = {task: cmap(i) for i, task in enumerate(unique_tasks)}
        
        for _, row in df.iterrows():
            start_h = row['start_time'].hour + row['start_time'].minute / 60
            end_h = row['end_time'].hour + row['end_time'].minute / 60
            if start_h < 0: start_h = 0
            if end_h > 24: end_h = 24
            duration_h = end_h - start_h
            if duration_h <= 0: continue
            
            rect = patches.Rectangle((15, start_h), 60, duration_h, linewidth=1, edgecolor='white', facecolor=task_colors[row['task']])
            ax.add_patch(rect)
            
            time_str = f"{row['start_time'].strftime('%H:%M')} - {row['end_time'].strftime('%H:%M')}"
            memo_str = f" ({row['memo']})" if row.get('memo') else ""
            label_str = f"{time_str}\n{row['task']}{memo_str}"
            ax.text(18, start_h + (duration_h/2), label_str, va='center', ha='left', fontsize=10, fontproperties=fp, color='#495057')

        ax.set_xticks([])
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_visible(False)
        ax.spines['left'].set_color('#ced4da')
        
        title_date = target_date.strftime('%Y/%m/%d')
        plt.title(f"DAILY TIMELINE (15min Grid) - {title_date}", fontproperties=fp_bold, pad=20)
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100)
        buf.seek(0)
        plt.close()
        return buf

    @staticmethod
    def calculate_progress(logs, goals):
        if not logs or not goals: return []
        df = pd.DataFrame(logs)
        if df.empty: return []
        if 'timestamp' in df.columns:
            df['ts_obj'] = pd.to_datetime(df['timestamp']).dt.tz_convert(JST).dt.tz_localize(None)
        else:
            df['ts_obj'] = pd.to_datetime(df['date'])
        now = datetime.datetime.now(JST).replace(tzinfo=None)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_week = today - pd.Timedelta(days=today.weekday())
        start_of_month = today.replace(day=1)
        progress_data = []
        for task_name, goal_list in goals.items():
            if isinstance(goal_list, dict): goal_list = [goal_list]
            for goal_info in goal_list:
                target = goal_info.get("target", 0)
                period = goal_info.get("period", "daily")
                custom_days = goal_info.get("custom_days", 0)
                created_at_str = goal_info.get("created_at")
                if target == 0: continue
                current = 0
                label_period = ""
                if period == "daily":
                    current = df[(df['task'] == task_name) & (df['ts_obj'] >= today)]['duration_min'].sum()
                    label_period = "今日"
                elif period == "weekly":
                    current = df[(df['task'] == task_name) & (df['ts_obj'] >= start_of_week)]['duration_min'].sum()
                    label_period = "今週"
                elif period == "monthly":
                    current = df[(df['task'] == task_name) & (df['ts_obj'] >= start_of_month)]['duration_min'].sum()
                    label_period = "今月"
                elif period == "custom" and created_at_str:
                    try: start_date = pd.to_datetime(created_at_str).tz_localize(None)
                    except: start_date = today
                    end_date = start_date + pd.Timedelta(days=custom_days)
                    current = df[(df['task'] == task_name) & (df['ts_obj'] >= start_date) & (df['ts_obj'] <= end_date)]['duration_min'].sum()
                    days_left = (end_date - now).days
                    if days_left < 0: days_left = 0
                    label_period = f"{custom_days}日間 (残{days_left}日)"
                progress_data.append({
                    "task": task_name,
                    "current": int(current),
                    "target": target,
                    "period_label": label_period,
                    "percent": min(100, int((current / target) * 100))
                })
        return progress_data

# ---------------------------------------------------------
# 6. UIコンポーネント
# ---------------------------------------------------------
class ReportConfigView(discord.ui.View):
    def __init__(self, bot, tasks):
        super().__init__(timeout=None)
        self.bot = bot
        self.tasks = tasks
        self.period = "30days"
        self.selected_tasks = []
        self.selected_charts = ["pie"]
        self.layout = "combined"
        self.custom_start = None
        self.custom_end = None
        
        self.add_item(ReportPeriodSelect())
        self.add_item(ReportTaskSelect(tasks))
        self.add_item(ReportChartSelect())
        self.add_item(ReportLayoutSelect())
        self.add_item(ReportGenerateButton())

class ReportPeriodSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="過去7日間", value="7days"),
            discord.SelectOption(label="過去30日間", value="30days", default=True),
            discord.SelectOption(label="今週 (月曜~)", value="this_week"),
            discord.SelectOption(label="先週", value="last_week"),
            discord.SelectOption(label="今月", value="this_month"),
            discord.SelectOption(label="先月", value="last_month"),
            discord.SelectOption(label="全期間", value="all"),
            discord.SelectOption(label="期間を指定 (日付入力)", value="custom"),
        ]
        super().__init__(placeholder="📅 期間 (デフォルト: 過去30日)", options=options, row=0)
    async def callback(self, interaction: discord.Interaction):
        self.view.period = self.values[0]
        if self.values[0] == "custom":
            await interaction.response.send_modal(ReportCustomDateModal(self.view))
        else:
            await interaction.response.defer()

class ReportCustomDateModal(discord.ui.Modal, title="期間指定"):
    start_date = discord.ui.TextInput(label="開始日 (YYYY-MM-DD)", placeholder="2024-01-01")
    end_date = discord.ui.TextInput(label="終了日 (YYYY-MM-DD)", placeholder="2024-01-31")
    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view
    async def on_submit(self, interaction: discord.Interaction):
        self.parent_view.custom_start = self.start_date.value
        self.parent_view.custom_end = self.end_date.value
        await interaction.response.defer()
        await interaction.followup.send(f"期間を設定しました: {self.start_date.value} ~ {self.end_date.value}", ephemeral=True)

class ReportTaskSelect(discord.ui.Select):
    def __init__(self, tasks):
        options = []
        for t in tasks[:25]:
            options.append(discord.SelectOption(label=t["name"]))
        super().__init__(placeholder="✅ タスク (未選択で全て)", options=options, min_values=0, max_values=len(options), row=1)
    async def callback(self, interaction: discord.Interaction):
        self.view.selected_tasks = self.values
        await interaction.response.defer()

class ReportChartSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="円グラフ (割合)", value="pie"),
            discord.SelectOption(label="積み上げ棒グラフ (推移)", value="bar"),
            discord.SelectOption(label="ヒートマップ (曜日×時間)", value="heatmap"),
            discord.SelectOption(label="パンチカード (活動密度)", value="punch"),
            discord.SelectOption(label="タイムライン (時系列・縦長)", value="timeline"),
        ]
        super().__init__(placeholder="📈 グラフ種類 (複数選択可)", options=options, min_values=1, max_values=5, row=2)
    async def callback(self, interaction: discord.Interaction):
        self.view.selected_charts = self.values
        await interaction.response.defer()

class ReportLayoutSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1枚の画像にまとめる", value="combined", description="複数のグラフを結合して出力", default=True),
            discord.SelectOption(label="個別に出力する", value="separate", description="グラフごとに別の画像として出力"),
        ]
        super().__init__(placeholder="🖼️ 出力形式", options=options, row=3)
    async def callback(self, interaction: discord.Interaction):
        self.view.layout = self.values[0]
        await interaction.response.defer()

class ReportGenerateButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="レポート生成", style=discord.ButtonStyle.primary, row=4)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view = self.view
        
        now = datetime.datetime.now(JST).replace(tzinfo=None)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_date = None
        end_date = None
        
        if view.period == "7days": start_date = now - pd.Timedelta(days=7)
        elif view.period == "30days": start_date = now - pd.Timedelta(days=30)
        elif view.period == "this_week": start_date = today - pd.Timedelta(days=today.weekday())
        elif view.period == "last_week":
            start_of_this_week = today - pd.Timedelta(days=today.weekday())
            start_date = start_of_this_week - pd.Timedelta(days=7)
            end_date = start_of_this_week - pd.Timedelta(seconds=1)
        elif view.period == "this_month": start_date = today.replace(day=1)
        elif view.period == "last_month":
            start_of_this_month = today.replace(day=1)
            end_date = start_of_this_month - pd.Timedelta(seconds=1)
            start_date = end_date.replace(day=1, hour=0, minute=0, second=0)
        elif view.period == "custom":
            try:
                start_date = pd.to_datetime(view.custom_start)
                end_date = pd.to_datetime(view.custom_end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            except:
                await interaction.followup.send("日付エラー", ephemeral=True)
                return
        
        dm = DataManager(view.bot)
        logs = await dm.fetch_logs(interaction.guild, limit=2000)
        
        generated_buffers = []
        titles = []
        
        chart_types = view.selected_charts
        if not chart_types: chart_types = ["pie"]

        for c_type in chart_types:
            buf = None
            t_str = ""
            if c_type == "pie":
                buf = GraphGenerator.create_pie_chart(logs, start_date, end_date, view.selected_tasks)
                t_str = "円グラフ"
            elif c_type == "bar":
                buf = GraphGenerator.create_bar_chart(logs, start_date, end_date, view.selected_tasks)
                t_str = "棒グラフ"
            elif c_type == "heatmap":
                buf = GraphGenerator.create_heatmap(logs, start_date, end_date, view.selected_tasks)
                t_str = "ヒートマップ"
            elif c_type == "punch":
                buf = GraphGenerator.create_punch_card(logs, start_date, end_date, view.selected_tasks)
                t_str = "パンチカード"
            elif c_type == "timeline":
                buf = GraphGenerator.create_timeline_vertical(logs, start_date, end_date, view.selected_tasks)
                t_str = "タイムライン"
            
            if buf:
                generated_buffers.append(buf)
                titles.append(t_str)

        if not generated_buffers:
            await interaction.followup.send("対象データがありません。", ephemeral=True)
            return

        report_ch = await dm.get_report_channel(interaction.guild)
        p_str = view.period
        if start_date: p_str = f"{start_date.strftime('%Y/%m/%d')} ~"
        if end_date: p_str += f" {end_date.strftime('%Y/%m/%d')}"

        if view.layout == "combined" and len(generated_buffers) > 1:
            combined_buf = GraphGenerator.combine_images(generated_buffers)
            file = discord.File(combined_buf, filename="report_combined.png")
            embed = discord.Embed(title=f"📊 統合レポート ({', '.join(titles)})", color=discord.Color.purple())
            embed.set_footer(text=f"期間: {p_str}")
            embed.set_image(url="attachment://report_combined.png")
            
            if report_ch:
                await report_ch.send(embed=embed, file=file)
                await interaction.followup.send(f"✅ レポートを出力しました: {report_ch.mention}", ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, file=file)
        else:
            files = []
            for i, buf in enumerate(generated_buffers):
                files.append(discord.File(buf, filename=f"report_{i}.png"))
            content = f"📊 **レポート出力** (期間: {p_str})"
            if report_ch:
                await report_ch.send(content=content, files=files)
                await interaction.followup.send(f"✅ レポートを出力しました: {report_ch.mention}", ephemeral=True)
            else:
                await interaction.followup.send(content=content, files=files)

        await resend_dashboard(interaction, view.bot)

class GoalManagePanel(discord.ui.View):
    def __init__(self, bot, tasks):
        super().__init__(timeout=None)
        self.bot = bot
        self.tasks = tasks
    @discord.ui.button(label="➕ 目標を追加", style=discord.ButtonStyle.success, custom_id="goal_panel_add", row=0)
    async def add_goal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("目標を追加するタスクを選択:", view=GoalAddSelectView(self.bot, self.tasks), ephemeral=True)
    @discord.ui.button(label="👀 目標リスト (編集・削除)", style=discord.ButtonStyle.primary, custom_id="goal_panel_list_edit", row=0)
    async def list_edit_goal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        dm = DataManager(self.bot)
        goals = await dm.load_goals(interaction.guild)
        if not goals:
            await interaction.followup.send("目標なし", ephemeral=True)
            return
        embed = discord.Embed(title="🎯 目標リスト", description="下部のメニューから目標を選択して編集・削除ができます。", color=discord.Color.blue())
        select_options = []
        for task, goal_list in goals.items():
            if isinstance(goal_list, dict): goal_list = [goal_list]
            for i, info in enumerate(goal_list):
                target = info.get('target')
                p_code = info.get('period')
                p_text = p_code
                if p_code == 'daily': p_text = "1日"
                elif p_code == 'weekly': p_text = "1週間"
                elif p_code == 'monthly': p_text = "1ヶ月"
                elif p_code == 'custom': p_text = f"{info.get('custom_days')}日間"
                label = f"{task}: {p_text} {target}分"
                value = f"{task}|{i}"
                embed.add_field(name=task, value=f"・{p_text}あたり {target}分", inline=False)
                if len(select_options) < 25:
                    select_options.append(discord.SelectOption(label=label[:100], value=value))
        view = GoalListActionView(self.bot, select_options)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
    @discord.ui.button(label="🔄 更新", style=discord.ButtonStyle.secondary, custom_id="goal_panel_refresh", row=0)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        dm = DataManager(self.bot)
        await dm.refresh_goals_panel(interaction.guild)
    @discord.ui.button(label="👀 目標一覧", style=discord.ButtonStyle.secondary, custom_id="goal_panel_list", row=1)
    async def list_goals(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        dm = DataManager(self.bot)
        goals = await dm.load_goals(interaction.guild)
        if not goals:
            await interaction.followup.send("設定なし", ephemeral=True)
            return
        embed = discord.Embed(title="🎯 目標設定一覧", color=discord.Color.blue())
        for task, goal_list in goals.items():
            if isinstance(goal_list, dict): goal_list = [goal_list]
            value_text = ""
            for info in goal_list:
                p_code = info.get('period')
                target = info.get('target')
                p_text = "不明"
                if p_code == 'daily': p_text = "1日"
                elif p_code == 'weekly': p_text = "1週間"
                elif p_code == 'monthly': p_text = "1ヶ月"
                elif p_code == 'custom': p_text = f"{info.get('custom_days')}日間"
                value_text += f"・{p_text} {target}分\n"
            if value_text: embed.add_field(name=task, value=value_text, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

class GoalListActionView(discord.ui.View):
    def __init__(self, bot, options):
        super().__init__()
        self.bot = bot
        if options: self.add_item(GoalListSelect(bot, options))
        else: self.add_item(discord.ui.Button(label="目標なし", disabled=True))

class GoalListSelect(discord.ui.Select):
    def __init__(self, bot, options):
        super().__init__(placeholder="編集・削除する目標を選択...", options=options)
        self.bot = bot
    async def callback(self, interaction: discord.Interaction):
        selected_val = self.values[0]
        try:
            task_name, index_str = selected_val.rsplit('|', 1)
            index = int(index_str)
            await interaction.response.send_message(
                f"**{task_name}** の目標を選択しました。",
                view=GoalActionView(self.bot, task_name, index),
                ephemeral=True
            )
        except:
            await interaction.response.send_message("エラーが発生しました。", ephemeral=True)

class GoalActionView(discord.ui.View):
    def __init__(self, bot, task_name, index):
        super().__init__()
        self.bot = bot
        self.task_name = task_name
        self.index = index
    @discord.ui.button(label="✏️ 編集", style=discord.ButtonStyle.primary)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GoalInputModal(self.bot, self.task_name, self.index))
    @discord.ui.button(label="🗑️ 削除", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        dm = DataManager(self.bot)
        goals = await dm.load_goals(interaction.guild)
        if self.task_name in goals:
            task_goals = goals[self.task_name]
            if isinstance(task_goals, dict): task_goals = [task_goals]
            if 0 <= self.index < len(task_goals):
                task_goals.pop(self.index)
                goals[self.task_name] = task_goals
                await dm.save_goals(interaction.guild, goals)
                await dm.refresh_goals_panel(interaction.guild)
                await interaction.followup.send("🗑️ 目標を削除しました。")
                await resend_dashboard(interaction, self.bot)
            else: await interaction.followup.send("エラー: 目標なし")
        else: await interaction.followup.send("エラー: タスクなし")

class GoalAddSelectView(discord.ui.View):
    def __init__(self, bot, tasks):
        super().__init__()
        options = [discord.SelectOption(label=t["name"][:100]) for t in tasks]
        self.add_item(GoalAddSelect(bot, options))

class GoalAddSelect(discord.ui.Select):
    def __init__(self, bot, options):
        super().__init__(placeholder="タスクを選択...", options=options)
        self.bot = bot
    async def callback(self, interaction: discord.Interaction):
        selected_name = self.values[0]
        await interaction.response.send_modal(GoalInputModal(self.bot, selected_name))

class GoalInputModal(discord.ui.Modal, title="目標設定"):
    target_time = discord.ui.TextInput(label="目標時間 (分)", placeholder="例: 60")
    period_select = discord.ui.TextInput(label="期間 (1日, 1週間, 1ヶ月, カスタム)", placeholder="1日")
    custom_days = discord.ui.TextInput(label="カスタム日数 (カスタムの場合のみ)", placeholder="例: 20", required=False)
    def __init__(self, bot, task_name, edit_index=None):
        super().__init__()
        self.bot = bot
        self.task_name = task_name
        self.edit_index = edit_index
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            target = int(self.target_time.value)
            p_val = self.period_select.value.strip().lower()
            period = None
            if p_val in ['d', 'day', 'daily', '1日', '日', '毎日']: period = 'daily'
            elif p_val in ['w', 'week', 'weekly', '1週間', '週', '毎週']: period = 'weekly'
            elif p_val in ['m', 'month', 'monthly', '1ヶ月', '月', '毎月']: period = 'monthly'
            elif p_val in ['c', 'custom', '期間', '指定']: period = 'custom'
            if not period:
                await interaction.followup.send("⚠️ 期間エラー")
                return
            dm = DataManager(self.bot)
            goals = await dm.load_goals(interaction.guild)
            goal_data = {
                "target": target,
                "period": period,
                "created_at": datetime.datetime.now().isoformat()
            }
            if period == 'custom':
                if not self.custom_days.value:
                    await interaction.followup.send("⚠️ 日数エラー")
                    return
                goal_data["custom_days"] = int(self.custom_days.value)
            if self.task_name not in goals: goals[self.task_name] = []
            elif isinstance(goals[self.task_name], dict): goals[self.task_name] = [goals[self.task_name]]
            
            msg = ""
            if self.edit_index is not None and 0 <= self.edit_index < len(goals[self.task_name]):
                goals[self.task_name][self.edit_index] = goal_data
                msg = f"✅ **{self.task_name}** の目標を更新しました。"
            else:
                goals[self.task_name].append(goal_data)
                msg = f"✅ **{self.task_name}** の目標を追加しました。"
            await dm.save_goals(interaction.guild, goals)
            await dm.refresh_goals_panel(interaction.guild)
            await interaction.followup.send(msg)
            await resend_dashboard(interaction, self.bot)
        except ValueError:
            await interaction.followup.send("⚠️ 数値エラー")

class DashboardView(discord.ui.View):
    def __init__(self, bot, tasks):
        super().__init__(timeout=None)
        self.bot = bot
        
        # タスクボタンの配置 (2行分、6個まで)
        buttons_per_row = 3
        max_task_rows = 2 # 2行に制限 (Row 0, 1)
        max_buttons = buttons_per_row * max_task_rows # 6個

        main_tasks = tasks[:max_buttons]
        overflow_tasks = tasks[max_buttons:]

        for i, task in enumerate(main_tasks):
            row = i // buttons_per_row
            self.add_item(TaskButton(task["name"], task.get("style", "secondary"), row=row))

        # あふれたタスク (Row 2)
        if overflow_tasks:
            self.add_item(OverflowTaskSelect(overflow_tasks, row=2))

        # 機能ボタン群1 (Row 3 - 5個)
        self.add_item(self.create_func_btn("📝 自由入力", discord.ButtonStyle.secondary, "free_input", self.free_input_btn, 3))
        self.add_item(self.create_func_btn("📅 今日の記録", discord.ButtonStyle.secondary, "daily_today", self.daily_today_btn, 3))
        self.add_item(self.create_func_btn("📅 昨日の記録", discord.ButtonStyle.secondary, "daily_yesterday", self.daily_yesterday_btn, 3))
        self.add_item(self.create_func_btn("📊 レポート", discord.ButtonStyle.secondary, "report", self.report_btn, 3))
        self.add_item(self.create_func_btn("🔥 進捗", discord.ButtonStyle.primary, "progress", self.progress_btn, 3))

        # 機能ボタン群2 (Row 4 - 2個)
        self.add_item(self.create_func_btn("⚙️ 設定", discord.ButtonStyle.secondary, "manage", self.manage_btn, 4))
        self.add_item(self.create_func_btn("🔄 再設置", discord.ButtonStyle.gray, "refresh", self.refresh_btn, 4))

    def create_func_btn(self, label, style, custom_id_suffix, callback_func, row):
        btn = discord.ui.Button(label=label, style=style, custom_id=f"dashboard_{custom_id_suffix}", row=row)
        btn.callback = callback_func
        return btn

    async def free_input_btn(self, interaction: discord.Interaction):
        await interaction.response.send_modal(FreeTaskStartModal())

    async def daily_today_btn(self, interaction: discord.Interaction):
        await self.generate_daily_timeline(interaction, target_date=datetime.datetime.now(JST).date())

    async def daily_yesterday_btn(self, interaction: discord.Interaction):
        yesterday = datetime.datetime.now(JST).date() - datetime.timedelta(days=1)
        await self.generate_daily_timeline(interaction, target_date=yesterday)

    async def generate_daily_timeline(self, interaction, target_date):
        await interaction.response.defer()
        dm = DataManager(self.bot)
        logs = await dm.fetch_logs(interaction.guild, limit=300)
        image_buf = GraphGenerator.create_daily_timeline(logs, target_date=target_date)
        
        if image_buf is None:
            await interaction.followup.send(f"{target_date.strftime('%Y/%m/%d')} のデータはありません。")
            await resend_dashboard(interaction, self.bot)
            return
            
        file = discord.File(image_buf, filename="daily.png")
        embed = discord.Embed(title=f"📅 デイリータイムライン ({target_date.strftime('%Y/%m/%d')})", color=discord.Color.blue())
        embed.set_image(url="attachment://daily.png")
        await interaction.followup.send(embed=embed, file=file)
        await resend_dashboard(interaction, self.bot)

    async def report_btn(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        dm = DataManager(self.bot)
        tasks = await dm.load_tasks(interaction.guild)
        view = ReportConfigView(self.bot, tasks)
        await interaction.followup.send("📊 **レポート設定**\n条件を選択して「レポート生成」を押してください。", view=view, ephemeral=True)

    async def progress_btn(self, interaction: discord.Interaction):
        await interaction.response.defer()
        dm = DataManager(self.bot)
        logs = await dm.fetch_logs(interaction.guild, limit=1000)
        goals = await dm.load_goals(interaction.guild)
        if not goals:
            await interaction.followup.send("目標なし")
            await resend_dashboard(interaction, self.bot)
            return
        progress_data = GraphGenerator.calculate_progress(logs, goals)
        if not progress_data:
            await interaction.followup.send("データなし")
            await resend_dashboard(interaction, self.bot)
            return
        embed = discord.Embed(title="🔥 目標進捗状況", color=discord.Color.orange())
        for p in progress_data:
            bar_len = 10
            filled = int(bar_len * (p['percent'] / 100))
            bar = "▓" * filled + "░" * (bar_len - filled)
            value_str = f"{p['current']}/{p['target']}分"
            embed.add_field(name=f"{p['task']} ({p['period_label']})", value=f"`[{bar}]` **{p['percent']}%** ({value_str})", inline=False)
        await interaction.followup.send(embed=embed)
        await resend_dashboard(interaction, self.bot)

    async def manage_btn(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        dm = DataManager(self.bot)
        tasks = await dm.load_tasks(interaction.guild)
        view = TaskManageView(self.bot, interaction.guild, tasks)
        await interaction.followup.send("📝 **タスク管理**", view=view, ephemeral=True)

    async def refresh_btn(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await resend_dashboard(interaction, self.bot)

# --- TaskManageView ---
class TaskManageView(discord.ui.View):
    def __init__(self, bot, guild, tasks):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild = guild
        self.tasks = tasks
        self.dm = DataManager(bot)

    async def refresh_panel_message(self, interaction):
        await self.dm.save_tasks(self.guild, self.tasks)
        await interaction.followup.send("✅ 保存しました。")
        await resend_dashboard(interaction, self.bot)

    @discord.ui.button(label="➕ 追加", style=discord.ButtonStyle.primary, row=0)
    async def add_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddTaskModal(self))
    @discord.ui.button(label="🗑️ 削除", style=discord.ButtonStyle.danger, row=0)
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("削除:", view=DeleteSelectView(self), ephemeral=True)
    @discord.ui.button(label="✏️ リネーム", style=discord.ButtonStyle.secondary, row=0)
    async def rename_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("リネーム:", view=RenameSelectView(self), ephemeral=True)
    @discord.ui.button(label="🎨 色変更", style=discord.ButtonStyle.secondary, row=0)
    async def color_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("色変更:", view=ColorSelectTaskView(self), ephemeral=True)
    @discord.ui.button(label="📋 一括編集", style=discord.ButtonStyle.success, row=1)
    async def edit_all_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        default_text = "\n".join([t["name"] for t in self.tasks])
        await interaction.response.send_modal(EditAllModal(self, default_text))
    @discord.ui.button(label="👀 目標一覧", style=discord.ButtonStyle.secondary, row=1)
    async def goal_list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        dm = DataManager(self.bot)
        goals = await dm.load_goals(interaction.guild)
        if not goals:
            await interaction.followup.send("設定なし")
            await resend_dashboard(interaction, self.bot)
            return
        embed = discord.Embed(title="🎯 目標設定一覧", color=discord.Color.blue())
        for task, goal_list in goals.items():
            if isinstance(goal_list, dict): goal_list = [goal_list]
            value_text = ""
            for info in goal_list:
                p_code = info.get('period')
                target = info.get('target')
                p_text = "不明"
                if p_code == 'daily': p_text = "1日"
                elif p_code == 'weekly': p_text = "1週間"
                elif p_code == 'monthly': p_text = "1ヶ月"
                elif p_code == 'custom': p_text = f"{info.get('custom_days')}日間"
                value_text += f"・{p_text} {target}分\n"
            if value_text: embed.add_field(name=task, value=value_text, inline=False)
        await interaction.followup.send(embed=embed)
        await resend_dashboard(interaction, self.bot)

class AddTaskModal(discord.ui.Modal, title="タスクの追加"):
    name = discord.ui.TextInput(label="タスク名", placeholder="例: 🏃 ランニング")
    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        new_task_name = self.name.value
        if not any(t["name"] == new_task_name for t in self.parent_view.tasks):
            self.parent_view.tasks.append({"name": new_task_name, "style": "secondary"})
            await self.parent_view.refresh_panel_message(interaction)
        else:
            await interaction.followup.send("重複しています。", ephemeral=True)

class DeleteSelectView(discord.ui.View):
    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view
        options = [discord.SelectOption(label=t["name"][:100]) for t in parent_view.tasks]
        self.add_item(DeleteSelect(options, parent_view))

class DeleteSelect(discord.ui.Select):
    def __init__(self, options, parent_view):
        super().__init__(placeholder="削除選択...", options=options)
        self.parent_view = parent_view
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        selected_name = self.values[0]
        self.parent_view.tasks = [t for t in self.parent_view.tasks if t["name"] != selected_name]
        await self.parent_view.refresh_panel_message(interaction)

class RenameSelectView(discord.ui.View):
    def __init__(self, parent_view):
        super().__init__()
        options = [discord.SelectOption(label=t["name"][:100]) for t in parent_view.tasks]
        self.add_item(RenameSelect(options, parent_view))

class RenameSelect(discord.ui.Select):
    def __init__(self, options, parent_view):
        super().__init__(placeholder="変更選択...", options=options)
        self.parent_view = parent_view
    async def callback(self, interaction: discord.Interaction):
        selected_name = self.values[0]
        await interaction.response.send_modal(RenameModal(self.parent_view, selected_name))

class RenameModal(discord.ui.Modal, title="名前の変更"):
    new_name = discord.ui.TextInput(label="新しい名前")
    def __init__(self, parent_view, old_name):
        super().__init__()
        self.parent_view = parent_view
        self.old_name = old_name
        self.new_name.default = old_name
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        val = self.new_name.value
        for task in self.parent_view.tasks:
            if task["name"] == self.old_name:
                task["name"] = val
                break
        await self.parent_view.refresh_panel_message(interaction)

class ColorSelectTaskView(discord.ui.View):
    def __init__(self, parent_view):
        super().__init__()
        options = [discord.SelectOption(label=t["name"][:100]) for t in parent_view.tasks]
        self.add_item(ColorSelectTask(options, parent_view))

class ColorSelectTask(discord.ui.Select):
    def __init__(self, options, parent_view):
        super().__init__(placeholder="タスク選択...", options=options)
        self.parent_view = parent_view
    async def callback(self, interaction: discord.Interaction):
        selected_name = self.values[0]
        await interaction.response.send_message(
            f"「{selected_name}」の色を選択:", 
            view=ColorSelectStyleView(self.parent_view, selected_name), 
            ephemeral=True
        )

class ColorSelectStyleView(discord.ui.View):
    def __init__(self, parent_view, target_task_name):
        super().__init__()
        self.parent_view = parent_view
        self.target_task_name = target_task_name
    @discord.ui.button(label="Primary (青)", style=discord.ButtonStyle.primary)
    async def primary(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_color(interaction, "primary")
    @discord.ui.button(label="Secondary (灰)", style=discord.ButtonStyle.secondary)
    async def secondary(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_color(interaction, "secondary")
    @discord.ui.button(label="Success (緑)", style=discord.ButtonStyle.success)
    async def success(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_color(interaction, "success")
    @discord.ui.button(label="Danger (赤)", style=discord.ButtonStyle.danger)
    async def danger(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_color(interaction, "danger")
    async def update_color(self, interaction: discord.Interaction, style_name):
        await interaction.response.defer()
        for task in self.parent_view.tasks:
            if task["name"] == self.target_task_name:
                task["style"] = style_name
                break
        await self.parent_view.refresh_panel_message(interaction)

class EditAllModal(discord.ui.Modal, title="並び替え・一括編集"):
    text = discord.ui.TextInput(label="1行に1つタスクを記述", style=discord.TextStyle.paragraph)
    def __init__(self, parent_view, default_text):
        super().__init__()
        self.parent_view = parent_view
        self.text.default = default_text
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        new_names = [line.strip() for line in self.text.value.split('\n') if line.strip()]
        if new_names:
            old_tasks_map = {t["name"]: t["style"] for t in self.parent_view.tasks}
            new_tasks = []
            for name in new_names:
                style = old_tasks_map.get(name, "secondary")
                new_tasks.append({"name": name, "style": style})
            self.parent_view.tasks = new_tasks
            await self.parent_view.refresh_panel_message(interaction)
        else:
            await interaction.followup.send("空です。", ephemeral=True)

class FreeTaskStartModal(discord.ui.Modal, title="自由入力でスタート"):
    task_name = discord.ui.TextInput(label="今からやることは？", placeholder="例: 電球交換")
    async def on_submit(self, interaction: discord.Interaction):
        selected = self.task_name.value
        now = datetime.datetime.now(JST)
        start_str = now.strftime("%Y-%m-%d %H:%M:%S")
        timestamp = int(now.timestamp())
        description = f"**{start_str}**\n経過: <t:{timestamp}:R>"
        embed = discord.Embed(title=f"🚀 スタート: {selected}", description=description, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=FinishTaskView())

class TaskButton(discord.ui.Button):
    def __init__(self, task_name, style_name="secondary", row=0):
        style = BUTTON_STYLES.get(style_name, discord.ButtonStyle.secondary)
        super().__init__(label=task_name[:80], style=style, row=row)
        self.task_name = task_name
    async def callback(self, interaction: discord.Interaction):
        now = datetime.datetime.now(JST)
        start_str = now.strftime("%Y-%m-%d %H:%M:%S")
        timestamp = int(now.timestamp())
        description = f"**{start_str}**\n経過: <t:{timestamp}:R>"
        embed = discord.Embed(title=f"🚀 スタート: {self.task_name}", description=description, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=FinishTaskView())

class OverflowTaskSelect(discord.ui.Select):
    def __init__(self, tasks, row=3):
        options = [discord.SelectOption(label=t["name"][:100]) for t in tasks]
        super().__init__(placeholder="⏬ その他のタスク...", options=options, custom_id="dashboard_overflow_select", row=row)
    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        now = datetime.datetime.now(JST)
        start_str = now.strftime("%Y-%m-%d %H:%M:%S")
        timestamp = int(now.timestamp())
        description = f"**{start_str}**\n経過: <t:{timestamp}:R>"
        embed = discord.Embed(title=f"🚀 スタート: {selected}", description=description, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=FinishTaskView())

class MemoModal(discord.ui.Modal, title='完了メモ'):
    memo = discord.ui.TextInput(label='一言メモ（任意）', style=discord.TextStyle.short, required=False)
    def __init__(self, task_name, start_time, view_item, original_message):
        super().__init__()
        self.task_name = task_name
        self.start_time = start_time
        self.view_item = view_item
        self.original_message = original_message
        
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        end_time = datetime.datetime.now(JST)
        if self.start_time.tzinfo is None:
             start_aware = self.start_time.replace(tzinfo=JST)
        else:
             start_aware = self.start_time
        duration = end_time - start_aware
        minutes = int(duration.total_seconds() // 60)
        seconds = int(duration.total_seconds() % 60)
        log_data = {
            "task": self.task_name,
            "duration_min": minutes,
            "duration_str": f"{minutes}分 {seconds}秒",
            "memo": self.memo.value,
            "date": end_time.strftime("%Y-%m-%d"),
            "timestamp": end_time.isoformat()
        }
        dm = DataManager(client)
        await dm.save_log(interaction.guild, log_data)
        praise = random.choice(PRAISE_MESSAGES)
        embed = discord.Embed(title=f"✅ {praise}", color=discord.Color.gold())
        embed.add_field(name="内容", value=self.task_name)
        embed.add_field(name="時間", value=log_data['duration_str'])
        if self.memo.value:
            embed.add_field(name="📝 メモ", value=self.memo.value, inline=False)
        for child in self.view_item.children:
            child.disabled = True
        await self.original_message.edit(view=self.view_item)
        await interaction.followup.send(embed=embed)
        await resend_dashboard(interaction, client)

class FinishTaskView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="完了 (Done)", style=discord.ButtonStyle.green, custom_id="finish_btn_v4")
    async def finish(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = interaction.message.embeds[0]
        try:
            lines = embed.description.split('\n')
            time_str = lines[0].replace('**', '').strip()
            start_time = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=JST)
            task_name = embed.title.replace("🚀 スタート: ", "")
            await interaction.response.send_modal(MemoModal(task_name, start_time, self, interaction.message))
        except:
            try:
                time_str = embed.footer.text.replace("開始時刻: ", "")
                start_time = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=JST)
                task_name = embed.title.replace("🚀 スタート: ", "")
                await interaction.response.send_modal(MemoModal(task_name, start_time, self, interaction.message))
            except:
                await interaction.response.send_message("エラー: タスク情報を読み取れませんでした。", ephemeral=True)

# ---------------------------------------------------------
# 7. 起動 & コマンド定義
# ---------------------------------------------------------
@client.event
async def on_ready():
    print(f'ログイン成功: {client.user}')
    try:
        await client.tree.sync()
        print("コマンド同期完了")
    except Exception as e:
        print(f"コマンド同期エラー: {e}")
        
    client.add_view(FinishTaskView())
    client.add_view(DashboardView(client, [{"name": "Loading...", "style": "secondary"}]))

@client.tree.command(name="setup_server", description="【推奨】サーバーのチャンネル構成を自動セットアップします")
async def setup_server(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    try:
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("⚠️ このコマンドはサーバー内でのみ使用できます。")
            return

        # 1. カテゴリ作成
        category = discord.utils.get(guild.categories, name=CAT_NAME)
        if not category:
            category = await guild.create_category(CAT_NAME)

        # 2. 各チャンネルの準備 (DataManager経由)
        dm = DataManager(client)
        # ダッシュボード
        dash_ch = await dm.get_channel_by_name(guild, CH_DASHBOARD, category)
        # その他チャンネル
        await dm.get_channel_by_name(guild, CH_TIMELINE, category)
        await dm.get_channel_by_name(guild, CH_GOALS, category)
        await dm.get_channel_by_name(guild, CH_REPORT, category)
        await dm.get_channel_by_name(guild, CH_DATA, category, hidden=True)
        
        # 3. パネル設置
        tasks = await dm.load_tasks(guild)
        
        # 既存メッセージの削除
        try:
            await dash_ch.purge(limit=5)
        except discord.Forbidden:
            await interaction.followup.send("⚠️ メッセージ削除の権限がありませんでした（動作に影響はありません）。", ephemeral=True)
        except Exception:
            pass

        await dash_ch.send("行動宣言パネル", view=DashboardView(client, tasks))
        
        # 4. 目標パネル更新
        await dm.refresh_goals_panel(guild)

        await interaction.followup.send("✅ 完了しました！すべてのチャンネルがセットアップされました。", ephemeral=True)

    except discord.Forbidden as e:
        await interaction.followup.send(f"🚫 **権限エラーが発生しました**\nBotに「チャンネルの管理」や「管理者(Administrator)」の権限がありません。\nエラー詳細: {e}", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"⚠️ **予期せぬエラーが発生しました**\nエラー詳細: {e}", ephemeral=True)

@client.tree.command(name="setup", description="現在のチャンネルにパネルを設置します")
async def setup(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        dm = DataManager(client)
        tasks = await dm.load_tasks(interaction.guild)
        await interaction.followup.send("行動宣言パネル", view=DashboardView(client, tasks))
    except Exception as e:
        await interaction.followup.send(f"エラーが発生しました: {e}")

keep_alive()
client.run(TOKEN)
