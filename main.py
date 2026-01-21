import discord
from discord import app_commands
from discord.ext import commands
import os
import datetime
import json
import asyncio
from flask import Flask
from threading import Thread
from collections import defaultdict
import io

# ---------------------------------------------------------
# 1. サーバー維持機能 (Render等のクラウド対応)
# ---------------------------------------------------------
app = Flask('')

@app.route('/')
def home():
    return "I am alive!"

def run():
    # Render等の環境変数PORTに対応、なければ8080
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ---------------------------------------------------------
# 2. Bot設定
# ---------------------------------------------------------
# 環境変数または直接指定でトークンを設定
TOKEN = os.getenv('DISCORD_TOKEN', 'YOUR_BOT_TOKEN_HERE')

# データを保存するチャンネル名（Botが自動生成・管理します）
DATA_CHANNEL_NAME = "mylifelog-data"

intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix='!', intents=intents)

# ---------------------------------------------------------
# 3. データ管理システム (Discord DB)
# ---------------------------------------------------------
class DataManager:
    def __init__(self, bot):
        self.bot = bot
        self.default_tasks = ["🛁 お風呂", "💻 作業・勉強", "🍽️ 食事", "🧹 家事・掃除", "🚶 移動", "💤 睡眠・仮眠", "🎮 趣味・休憩"]

    async def get_channel(self, guild):
        """データ保存用チャンネルを取得or作成"""
        channel = discord.utils.get(guild.text_channels, name=DATA_CHANNEL_NAME)
        if not channel:
            # 自分専用のプライベートチャンネルとして作成
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True),
            }
            channel = await guild.create_text_channel(DATA_CHANNEL_NAME, overwrites=overwrites)
        return channel

    async def load_tasks(self, guild):
        """ピン留めされたメッセージからタスクリスト設定を読み込む"""
        channel = await self.get_channel(guild)
        pins = await channel.pins()
        
        for msg in pins:
            if msg.content.startswith("CONFIG_TASKS:"):
                try:
                    data_str = msg.content.replace("CONFIG_TASKS:", "")
                    return json.loads(data_str)
                except:
                    pass
        
        # データがない場合は初期化して保存
        initial_data = self.default_tasks
        msg = await channel.send(f"CONFIG_TASKS:{json.dumps(initial_data, ensure_ascii=False)}")
        await msg.pin()
        return initial_data

    async def save_tasks(self, guild, tasks):
        """タスクリスト設定をピン留めメッセージに保存"""
        channel = await self.get_channel(guild)
        pins = await channel.pins()
        
        # 既存の設定メッセージを探して更新
        for msg in pins:
            if msg.content.startswith("CONFIG_TASKS:"):
                await msg.edit(content=f"CONFIG_TASKS:{json.dumps(tasks, ensure_ascii=False)}")
                return

        # なければ新規作成
        msg = await channel.send(f"CONFIG_TASKS:{json.dumps(tasks, ensure_ascii=False)}")
        await msg.pin()

    async def save_log(self, guild, log_data):
        """完了ログをチャンネルに投稿（これがDBのレコードになる）"""
        channel = await self.get_channel(guild)
        
        # 人間が見る用の表示
        embed = discord.Embed(title=f"✅ {log_data['task']}", color=discord.Color.green())
        embed.add_field(name="時間", value=f"{log_data['duration_str']}")
        if log_data.get('memo'):
            embed.add_field(name="📝 メモ", value=log_data['memo'], inline=False)
        
        # 機械が読む用のデータをフッターに隠し込む
        # LOG_IDプレフィックスをつけてJSONを埋め込む
        embed.set_footer(text=f"LOG_ID:{json.dumps(log_data, ensure_ascii=False)}")
        embed.timestamp = datetime.datetime.now()
        
        await channel.send(embed=embed)

# ---------------------------------------------------------
# 4. UIコンポーネント (メモ入力・完了処理)
# ---------------------------------------------------------
class MemoModal(discord.ui.Modal, title='完了メモ'):
    memo = discord.ui.TextInput(
        label='一言メモ（任意）', 
        style=discord.TextStyle.short, 
        required=False, 
        placeholder="例: 集中できた、新しい入浴剤使った"
    )

    def __init__(self, task_name, start_time, view_item):
        super().__init__()
        self.task_name = task_name
        self.start_time = start_time
        self.view_item = view_item # 完了ボタンのView

    async def on_submit(self, interaction: discord.Interaction):
        end_time = datetime.datetime.now()
        duration = end_time - self.start_time
        minutes = int(duration.total_seconds() // 60)
        seconds = int(duration.total_seconds() % 60)
        duration_str = f"{minutes}分 {seconds}秒"

        # ログデータ作成
        log_data = {
            "task": self.task_name,
            "duration_min": minutes, # 統計用に分だけ保存
            "duration_str": duration_str,
            "memo": self.memo.value,
            "date": end_time.strftime("%Y-%m-%d"),
            "timestamp": end_time.isoformat()
        }

        # DBチャンネルに保存
        dm = DataManager(client)
        await dm.save_log(interaction.guild, log_data)

        # ユーザーへの返信
        embed = discord.Embed(title="✅ お疲れ様でした！", color=discord.Color.gold())
        embed.add_field(name="内容", value=self.task_name)
        embed.add_field(name="時間", value=duration_str)
        if self.memo.value:
            embed.add_field(name="📝 メモ", value=self.memo.value, inline=False)
        
        # 元のボタンを無効化して更新
        for child in self.view_item.children:
            child.disabled = True
        await self.view_item.message.edit(view=self.view_item)
        
        await interaction.response.send_message(embed=embed)

class FinishTaskView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="完了 (Done)", style=discord.ButtonStyle.green, custom_id="finish_task_btn_v3")
    async def finish(self, interaction: discord.Interaction, button: discord.ui.Button):
        # メッセージから開始時間を復元
        embed = interaction.message.embeds[0]
        footer_text = embed.footer.text
        try:
            # フッターから時間を取得
            time_str = footer_text.replace("開始時刻: ", "")
            start_time = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            task_name = embed.title.replace("🚀 スタート: ", "")
            
            # メモ入力用モーダルを表示
            self.message = interaction.message # View更新用に保持
            await interaction.response.send_modal(MemoModal(task_name, start_time, self))
            
        except Exception as e:
            await interaction.response.send_message(f"エラーが発生しました（古い形式のタスク可能性があります）: {e}", ephemeral=True)

# ---------------------------------------------------------
# 5. UIコンポーネント (タスク選択パネル)
# ---------------------------------------------------------
class TaskSelect(discord.ui.Select):
    def __init__(self, tasks):
        # 文字数が多すぎるとエラーになるため25文字制限などを考慮してもよい
        options = [discord.SelectOption(label=t[:100]) for t in tasks]
        super().__init__(
            placeholder="今から何をしますか？", 
            min_values=1, 
            max_values=1, 
            options=options, 
            custom_id="task_select_v3"
        )

    async def callback(self, interaction: discord.Interaction):
        selected_task = self.values[0]
        start_time = datetime.datetime.now()
        time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")

        embed = discord.Embed(title=f"🚀 スタート: {selected_task}", color=discord.Color.blue())
        embed.set_footer(text=f"開始時刻: {time_str}")
        
        await interaction.response.send_message(embed=embed, view=FinishTaskView())

class PermanentPanelView(discord.ui.View):
    def __init__(self, tasks):
        super().__init__(timeout=None)
        self.add_item(TaskSelect(tasks))

# ---------------------------------------------------------
# 6. コマンド群
# ---------------------------------------------------------
@client.event
async def on_ready():
    print(f'ログイン成功: {client.user}')
    await client.tree.sync()
    # 完了ボタンはステートレス（情報を持たない）なので汎用的に登録
    client.add_view(FinishTaskView())

@client.tree.command(name="setup", description="宣言パネルを設置（または更新）します")
async def setup(interaction: discord.Interaction):
    await interaction.response.defer()
    dm = DataManager(client)
    tasks = await dm.load_tasks(interaction.guild)
    await interaction.followup.send("行動宣言パネル", view=PermanentPanelView(tasks))

@client.tree.command(name="add_task", description="選択肢に新しいタスクを追加します")
@app_commands.describe(task_name="追加するタスク名（絵文字込みがおすすめ）")
async def add_task(interaction: discord.Interaction, task_name: str):
    await interaction.response.defer(ephemeral=True)
    dm = DataManager(client)
    tasks = await dm.load_tasks(interaction.guild)
    
    if task_name in tasks:
        await interaction.followup.send(f"⚠️ 「{task_name}」は既に存在します。", ephemeral=True)
        return
        
    tasks.append(task_name)
    await dm.save_tasks(interaction.guild, tasks)
    
    await interaction.followup.send(f"✅ 「{task_name}」を追加しました。\n反映するには `/setup` でパネルを出し直してください。", ephemeral=True)

@client.tree.command(name="delete_task", description="選択肢からタスクを削除します")
@app_commands.describe(task_name="削除するタスク名（完全一致）")
async def delete_task(interaction: discord.Interaction, task_name: str):
    await interaction.response.defer(ephemeral=True)
    dm = DataManager(client)
    tasks = await dm.load_tasks(interaction.guild)
    
    if task_name not in tasks:
        await interaction.followup.send(f"⚠️ 「{task_name}」が見つかりません。", ephemeral=True)
        return
        
    tasks.remove(task_name)
    await dm.save_tasks(interaction.guild, tasks)
    await interaction.followup.send(f"🗑️ 「{task_name}」を削除しました。\n反映するには `/setup` でパネルを出し直してください。", ephemeral=True)

@client.tree.command(name="report", description="行動統計を表示します")
@app_commands.describe(days="過去何日分を集計するか（デフォルト7日）")
async def report(interaction: discord.Interaction, days: int = 7):
    await interaction.response.defer()
    
    dm = DataManager(client)
    channel = await dm.get_channel(interaction.guild)
    
    # 集計用変数
    stats = defaultdict(int) # 回数
    time_stats = defaultdict(int) # 合計時間
    total_logs = 0
    
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
    
    # チャンネルの履歴を走査 (最新300件まで取得)
    async for msg in channel.history(limit=300):
        if not msg.embeds: continue
        embed = msg.embeds[0]
        # フッターにデータがあるか確認
        if not embed.footer.text or "LOG_ID:" not in embed.footer.text: continue
        
        try:
            # 隠しデータから復元
            json_str = embed.footer.text.replace("LOG_ID:", "")
            data = json.loads(json_str)
            
            # 日付フィルタ
            log_date = datetime.datetime.strptime(data['date'], "%Y-%m-%d")
            if log_date < cutoff_date: continue
            
            task = data['task']
            duration = data['duration_min']
            
            stats[task] += 1
            time_stats[task] += duration
            total_logs += 1
        except:
            continue

    if total_logs == 0:
        await interaction.followup.send(f"過去 {days} 日間のデータが見つかりませんでした。")
        return

    # レポート作成
    embed = discord.Embed(title=f"📊 行動レポート (過去{days}日間)", color=discord.Color.purple())
    
    # 回数ランキング
    sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
    text_count = ""
    for task, count in sorted_stats:
        text_count += f"**{task}**: {count}回\n"
    embed.add_field(name="🏆 実行回数", value=text_count or "なし", inline=True)

    # 時間ランキング
    sorted_time = sorted(time_stats.items(), key=lambda x: x[1], reverse=True)
    text_time = ""
    for task, minutes in sorted_time:
        text_time += f"**{task}**: {minutes}分\n"
    embed.add_field(name="⏱️ 合計時間", value=text_time or "なし", inline=True)

    embed.set_footer(text=f"Total: {total_logs} actions")
    await interaction.followup.send(embed=embed)

@client.tree.command(name="export_csv", description="全ログデータをCSVファイルとして出力します")
async def export_csv(interaction: discord.Interaction):
    await interaction.response.defer()
    
    dm = DataManager(client)
    channel = await dm.get_channel(interaction.guild)
    
    csv_lines = ["Date,Time,Task,Duration(min),Memo"]
    count = 0

    # 全履歴を取得（制限なしで取得するのは時間がかかるため、実用上は500-1000件程度で区切るのが無難）
    async for msg in channel.history(limit=1000):
        if not msg.embeds: continue
        embed = msg.embeds[0]
        if not embed.footer.text or "LOG_ID:" not in embed.footer.text: continue
        
        try:
            json_str = embed.footer.text.replace("LOG_ID:", "")
            data = json.loads(json_str)
            
            # CSV行作成 (カンマを含むメモなどはダブルクォートで囲む簡易処理)
            memo = data.get('memo', '').replace('"', '""')
            line = f"{data['date']},{data.get('timestamp', '')},{data['task']},{data['duration_min']},\"{memo}\""
            csv_lines.append(line)
            count += 1
        except:
            continue
            
    if count == 0:
        await interaction.followup.send("エクスポートするデータがありませんでした。")
        return

    # メモリ上でファイル作成
    csv_data = "\n".join(csv_lines)
    file = discord.File(fp=io.StringIO(csv_data), filename=f"mylifelog_{datetime.date.today()}.csv")
    
    await interaction.followup.send(f"📂 {count}件のデータをエクスポートしました。", file=file)

# ---------------------------------------------------------
# 起動
# ---------------------------------------------------------
if __name__ == "__main__":
    keep_alive() # Webサーバー起動
    if TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print("【エラー】TOKENを設定してください")
    else:
        client.run(TOKEN)
