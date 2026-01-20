import discord
from discord.ext import commands
import os
import datetime
from flask import Flask
from threading import Thread

# ---------------------------------------------------------
# 1. Botを起こし続けるためのWebサーバー機能 (Render対応版)
# ---------------------------------------------------------
app = Flask('')

@app.route('/')
def home():
    return "I am alive!"

def run():
    # Renderなどのクラウド環境ではポート番号が環境変数(PORT)で渡されます
    # 指定がない場合はデフォルトで8080を使います
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ---------------------------------------------------------
# 2. Botの本体設定
# ---------------------------------------------------------
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.message_content = True
client = commands.Bot(command_prefix='!', intents=intents)

# ---------------------------------------------------------
# 3. ボタンの処理（ボタンの中に開始時間を埋め込む）
# ---------------------------------------------------------
class FinishTaskView(discord.ui.View):
    def __init__(self, start_timestamp=None):
        super().__init__(timeout=None) # 永続化
    
    @discord.ui.button(label="完了 (Done)", style=discord.ButtonStyle.green, custom_id="finish_task_btn")
    async def finish(self, interaction: discord.Interaction, button: discord.ui.Button):
        message = interaction.message
        embed = message.embeds[0]
        
        try:
            footer_text = embed.footer.text
            time_str = footer_text.replace("開始時刻: ", "")
            start_time = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            
            end_time = datetime.datetime.now()
            duration = end_time - start_time
            minutes = int(duration.total_seconds() // 60)
            seconds = int(duration.total_seconds() % 60)

            result_embed = discord.Embed(title="✅ タスク完了", color=discord.Color.green())
            result_embed.add_field(name="内容", value=embed.title.replace("🚀 スタート: ", ""), inline=False)
            result_embed.add_field(name="時間", value=f"{minutes}分 {seconds}秒", inline=False)
            
            for child in self.children:
                child.disabled = True
            
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(embed=result_embed)

        except Exception as e:
            await interaction.response.send_message(f"エラーが発生しました: {e}", ephemeral=True)

# ---------------------------------------------------------
# 4. 常設メニューパネル
# ---------------------------------------------------------
DEFAULT_TASKS = [
    discord.SelectOption(label="🛁 お風呂", emoji="🛁"),
    discord.SelectOption(label="💻 作業・勉強", emoji="💻"),
    discord.SelectOption(label="🍽️ 食事", emoji="🍽️"),
    discord.SelectOption(label="🧹 家事・掃除", emoji="🧹"),
    discord.SelectOption(label="🚶 移動", emoji="🚶"),
    discord.SelectOption(label="💤 睡眠・仮眠", emoji="💤"),
    discord.SelectOption(label="🎮 趣味・休憩", emoji="🎮"),
]

class TaskSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="今から何をしますか？",
            min_values=1, max_values=1, options=DEFAULT_TASKS, custom_id="task_select"
        )

    async def callback(self, interaction: discord.Interaction):
        selected_task = self.values[0]
        start_time = datetime.datetime.now()
        time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")

        embed = discord.Embed(title=f"🚀 スタート: {selected_task}", color=discord.Color.blue())
        embed.set_footer(text=f"開始時刻: {time_str}")
        
        await interaction.response.send_message(embed=embed, view=FinishTaskView())

class PermanentPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TaskSelect())

# ---------------------------------------------------------
# 5. 起動処理
# ---------------------------------------------------------
@client.event
async def on_ready():
    print(f'ログイン成功: {client.user}')
    await client.tree.sync()
    client.add_view(PermanentPanelView())
    client.add_view(FinishTaskView())

@client.tree.command(name="setup", description="パネル設置")
async def setup(interaction: discord.Interaction):
    await interaction.response.send_message("行動宣言パネル", view=PermanentPanelView())

keep_alive()
client.run(TOKEN)
