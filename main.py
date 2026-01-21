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
CH_GOALS = "🎯目標管理" # 新規追加
CAT_NAME = "MY LIFE LOG"

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
# 3. データ管理クラス
# ---------------------------------------------------------
class DataManager:
    def __init__(self, bot):
        self.bot = bot
        self.default_tasks = [
            {"name": "🛁 お風呂", "style": "primary"},
            {"name": "💻 作業・勉強", "style": "primary"},
            {"name": "🍽️ 食事", "style": "success"},
            {"name": "🧹 家事・掃除", "style": "secondary"},
            {"name": "🚶 移動", "style": "secondary"},
            {"name": "💤 睡眠・仮眠", "style": "secondary"},
            {"name": "🎮 趣味・休憩", "style": "success"}
        ]

    async def get_channel_by_name(self, guild, name, category=None, hidden=False):
        channel = discord.utils.get(guild.text_channels, name=name)
        if channel: return channel
        
        # なければ作成
        overwrites = {}
        if hidden:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True),
            }
        elif name == CH_DASHBOARD or name == CH_GOALS: # 書き込み不可チャンネル
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

    # --- タスク設定 ---
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

    # --- 目標設定 (複数目標対応) ---
    async def load_goals(self, guild):
        channel = await self.get_data_channel(guild)
        pins = await channel.pins()
        for msg in pins:
            if msg.content.startswith("CONFIG_GOALS:"):
                try:
                    data = json.loads(msg.content.replace("CONFIG_GOALS:", ""))
                    # マイグレーション: 古い形式 {task: {target: 60}} -> {task: [{target: 60}]}
                    new_data = {}
                    for k, v in data.items():
                        if isinstance(v, dict): # 古い形式
                            new_data[k] = [v]
                        else: # 新しい形式 (list)
                            new_data[k] = v
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

    # --- ログ ---
    async def save_log(self, guild, log_data):
        data_ch = await self.get_data_channel(guild)
        timeline_ch = await self.get_timeline_channel(guild)

        embed = discord.Embed(title=f"✅ {log_data['task']}", color=discord.Color.green())
        embed.add_field(name="時間", value=f"{log_data['duration_str']}")
        if log_data.get('memo'):
            embed.add_field(name="📝 メモ", value=log_data['memo'], inline=False)
        embed.set_footer(text="Logged via MyLifeLog")
        embed.timestamp = datetime.datetime.now()
        
        await timeline_ch.send(embed=embed)

        embed.set_footer(text=f"LOG_ID:{json.dumps(log_data, ensure_ascii=False)}")
        await data_ch.send(embed=embed)

        # ログ保存後に目標パネルを更新（進捗が変わるため）
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

    # --- 目標パネルの更新 ---
    async def refresh_goals_panel(self, guild):
        """目標管理チャンネルのパネルを再描画"""
        goals_ch = await self.get_goals_channel(guild)
        if not goals_ch: return

        # データを取得してEmbed作成
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
        
        # 過去のパネルを消して新しいのを送る
        await goals_ch.purge(limit=5)
        # タスクリストを渡す必要があるのでロード
        tasks = await self.load_tasks(guild)
        await goals_ch.send(embed=embed, view=GoalManagePanel(self.bot, tasks))

# ---------------------------------------------------------
# 4. グラフ & 進捗計算クラス
# ---------------------------------------------------------
class GraphGenerator:
    @staticmethod
    def create_report_images(logs, days=30):
        if not logs: return None, None
        df = pd.DataFrame(logs)
        if df.empty: return None, None
        
        df['date_obj'] = pd.to_datetime(df['date'])
        if 'timestamp' in df.columns:
             df['timestamp_obj'] = pd.to_datetime(df['timestamp'])
        else:
             df['timestamp_obj'] = df['date_obj']

        cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=days)
        df = df[df['date_obj'] >= cutoff_date]
        
        if df.empty: return None, None

        images = {}
        fp = fm.FontProperties(fname=FONT_PATH, size=14) if os.path.exists(FONT_PATH) else None

        # 円グラフ
        plt.figure(figsize=(10, 6))
        task_sum = df.groupby('task')['duration_min'].sum()
        if not task_sum.empty:
            colors = plt.cm.Pastel1.colors
            wedges, texts, autotexts = plt.pie(
                task_sum, labels=None, autopct='%1.1f%%', startangle=90, colors=colors, pctdistance=0.85
            )
            centre_circle = plt.Circle((0,0),0.70,fc='white')
            fig = plt.gcf()
            fig.gca().add_artist(centre_circle)
            plt.legend(wedges, task_sum.index, title="Tasks", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1), prop=fp)
            plt.title(f"行動内訳 (過去{days}日間)", fontproperties=fp, fontsize=16)
            plt.tight_layout()
            buf_pie = io.BytesIO()
            plt.savefig(buf_pie, format='png')
            buf_pie.seek(0)
            images['pie'] = buf_pie
            plt.close()

        # 積み上げ棒グラフ
        plt.figure(figsize=(12, 6))
        pivot_df = df.pivot_table(index='date', columns='task', values='duration_min', aggfunc='sum', fill_value=0)
        if not pivot_df.empty:
            display_pivot = pivot_df.sort_index().tail(14)
            ax = display_pivot.plot(kind='bar', stacked=True, colormap='Pastel1', figsize=(12, 6))
            plt.title("日別積み上げグラフ (直近14日)", fontproperties=fp, fontsize=16)
            plt.xlabel("日付", fontproperties=fp)
            plt.ylabel("時間 (分)", fontproperties=fp)
            plt.legend(prop=fp, bbox_to_anchor=(1.05, 1), loc='upper left')
            plt.xticks(rotation=45, fontproperties=fp)
            plt.tight_layout()
            buf_bar = io.BytesIO()
            plt.savefig(buf_bar, format='png')
            buf_bar.seek(0)
            images['bar'] = buf_bar
            plt.close()

        # ヒートマップ
        plt.figure(figsize=(10, 5))
        df['weekday'] = df['timestamp_obj'].dt.weekday
        df['hour'] = df['timestamp_obj'].dt.hour
        heatmap_data = df.pivot_table(index='weekday', columns='hour', values='duration_min', aggfunc='count', fill_value=0)
        heatmap_data = heatmap_data.reindex(index=range(7), columns=range(24), fill_value=0)
        
        plt.imshow(heatmap_data, cmap='Blues', aspect='auto')
        days_label = ['月', '火', '水', '木', '金', '土', '日']
        plt.yticks(range(7), days_label, fontproperties=fp)
        plt.xticks(range(24), [str(h) for h in range(24)], fontproperties=fp)
        plt.xlabel("時間帯 (時)", fontproperties=fp)
        plt.ylabel("曜日", fontproperties=fp)
        plt.title("活動リズム ヒートマップ (濃い=頻度高)", fontproperties=fp, fontsize=16)
        plt.colorbar(label="回数", pad=0.02)
        plt.tight_layout()
        buf_heat = io.BytesIO()
        plt.savefig(buf_heat, format='png')
        buf_heat.seek(0)
        images['heatmap'] = buf_heat
        plt.close()

        stats = {
            "total_time_min": int(df['duration_min'].sum()),
            "total_tasks": int(len(df)),
            "days_active": int(df['date'].nunique()),
            "most_frequent_task": df['task'].mode()[0] if not df['task'].mode().empty else "なし",
            "most_time_task": task_sum.idxmax() if not task_sum.empty else "なし",
            "daily_average_min": int(df['duration_min'].sum() / days) if days > 0 else 0
        }

        return images, stats

    @staticmethod
    def create_daily_timeline(logs, target_date=None):
        if not logs: return None
        df = pd.DataFrame(logs)
        if df.empty: return None

        if 'timestamp' in df.columns:
             df['end_time'] = pd.to_datetime(df['timestamp'])
        else:
             df['end_time'] = pd.to_datetime(df['date'])

        if target_date is None:
            target_date = datetime.date.today()
        
        df['date_only'] = df['end_time'].dt.date
        df = df[df['date_only'] == target_date].copy()
        
        if df.empty: return None

        df['start_time'] = df['end_time'] - pd.to_timedelta(df['duration_min'], unit='m')

        fp = fm.FontProperties(fname=FONT_PATH, size=12) if os.path.exists(FONT_PATH) else None
        fp_bold = fm.FontProperties(fname=FONT_PATH, size=14, weight='bold') if os.path.exists(FONT_PATH) else None
        
        fig, ax = plt.subplots(figsize=(8, 12))
        ax.set_xlim(0, 100)
        ax.set_ylim(24, 0)
        ax.set_facecolor('#f8f9fa')
        ax.grid(axis='y', linestyle='--', alpha=0.5, color='#dee2e6')
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
            
            rect = patches.Rectangle((15, start_h), 10, duration_h, linewidth=1, edgecolor='white', facecolor=task_colors[row['task']])
            ax.add_patch(rect)
            
            time_str = f"{row['start_time'].strftime('%H:%M')} - {row['end_time'].strftime('%H:%M')}"
            memo_str = f" ({row['memo']})" if row.get('memo') else ""
            label_str = f"{time_str}\n{row['task']}{memo_str}"
            ax.text(28, start_h + (duration_h/2), label_str, va='center', ha='left', fontsize=11, fontproperties=fp, color='#495057')

        ax.set_xticks([])
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_visible(False)
        ax.spines['left'].set_color('#ced4da')
        
        plt.title(f"DAILY TIMELINE - {target_date.strftime('%Y/%m/%d')}", fontproperties=fp_bold, pad=20)
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100)
        buf.seek(0)
        plt.close()
        return buf

    # --- 進捗計算ロジック (複数目標対応版) ---
    @staticmethod
    def calculate_progress(logs, goals):
        if not logs or not goals: return []
        df = pd.DataFrame(logs)
        if df.empty: return []
        
        if 'timestamp' in df.columns:
            df['ts_obj'] = pd.to_datetime(df['timestamp'])
        else:
            df['ts_obj'] = pd.to_datetime(df['date'])

        now = pd.Timestamp.now()
        today = now.normalize()
        start_of_week = today - pd.Timedelta(days=today.dayofweek)
        start_of_month = today.replace(day=1)
        
        progress_data = []
        
        for task_name, goal_list in goals.items():
            # 形式統一: 単一辞書ならリストに入れる
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
                    start_date = pd.to_datetime(created_at_str)
                    end_date = start_date + pd.Timedelta(days=custom_days)
                    current = df[(df['task'] == task_name) & (df['ts_obj'] >= start_date) & (df['ts_obj'] <= end_date)]['duration_min'].sum()
                    days_left = (end_date - now).days
                    label_period = f"{custom_days}日間 (残り{days_left}日)"
                
                progress_data.append({
                    "task": task_name,
                    "current": int(current),
                    "target": target,
                    "period_label": label_period,
                    "percent": min(100, int((current / target) * 100))
                })
            
        return progress_data

# ---------------------------------------------------------
# 5. UIコンポーネント: 目標管理パネル
# ---------------------------------------------------------
class GoalManagePanel(discord.ui.View):
    def __init__(self, bot, tasks):
        super().__init__(timeout=None)
        self.bot = bot
        self.tasks = tasks

    @discord.ui.button(label="➕ 目標を追加", style=discord.ButtonStyle.success, custom_id="goal_panel_add")
    async def add_goal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("目標を追加するタスクを選択:", view=GoalAddSelectView(self.bot, self.tasks), ephemeral=True)

    @discord.ui.button(label="🗑️ 目標を削除", style=discord.ButtonStyle.danger, custom_id="goal_panel_delete")
    async def delete_goal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("削除する目標のタスクを選択:", view=GoalDeleteTaskSelectView(self.bot, self.tasks), ephemeral=True)

    @discord.ui.button(label="🔄 更新", style=discord.ButtonStyle.secondary, custom_id="goal_panel_refresh")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        dm = DataManager(self.bot)
        await dm.refresh_goals_panel(interaction.guild)

# --- 目標追加フロー ---
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

class GoalInputModal(discord.ui.Modal, title="目標を追加"):
    target_time = discord.ui.TextInput(label="目標時間 (分)", placeholder="例: 60")
    period_select = discord.ui.TextInput(label="期間 (d=日, w=週, m=月, c=カスタム)", placeholder="d", min_length=1, max_length=1)
    custom_days = discord.ui.TextInput(label="カスタム日数 (cを選んだ場合のみ)", placeholder="例: 20 (今後20日間で)", required=False)

    def __init__(self, bot, task_name):
        super().__init__()
        self.bot = bot
        self.task_name = task_name

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            target = int(self.target_time.value)
            p_val = self.period_select.value.lower()
            period_map = {'d': 'daily', 'w': 'weekly', 'm': 'monthly', 'c': 'custom'}
            period = period_map.get(p_val)
            
            if not period:
                await interaction.followup.send("⚠️ 期間エラー", ephemeral=True)
                return

            dm = DataManager(self.bot)
            goals = await dm.load_goals(interaction.guild)
            
            # データ構築
            goal_data = {
                "target": target,
                "period": period,
                "created_at": datetime.datetime.now().isoformat()
            }
            if period == 'custom':
                goal_data["custom_days"] = int(self.custom_days.value)

            # リストに追加 (存在しなければ作成)
            if self.task_name not in goals:
                goals[self.task_name] = []
            elif isinstance(goals[self.task_name], dict): # 旧データ保護
                goals[self.task_name] = [goals[self.task_name]]
            
            goals[self.task_name].append(goal_data)
            
            await dm.save_goals(interaction.guild, goals)
            await dm.refresh_goals_panel(interaction.guild) # パネル更新
            
            await interaction.followup.send(f"✅ **{self.task_name}** に目標を追加しました。", ephemeral=True)
            
        except ValueError:
            await interaction.followup.send("⚠️ 数値入力エラー", ephemeral=True)

# --- 目標削除フロー ---
class GoalDeleteTaskSelectView(discord.ui.View):
    def __init__(self, bot, tasks):
        super().__init__()
        options = [discord.SelectOption(label=t["name"][:100]) for t in tasks]
        self.add_item(GoalDeleteTaskSelect(bot, options))

class GoalDeleteTaskSelect(discord.ui.Select):
    def __init__(self, bot, options):
        super().__init__(placeholder="どのタスクの目標を消しますか？", options=options)
        self.bot = bot
    async def callback(self, interaction: discord.Interaction):
        task_name = self.values[0]
        dm = DataManager(self.bot)
        goals = await dm.load_goals(interaction.guild)
        
        task_goals = goals.get(task_name, [])
        if isinstance(task_goals, dict): task_goals = [task_goals]
        
        if not task_goals:
            await interaction.response.send_message("このタスクには目標がありません。", ephemeral=True)
            return
            
        await interaction.response.send_message(
            "削除する目標を選択してください:", 
            view=GoalDeleteSpecificSelectView(self.bot, task_name, task_goals),
            ephemeral=True
        )

class GoalDeleteSpecificSelectView(discord.ui.View):
    def __init__(self, bot, task_name, goal_list):
        super().__init__()
        self.bot = bot
        self.task_name = task_name
        self.goal_list = goal_list
        
        options = []
        for i, g in enumerate(goal_list):
            label = f"{g['target']}分 ({g['period']})"
            options.append(discord.SelectOption(label=label, value=str(i)))
            
        self.add_item(GoalDeleteSpecificSelect(options))

class GoalDeleteSpecificSelect(discord.ui.Select):
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        index = int(self.values[0])
        view = self.view # parent view
        
        dm = DataManager(view.bot)
        goals = await dm.load_goals(interaction.guild)
        
        # 削除処理
        task_goals = goals.get(view.task_name, [])
        if isinstance(task_goals, dict): task_goals = [task_goals]
        
        if 0 <= index < len(task_goals):
            task_goals.pop(index)
            goals[view.task_name] = task_goals
            await dm.save_goals(interaction.guild, goals)
            await dm.refresh_goals_panel(interaction.guild)
            await interaction.followup.send("🗑️ 目標を削除しました。", ephemeral=True)
        else:
            await interaction.followup.send("エラー: 目標が見つかりません。", ephemeral=True)

# ---------------------------------------------------------
# 6. メインダッシュボード & タスク管理 (簡略化)
# ---------------------------------------------------------
# (ダッシュボードから目標系ボタンを削除し、専用チャンネルへ誘導)
class DashboardView(discord.ui.View):
    def __init__(self, bot, tasks):
        super().__init__(timeout=None)
        self.bot = bot
        
        buttons_per_row = 3
        max_task_rows = 3
        max_buttons = buttons_per_row * max_task_rows

        main_tasks = tasks[:max_buttons]
        overflow_tasks = tasks[max_buttons:]

        for i, task in enumerate(main_tasks):
            row = i // buttons_per_row
            self.add_item(TaskButton(task["name"], task.get("style", "secondary"), row=row))

        if overflow_tasks:
            self.add_item(OverflowTaskSelect(overflow_tasks, row=3))

        self.add_item(self.create_func_btn("📝 自由入力", discord.ButtonStyle.secondary, "free_input", self.free_input_btn))
        self.add_item(self.create_func_btn("📅 今日の記録", discord.ButtonStyle.secondary, "daily", self.daily_btn))
        self.add_item(self.create_func_btn("📊 レポート", discord.ButtonStyle.secondary, "report", self.report_btn))
        self.add_item(self.create_func_btn("⚙️ 設定", discord.ButtonStyle.secondary, "manage", self.manage_btn))
        self.add_item(self.create_func_btn("🔄 再設置", discord.ButtonStyle.gray, "refresh", self.refresh_btn))

    def create_func_btn(self, label, style, custom_id_suffix, callback_func):
        btn = discord.ui.Button(label=label, style=style, custom_id=f"dashboard_{custom_id_suffix}", row=4)
        btn.callback = callback_func
        return btn

    async def free_input_btn(self, interaction: discord.Interaction):
        await interaction.response.send_modal(FreeTaskStartModal())

    async def daily_btn(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        dm = DataManager(self.bot)
        logs = await dm.fetch_logs(interaction.guild, limit=200)
        image_buf = GraphGenerator.create_daily_timeline(logs)
        if image_buf is None:
            await interaction.followup.send("データなし", ephemeral=True)
            return
        file = discord.File(image_buf, filename="daily.png")
        embed = discord.Embed(title="📅 デイリータイムライン", color=discord.Color.blue())
        embed.set_image(url="attachment://daily.png")
        await interaction.followup.send(embed=embed, file=file, ephemeral=True)

    async def report_btn(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        dm = DataManager(self.bot)
        logs = await dm.fetch_logs(interaction.guild, limit=1000)
        if not logs:
            await interaction.followup.send("データなし", ephemeral=True)
            return
        images, stats = GraphGenerator.create_report_images(logs)
        files = []
        if 'pie' in images: files.append(discord.File(images['pie'], filename="pie.png"))
        if 'bar' in images: files.append(discord.File(images['bar'], filename="bar.png"))
        embed = discord.Embed(title="📊 レポート", color=discord.Color.purple())
        if 'pie' in images: embed.set_image(url="attachment://pie.png")
        await interaction.followup.send(embed=embed, files=files, ephemeral=True)

    async def manage_btn(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        dm = DataManager(self.bot)
        tasks = await dm.load_tasks(interaction.guild)
        view = TaskManageView(self.bot, interaction.guild, tasks)
        await interaction.followup.send("📝 **タスク管理**", view=view, ephemeral=True)

    async def refresh_btn(self, interaction: discord.Interaction):
        await interaction.response.defer()
        dm = DataManager(self.bot)
        tasks = await dm.load_tasks(interaction.guild)
        try: await interaction.message.delete()
        except: pass
        dashboard_ch = discord.utils.get(interaction.guild.text_channels, name=CH_DASHBOARD)
        target_ch = dashboard_ch if dashboard_ch else interaction.channel
        await target_ch.send("行動宣言パネル", view=DashboardView(self.bot, tasks))

# --- TaskManageView (目標ボタン削除) ---
class TaskManageView(discord.ui.View):
    def __init__(self, bot, guild, tasks):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild = guild
        self.tasks = tasks
        self.dm = DataManager(bot)

    async def refresh_panel_message(self, interaction):
        await self.dm.save_tasks(self.guild, self.tasks)
        await interaction.followup.send("✅ 保存しました。", ephemeral=True)
        dashboard_ch = discord.utils.get(self.guild.text_channels, name=CH_DASHBOARD)
        if dashboard_ch:
            await dashboard_ch.send("行動宣言パネル", view=DashboardView(self.bot, self.tasks))

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

# ---------------------------------------------------------
# その他モーダル・View (省略なし)
# ---------------------------------------------------------
class AddTaskModal(discord.ui.Modal, title="タスクの追加"):
    name = discord.ui.TextInput(label="タスク名", placeholder="例: 🏃 ランニング")
    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
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
        await interaction.response.defer(ephemeral=True)
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
        await interaction.response.defer(ephemeral=True)
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
        await interaction.response.defer(ephemeral=True)
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
        await interaction.response.defer(ephemeral=True)
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
        now = datetime.datetime.now()
        start_str = now.strftime("%Y-%m-%d %H:%M:%S")
        timestamp = int(now.timestamp())
        embed = discord.Embed(title=f"🚀 スタート: {selected}", description=f"経過: <t:{timestamp}:R>", color=discord.Color.blue())
        embed.set_footer(text=f"開始時刻: {start_str}")
        await interaction.response.send_message(embed=embed, view=FinishTaskView())

class TaskButton(discord.ui.Button):
    def __init__(self, task_name, style_name="secondary", row=0):
        style = BUTTON_STYLES.get(style_name, discord.ButtonStyle.secondary)
        super().__init__(label=task_name[:80], style=style, row=row)
        self.task_name = task_name
    async def callback(self, interaction: discord.Interaction):
        now = datetime.datetime.now()
        start_str = now.strftime("%Y-%m-%d %H:%M:%S")
        timestamp = int(now.timestamp())
        embed = discord.Embed(title=f"🚀 スタート: {self.task_name}", description=f"経過: <t:{timestamp}:R>", color=discord.Color.blue())
        embed.set_footer(text=f"開始時刻: {start_str}")
        await interaction.response.send_message(embed=embed, view=FinishTaskView())

class OverflowTaskSelect(discord.ui.Select):
    def __init__(self, tasks, row=3):
        options = [discord.SelectOption(label=t["name"][:100]) for t in tasks]
        super().__init__(placeholder="⏬ その他のタスク...", options=options, custom_id="dashboard_overflow_select", row=row)
    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        now = datetime.datetime.now()
        start_str = now.strftime("%Y-%m-%d %H:%M:%S")
        timestamp = int(now.timestamp())
        embed = discord.Embed(title=f"🚀 スタート: {selected}", description=f"経過: <t:{timestamp}:R>", color=discord.Color.blue())
        embed.set_footer(text=f"開始時刻: {start_str}")
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
        end_time = datetime.datetime.now()
        duration = end_time - self.start_time
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

class FinishTaskView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="完了 (Done)", style=discord.ButtonStyle.green, custom_id="finish_btn_v4")
    async def finish(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = interaction.message.embeds[0]
        try:
            time_str = embed.footer.text.replace("開始時刻: ", "")
            start_time = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            task_name = embed.title.replace("🚀 スタート: ", "")
            await interaction.response.send_modal(MemoModal(task_name, start_time, self, interaction.message))
        except:
            await interaction.response.send_message("エラー", ephemeral=True)

# ---------------------------------------------------------
# 7. 起動 & コマンド定義
# ---------------------------------------------------------
@client.event
async def on_ready():
    print(f'ログイン成功: {client.user}')
    await client.tree.sync()
    client.add_view(FinishTaskView())
    client.add_view(DashboardView(client, [{"name": "Loading...", "style": "secondary"}]))
    # 目標パネルは起動時にタスクリストが必要だが、ここではダミー登録せずコマンド経由で作成される

@client.tree.command(name="setup_server", description="サーバー構成を自動セットアップします")
async def setup_server(interaction: discord.Interaction):
    await interaction.response.defer()
    guild = interaction.guild
    dm = DataManager(client)
    
    # カテゴリ
    category = discord.utils.get(guild.categories, name=CAT_NAME)
    if not category:
        category = await guild.create_category(CAT_NAME)

    # チャンネル作成
    await dm.get_channel_by_name(guild, CH_DASHBOARD, category)
    await dm.get_channel_by_name(guild, CH_TIMELINE, category)
    await dm.get_channel_by_name(guild, CH_GOALS, category)
    await dm.get_channel_by_name(guild, CH_DATA, category, hidden=True)
    
    # パネル設置
    tasks = await dm.load_tasks(guild)
    
    # ダッシュボード
    dash_ch = await dm.get_channel_by_name(guild, CH_DASHBOARD)
    await dash_ch.purge(limit=5)
    await dash_ch.send("行動宣言パネル", view=DashboardView(client, tasks))

    # 目標管理パネル
    await dm.refresh_goals_panel(guild)

    await interaction.followup.send("✅ サーバー構成を最適化しました！", ephemeral=True)

@client.tree.command(name="setup", description="パネルを設置します")
async def setup(interaction: discord.Interaction):
    await interaction.response.defer()
    dm = DataManager(client)
    tasks = await dm.load_tasks(interaction.guild)
    await interaction.followup.send("行動宣言パネル", view=DashboardView(client, tasks))

keep_alive()
client.run(TOKEN)
