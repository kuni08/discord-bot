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
VC_FOCUS = "🎙️集中ルーム"
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
intents.voice_states = True # ボイス状態の監視に必要
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

    async def get_data_channel(self, guild):
        """データ保存用チャンネルを取得（なければ作成）"""
        # まず名前で探す（新構成）
        channel = discord.utils.get(guild.text_channels, name=CH_DATA)
        if channel: return channel
        
        # なければ旧名で探す
        channel = discord.utils.get(guild.text_channels, name="mylifelog-data")
        if channel: return channel

        # どちらもなければ作成（とりあえずカテゴリなしで）
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True),
        }
        return await guild.create_text_channel(CH_DATA, overwrites=overwrites)

    async def get_timeline_channel(self, guild):
        """タイムラインチャンネルを取得（なければ作成した場所 or setupした場所）"""
        channel = discord.utils.get(guild.text_channels, name=CH_TIMELINE)
        if channel: return channel
        # なければデータチャンネルと同じ場所へ（フォールバック）
        return await self.get_data_channel(guild)

    async def load_tasks(self, guild):
        channel = await self.get_data_channel(guild)
        pins = await channel.pins()
        for msg in pins:
            if msg.content.startswith("CONFIG_TASKS:"):
                try:
                    data = json.loads(msg.content.replace("CONFIG_TASKS:", ""))
                    if data and isinstance(data[0], str): # 旧形式互換
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

    async def save_log(self, guild, log_data):
        # データはDataChannelへ
        data_ch = await self.get_data_channel(guild)
        
        # ユーザーへの表示はTimelineChannelへ
        timeline_ch = await self.get_timeline_channel(guild)

        embed = discord.Embed(title=f"✅ {log_data['task']}", color=discord.Color.green())
        embed.add_field(name="時間", value=f"{log_data['duration_str']}")
        if log_data.get('memo'):
            embed.add_field(name="📝 メモ", value=log_data['memo'], inline=False)
        embed.set_footer(text="Logged via MyLifeLog")
        embed.timestamp = datetime.datetime.now()
        
        # タイムラインに表示
        await timeline_ch.send(embed=embed)

        # データ保存用（隠しデータ付き）
        embed.set_footer(text=f"LOG_ID:{json.dumps(log_data, ensure_ascii=False)}")
        await data_ch.send(embed=embed)

    async def fetch_logs(self, guild, limit=1000):
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

    # VC計測用の一時保存（ステートレスにするためチャンネルのトピックやメッセージを使いたいが、
    # 頻繁な書き込み制限を避けるため、今回はメモリ上のキャッシュを使用する）
    # ※Bot再起動でVC計測中のデータは消えるが、利便性優先
    vc_sessions = {} # {user_id: start_time}

# ---------------------------------------------------------
# 4. グラフ生成クラス
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

# ---------------------------------------------------------
# 5. UIコンポーネント
# ---------------------------------------------------------
class TaskManageView(discord.ui.View):
    def __init__(self, bot, guild, tasks):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild = guild
        self.tasks = tasks
        self.dm = DataManager(bot)

    async def refresh_panel_message(self, interaction):
        await self.dm.save_tasks(self.guild, self.tasks)
        await interaction.followup.send("✅ 設定を保存しました。新しいパネルを下に表示します。", ephemeral=True)
        # ダッシュボードチャンネルを探してそこに再表示推奨
        dashboard_ch = discord.utils.get(self.guild.text_channels, name=CH_DASHBOARD)
        target_ch = dashboard_ch if dashboard_ch else interaction.channel
        await target_ch.send("行動宣言パネル", view=DashboardView(self.bot, self.tasks))

    @discord.ui.button(label="➕ 追加", style=discord.ButtonStyle.primary)
    async def add_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddTaskModal(self))

    @discord.ui.button(label="🗑️ 削除", style=discord.ButtonStyle.danger)
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("削除するタスクを選択してください:", view=DeleteSelectView(self), ephemeral=True)

    @discord.ui.button(label="✏️ リネーム", style=discord.ButtonStyle.secondary)
    async def rename_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("名前を変更するタスクを選択してください:", view=RenameSelectView(self), ephemeral=True)

    @discord.ui.button(label="🎨 色変更", style=discord.ButtonStyle.secondary)
    async def color_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("色を変更するタスクを選択してください:", view=ColorSelectTaskView(self), ephemeral=True)

    @discord.ui.button(label="📋 並び替え/一括編集", style=discord.ButtonStyle.success)
    async def edit_all_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        default_text = "\n".join([t["name"] for t in self.tasks])
        await interaction.response.send_modal(EditAllModal(self, default_text))

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
            await interaction.followup.send("そのタスクは既に存在します。", ephemeral=True)

class DeleteSelectView(discord.ui.View):
    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view
        options = [discord.SelectOption(label=t["name"][:100]) for t in parent_view.tasks]
        self.add_item(DeleteSelect(options, parent_view))

class DeleteSelect(discord.ui.Select):
    def __init__(self, options, parent_view):
        super().__init__(placeholder="削除する項目を選択...", options=options)
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
        super().__init__(placeholder="変更する項目を選択...", options=options)
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
        super().__init__(placeholder="色を変更するタスクを選択...", options=options)
        self.parent_view = parent_view
    async def callback(self, interaction: discord.Interaction):
        selected_name = self.values[0]
        await interaction.response.send_message(
            f"「{selected_name}」の色を選択してください:", 
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
            await interaction.followup.send("タスクが空です。", ephemeral=True)

class FreeTaskStartModal(discord.ui.Modal, title="自由入力でスタート"):
    task_name = discord.ui.TextInput(label="今からやることは？", placeholder="例: 電球交換、ゴミ捨て")
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
        self.add_item(self.create_func_btn("📅 今日の記録", discord.ButtonStyle.primary, "daily", self.daily_btn))
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
            await interaction.followup.send("今日のデータはまだありません。", ephemeral=True)
            return

        file = discord.File(image_buf, filename="daily_timeline.png")
        embed = discord.Embed(title="📅 今日のデイリータイムライン", color=discord.Color.blue())
        embed.set_image(url="attachment://daily_timeline.png")
        await interaction.followup.send(embed=embed, file=file, ephemeral=True)

    async def report_btn(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        dm = DataManager(self.bot)
        logs = await dm.fetch_logs(interaction.guild, limit=1000)
        if not logs:
            await interaction.followup.send("データが見つかりませんでした。", ephemeral=True)
            return
            
        days = 30
        images, stats = GraphGenerator.create_report_images(logs, days=days)
        if not images:
            await interaction.followup.send(f"過去{days}日間のデータがありません。", ephemeral=True)
            return
        
        files = []
        if 'pie' in images: files.append(discord.File(images['pie'], filename="pie_chart.png"))
        if 'bar' in images: files.append(discord.File(images['bar'], filename="bar_chart.png"))
        if 'heatmap' in images: files.append(discord.File(images['heatmap'], filename="heatmap.png"))
        
        embed = discord.Embed(title=f"📊 行動分析レポート (過去{days}日間)", color=discord.Color.purple())
        
        total_h = stats['total_time_min'] // 60
        total_m = stats['total_time_min'] % 60
        avg_h = stats['daily_average_min'] // 60
        avg_m = stats['daily_average_min'] % 60
        
        summary_text = (
            f"⏱️ **総活動時間**: {total_h}時間 {total_m}分\n"
            f"📅 **記録日数**: {stats['days_active']}日\n"
            f"🔄 **完了タスク数**: {stats['total_tasks']}回\n"
            f"⚖️ **1日平均**: {avg_h}時間 {avg_m}分\n"
            f"👑 **最多頻度タスク**: {stats['most_frequent_task']}\n"
            f"⏳ **最多時間タスク**: {stats['most_time_task']}"
        )
        embed.add_field(name="📈 統計サマリー", value=summary_text, inline=False)
        embed.add_field(name="🖼️ 添付グラフ", value="・行動内訳\n・日別推移\n・活動ヒートマップ", inline=False)
        
        if 'pie' in images: embed.set_image(url="attachment://pie_chart.png")
        await interaction.followup.send(embed=embed, files=files, ephemeral=True)

    async def manage_btn(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        dm = DataManager(self.bot)
        tasks = await dm.load_tasks(interaction.guild)
        view = TaskManageView(self.bot, interaction.guild, tasks)
        await interaction.followup.send("📝 **タスク管理パネル**", view=view, ephemeral=True)

    async def csv_btn(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        dm = DataManager(self.bot)
        channel = await dm.get_channel(interaction.guild)
        csv_lines = ["Date,Time,Task,Duration(min),Memo"]
        count = 0
        async for msg in channel.history(limit=1000):
            if not msg.embeds: continue
            embed = msg.embeds[0]
            if not embed.footer.text or "LOG_ID:" not in embed.footer.text: continue
            try:
                json_str = embed.footer.text.replace("LOG_ID:", "")
                data = json.loads(json_str)
                memo = data.get('memo', '').replace('"', '""')
                line = f"{data['date']},{data.get('timestamp', '')},{data['task']},{data['duration_min']},\"{memo}\""
                csv_lines.append(line)
                count += 1
            except: continue
        if count == 0:
            await interaction.followup.send("データがありません。", ephemeral=True)
            return
        csv_data = "\n".join(csv_lines)
        file = discord.File(fp=io.StringIO(csv_data), filename=f"mylifelog_{datetime.date.today()}.csv")
        await interaction.followup.send(f"📂 {count}件のデータをエクスポートしました。", file=file, ephemeral=True)

    async def refresh_btn(self, interaction: discord.Interaction):
        await interaction.response.defer()
        dm = DataManager(self.bot)
        tasks = await dm.load_tasks(interaction.guild)
        try:
            await interaction.message.delete()
        except: pass
        # 設置場所はダッシュボードチャンネル優先
        dashboard_ch = discord.utils.get(self.bot.guilds[0].text_channels, name=CH_DASHBOARD)
        target_ch = dashboard_ch if dashboard_ch else interaction.channel
        await target_ch.send("行動宣言パネル", view=DashboardView(self.bot, tasks))

# ---------------------------------------------------------
# 6. 完了処理View
# ---------------------------------------------------------
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
            await interaction.response.send_message("エラー: タスク情報を読み取れませんでした。", ephemeral=True)

# ---------------------------------------------------------
# 7. ボイスチャンネル・イベントハンドラ
# ---------------------------------------------------------
@client.event
async def on_voice_state_update(member, before, after):
    if member.bot: return
    dm = DataManager(client)
    
    # 集中ルームに入室したとき
    if after.channel and after.channel.name == VC_FOCUS:
        start_time = datetime.datetime.now()
        dm.vc_sessions[member.id] = start_time
        
        # タイムラインに通知
        timeline_ch = await dm.get_timeline_channel(member.guild)
        start_str = start_time.strftime("%H:%M")
        embed = discord.Embed(description=f"🎙️ **{member.display_name}** さんが集中ルームに入室しました。\n計測を開始します... ({start_str})", color=discord.Color.blue())
        await timeline_ch.send(embed=embed)

    # 集中ルームから退室（または移動）したとき
    if before.channel and before.channel.name == VC_FOCUS:
        start_time = dm.vc_sessions.pop(member.id, None)
        if start_time:
            end_time = datetime.datetime.now()
            duration = end_time - start_time
            minutes = int(duration.total_seconds() // 60)
            seconds = int(duration.total_seconds() % 60)
            
            # ログ保存
            log_data = {
                "task": "💻 作業・勉強 (VC)",
                "duration_min": minutes,
                "duration_str": f"{minutes}分 {seconds}秒",
                "memo": "集中ルーム自動計測",
                "date": end_time.strftime("%Y-%m-%d"),
                "timestamp": end_time.isoformat()
            }
            await dm.save_log(member.guild, log_data)

# ---------------------------------------------------------
# 8. 起動 & コマンド定義
# ---------------------------------------------------------
@client.event
async def on_ready():
    print(f'ログイン成功: {client.user}')
    await client.tree.sync()
    client.add_view(FinishTaskView())
    client.add_view(DashboardView(client, [{"name": "Loading...", "style": "secondary"}]))

@client.tree.command(name="setup_server", description="【推奨】サーバーのチャンネル構成を自動セットアップします")
async def setup_server(interaction: discord.Interaction):
    await interaction.response.defer()
    guild = interaction.guild
    
    # カテゴリ作成
    category = discord.utils.get(guild.categories, name=CAT_NAME)
    if not category:
        category = await guild.create_category(CAT_NAME)

    # 1. ダッシュボード（書き込み不可、操作専用）
    dash_ch = discord.utils.get(guild.text_channels, name=CH_DASHBOARD)
    if not dash_ch:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(send_messages=False),
            guild.me: discord.PermissionOverwrite(send_messages=True)
        }
        dash_ch = await guild.create_text_channel(CH_DASHBOARD, category=category, overwrites=overwrites)
    
    # 2. タイムライン（ログ表示用）
    time_ch = discord.utils.get(guild.text_channels, name=CH_TIMELINE)
    if not time_ch:
        time_ch = await guild.create_text_channel(CH_TIMELINE, category=category)

    # 3. データ保存用（非表示）
    data_ch = discord.utils.get(guild.text_channels, name=CH_DATA)
    if not data_ch:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        data_ch = await guild.create_text_channel(CH_DATA, category=category, overwrites=overwrites)
    
    # 4. 集中ルーム（ボイス）
    vc_ch = discord.utils.get(guild.voice_channels, name=VC_FOCUS)
    if not vc_ch:
        await guild.create_voice_channel(VC_FOCUS, category=category)

    # パネル設置
    dm = DataManager(client)
    tasks = await dm.load_tasks(guild)
    
    # 古いパネルがあれば消したいが、特定できないので新規投稿
    await dash_ch.purge(limit=5) # 掃除
    await dash_ch.send("行動宣言パネル", view=DashboardView(client, tasks))

    await interaction.followup.send("✅ サーバー構成を最適化しました！\n`🎮ダッシュボード` チャンネルから操作を開始してください。", ephemeral=True)

# 旧コマンドも互換性のため残すが、基本はsetup_server推奨
@client.tree.command(name="setup", description="現在のチャンネルにパネルを設置します")
async def setup(interaction: discord.Interaction):
    await interaction.response.defer()
    dm = DataManager(client)
    tasks = await dm.load_tasks(interaction.guild)
    await interaction.followup.send("行動宣言パネル", view=DashboardView(client, tasks))

keep_alive()
client.run(TOKEN)
