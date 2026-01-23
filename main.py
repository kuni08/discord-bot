# ... (これより上のコードは変更なし) ...

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
    # 処理開始をDiscordに伝える（これで「考え中」のタイムアウト時間を15分まで延長）
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
        
        # 既存メッセージの削除（権限がないとここでコケることがあるためtryで囲む）
        try:
            await dash_ch.purge(limit=5)
        except discord.Forbidden:
            await interaction.followup.send("⚠️ メッセージ削除の権限がありませんでした（古いパネルが残るだけなので動作に影響はありません）。", ephemeral=True)
        except Exception:
            pass

        await dash_ch.send("行動宣言パネル", view=DashboardView(client, tasks))
        
        # 4. 目標パネル更新
        await dm.refresh_goals_panel(guild)

        await interaction.followup.send("✅ 完了しました！すべてのチャンネルがセットアップされました。", ephemeral=True)

    except discord.Forbidden as e:
        # 権限エラーの場合
        await interaction.followup.send(f"🚫 **権限エラーが発生しました**\nBotに「チャンネルの管理」や「管理者(Administrator)」の権限がありません。\nサーバー設定 > 連携サービス > Botのロール設定を確認してください。\nエラー詳細: {e}", ephemeral=True)
    except Exception as e:
        # その他のエラー
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
