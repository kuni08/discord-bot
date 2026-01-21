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
import pandas as pd
import random

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
# 2. 設定・フォント読み込み
# ---------------------------------------------------------
TOKEN = os.getenv('DISCORD_TOKEN')
DATA_CHANNEL_NAME = "mylifelog-data"

# 褒め言葉リスト
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

# 日本語フォントの設定
FONT_PATH = "font.ttf"
try:
    if os.path.exists(FONT_PATH):
        font_prop = fm.FontProperties(fname=FONT_PATH)
        plt.rcParams['font.family'] = font_prop.get_name()
    else:
        print("【警告】font.ttfが見つかりません。日本語が文字化けする可能性があります。")
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
        self.default_tasks = ["🛁 お風呂", "💻 作業・勉強", "🍽️ 食事", "🧹 家事・掃除", "🚶 移動", "💤 睡眠・仮眠", "🎮 趣味・休憩"]

    async def get_channel(self, guild):
        channel = discord.utils.get(guild.text_channels, name=DATA_CHANNEL_NAME)
        if not channel:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True),
            }
            channel = await guild.create_text_channel(DATA_CHANNEL_NAME, overwrites=overwrites)
        return channel

    async def load_tasks(self, guild):
        channel = await self.get_channel(guild)
        pins = await channel.pins()
        for msg in pins:
            if msg.content.startswith("CONFIG_TASKS:"):
                try:
                    return json.loads(msg.content.replace("CONFIG_TASKS:", ""))
                except: pass
        
        initial_data = self.default_tasks
        msg = await channel.send(f"CONFIG_TASKS:{json.dumps(initial_data, ensure_ascii=False)}")
        await msg.pin()
        return initial_data

    async def save_tasks(self, guild, tasks):
        channel = await self.get_channel(guild)
        pins = await channel.pins()
        for msg in pins:
            if msg.content.startswith("CONFIG_TASKS:"):
                await msg.edit(content=f"CONFIG_TASKS:{json.dumps(tasks, ensure_ascii=False)}")
                return
        msg = await channel.send(f"CONFIG_TASKS:{json.dumps(tasks, ensure_ascii=False)}")
        await msg.pin()

    async def save_log(self, guild, log_data):
        channel = await self.get_channel(guild)
        embed = discord.Embed(title=f"✅ {log_data['task']}", color=discord.Color.green())
        embed.add_field(name="時間", value=f"{log_data['duration_str']}")
        if log_data.get('memo'):
            embed.add_field(name="📝 メモ", value=log_data['memo'], inline=False)
        embed.set_footer(text=f"LOG_ID:{json.dumps(log_data, ensure_ascii=False)}")
        embed.timestamp = datetime.datetime.now()
        await channel.send(embed=embed)

    async def fetch_logs(self, guild, limit=500):
        channel = await self.get_channel(guild)
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

    async def get_frequent_tasks(self, guild, limit=20):
        """よく使うタスク順に並べ替えて返す"""
        logs = await self.fetch_logs(guild, limit=300)
        return None 

# ---------------------------------------------------------
# 4. グラフ生成クラス
# ---------------------------------------------------------
class GraphGenerator:
    @staticmethod
    def create_report_images(logs, days=7):
        if not logs: return None
        df = pd.DataFrame(logs)
        if df.empty: return None
        
        df['date_obj'] = pd.to_datetime(df['date'])
        cutoff_date = pd.Timestamp.now() - pd.Timedelta(days=days)
        df = df[df['date_obj'] >= cutoff_date]
        
        if df.empty: return None

        images = {}
        fp = fm.FontProperties(fname=FONT_PATH, size=14) if os.path.exists(FONT_PATH) else None

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

        plt.figure(figsize=(12, 6))
        pivot_df = df.pivot_table(index='date', columns='task', values='duration_min', aggfunc='sum', fill_value=0)
        if not pivot_df.empty:
            pivot_df = pivot_df.sort_index().tail(14)
            ax = pivot_df.plot(kind='bar', stacked=True, colormap='Pastel1', figsize=(12, 6))
            plt.title("日別積み上げグラフ", fontproperties=fp, fontsize=16)
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

        return images

# ---------------------------------------------------------
# 5. UI: タスク管理 & メインダッシュボード
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
        await interaction.channel.send("行動宣言パネル", view=DashboardView(self.bot, self.tasks))

    @discord.ui.button(label="➕ 追加", style=discord.ButtonStyle.primary)
    async def add_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddTaskModal(self))

    @discord.ui.button(label="🗑️ 削除", style=discord.ButtonStyle.danger)
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("削除するタスクを選択してください:", view=DeleteSelectView(self), ephemeral=True)

    @discord.ui.button(label="✏️ リネーム", style=discord.ButtonStyle.secondary)
    async def rename_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("名前を変更するタスクを選択してください:", view=RenameSelectView(self), ephemeral=True)

    @discord.ui.button(label="📋 並び替え/一括編集", style=discord.ButtonStyle.success)
    async def edit_all_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        default_text = "\n".join(self.tasks)
        await interaction.response.send_modal(EditAllModal(self, default_text))

class AddTaskModal(discord.ui.Modal, title="タスクの追加"):
    name = discord.ui.TextInput(label="タスク名", placeholder="例: 🏃 ランニング")
    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        new_task = self.name.value
        if new_task not in self.parent_view.tasks:
            self.parent_view.tasks.append(new_task)
            await self.parent_view.refresh_panel_message(interaction)
        else:
            await interaction.followup.send("そのタスクは既に存在します。", ephemeral=True)

class DeleteSelectView(discord.ui.View):
    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view
        options = [discord.SelectOption(label=t[:100]) for t in parent_view.tasks]
        self.add_item(DeleteSelect(options, parent_view))

class DeleteSelect(discord.ui.Select):
    def __init__(self, options, parent_view):
        super().__init__(placeholder="削除する項目を選択...", options=options)
        self.parent_view = parent_view
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        selected = self.values[0]
        if selected in self.parent_view.tasks:
            self.parent_view.tasks.remove(selected)
            await self.parent_view.refresh_panel_message(interaction)

class RenameSelectView(discord.ui.View):
    def __init__(self, parent_view):
        super().__init__()
        options = [discord.SelectOption(label=t[:100]) for t in parent_view.tasks]
        self.add_item(RenameSelect(options, parent_view))

class RenameSelect(discord.ui.Select):
    def __init__(self, options, parent_view):
        super().__init__(placeholder="変更する項目を選択...", options=options)
        self.parent_view = parent_view
    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        await interaction.response.send_modal(RenameModal(self.parent_view, selected))

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
        if self.old_name in self.parent_view.tasks:
            idx = self.parent_view.tasks.index(self.old_name)
            self.parent_view.tasks[idx] = val
            await self.parent_view.refresh_panel_message(interaction)

class EditAllModal(discord.ui.Modal, title="並び替え・一括編集"):
    text = discord.ui.TextInput(label="1行に1つタスクを記述", style=discord.TextStyle.paragraph)
    def __init__(self, parent_view, default_text):
        super().__init__()
        self.parent_view = parent_view
        self.text.default = default_text
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        new_tasks = [line.strip() for line in self.text.value.split('\n') if line.strip()]
        if new_tasks:
            self.parent_view.tasks = new_tasks
            await self.parent_view.refresh_panel_message(interaction)
        else:
            await interaction.followup.send("タスクが空です。", ephemeral=True)

# --- Dashboard Components ---

class FreeTaskStartModal(discord.ui.Modal, title="自由入力でスタート"):
    task_name = discord.ui.TextInput(label="今からやることは？", placeholder="例: 電球交換、ゴミ捨て")
    async def on_submit(self, interaction: discord.Interaction):
        selected = self.task_name.value
        start = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        embed = discord.Embed(title=f"🚀 スタート: {selected}", color=discord.Color.blue())
        embed.set_footer(text=f"開始時刻: {start}")
        await interaction.response.send_message(embed=embed, view=FinishTaskView())

# タスクボタン（タイル状に配置される個別のボタン）
class TaskButton(discord.ui.Button):
    def __init__(self, task_name, style=discord.ButtonStyle.secondary):
        super().__init__(label=task_name[:80], style=style) # Discordの制限考慮
        self.task_name = task_name

    async def callback(self, interaction: discord.Interaction):
        start = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        embed = discord.Embed(title=f"🚀 スタート: {self.task_name}", color=discord.Color.blue())
        embed.set_footer(text=f"開始時刻: {start}")
        await interaction.response.send_message(embed=embed, view=FinishTaskView())

# あふれたタスク用のセレクトメニュー
class OverflowTaskSelect(discord.ui.Select):
    def __init__(self, tasks):
        options = [discord.SelectOption(label=t[:100]) for t in tasks]
        super().__init__(placeholder="⏬ その他のタスク...", options=options, custom_id="dashboard_overflow_select")
    
    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        start = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        embed = discord.Embed(title=f"🚀 スタート: {selected}", color=discord.Color.blue())
        embed.set_footer(text=f"開始時刻: {start}")
        await interaction.response.send_message(embed=embed, view=FinishTaskView())

class DashboardView(discord.ui.View):
    def __init__(self, bot, tasks):
        super().__init__(timeout=None)
        self.bot = bot
        
        # ボタンのスタイルのパターン（カラフルにするため）
        styles = [
            discord.ButtonStyle.primary,   # 青
            discord.ButtonStyle.secondary, # グレー
            discord.ButtonStyle.success,   # 緑
            # Danger(赤)は「削除」っぽく見えるのであまり使わない方が良いが、アクセントとして入れるならあり
            # discord.ButtonStyle.danger
        ]

        # 配置制限の計算
        # DiscordのActionRowは5つまで。1行に5個ボタンを置ける。
        # 最終行(row=4)は機能ボタン用に空けておく。
        # SelectMenuを使う場合は1行消費する。
        # 最大: 4行 x 5個 = 20個のタスクボタンが限界。
        # もしタスクが多すぎる場合は、1行分をSelectMenuに回す。
        
        max_buttons = 15 # 安全策で3行分(15個)までボタンにする
        main_tasks = tasks[:max_buttons]
        overflow_tasks = tasks[max_buttons:]

        # メインのタスクをボタンとして配置
        for i, task in enumerate(main_tasks):
            # 色をローテーション
            style = styles[i % len(styles)]
            self.add_item(TaskButton(task, style=style))

        # あふれたタスクがある場合はSelectMenuを追加
        if overflow_tasks:
            self.add_item(OverflowTaskSelect(overflow_tasks))

        # 機能ボタン群 (row=4 に固定)
        self.add_item(self.create_func_btn("📝 自由入力", discord.ButtonStyle.secondary, "free_input", self.free_input_btn))
        self.add_item(self.create_func_btn("📊 レポート", discord.ButtonStyle.primary, "report", self.report_btn))
        self.add_item(self.create_func_btn("⚙️ 設定", discord.ButtonStyle.secondary, "manage", self.manage_btn))
        self.add_item(self.create_func_btn("📂 CSV", discord.ButtonStyle.secondary, "csv", self.csv_btn))
        self.add_item(self.create_func_btn("🔄 再設置", discord.ButtonStyle.gray, "refresh", self.refresh_btn))

    def create_func_btn(self, label, style, custom_id_suffix, callback_func):
        btn = discord.ui.Button(label=label, style=style, custom_id=f"dashboard_{custom_id_suffix}", row=4)
        btn.callback = callback_func
        return btn

    # コールバック関数群
    async def free_input_btn(self, interaction: discord.Interaction):
        await interaction.response.send_modal(FreeTaskStartModal())

    async def report_btn(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        dm = DataManager(self.bot)
        logs = await dm.fetch_logs(interaction.guild)
        if not logs:
            await interaction.followup.send("データが見つかりませんでした。", ephemeral=True)
            return
        images = GraphGenerator.create_report_images(logs, days=7)
        if not images:
            await interaction.followup.send("過去7日間のデータがありません。", ephemeral=True)
            return
        files = []
        if 'pie' in images: files.append(discord.File(images['pie'], filename="pie_chart.png"))
        if 'bar' in images: files.append(discord.File(images['bar'], filename="bar_chart.png"))
        embed = discord.Embed(title="📊 行動レポート (過去7日間)", color=discord.Color.purple())
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
                # 過去のデータにRatingがあっても無視して保存
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
        await interaction.channel.send("行動宣言パネル", view=DashboardView(self.bot, tasks))

# ---------------------------------------------------------
# 6. 完了処理View
# ---------------------------------------------------------
class MemoModal(discord.ui.Modal, title='完了メモ'):
    memo = discord.ui.TextInput(label='一言メモ（任意）', style=discord.TextStyle.short, required=False)
    def __init__(self, task_name, start_time, view_item):
        super().__init__()
        self.task_name = task_name
        self.start_time = start_time
        self.view_item = view_item
        
    async def on_submit(self, interaction: discord.Interaction):
        # 先に応答してタイムアウトを防ぐ
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
        await self.view_item.message.edit(view=self.view_item)
        
        # deferしているのでfollowupを使う
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
            # 評価画面を経由せず、直接メモモーダルを表示
            await interaction.response.send_modal(MemoModal(task_name, start_time, self))
        except:
            await interaction.response.send_message("エラー: タスク情報を読み取れませんでした。", ephemeral=True)

# ---------------------------------------------------------
# 7. 起動 & コマンド定義
# ---------------------------------------------------------
@client.event
async def on_ready():
    print(f'ログイン成功: {client.user}')
    await client.tree.sync()
    client.add_view(FinishTaskView())
    client.add_view(DashboardView(client, ["Loading..."]))

@client.tree.command(name="setup", description="ダッシュボード(行動宣言パネル)を設置します")
async def setup(interaction: discord.Interaction):
    await interaction.response.defer()
    dm = DataManager(client)
    tasks = await dm.load_tasks(interaction.guild)
    await interaction.followup.send("行動宣言パネル", view=DashboardView(client, tasks))

keep_alive()
client.run(TOKEN)
